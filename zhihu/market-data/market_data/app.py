from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request

from market_data.contracts import JobSearchResponse, SalaryInsightResponse, SkillInsightResponse
from market_data.providers import FixtureMarketProvider, PinMarketProvider


ROOT = Path(__file__).resolve().parents[1]


def build_provider():
    provider_name = os.getenv("MARKET_PROVIDER", "fixture").strip().lower()
    if provider_name == "pin":
        return PinMarketProvider(
            os.getenv("PIN_API_BASE", "http://127.0.0.1:8001"),
            float(os.getenv("PIN_API_TIMEOUT_SECONDS", "5")),
        )
    return FixtureMarketProvider(
        os.getenv("MARKET_FIXTURE_PATH", str(ROOT / "fixtures/integrated_graduate_case.json"))
    )


def create_app(provider=None) -> FastAPI:
    selected_provider = provider or build_provider()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        close = getattr(selected_provider, "close", None)
        if close:
            close()

    app = FastAPI(title="职护市场洞察 API", version="0.1.0", lifespan=lifespan)
    app.state.provider = selected_provider

    @app.get("/api/health")
    def health(request: Request):
        current = request.app.state.provider
        return {
            "status": "ok",
            "service": "market-insight-api",
            "version": "0.1.0",
            "provider": current.name,
            "data_mode": current.data_mode,
        }

    @app.get("/api/jobs", response_model=JobSearchResponse)
    def jobs(
        request: Request,
        keyword: str | None = None,
        city: str | None = None,
        limit: int = Query(10, ge=1, le=20),
    ):
        try:
            return request.app.state.provider.search_jobs(keyword, city, limit)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return JobSearchResponse(
                availability="unavailable",
                data_mode=request.app.state.provider.data_mode,
                keyword=keyword,
                city=city,
                total=0,
                generated_at=datetime.now(timezone.utc),
                jobs=[],
                note=f"市场数据源暂时不可用：{type(exc).__name__}",
            )

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

    return app


app = create_app()
