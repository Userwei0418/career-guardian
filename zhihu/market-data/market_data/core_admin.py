from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from market_data.models.core import Company, Job, JobSource, MarketAdminAuditLog


CompanySort = Literal["updated_desc", "created_desc", "name_asc", "name_desc", "job_count_desc"]
JobSort = Literal["updated_desc", "created_desc", "published_desc", "quality_desc", "title_asc"]


class CoreCompanyView(BaseModel):
    id: int
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
    logo_url: str | None = None
    tags: list = Field(default_factory=list)
    status: str
    job_count: int = 0
    created_at: datetime
    updated_at: datetime


class CoreCompanyList(BaseModel):
    items: list[CoreCompanyView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    sort_by: CompanySort


class CoreCompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    alias_name: str | None = Field(default=None, max_length=255)
    short_name: str | None = Field(default=None, max_length=100)
    website_url: str | None = Field(default=None, max_length=1000)
    career_page_url: str | None = Field(default=None, max_length=1000)
    industry: str | None = Field(default=None, max_length=100)
    company_type: str | None = Field(default=None, max_length=100)
    size_range: str | None = Field(default=None, max_length=100)
    headquarters: str | None = Field(default=None, max_length=255)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    actor: str = Field(min_length=1, max_length=100)


class CoreCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    alias_name: str | None = Field(default=None, max_length=255)
    short_name: str | None = Field(default=None, max_length=100)
    website_url: str | None = Field(default=None, max_length=1000)
    career_page_url: str | None = Field(default=None, max_length=1000)
    industry: str | None = Field(default=None, max_length=100)
    company_type: str | None = Field(default=None, max_length=100)
    size_range: str | None = Field(default=None, max_length=100)
    headquarters: str | None = Field(default=None, max_length=255)
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, pattern=r"^(active|inactive|deleted)$")
    actor: str = Field(min_length=1, max_length=100)


class CoreJobView(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    location_text: str | None = None
    department: str | None = None
    job_category: str | None = None
    employment_type: str | None = None
    education_requirement: str | None = None
    experience_requirement: str | None = None
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    salary_text: str | None = None
    apply_url: str | None = None
    detail_url: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    status: str
    quality_score: int
    quality_grade: str
    created_at: datetime
    updated_at: datetime


class CoreJobList(BaseModel):
    items: list[CoreJobView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    sort_by: JobSort


class CoreJobCreate(BaseModel):
    company_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=255)
    location_text: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=255)
    job_category: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=100)
    education_requirement: str | None = Field(default=None, max_length=255)
    experience_requirement: str | None = Field(default=None, max_length=255)
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    salary_text: str | None = Field(default=None, max_length=255)
    apply_url: str | None = Field(default=None, max_length=2000)
    detail_url: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    status: str = Field(default="draft", pattern=r"^(draft|open|closed|expired)$")
    actor: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_publishable(self) -> "CoreJobCreate":
        if self.status == "open" and not ((self.description or self.responsibilities) and self.requirements):
            raise ValueError("发布职位必须填写职位正文或职责，并填写任职要求")
        return self


class CoreJobUpdate(BaseModel):
    company_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    location_text: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=255)
    job_category: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=100)
    education_requirement: str | None = Field(default=None, max_length=255)
    experience_requirement: str | None = Field(default=None, max_length=255)
    description: str | None = None
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    salary_text: str | None = Field(default=None, max_length=255)
    apply_url: str | None = Field(default=None, max_length=2000)
    detail_url: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    status: str | None = Field(default=None, pattern=r"^(draft|open|closed|expired|deleted)$")
    actor: str = Field(min_length=1, max_length=100)


class CoreAuditView(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    actor: str
    before_payload: dict | None = None
    after_payload: dict | None = None
    created_at: datetime


class CoreAuditList(BaseModel):
    items: list[CoreAuditView]
    total: int


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _company_payload(company: Company) -> dict:
    return {key: getattr(company, key) for key in (
        "id", "name", "alias_name", "short_name", "website_url", "career_page_url",
        "industry", "company_type", "size_range", "headquarters", "description",
        "logo_url", "tags", "status", "created_at", "updated_at",
    )}


def _job_payload(job: Job) -> dict:
    return {key: getattr(job, key) for key in (
        "id", "company_id", "title", "location_text", "department", "job_category",
        "employment_type", "education_requirement", "experience_requirement", "description",
        "requirements", "responsibilities", "benefits", "salary_text", "apply_url",
        "detail_url", "published_at", "deadline_at", "status", "quality_score",
        "quality_grade", "created_at", "updated_at",
    )}


def _json_safe(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    return json.loads(json.dumps(payload, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)))


def _audit(session: Session, entity_type: str, entity_id: int, action: str, actor: str, before: dict | None, after: dict | None) -> None:
    session.add(MarketAdminAuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor=actor,
        before_payload=_json_safe(before),
        after_payload=_json_safe(after),
    ))


