from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas.market import JobSearchResponse, SalaryInsightResponse, SkillInsightResponse


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketInsightClient:
    """Read-only gateway from the Guardian business API to market facts."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 3,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _get(self, path: str, params: dict, response_model: type[ResponseModel]) -> ResponseModel:
        if self.client is not None:
            response = self.client.get(path, params=params)
        else:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = client.get(path, params=params)
        response.raise_for_status()
        return response_model.model_validate(response.json())

    def search_jobs(
        self,
        keyword: str | None,
        city: str | None,
        limit: int,
    ) -> JobSearchResponse:
        try:
            return self._get(
                "/api/jobs",
                {key: value for key, value in {"keyword": keyword, "city": city, "limit": limit}.items() if value is not None},
                JobSearchResponse,
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            return JobSearchResponse(
                availability="unavailable",
                data_mode="unknown",
                keyword=keyword,
                city=city,
                total=0,
                generated_at=utc_now(),
                jobs=[],
                note=f"市场洞察服务暂时不可用：{type(exc).__name__}",
            )

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse:
        try:
            return self._get(
                "/api/insights/salary",
                {"job_family": job_family, "city": city},
                SalaryInsightResponse,
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            return SalaryInsightResponse(
                availability="unavailable",
                data_mode="unknown",
                job_family=job_family,
                city=city,
                sample_size=0,
                calculated_at=utc_now(),
                methodology_version="unavailable-v1",
                quality_grade="insufficient",
                sources=[],
                note=f"市场洞察服务暂时不可用：{type(exc).__name__}",
            )

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse:
        try:
            return self._get(
                "/api/insights/skills",
                {"job_family": job_family, "limit": limit},
                SkillInsightResponse,
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            return SkillInsightResponse(
                availability="unavailable",
                data_mode="unknown",
                job_family=job_family,
                sample_size=0,
                calculated_at=utc_now(),
                methodology_version="unavailable-v1",
                quality_grade="insufficient",
                skills=[],
                sources=[],
                note=f"市场洞察服务暂时不可用：{type(exc).__name__}",
            )
