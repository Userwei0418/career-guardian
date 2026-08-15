from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from market_data.contracts import (
    CompanyFact,
    JobDetailResponse,
    JobFact,
    JobSearchResponse,
    MarketSourceRef,
    QualityMeta,
    SalaryInsightResponse,
    SkillInsightResponse,
    SkillItem,
)
from market_data.db import make_engine
from market_data.models.core import (
    City,
    Company,
    Job,
    JobFamily,
    JobSkill,
    JobSource,
    QualityGatePolicy,
    RecruitmentType,
    Skill,
)
from market_data.quality_gate import GatePolicy


DEFAULT_GATE_POLICY_VERSION = GatePolicy.load().policy_version


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketProvider(Protocol):
    name: str
    data_mode: str

    def search_jobs(
        self,
        keyword: str | None,
        city: str | None,
        limit: int,
        offset: int = 0,
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: str | None = None,
    ) -> JobSearchResponse: ...

    def get_job(self, job_id: str) -> JobDetailResponse | None: ...

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse: ...

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse: ...


class FixtureMarketProvider:
    name = "integrated-demo-fixture"
    data_mode = "fixture"

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self.payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def search_jobs(
        self,
        keyword: str | None,
        city: str | None,
        limit: int,
        offset: int = 0,
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: str | None = None,
    ) -> JobSearchResponse:
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
        if company:
            lowered = company.strip().lower()
            jobs = [job for job in jobs if lowered in job.company_name.lower()]
        if job_title:
            lowered = job_title.strip().lower()
            jobs = [
                job
                for job in jobs
                if lowered in f"{job.title} {job.normalized_title or ''}".lower()
            ]
        if major:
            lowered = major.strip().lower()
            jobs = [job for job in jobs if lowered in " ".join(job.skills).lower()]
        if recruitment_type:
            jobs = [job for job in jobs if job.recruitment_type == recruitment_type]
        total = len(jobs)
        jobs = jobs[offset : offset + limit]
        page = offset // limit + 1
        return JobSearchResponse(
            availability="available" if total else "insufficient_sample",
            data_mode="fixture",
            keyword=keyword,
            company=company,
            job_title=job_title,
            major=major,
            recruitment_type=recruitment_type,
            city=city,
            total=total,
            page=page,
            page_size=limit,
            total_pages=math.ceil(total / limit) if total else 0,
            has_previous=page > 1,
            has_next=offset + limit < total,
            generated_at=utc_now(),
            jobs=jobs,
            note="脱敏演示岗位，用于 V2 连续链路集成，不是实时招聘数据。",
        )

    def get_job(self, job_id: str) -> JobDetailResponse | None:
        job = next(
            (
                JobFact.model_validate(item)
                for item in self.payload["jobs"]
                if item.get("job_id") == job_id
            ),
            None,
        )
        if job is None:
            return None
        observed_at = job.sources[0].observed_at
        first_seen_at = job.quality.window_start or observed_at
        last_seen_at = job.quality.window_end or observed_at
        return JobDetailResponse(
            availability="available",
            data_mode="fixture",
            job=job,
            company=CompanyFact(
                company_id=f"fixture-company:{job.company_name}",
                name=job.company_name,
            ),
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            quality_score={"A": 90, "B": 80, "C": 60}.get(job.quality.grade, 0),
            quality_reasons=["fixture_traceable_source"],
            gate_policy_version=job.quality.methodology_version,
            gate_evaluated_at=last_seen_at,
            note="脱敏演示岗位只用于验证产品链路，不代表当前仍在招聘。",
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


def percentile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


class CoreMarketProvider:
    """面向用户查询清洗后的 Core 数据，绝不回退到 Raw 或 Staging。"""

    name = "market-core"
    data_mode = "historical"
    methodology_version = "market-core-v2"
    def __init__(self, database_url: str):
        self.engine = make_engine(database_url)

    @property
    def policy_version(self) -> str:
        with Session(self.engine) as session:
            return session.scalar(
                select(QualityGatePolicy.policy_version)
                .where(QualityGatePolicy.status == "active")
                .order_by(QualityGatePolicy.id.desc())
                .limit(1)
            ) or DEFAULT_GATE_POLICY_VERSION

    def close(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _quality_grade(sample_size: int) -> str:
        if sample_size >= 100:
            return "A"
        if sample_size >= 30:
            return "B"
        if sample_size > 0:
            return "C"
        return "insufficient"

    @staticmethod
    def _source_ref(source: JobSource, observed_at: datetime) -> MarketSourceRef:
        return MarketSourceRef(
            source_id=f"core-source:{source.id}",
            source_name="职护市场数据",
            source_url=source.source_url,
            observed_at=source.last_seen_at or observed_at,
        )

    @staticmethod
    def _job_conditions(
        keyword: str | None,
        city: str | None,
        company: str | None,
        job_title: str | None,
        major: str | None,
        recruitment_type: str | None,
    ):
        conditions = [
            Job.gate_policy_version != "uncertified",
        ]
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    Job.title.ilike(pattern),
                    Job.normalized_title.ilike(pattern),
                    Company.name.ilike(pattern),
                )
            )
        if city:
            conditions.append(City.name == city.strip())
        if company:
            pattern = f"%{company.strip()}%"
            conditions.append(
                or_(
                    Company.name.ilike(pattern),
                    Company.normalized_name.ilike(pattern),
                    Company.alias_name.ilike(pattern),
                    Company.short_name.ilike(pattern),
                )
            )
        if job_title:
            pattern = f"%{job_title.strip()}%"
            conditions.append(
                or_(
                    Job.title.ilike(pattern),
                    Job.normalized_title.ilike(pattern),
                    JobFamily.name.ilike(pattern),
                    JobFamily.code.ilike(pattern),
                )
            )
        if major:
            pattern = f"%{major.strip()}%"
            conditions.append(or_(Job.requirements.ilike(pattern), Job.description.ilike(pattern)))
        if recruitment_type:
            conditions.append(RecruitmentType.code == recruitment_type)
        return conditions

    def search_jobs(
        self,
        keyword: str | None,
        city: str | None,
        limit: int,
        offset: int = 0,
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: str | None = None,
    ) -> JobSearchResponse:
        with Session(self.engine) as session:
            conditions = self._job_conditions(
                keyword, city, company, job_title, major, recruitment_type
            )
            joins = (
                select(Job, Company, City, RecruitmentType)
                .join(Company, Company.id == Job.company_id)
                .outerjoin(City, City.id == Job.city_id)
                .outerjoin(JobFamily, JobFamily.id == Job.job_family_id)
                .outerjoin(RecruitmentType, RecruitmentType.id == Job.recruitment_type_id)
            )
            total = session.scalar(
                select(func.count(Job.id))
                .select_from(Job)
                .join(Company, Company.id == Job.company_id)
                .outerjoin(City, City.id == Job.city_id)
                .outerjoin(JobFamily, JobFamily.id == Job.job_family_id)
                .outerjoin(RecruitmentType, RecruitmentType.id == Job.recruitment_type_id)
                .where(*conditions)
            ) or 0
            rows = session.execute(
                joins.where(*conditions)
                .order_by(Job.quality_score.desc(), Job.last_seen_at.desc(), Job.id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            job_ids = [job.id for job, *_ in rows]
            source_map: dict[int, list[JobSource]] = defaultdict(list)
            skill_map: dict[int, list[str]] = defaultdict(list)
            if job_ids:
                for source in session.scalars(
                    select(JobSource)
                    .where(JobSource.job_id.in_(job_ids))
                    .order_by(JobSource.job_id, JobSource.last_seen_at.desc())
                ):
                    source_map[source.job_id].append(source)
                for job_id, skill_name in session.execute(
                    select(JobSkill.job_id, Skill.name)
                    .join(Skill, Skill.id == JobSkill.skill_id)
                    .where(JobSkill.job_id.in_(job_ids))
                    .order_by(JobSkill.job_id, Skill.name)
                ):
                    skill_map[job_id].append(skill_name)

            jobs: list[JobFact] = []
            for job, job_company, job_city, recruitment in rows:
                sources = source_map.get(job.id, [])
                if not sources:
                    # Core 的完整性约束要求每个可展示岗位都能追溯来源。
                    continue
                recruitment_code = recruitment.code if recruitment else "unknown"
                if recruitment_code not in {"campus", "internship", "social"}:
                    recruitment_code = "unknown"
                jobs.append(
                    JobFact(
                        job_id=f"core:{job.id}",
                        title=job.title,
                        normalized_title=job.normalized_title,
                        company_name=job_company.name,
                        city=job_city.name if job_city else None,
                        recruitment_type=recruitment_code,
                        salary_min=job.salary_min,
                        salary_max=job.salary_max,
                        salary_period=job.salary_period
                        if job.salary_period in {"month", "year", "day", "hour"}
                        else "unknown",
                        skills=skill_map.get(job.id, []),
                        published_at=job.published_at,
                        status=job.status
                        if job.status in {"open", "closed", "expired", "unknown"}
                        else "unknown",
                        data_mode="historical",
                        quality=QualityMeta(
                            grade=job.quality_grade
                            if job.quality_grade in {"A", "B", "C"}
                            else "C",
                            sample_size=1,
                            window_start=job.first_seen_at,
                            window_end=job.last_seen_at,
                            methodology_version=self.methodology_version,
                        ),
                        sources=[self._source_ref(item, job.last_seen_at) for item in sources[:3]],
                    )
                )

        page = offset // limit + 1
        return JobSearchResponse(
            availability="available" if total else "insufficient_sample",
            data_mode="historical",
            keyword=keyword,
            company=company,
            job_title=job_title,
            major=major,
            recruitment_type=recruitment_type,
            city=city,
            total=int(total),
            page=page,
            page_size=limit,
            total_pages=math.ceil(total / limit) if total else 0,
            has_previous=page > 1,
            has_next=offset + limit < total,
            generated_at=utc_now(),
            jobs=jobs,
            note="仅展示通过职护清洗与质量门的历史岗位；历史开放状态不会被当作当前在招事实。",
        )

    def get_job(self, job_id: str) -> JobDetailResponse | None:
        try:
            prefix, raw_id = job_id.split(":", 1)
            numeric_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        if prefix != "core" or numeric_id < 1:
            return None

        with Session(self.engine) as session:
            row = session.execute(
                select(Job, Company, City, RecruitmentType)
                .join(Company, Company.id == Job.company_id)
                .outerjoin(City, City.id == Job.city_id)
                .outerjoin(RecruitmentType, RecruitmentType.id == Job.recruitment_type_id)
                .where(Job.id == numeric_id, Job.gate_policy_version != "uncertified")
            ).one_or_none()
            if row is None:
                return None
            job, company, job_city, recruitment = row
            sources = list(
                session.scalars(
                    select(JobSource)
                    .where(JobSource.job_id == job.id)
                    .order_by(JobSource.last_seen_at.desc(), JobSource.id.desc())
                )
            )
            if not sources:
                return None
            skill_names = list(
                session.scalars(
                    select(Skill.name)
                    .join(JobSkill, JobSkill.skill_id == Skill.id)
                    .where(JobSkill.job_id == job.id)
                    .order_by(Skill.name)
                )
            )
            recruitment_code = recruitment.code if recruitment else "unknown"
            if recruitment_code not in {"campus", "internship", "social"}:
                recruitment_code = "unknown"
            fact = JobFact(
                job_id=f"core:{job.id}",
                title=job.title,
                normalized_title=job.normalized_title,
                company_name=company.name,
                city=job_city.name if job_city else None,
                recruitment_type=recruitment_code,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                salary_period=job.salary_period
                if job.salary_period in {"month", "year", "day", "hour"}
                else "unknown",
                skills=skill_names,
                published_at=job.published_at,
                status=job.status
                if job.status in {"open", "closed", "expired", "unknown"}
                else "unknown",
                data_mode="historical",
                quality=QualityMeta(
                    grade=job.quality_grade if job.quality_grade in {"A", "B", "C"} else "C",
                    sample_size=1,
                    window_start=job.first_seen_at,
                    window_end=job.last_seen_at,
                    methodology_version=self.methodology_version,
                ),
                sources=[self._source_ref(item, job.last_seen_at) for item in sources],
            )
            return JobDetailResponse(
                availability="available",
                data_mode="historical",
                job=fact,
                company=CompanyFact(
                    company_id=f"core-company:{company.id}",
                    name=company.name,
                    alias_name=company.alias_name,
                    short_name=company.short_name,
                    website_url=company.website_url,
                    career_page_url=company.career_page_url,
                    industry=company.industry,
                    company_type=company.company_type,
                    size_range=company.size_range,
                    headquarters=company.headquarters,
                    description=company.description,
                    status=company.status,
                ),
                location_text=job.location_text,
                description=job.description,
                requirements=job.requirements,
                salary_months=job.salary_months,
                salary_currency=job.salary_currency,
                first_seen_at=job.first_seen_at,
                last_seen_at=job.last_seen_at,
                quality_score=job.quality_score,
                quality_reasons=[str(reason) for reason in (job.quality_reasons or [])],
                gate_policy_version=job.gate_policy_version,
                gate_evaluated_at=job.gate_evaluated_at,
                note="该详情来自通过质量门的 Core 历史事实；请结合最后观察时间确认岗位当前状态。",
            )

    def _family_conditions(self, job_family: str, city: str | None = None):
        family_pattern = f"%{job_family.strip()}%"
        conditions = [
            Job.gate_policy_version != "uncertified",
            or_(
                JobFamily.code == job_family.strip(),
                JobFamily.name.ilike(family_pattern),
                Job.title.ilike(family_pattern),
                Job.normalized_title.ilike(family_pattern),
            ),
        ]
        if city:
            conditions.append(City.name == city.strip())
        return conditions

    def salary_insight(self, job_family: str, city: str) -> SalaryInsightResponse:
        with Session(self.engine) as session:
            rows = session.execute(
                select(
                    Job.id,
                    Job.salary_min,
                    Job.salary_max,
                    Job.first_seen_at,
                    Job.last_seen_at,
                )
                .outerjoin(JobFamily, JobFamily.id == Job.job_family_id)
                .outerjoin(City, City.id == Job.city_id)
                .where(
                    *self._family_conditions(job_family, city),
                    Job.salary_min.is_not(None),
                    Job.salary_max.is_not(None),
                    Job.salary_period == "month",
                )
            ).all()
            source_rows = list(
                session.scalars(
                    select(JobSource)
                    .where(JobSource.job_id.in_([row.id for row in rows]))
                    .order_by(JobSource.last_seen_at.desc())
                    .limit(5)
                )
            ) if rows else []
        values = [round((row.salary_min + row.salary_max) / 2) for row in rows]
        starts = [row.first_seen_at for row in rows if row.first_seen_at]
        ends = [row.last_seen_at for row in rows if row.last_seen_at]
        sample_size = len(values)
        return SalaryInsightResponse(
            availability="available" if values else "insufficient_sample",
            data_mode="historical",
            job_family=job_family,
            city=city,
            p25=percentile(values, 0.25),
            p50=percentile(values, 0.50),
            p75=percentile(values, 0.75),
            sample_size=sample_size,
            window_start=min(starts) if starts else None,
            window_end=max(ends) if ends else None,
            calculated_at=utc_now(),
            methodology_version=self.methodology_version,
            quality_grade=self._quality_grade(sample_size),
            sources=[self._source_ref(source, source.last_seen_at) for source in source_rows],
            note="基于通过质量门且薪资周期为月的岗位区间中点统计。"
            if values
            else "清洗后的 Core 数据中暂无足够的同城同岗位族月薪样本。",
        )

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse:
        with Session(self.engine) as session:
            job_ids = select(Job.id).outerjoin(
                JobFamily, JobFamily.id == Job.job_family_id
            ).where(*self._family_conditions(job_family))
            sample_size = session.scalar(select(func.count()).select_from(job_ids.subquery())) or 0
            rows = session.execute(
                select(Skill.name, func.count(JobSkill.job_id).label("job_count"))
                .join(JobSkill, JobSkill.skill_id == Skill.id)
                .where(JobSkill.job_id.in_(job_ids))
                .group_by(Skill.id, Skill.name)
                .order_by(func.count(JobSkill.job_id).desc(), Skill.name)
                .limit(limit)
            ).all()
            source_rows = list(
                session.scalars(
                    select(JobSource)
                    .where(JobSource.job_id.in_(job_ids))
                    .order_by(JobSource.last_seen_at.desc())
                    .limit(5)
                )
            )
        skills = [
            SkillItem(
                name=name,
                count=count,
                share=round(count / sample_size, 4) if sample_size else None,
            )
            for name, count in rows
        ]
        return SkillInsightResponse(
            availability="available" if skills else "insufficient_sample",
            data_mode="historical",
            job_family=job_family,
            sample_size=int(sample_size),
            calculated_at=utc_now(),
            methodology_version=self.methodology_version,
            quality_grade=self._quality_grade(int(sample_size)),
            skills=skills,
            sources=[self._source_ref(source, source.last_seen_at) for source in source_rows],
            note="技能频次来自清洗后岗位的结构化技能标签。"
            if skills
            else "清洗后的 Core 数据中暂无该岗位族的结构化技能样本。",
        )


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

    def _job_fact(self, item: dict, detail: dict, raw_sources: list[dict]) -> JobFact:
        job_id = detail.get("id") or item["id"]
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
        return JobFact(
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

    def search_jobs(
        self,
        keyword: str | None,
        city: str | None,
        limit: int,
        offset: int = 0,
        company: str | None = None,
        job_title: str | None = None,
        major: str | None = None,
        recruitment_type: str | None = None,
    ) -> JobSearchResponse:
        page = offset // limit + 1
        legacy_keyword = job_title or company or keyword
        result = self._get(
            "/api/jobs",
            {
                key: value
                for key, value in {
                    "keyword": legacy_keyword,
                    "city": city,
                    "page": page,
                    "page_size": limit,
                    "status": "open",
                    "is_intern": 1 if recruitment_type == "internship" else None,
                    "is_campus": 1 if recruitment_type == "campus" else None,
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
            jobs.append(self._job_fact(item, detail, raw_sources))
        total = int(result.get("total", len(jobs)))
        return JobSearchResponse(
            availability="available" if total else "insufficient_sample",
            data_mode="historical",
            keyword=keyword,
            company=company,
            job_title=job_title,
            major=major,
            recruitment_type=recruitment_type,
            city=city,
            total=total,
            page=page,
            page_size=limit,
            total_pages=math.ceil(total / limit) if total else 0,
            has_previous=page > 1,
            has_next=offset + limit < total,
            generated_at=utc_now(),
            jobs=jobs,
            note="Pin 历史/当前数据经 V2 只读适配层输出。",
        )

    def get_job(self, job_id: str) -> JobDetailResponse | None:
        try:
            prefix, raw_id = job_id.split(":", 1)
            numeric_id = int(raw_id)
        except (TypeError, ValueError):
            return None
        if prefix != "pin" or numeric_id < 1:
            return None
        detail = self._get(f"/api/jobs/{numeric_id}")
        try:
            source_payload = self._get(f"/api/jobs/{numeric_id}/sources")
            raw_sources = source_payload.get("sources", [])
        except httpx.HTTPError:
            raw_sources = []
        fact = self._job_fact({"id": numeric_id}, detail, raw_sources)
        first_seen_at = detail.get("first_seen_at") or fact.sources[0].observed_at
        last_seen_at = detail.get("last_seen_at") or fact.sources[0].observed_at
        raw_reasons = detail.get("quality_reasons") or []
        return JobDetailResponse(
            availability="available",
            data_mode="historical",
            job=fact,
            company=CompanyFact(
                company_id=f"pin-company:{detail.get('company_id') or fact.company_name}",
                name=fact.company_name,
                alias_name=detail.get("company_alias"),
                short_name=detail.get("company_short_name"),
                website_url=detail.get("company_website"),
                career_page_url=detail.get("company_career_page"),
                industry=detail.get("industry"),
                company_type=detail.get("company_type"),
                size_range=detail.get("company_size"),
                headquarters=detail.get("headquarters"),
                description=detail.get("company_description"),
                status=detail.get("company_status") or "unknown",
            ),
            location_text=detail.get("location") or fact.city,
            description=detail.get("description") or detail.get("job_description"),
            requirements=detail.get("requirements") or detail.get("job_requirements"),
            salary_months=detail.get("salary_months"),
            salary_currency=detail.get("salary_currency") or "CNY",
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            quality_score=max(0, min(100, int(detail.get("quality_score") or 0))),
            quality_reasons=[str(reason) for reason in raw_reasons],
            gate_policy_version="pin-job-adapter-v1",
            gate_evaluated_at=last_seen_at,
            note="该详情来自 Pin 只读适配层，请结合最后观察时间核对当前招聘状态。",
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