def _company_view(company: Company, job_count: int) -> CoreCompanyView:
    return CoreCompanyView(**_company_payload(company), job_count=job_count)


def _job_view(job: Job, company_name: str) -> CoreJobView:
    return CoreJobView(**_job_payload(job), company_name=company_name)


class CoreAdminService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def list_companies(self, query: str | None, status: str | None, sort_by: CompanySort, page: int, page_size: int) -> CoreCompanyList:
        with self.session_factory() as session:
            job_count = select(func.count(Job.id)).where(Job.company_id == Company.id, Job.status != "deleted").correlate(Company).scalar_subquery()
            filters = []
            if query:
                term = f"%{query.strip()}%"
                filters.append(or_(Company.name.like(term), Company.short_name.like(term), Company.alias_name.like(term), Company.industry.like(term)))
            if status:
                filters.append(Company.status == status)
            else:
                filters.append(Company.status != "deleted")
            orders = {
                "updated_desc": (Company.updated_at.desc(), Company.id.desc()),
                "created_desc": (Company.created_at.desc(), Company.id.desc()),
                "name_asc": (Company.name.asc(), Company.id.asc()),
                "name_desc": (Company.name.desc(), Company.id.desc()),
                "job_count_desc": (job_count.desc(), Company.updated_at.desc(), Company.id.desc()),
            }
            total = int(session.scalar(select(func.count(Company.id)).where(*filters)) or 0)
            rows = session.execute(select(Company, job_count.label("job_count")).where(*filters).order_by(*orders[sort_by]).offset((page - 1) * page_size).limit(page_size)).all()
            return CoreCompanyList(items=[_company_view(company, int(count or 0)) for company, count in rows], total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size, sort_by=sort_by)

    def create_company(self, request: CoreCompanyCreate) -> CoreCompanyView:
        with self.session_factory() as session:
            if session.scalar(select(Company.id).where(Company.name == request.name.strip())):
                raise ValueError("公司名称已存在")
            values = request.model_dump(exclude={"actor"})
            values["name"] = request.name.strip()
            values["normalized_name"] = request.name.strip().lower()
            company = Company(**values)
            session.add(company)
            session.flush()
            _audit(session, "company", company.id, "create", request.actor, None, _company_payload(company))
            session.commit()
            session.refresh(company)
            return _company_view(company, 0)

    def update_company(self, company_id: int, request: CoreCompanyUpdate) -> CoreCompanyView:
        with self.session_factory() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise LookupError("公司不存在")
            before = _company_payload(company)
            values = request.model_dump(exclude={"actor"}, exclude_unset=True)
            if values.get("name"):
                duplicate = session.scalar(select(Company.id).where(Company.name == values["name"].strip(), Company.id != company_id))
                if duplicate:
                    raise ValueError("公司名称已存在")
                values["name"] = values["name"].strip()
                values["normalized_name"] = values["name"].lower()
            for key, value in values.items():
                setattr(company, key, value)
            session.flush()
            count = int(session.scalar(select(func.count(Job.id)).where(Job.company_id == company.id, Job.status != "deleted")) or 0)
            _audit(session, "company", company.id, "update", request.actor, before, _company_payload(company))
            session.commit()
            session.refresh(company)
            return _company_view(company, count)

    def delete_company(self, company_id: int, actor: str) -> CoreCompanyView:
        with self.session_factory() as session:
            company = session.get(Company, company_id)
            if company is None:
                raise LookupError("公司不存在")
            before = _company_payload(company)
            company.status = "deleted"
            session.flush()
            count = int(session.scalar(select(func.count(Job.id)).where(Job.company_id == company.id, Job.status != "deleted")) or 0)
            _audit(session, "company", company.id, "delete", actor, before, _company_payload(company))
            session.commit()
            session.refresh(company)
            return _company_view(company, count)

    def list_jobs(self, query: str | None, status: str | None, company_id: int | None, sort_by: JobSort, page: int, page_size: int) -> CoreJobList:
        with self.session_factory() as session:
            filters = []
            if query:
                term = f"%{query.strip()}%"
                filters.append(or_(Job.title.like(term), Company.name.like(term), Job.location_text.like(term), Job.department.like(term)))
            if status:
                filters.append(Job.status == status)
            else:
                filters.append(Job.status != "deleted")
            if company_id:
                filters.append(Job.company_id == company_id)
            orders = {
                "updated_desc": (Job.updated_at.desc(), Job.id.desc()),
                "created_desc": (Job.created_at.desc(), Job.id.desc()),
                "published_desc": (Job.published_at.desc(), Job.id.desc()),
                "quality_desc": (Job.quality_score.desc(), Job.updated_at.desc(), Job.id.desc()),
                "title_asc": (Job.title.asc(), Job.id.asc()),
            }
            base = select(Job, Company.name).join(Company, Company.id == Job.company_id).where(*filters)
            total = int(session.scalar(select(func.count(Job.id)).join(Company, Company.id == Job.company_id).where(*filters)) or 0)
            rows = session.execute(base.order_by(*orders[sort_by]).offset((page - 1) * page_size).limit(page_size)).all()
            return CoreJobList(items=[_job_view(job, name) for job, name in rows], total=total, page=page, page_size=page_size, total_pages=(total + page_size - 1) // page_size, sort_by=sort_by)

    def create_job(self, request: CoreJobCreate) -> CoreJobView:
        with self.session_factory() as session:
            company = session.get(Company, request.company_id)
            if company is None or company.status == "deleted":
                raise ValueError("请选择有效公司")
            now = _now()
            identity = f"admin:{uuid4().hex}"
            values = request.model_dump(exclude={"actor"})
            job = Job(
                **values,
                identity_key=identity,
                normalized_title=request.title.strip().lower(),
                first_seen_at=now,
                last_seen_at=now,
                quality_score=80 if request.status == "open" else 0,
                quality_grade="B" if request.status == "open" else "C",
                quality_reasons=["manual_admin_entry"],
                gate_policy_version="manual-admin-v1",
                gate_evaluated_at=now,
            )
            session.add(job)
            session.flush()
            source_url = request.detail_url or request.apply_url or company.career_page_url or company.website_url or f"admin://market/jobs/{job.id}"
            content_hash = hashlib.sha256(json.dumps(_job_payload(job), ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()
            session.add(JobSource(job_id=job.id, provenance_type="admin", source_url=source_url, content_hash=content_hash, fetched_at=now, first_seen_at=now, last_seen_at=now, is_official=False))
            _audit(session, "job", job.id, "create", request.actor, None, _job_payload(job))
            session.commit()
            session.refresh(job)
            return _job_view(job, company.name)

    def update_job(self, job_id: int, request: CoreJobUpdate) -> CoreJobView:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise LookupError("职位不存在")
            before = _job_payload(job)
            values = request.model_dump(exclude={"actor"}, exclude_unset=True)
            if "company_id" in values:
                company = session.get(Company, values["company_id"])
                if company is None or company.status == "deleted":
                    raise ValueError("请选择有效公司")
            else:
                company = session.get(Company, job.company_id)
            for key, value in values.items():
                setattr(job, key, value)
            if values.get("title"):
                job.normalized_title = values["title"].strip().lower()
            if job.status == "open" and not ((job.description or job.responsibilities) and job.requirements):
                raise ValueError("发布职位必须填写职位正文或职责，并填写任职要求")
            job.quality_score = 80 if job.status == "open" else job.quality_score
            job.quality_grade = "B" if job.status == "open" else job.quality_grade
            job.last_seen_at = _now()
            session.flush()
            _audit(session, "job", job.id, "update", request.actor, before, _job_payload(job))
            session.commit()
            session.refresh(job)
            assert company is not None
            return _job_view(job, company.name)

    def delete_job(self, job_id: int, actor: str) -> CoreJobView:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise LookupError("职位不存在")
            company = session.get(Company, job.company_id)
            before = _job_payload(job)
            job.status = "deleted"
            job.last_seen_at = _now()
            session.flush()
            _audit(session, "job", job.id, "delete", actor, before, _job_payload(job))
            session.commit()
            session.refresh(job)
            assert company is not None
            return _job_view(job, company.name)

    def list_audit_logs(self, entity_type: str | None, limit: int) -> CoreAuditList:
        with self.session_factory() as session:
            filters = [MarketAdminAuditLog.entity_type == entity_type] if entity_type else []
            total = int(session.scalar(select(func.count(MarketAdminAuditLog.id)).where(*filters)) or 0)
            rows = list(session.scalars(select(MarketAdminAuditLog).where(*filters).order_by(MarketAdminAuditLog.created_at.desc(), MarketAdminAuditLog.id.desc()).limit(limit)))
            items = []
            for row in rows:
                action = row.action
                before = row.before_payload or {}
                after = row.after_payload or {}
                # Correct early soft-delete records that were written through the update path.
                if action == "update" and before.get("status") != "deleted" and after.get("status") == "deleted":
                    action = "delete"
                items.append(CoreAuditView(
                    id=row.id,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    action=action,
                    actor=row.actor,
                    before_payload=row.before_payload,
                    after_payload=row.after_payload,
                    created_at=row.created_at,
                ))
            return CoreAuditList(items=items, total=total)
