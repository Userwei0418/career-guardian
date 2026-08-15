from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx

from market_data.contracts import (
    JobFact,
    JobSearchResponse,
    MarketSourceRef,
    QualityMeta,
    SalaryInsightResponse,
    SkillInsightResponse,
    SkillItem,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketProvider(Protocol):
    name: str
    data_mode: str

    def search_jobs(self, keyword: str | None, city: str | None, limit: int) -> JobSearchResponse: ...

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse: ...

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse: ...


class FixtureMarketProvider:
    name = "integrated-demo-fixture"
    data_mode = "fixture"

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self.payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def search_jobs(self, keyword: str | None, city: str | None, limit: int) -> JobSearchResponse:
        jobs = [JobFact.model_validate(item) for item in self.payload["jobs"]]
        if keyword:
            lowered = keyword.lower()
            jobs = [
                job
                for job in jobs
                if lowered in f"{job.title} {job.normalized_title or ''} {job.company_name}".lower()
            ]
        if city:
            jobs = [job for job in jobs if job.city == city]
        jobs = jobs[:limit]
        return JobSearchResponse(
            availability="available" if jobs else "insufficient_sample",
            data_mode="fixture",
            keyword=keyword,
            city=city,
            total=len(jobs),
            generated_at=utc_now(),
            jobs=jobs,
            note="脱敏演示岗位，用于 V2 连续链路集成，不是实时招聘数据。",
        )

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse:
        template = dict(self.payload["salary_insight"])
        template.update({"job_family": job_family, "city": city, "calculated_at": utc_now()})
        return SalaryInsightResponse.model_validate(template)

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse:
        template = dict(self.payload["skill_insight"])
        template.update(
            {
                "job_family": job_family,
                "calculated_at": utc_now(),
                "skills": template["skills"][:limit],
            }
        )
        return SkillInsightResponse.model_validate(template)


class PinMarketProvider:
    name = "pin-api-adapter"
    data_mode = "historical"

    def __init__(self, base_url: str, timeout_seconds: float = 5, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.Client(base_url=self.base_url, timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(self, path: str, params: dict | None = None):
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _skills(value) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str) and value:
            try:
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return [str(item) for item in decoded if item]
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return []

    def search_jobs(self, keyword: str | None, city: str | None, limit: int) -> JobSearchResponse:
        result = self._get(
            "/api/jobs",
            {
                key: value
                for key, value in {
                    "keyword": keyword,
                    "city": city,
                    "page": 1,
                    "page_size": limit,
                    "status": "open",
                }.items()
                if value is not None
            },
        )
        jobs: list[JobFact] = []
        for item in result.get("jobs", []):
            job_id = item["id"]
            try:
                detail = self._get(f"/api/jobs/{job_id}")
            except httpx.HTTPError:
                detail = item
            try:
                source_payload = self._get(f"/api/jobs/{job_id}/sources")
                raw_sources = source_payload.get("sources", [])
            except httpx.HTTPError:
                raw_sources = []
            observed = detail.get("last_seen_at") or detail.get("published_at") or utc_now()
            sources = [
                MarketSourceRef(
                    source_id=f"pin-source:{source.get('id', index)}",
                    source_name=source.get("source_site") or detail.get("source_site") or "Pin 招聘数据",
                    source_url=source.get("source_url") or detail.get("detail_url"),
                    observed_at=source.get("last_seen_at") or observed,
                )
                for index, source in enumerate(raw_sources)
            ]
            if not sources:
                sources = [
                    MarketSourceRef(
                        source_id=f"pin-job:{job_id}",
                        source_name=detail.get("source_site") or "Pin 招聘数据",
                        source_url=detail.get("detail_url"),
                        observed_at=observed,
                    )
                ]
            quality_score = int(detail.get("quality_score") or 0)
            grade = "A" if quality_score >= 85 else "B" if quality_score >= 70 else "C"
            salary_unit = str(detail.get("salary_unit") or "").lower()
            period = {
                "月": "month",
                "month": "month",
                "年": "year",
                "year": "year",
                "日": "day",
                "day": "day",
                "小时": "hour",
                "hour": "hour",
            }.get(salary_unit, "unknown")
            recruitment_type = (
                "internship"
                if detail.get("is_intern")
                else "campus"
                if detail.get("is_campus")
                else "social"
            )
            jobs.append(
                JobFact(
                    job_id=f"pin:{job_id}",
                    title=detail.get("title") or item.get("title") or "未命名岗位",
                    normalized_title=detail.get("normalized_title"),
                    company_name=detail.get("company_name") or item.get("company_name") or "未知企业",
                    city=detail.get("city") or item.get("city"),
                    recruitment_type=recruitment_type,
                    salary_min=detail.get("salary_min"),
                    salary_max=detail.get("salary_max"),
                    salary_period=period,
                    skills=self._skills(detail.get("skill_tags")),
                    published_at=detail.get("published_at"),
                    status=(detail.get("status") or "unknown")
                    if (detail.get("status") or "unknown") in {"open", "closed", "expired", "unknown"}
                    else "unknown",
                    data_mode="historical",
                    quality=QualityMeta(
                        grade=grade,
                        sample_size=1,
                        window_start=detail.get("first_seen_at"),
                        window_end=detail.get("last_seen_at"),
                        methodology_version="pin-job-adapter-v1",
                    ),
                    sources=sources,
                )
            )
        return JobSearchResponse(
            availability="available" if jobs else "insufficient_sample",
            data_mode="historical",
            keyword=keyword,
            city=city,
            total=int(result.get("total", len(jobs))),
            generated_at=utc_now(),
            jobs=jobs,
            note="Pin 历史/当前数据经 V2 只读适配层输出。",
        )

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse:
        rows = self._get(
            "/api/analysis/salary/city-comparison",
            {"category": job_family, "min_samples": 1},
        )
        match = next((row for row in rows if row.get("city") == city), None)
        source = MarketSourceRef(
            source_id="pin-salary-city-comparison",
            source_name="Pin 城市薪资分析",
            source_url=f"{self.base_url}/api/analysis/salary/city-comparison",
            observed_at=utc_now(),
        )
        if match is None:
            return SalaryInsightResponse(
                availability="insufficient_sample",
                data_mode="historical",
                job_family=job_family,
                city=city,
                sample_size=0,
                calculated_at=utc_now(),
                methodology_version="pin-salary-adapter-v1",
                quality_grade="insufficient",
                sources=[source],
                note="Pin 当前返回中没有该城市的有效样本。",
            )
        sample_size = int(match.get("sampleSize") or 0)
        grade = "A" if sample_size >= 100 else "B" if sample_size >= 30 else "C"
        return SalaryInsightResponse(
            availability="available",
            data_mode="historical",
            job_family=job_family,
            city=city,
            p25=match.get("salaryP25"),
            p50=match.get("salaryMedian"),
            p75=match.get("salaryP75"),
            sample_size=sample_size,
            calculated_at=utc_now(),
            methodology_version="pin-salary-adapter-v1",
            quality_grade=grade,
            sources=[source],
        )

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse:
        rows = self._get(
            "/api/analysis/skills/top-skills",
            {"category": job_family, "limit": max(10, limit)},
        )
        skills = [SkillItem(name=row["skill"], count=int(row.get("count") or 0)) for row in rows[:limit]]
        sample_size = sum(skill.count for skill in skills)
        return SkillInsightResponse(
            availability="available" if skills else "insufficient_sample",
            data_mode="historical",
            job_family=job_family,
            sample_size=sample_size,
            calculated_at=utc_now(),
            methodology_version="pin-skill-adapter-v1",
            quality_grade="B" if sample_size >= 30 else "C" if skills else "insufficient",
            skills=skills,
            sources=[
                MarketSourceRef(
                    source_id="pin-top-skills",
                    source_name="Pin 岗位技能统计",
                    source_url=f"{self.base_url}/api/analysis/skills/top-skills",
                    observed_at=utc_now(),
                )
            ],
        )
