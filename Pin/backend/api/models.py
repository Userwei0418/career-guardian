from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CompanyBase(BaseModel):
    name: str
    alias_name: Optional[str] = None
    short_name: Optional[str] = None
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    career_page_url: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    size_range: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class Company(CompanyBase):
    id: int
    status: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobBase(BaseModel):
    title: str
    normalized_title: Optional[str] = None
    department: Optional[str] = None
    job_category: Optional[str] = None
    employment_type: Optional[str] = None
    is_campus: int = 0
    is_intern: int = 0
    location_text: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    education_requirement: Optional[str] = None
    education_level: Optional[str] = None
    experience_requirement: Optional[str] = None
    salary_text: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_unit: Optional[str] = None
    salary_months: Optional[int] = None
    job_description: Optional[str] = None
    job_requirements: Optional[str] = None
    job_responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    skill_tags: Optional[List[str]] = None
    major_requirement: Optional[str] = None
    language_requirement: Optional[str] = None
    certificate_requirement: Optional[str] = None
    work_time: Optional[str] = None
    salary_payment: Optional[str] = None
    industry_requirement: Optional[str] = None
    job_level: Optional[str] = None
    apply_url: Optional[str] = None
    detail_url: Optional[str] = None
    source_site: Optional[str] = None
    source_job_id: Optional[str] = None
    published_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: str = "open"


class Job(JobBase):
    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobWithCompany(Job):
    company_name: Optional[str] = None
    company_short_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    company_website_url: Optional[str] = None
    company_career_page_url: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    size_range: Optional[str] = None


class JobSource(BaseModel):
    id: int
    job_id: int
    source_site: str
    source_type: Optional[str] = None
    source_job_id: Optional[str] = None
    source_url: Optional[str] = None
    apply_url: Optional[str] = None
    is_official: int = 0
    is_primary_source: int = 0
    published_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    status: str = "active"

    class Config:
        from_attributes = True


class JobListItem(BaseModel):
    id: int
    title: str
    normalized_title: Optional[str] = None
    job_category: Optional[str] = None
    employment_type: Optional[str] = None
    is_campus: int = 0
    is_intern: int = 0
    city: Optional[str] = None
    education_level: Optional[str] = None
    salary_text: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    published_at: Optional[datetime] = None
    company_id: int
    company_name: str
    company_short_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    source_site: Optional[str] = None

    class Config:
        from_attributes = True


class JobListResponseV2(BaseModel):
    total: Optional[int] = None
    page: int
    page_size: int
    has_more: bool
    jobs: List[JobListItem]


class CursorJobListResponse(BaseModel):
    page_size: int
    has_more: bool
    next_cursor_published_at: Optional[datetime] = None
    next_cursor_id: Optional[int] = None
    jobs: List[JobListItem]


class CompanyListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    companies: List[Company]


class JobSourceListResponse(BaseModel):
    total: int
    sources: List[JobSource]


class CityStats(BaseModel):
    city: str
    count: int


class CompanyStats(BaseModel):
    company_id: int
    company_name: str
    company_short_name: Optional[str] = None
    company_logo_url: Optional[str] = None
    job_count: int


class Stats(BaseModel):
    job_count: int
    company_count: int
    city_count: int


class CompanyJobListItem(BaseModel):
    id: int
    title: str
    employment_type: Optional[str] = None
    is_campus: int = 0
    is_intern: int = 0
    city: Optional[str] = None
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True