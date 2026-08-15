from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Availability = Literal["available", "insufficient_sample", "stale", "unavailable"]
DataMode = Literal["live", "historical", "fixture"]
QualityGrade = Literal["A", "B", "C", "insufficient"]


class MarketSourceRef(BaseModel):
    source_id: str
    source_name: str
    source_url: str | None = None
    observed_at: datetime


class CompanyFact(BaseModel):
    company_id: str
    name: str
    alias_name: str | None = None
    short_name: str | None = None
    website_url: str | None = None
    career_page_url: str | None = None
    industry: str | None = None
    company_type: str | None = None
    size_range: str | None = None
    headquarters: str | None = None
    description: str | None = None
    status: str = "unknown"


class QualityMeta(BaseModel):
    grade: QualityGrade
    sample_size: int = Field(ge=0)
    window_start: datetime | None = None
    window_end: datetime | None = None
    methodology_version: str


class JobFact(BaseModel):
    job_id: str
    title: str
    normalized_title: str | None = None
    company_name: str
    city: str | None = None
    recruitment_type: Literal["campus", "internship", "social", "unknown"] = "unknown"
    salary_min: int | None = None
    salary_max: int | None = None
    salary_period: Literal["month", "year", "day", "hour", "unknown"] = "unknown"
    skills: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    status: Literal["open", "closed", "expired", "unknown"] = "unknown"
    data_mode: DataMode
    quality: QualityMeta
    sources: list[MarketSourceRef] = Field(min_length=1)


class JobSearchResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    keyword: str | None = None
    city: str | None = None
    total: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    total_pages: int = Field(default=0, ge=0)
    has_previous: bool = False
    has_next: bool = False
    generated_at: datetime
    jobs: list[JobFact]
    note: str | None = None


class JobDetailResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    job: JobFact
    company: CompanyFact
    location_text: str | None = None
    description: str | None = None
    requirements: str | None = None
    salary_months: int | None = None
    salary_currency: str = "CNY"
    first_seen_at: datetime
    last_seen_at: datetime
    quality_score: int = Field(ge=0, le=100)
    quality_reasons: list[str] = Field(default_factory=list)
    gate_policy_version: str
    gate_evaluated_at: datetime
    note: str | None = None


class SalaryInsightResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    job_family: str
    city: str
    currency: str = "CNY"
    period: Literal["month", "year"] = "month"
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    sample_size: int = Field(ge=0)
    window_start: datetime | None = None
    window_end: datetime | None = None
    calculated_at: datetime
    methodology_version: str
    quality_grade: QualityGrade
    sources: list[MarketSourceRef]
    note: str | None = None


class SkillItem(BaseModel):
    name: str
    count: int = Field(ge=0)
    share: float | None = Field(default=None, ge=0, le=1)


class SkillInsightResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    job_family: str
    sample_size: int = Field(ge=0)
    calculated_at: datetime
    methodology_version: str
    quality_grade: QualityGrade
    skills: list[SkillItem]
    sources: list[MarketSourceRef]
    note: str | None = None
