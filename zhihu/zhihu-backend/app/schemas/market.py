from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


Availability = Literal["available", "insufficient_sample", "stale", "unavailable"]
DataMode = Literal["live", "historical", "fixture", "unknown"]
QualityGrade = Literal["A", "B", "C", "insufficient"]


class MarketSourceRef(BaseModel):
    source_id: str
    source_name: str
    source_url: Optional[str] = None
    observed_at: datetime


class CompanyFact(BaseModel):
    company_id: str
    name: str
    alias_name: Optional[str] = None
    short_name: Optional[str] = None
    website_url: Optional[str] = None
    career_page_url: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    size_range: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    status: str = "unknown"


class QualityMeta(BaseModel):
    grade: QualityGrade
    sample_size: int = Field(ge=0)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    methodology_version: str


class JobFact(BaseModel):
    job_id: str
    title: str
    normalized_title: Optional[str] = None
    company_name: str
    city: Optional[str] = None
    recruitment_type: Literal["campus", "internship", "social", "unknown"] = "unknown"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_period: Literal["month", "year", "day", "hour", "unknown"] = "unknown"
    skills: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    status: Literal["open", "closed", "expired", "unknown"] = "unknown"
    data_mode: DataMode
    quality: QualityMeta
    sources: list[MarketSourceRef] = Field(min_length=1)
    match_score: Optional[int] = Field(default=None, ge=0, le=100)
    match_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)


class JobSearchResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    keyword: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    major: Optional[str] = None
    recruitment_type: Optional[Literal["campus", "internship", "social"]] = None
    city: Optional[str] = None
    total: int = Field(ge=0)
    candidate_total: Optional[int] = Field(default=None, ge=0)
    sort_by: Literal["default", "relevance"] = "default"
    personalized: bool = False
    ranking_basis: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    total_pages: int = Field(default=0, ge=0)
    has_previous: bool = False
    has_next: bool = False
    generated_at: datetime
    jobs: list[JobFact]
    note: Optional[str] = None


class JobDetailResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    job: JobFact
    company: CompanyFact
    location_text: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    department: Optional[str] = None
    job_category: Optional[str] = None
    employment_type: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    education_requirement: Optional[str] = None
    education_level: Optional[str] = None
    experience_requirement: Optional[str] = None
    major_requirement: Optional[str] = None
    language_requirement: Optional[str] = None
    certificate_requirement: Optional[str] = None
    work_time: Optional[str] = None
    salary_payment: Optional[str] = None
    industry_requirement: Optional[str] = None
    job_level: Optional[str] = None
    salary_text: Optional[str] = None
    deadline_at: Optional[datetime] = None
    apply_url: Optional[str] = None
    detail_url: Optional[str] = None
    salary_months: Optional[int] = None
    salary_currency: str = "CNY"
    first_seen_at: datetime
    last_seen_at: datetime
    quality_score: int = Field(ge=0, le=100)
    quality_reasons: list[str] = Field(default_factory=list)
    gate_policy_version: str
    gate_evaluated_at: datetime
    note: Optional[str] = None


class SalaryInsightResponse(BaseModel):
    availability: Availability
    data_mode: DataMode = "unknown"
    job_family: str
    city: str
    currency: str = "CNY"
    period: Literal["month", "year"] = "month"
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    sample_size: int = Field(ge=0)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    calculated_at: datetime
    methodology_version: str
    quality_grade: QualityGrade
    sources: list[MarketSourceRef]
    note: Optional[str] = None


class SkillItem(BaseModel):
    name: str
    count: int = Field(ge=0)
    share: Optional[float] = Field(default=None, ge=0, le=1)


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
    note: Optional[str] = None


class DistributionItem(BaseModel):
    code: Optional[str] = None
    name: str
    count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class MarketOverviewResponse(BaseModel):
    availability: Availability
    data_mode: DataMode
    scope: Literal["market", "job_family"]
    scope_label: str
    job_count: int = Field(ge=0)
    company_count: int = Field(ge=0)
    city_count: int = Field(ge=0)
    salary_sample_count: int = Field(ge=0)
    skill_sample_count: int = Field(ge=0)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    recruitment_types: list[DistributionItem]
    cities: list[DistributionItem]
    job_families: list[DistributionItem]
    skills: list[DistributionItem]
    education_levels: list[DistributionItem] = Field(default_factory=list)
    salary_p25: Optional[float] = None
    salary_p50: Optional[float] = None
    salary_p75: Optional[float] = None
    bachelor_salary_median: Optional[float] = None
    master_salary_median: Optional[float] = None
    master_salary_premium: Optional[float] = None
    bachelor_salary_sample_count: int = Field(default=0, ge=0)
    master_salary_sample_count: int = Field(default=0, ge=0)
    generated_at: datetime
    note: Optional[str] = None


class DirectionResolveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=80)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("请输入至少 2 个字的专业或学习方向")
        return cleaned


class DirectionMatchItem(BaseModel):
    direction: str
    score: float = Field(ge=0, le=1)
    reason: str
    job_count: int = Field(ge=0)
    share: float = Field(ge=0, le=1)


class DirectionResolveResponse(BaseModel):
    query: str
    mode: Literal["exact", "taxonomy", "ai", "unresolved"]
    matches: list[DirectionMatchItem]
    note: str
