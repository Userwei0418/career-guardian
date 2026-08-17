from __future__ import annotations

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from market_data.contracts import (
    JobDetailResponse,
    JobSearchResponse,
    MarketOverviewResponse,
    SalaryInsightResponse,
    SkillInsightResponse,
)
from market_data.errors import SourcePolicyError
from market_data.management import (
    CrawlTaskAdminListResponse,
    CrawlTaskDetailAdminView,
    CrawlTaskAdminView,
    CollectionCompanyListResponse,
    CollectionCompanyView,
    CollectionRunOptions,
    CompanyGovernanceUpdate,
    CrawlBatchAdminView,
    DataSourceAdminView,
    GateDraftUpdate,
    GatePublishRequest,
    GateSettingsAdminView,
    MarketAdminRuntime,
    SourceAdminListResponse,
    SourceGovernanceUpdate,
    SourceTechnicalUpdate,
    StrategyRepairCandidateCreate,
    StrategyRepairCandidateView,
    StrategyRepairBackfillResult,
    StrategyRepairClaim,
    StrategyRepairComplete,
    StrategyRepairEvidenceView,
    StrategyRepairFailure,
    StrategyRepairReview,
    build_management_runtime,
)
from market_data.providers import CoreMarketProvider, FixtureMarketProvider


ROOT = Path(__file__).resolve().parents[1]


