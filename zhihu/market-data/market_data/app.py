from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from market_data.contracts import (
    JobDetailResponse,
    JobSearchResponse,
    SalaryInsightResponse,
    SkillInsightResponse,
)
from market_data.errors import SourcePolicyError
from market_data.management import (
    CrawlTaskAdminListResponse,
    CrawlTaskAdminView,
    GateDraftUpdate,
    GatePublishRequest,
    GateSettingsAdminView,
    MarketAdminRuntime,
    SourceAdminListResponse,
    build_management_runtime,
)
from market_data.providers import CoreMarketProvider, FixtureMarketProvider, PinMarketProvider


ROOT = Path(__file__).resolve().parents[1]


def build_provider():
    provider_name = os.getenv("MARKET_PROVIDER", "fixture").strip().lower()
    if provider_name == "core":
        database_url = os.getenv("MARKET_CORE_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("MARKET_PROVIDER=core 时必须配置 MARKET_CORE_DATABASE_URL")
        return CoreMarketProvider(database_url)
    if provider_name == "pin":
        return PinMarketProvider(
            os.getenv("PIN_API_BASE", "http://127.0.0.1:8001"),
            float(os.getenv("PIN_API_TIMEOUT_SECONDS", "5")),
        )
    return FixtureMarketProvider(
        os.getenv("MARKET_FIXTURE_PATH", str(ROOT / "fixtures/integrated_graduate_case.json"))
    )


_AUTO_MANAGEMENT = object()


def create_app(
    provider=None,
    management_runtime: MarketAdminRuntime | None | object = _AUTO_MANAGEMENT,
    admin_token: str | None = None,
) -> FastAPI:
    selected_provider = provider or build_provider()
    management_engines = []
    if management_runtime is _AUTO_MANAGEMENT:
        selected_management, management_engines = build_management_runtime()
    else:
        selected_management = management_runtime
    selected_admin_token = admin_token if admin_token is not None else os.getenv("MARKET_INTERNAL_TOKEN")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        close = getattr(selected_provider, "close", None)
        if close:
            close()
        for engine in management_engines:
            engine.dispose()

    app = FastAPI(title="职护市场洞察 API", version="0.1.0", lifespan=lifespan)
    app.state.provider = selected_provider
    app.state.management = selected_management
    app.state.admin_token = selected_admin_token

    def require_internal_admin(
        request: Request,
        x_market_admin_token: str | None = Header(default=None),
    ) -> MarketAdminRuntime:
        configured_token = request.app.state.admin_token
        if not configured_token:
            raise HTTPException(status_code=503, detail="市场采集管理令牌尚未配置")
        if not x_market_admin_token or not secrets.compare_digest(x_market_admin_token, configured_token):
            raise HTTPException(status_code=403, detail="无权访问市场采集管理接口")
        runtime = request.app.state.management
        if runtime is None:
            raise HTTPException(status_code=503, detail="市场 Raw 数据库尚未配置")
        return runtime

    @app.get("/api/health")
    def health(request: Request):
        current = request.app.state.provider
        return {
            "status": "ok",
            "service": "market-insight-api",
            "version": "0.1.0",
            "provider": current.name,
            "data_mode": current.data_mode,
            "gate_policy_version": getattr(current, "policy_version", None),
        }

    @app.get("/api/jobs", response_model=JobSearchResponse)
    def jobs(
        request: Request,
        keyword: str | None = None,
        city: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
        limit: int | None = Query(None, ge=1, le=50),
    ):
        selected_page_size = limit or page_size
        offset = (page - 1) * selected_page_size
        try:
            return request.app.state.provider.search_jobs(
                keyword, city, selected_page_size, offset
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return JobSearchResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                keyword=keyword,
                city=city,
                total=0,
                page=page,
                page_size=selected_page_size,
                generated_at=datetime.now(timezone.utc),
                jobs=[],
                note=f"市场数据源暂时不可用：{type(exc).__name__}",
            )

    @app.get("/api/jobs/{job_id}", response_model=JobDetailResponse)
    def job_detail(request: Request, job_id: str):
        try:
            detail = request.app.state.provider.get_job(job_id)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="岗位详情数据源暂时不可用") from exc
        if detail is None:
            raise HTTPException(status_code=404, detail="岗位不存在或尚未通过质量门")
        return detail

    @app.get("/api/insights/salary", response_model=SalaryInsightResponse)
    def salary(request: Request, job_family: str, city: str):
        try:
            return request.app.state.provider.salary_insight(job_family, city)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return SalaryInsightResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                job_family=job_family,
                city=city,
                sample_size=0,
                calculated_at=datetime.now(timezone.utc),
                methodology_version="unavailable-v1",
                quality_grade="insufficient",
                sources=[],
                note=f"市场薪资数据源暂时不可用：{type(exc).__name__}",
            )

    @app.get("/api/insights/skills", response_model=SkillInsightResponse)
    def skills(request: Request, job_family: str, limit: int = Query(8, ge=1, le=20)):
        try:
            return request.app.state.provider.skill_insight(job_family, limit)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return SkillInsightResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                job_family=job_family,
                sample_size=0,
                calculated_at=datetime.now(timezone.utc),
                methodology_version="unavailable-v1",
                quality_grade="insufficient",
                skills=[],
                sources=[],
                note=f"市场技能数据源暂时不可用：{type(exc).__name__}",
            )

    @app.get("/internal/admin/sources", response_model=SourceAdminListResponse)
    def admin_sources(runtime: MarketAdminRuntime = Depends(require_internal_admin)):
        return runtime.list_sources()

    @app.get("/internal/admin/tasks", response_model=CrawlTaskAdminListResponse)
    def admin_tasks(
        limit: int = Query(50, ge=1, le=200),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        return runtime.list_tasks(limit)

    @app.post("/internal/admin/sources/{source_code}/runs", response_model=CrawlTaskAdminView)
    def admin_run_source(
        source_code: str,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.run_source(source_code)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SourcePolicyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/internal/admin/gate", response_model=GateSettingsAdminView)
    def admin_gate_settings(runtime: MarketAdminRuntime = Depends(require_internal_admin)):
        try:
            return runtime.get_gate_settings()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.put("/internal/admin/gate/draft", response_model=GateSettingsAdminView)
    def admin_save_gate_draft(
        request: GateDraftUpdate,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.save_gate_draft(request)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/internal/admin/gate/draft/preview", response_model=GateSettingsAdminView)
    def admin_preview_gate_draft(
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.preview_gate_draft()
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/internal/admin/gate/draft/publish", response_model=GateSettingsAdminView)
    def admin_publish_gate_draft(
        request: GatePublishRequest,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.publish_gate_draft(request)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()
