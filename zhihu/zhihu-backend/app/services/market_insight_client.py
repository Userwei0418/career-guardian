from __future__ import annotations

from datetime import datetime, timezone
from typing import TypeVar
from urllib.parse import quote, unquote

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas.market import (
    JobDetailResponse,
    JobSearchResponse,
    MarketOverviewResponse,
    SalaryInsightResponse,
    SkillInsightResponse,
)


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
        page: int,
        page_size: int,
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: str | None = None,
        sort_by: str = "default",
        match_major: str | None = None,
        match_skills: list[str] | None = None,
        match_experience_months: int | None = None,
        match_education_level: int | None = None,
    ) -> JobSearchResponse:
        try:
            return self._get(
                "/api/jobs",
                {
                    key: value
                    for key, value in {
                        "keyword": keyword,
                        "company": company,
                        "job_title": job_title,
                        "major": major,
                        "recruitment_type": recruitment_type,
                        "city": city,
                        "sort_by": sort_by,
                        "match_major": match_major,
                        "match_skills": ",".join(match_skills or []),
                        "match_experience_months": match_experience_months,
                        "match_education_level": match_education_level,
                        "page": page,
                        "page_size": page_size,
                    }.items()
                    if value is not None
                },
                JobSearchResponse,
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            return JobSearchResponse(
                availability="unavailable",
                data_mode="unknown",
                keyword=keyword,
                company=company,
                job_title=job_title,
                major=major,
                recruitment_type=recruitment_type,
                city=city,
                total=0,
                candidate_total=0,
                sort_by="relevance" if sort_by == "relevance" else "default",
                page=page,
                page_size=page_size,
                generated_at=utc_now(),
                jobs=[],
                note=f"市场洞察服务暂时不可用：{type(exc).__name__}",
            )

    def get_job(self, job_id: str) -> JobDetailResponse:
        normalized_job_id = unquote(job_id)
        return self._get(
            f"/api/jobs/{quote(normalized_job_id, safe='')}",
            {},
            JobDetailResponse,
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

    def overview(self, job_family: str | None = None) -> MarketOverviewResponse:
        try:
            return self._get(
                "/api/insights/overview",
                {"job_family": job_family} if job_family else {},
                MarketOverviewResponse,
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            return MarketOverviewResponse(
                availability="unavailable",
                data_mode="unknown",
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
                generated_at=utc_now(),
                note=f"市场全景服务暂时不可用：{type(exc).__name__}",
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