def build_provider():
    provider_name = os.getenv("MARKET_PROVIDER", "fixture").strip().lower()
    if provider_name == "core":
        database_url = os.getenv("MARKET_CORE_DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("MARKET_PROVIDER=core 时必须配置 MARKET_CORE_DATABASE_URL")
        return CoreMarketProvider(database_url)
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
    task_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-crawl") if selected_management else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        close = getattr(selected_provider, "close", None)
        if close:
            close()
        if task_executor:
            task_executor.shutdown(wait=True, cancel_futures=False)
        for engine in management_engines:
            engine.dispose()

    app = FastAPI(title="职护市场洞察 API", version="0.1.0", lifespan=lifespan)
    app.state.provider = selected_provider
    app.state.management = selected_management
    app.state.admin_token = selected_admin_token
    app.state.task_executor = task_executor

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
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: Literal["campus", "internship", "social"] | None = None,
        sort_by: Literal[
            "default",
            "relevance",
            "observed_desc",
            "observed_asc",
            "published_desc",
            "published_asc",
        ] = "default",
        match_major: str | None = None,
        match_skills: str | None = None,
        match_experience_months: int | None = Query(None, ge=0, le=1200),
        match_education_level: int | None = Query(None, ge=0, le=4),
        city: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
        limit: int | None = Query(None, ge=1, le=50),
    ):
        selected_page_size = limit or page_size
        offset = (page - 1) * selected_page_size
        try:
            return request.app.state.provider.search_jobs(
                keyword,
                city,
                selected_page_size,
                offset,
                company=company,
                job_title=job_title,
                major=major,
                recruitment_type=recruitment_type,
                sort_by=sort_by,
                match_major=match_major,
                match_skills=[item.strip() for item in match_skills.split(",") if item.strip()][:20] if match_skills else [],
                match_experience_months=match_experience_months,
                match_education_level=match_education_level,
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return JobSearchResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                keyword=keyword,
                company=company,
                job_title=job_title,
                major=major,
                recruitment_type=recruitment_type,
                city=city,
                total=0,
                candidate_total=0,
                sort_by=sort_by,
                page=page,
                page_size=selected_page_size,
                generated_at=datetime.now(timezone.utc),
                jobs=[],
                note=f"市场数据源暂时不可用：{type(exc).__name__}",
            )

    @app.get("/api/jobs/{job_id}", response_model=JobDetailResponse)
    def job_detail(request: Request, job_id: str):
        try:
            detail = request.app.state.provider.get_job(unquote(job_id))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="岗位详情数据源暂时不可用") from exc
        if detail is None:
            raise HTTPException(status_code=404, detail="岗位不存在或暂不提供展示")
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

    @app.get("/api/insights/overview", response_model=MarketOverviewResponse)
    def overview(request: Request, job_family: str | None = None):
        try:
            return request.app.state.provider.overview(job_family)
        except (AttributeError, httpx.HTTPError, ValueError, KeyError) as exc:
            return MarketOverviewResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                scope="job_family" if job_family else "market",
                scope_label=job_family or "整体就业市场",
                job_count=0,
                company_count=0,
                city_count=0,
                salary_sample_count=0,
                skill_sample_count=0,
                recruitment_types=[],
                cities=[],
                job_families=[],
                skills=[],
                generated_at=datetime.now(timezone.utc),
                note=f"市场全景数据暂时不可用：{type(exc).__name__}",
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

    @app.get(
        "/internal/admin/collection/companies",
        response_model=CollectionCompanyListResponse,
    )
    def admin_collection_companies(
        query: str | None = None,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        return runtime.list_collection_companies(query)

    @app.put(
        "/internal/admin/collection/companies/{company_code}/governance",
        response_model=CollectionCompanyView,
    )
    def admin_update_company_governance(
        company_code: str,
        update: CompanyGovernanceUpdate,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.update_company_governance(company_code, update)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/collection/companies/{company_code}/runs",
        response_model=CrawlBatchAdminView,
    )
    def admin_run_company(
        request: Request,
        company_code: str,
        options: CollectionRunOptions | None = None,
        actor: str = Query(..., min_length=1, max_length=100),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            batch = runtime.queue_company(
                company_code,
                actor,
                browser_mode=options.browser_mode if options else "default",
            )
            for task in batch.tasks:
                request.app.state.task_executor.submit(runtime.execute_task, task.id)
            return batch
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (SourcePolicyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.put("/internal/admin/sources/{source_code}", response_model=DataSourceAdminView)
    def admin_update_source(
        source_code: str,
        update: SourceGovernanceUpdate,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.update_source_governance(source_code, update)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/internal/admin/tasks", response_model=CrawlTaskAdminListResponse)
    def admin_tasks(
        limit: int = Query(50, ge=1, le=200),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        return runtime.list_tasks(limit)

    @app.get("/internal/admin/tasks/{task_id}", response_model=CrawlTaskDetailAdminView)
    def admin_task_detail(
        task_id: int,
        limit: int = Query(100, ge=1, le=500),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.get_task_detail(task_id, limit)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put(
        "/internal/admin/sources/{source_code}/configuration",
        response_model=DataSourceAdminView,
    )
    def admin_update_source_configuration(
        source_code: str,
        update: SourceTechnicalUpdate,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.update_source_configuration(source_code, update)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/internal/admin/sources/{source_code}/runs", response_model=CrawlTaskAdminView)
    def admin_run_source(
        request: Request,
        source_code: str,
        options: CollectionRunOptions | None = None,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            task = runtime.queue_source(
                source_code,
                browser_mode=options.browser_mode if options else "default",
            )
            request.app.state.task_executor.submit(runtime.execute_task, task.id)
            return task
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SourcePolicyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/internal/admin/strategy-repairs",
        response_model=list[StrategyRepairCandidateView],
    )
    def admin_strategy_repairs(
        source_code: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        return runtime.list_strategy_repair_candidates(source_code, limit)

    @app.post(
        "/internal/admin/strategy-repairs/backfill",
        response_model=StrategyRepairBackfillResult,
    )
    def admin_backfill_strategy_repairs(
        limit: int = Query(200, ge=1, le=1000),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        return runtime.backfill_strategy_repair_candidates(limit)

    @app.get(
        "/internal/admin/sources/{source_code}/strategy-repair-evidence",
        response_model=StrategyRepairEvidenceView,
    )
    def admin_strategy_repair_evidence(
        source_code: str,
        failure_task_id: int | None = Query(default=None, ge=1),
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.get_strategy_repair_evidence(source_code, failure_task_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (SourcePolicyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/sources/{source_code}/strategy-repairs",
        response_model=StrategyRepairCandidateView,
    )
    def admin_create_strategy_repair(
        source_code: str,
        payload: StrategyRepairCandidateCreate,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.create_strategy_repair_candidate(source_code, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/claim",
        response_model=StrategyRepairCandidateView,
    )
    def admin_claim_strategy_repair(
        candidate_id: int,
        payload: StrategyRepairClaim,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.claim_strategy_repair_candidate(candidate_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/complete",
        response_model=StrategyRepairCandidateView,
    )
    def admin_complete_strategy_repair(
        candidate_id: int,
        payload: StrategyRepairComplete,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.complete_strategy_repair_candidate(candidate_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/fail",
        response_model=StrategyRepairCandidateView,
    )
    def admin_fail_strategy_repair(
        candidate_id: int,
        payload: StrategyRepairFailure,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.fail_strategy_repair_candidate(candidate_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/replay",
        response_model=StrategyRepairCandidateView,
    )
    def admin_replay_strategy_repair(
        candidate_id: int,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.replay_strategy_repair_candidate(candidate_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (SourcePolicyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/approve",
        response_model=StrategyRepairCandidateView,
    )
    def admin_approve_strategy_repair(
        candidate_id: int,
        payload: StrategyRepairReview,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.approve_strategy_repair_candidate(candidate_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/internal/admin/strategy-repairs/{candidate_id}/rollback",
        response_model=StrategyRepairCandidateView,
    )
    def admin_rollback_strategy_repair(
        candidate_id: int,
        payload: StrategyRepairReview,
        runtime: MarketAdminRuntime = Depends(require_internal_admin),
    ):
        try:
            return runtime.rollback_strategy_repair_candidate(candidate_id, payload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
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
