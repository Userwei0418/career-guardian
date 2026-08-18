from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from market_data.models.raw import (
    DataSource,
    RawRecord,
    RecruitmentSchool,
    SchoolAdminAuditLog,
)


SchoolSort = Literal[
    "updated_desc",
    "created_desc",
    "name_asc",
    "name_desc",
    "source_count_desc",
]


class SchoolView(BaseModel):
    id: int
    code: str
    name: str
    employment_center_name: str
    short_name: str | None = None
    province: str | None = None
    city: str | None = None
    website_url: str | None = None
    description: str | None = None
    origin: str
    status: str
    source_count: int = 0
    enabled_source_count: int = 0
    raw_record_count: int = 0
    created_at: datetime
    updated_at: datetime


class SchoolList(BaseModel):
    items: list[SchoolView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    sort_by: SchoolSort


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    employment_center_name: str = Field(min_length=2, max_length=255)
    short_name: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    website_url: str | None = Field(default=None, max_length=1000)
    description: str | None = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    actor: str = Field(min_length=1, max_length=100)


class SchoolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    employment_center_name: str | None = Field(default=None, min_length=2, max_length=255)
    short_name: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    website_url: str | None = Field(default=None, max_length=1000)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|inactive|deleted)$")
    actor: str = Field(min_length=1, max_length=100)


class SchoolAuditView(BaseModel):
    id: int
    school_id: int | None = None
    entity_id: str
    action: str
    actor: str
    before_payload: dict | None = None
    after_payload: dict | None = None
    created_at: datetime


class SchoolAuditList(BaseModel):
    items: list[SchoolAuditView]
    total: int


def _school_payload(school: RecruitmentSchool) -> dict:
    return {
        key: getattr(school, key)
        for key in (
            "id",
            "code",
            "name",
            "employment_center_name",
            "short_name",
            "province",
            "city",
            "website_url",
            "description",
            "origin",
            "status",
            "created_at",
            "updated_at",
        )
    }


def _json_safe(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    return json.loads(
        json.dumps(
            payload,
            default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        )
    )


def _school_view(
    school: RecruitmentSchool,
    source_count: int,
    enabled_source_count: int,
    raw_record_count: int,
) -> SchoolView:
    return SchoolView(
        **_school_payload(school),
        source_count=source_count,
        enabled_source_count=enabled_source_count,
        raw_record_count=raw_record_count,
    )


class SchoolAdminService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    @staticmethod
    def _counts():
        source_count = (
            select(func.count(DataSource.id))
            .where(DataSource.school_id == RecruitmentSchool.id)
            .correlate(RecruitmentSchool)
            .scalar_subquery()
        )
        enabled_source_count = (
            select(func.count(DataSource.id))
            .where(DataSource.school_id == RecruitmentSchool.id, DataSource.enabled.is_(True))
            .correlate(RecruitmentSchool)
            .scalar_subquery()
        )
        raw_record_count = (
            select(func.count(RawRecord.id))
            .join(DataSource, DataSource.id == RawRecord.source_id)
            .where(DataSource.school_id == RecruitmentSchool.id)
            .correlate(RecruitmentSchool)
            .scalar_subquery()
        )
        return source_count, enabled_source_count, raw_record_count

    def list_schools(
        self,
        query: str | None,
        status: str | None,
        sort_by: SchoolSort,
        page: int,
        page_size: int,
    ) -> SchoolList:
        with self.session_factory() as session:
            source_count, enabled_source_count, raw_record_count = self._counts()
            filters = []
            if query:
                term = f"%{query.strip()}%"
                filters.append(
                    or_(
                        RecruitmentSchool.name.like(term),
                        RecruitmentSchool.employment_center_name.like(term),
                        RecruitmentSchool.short_name.like(term),
                        RecruitmentSchool.province.like(term),
                        RecruitmentSchool.city.like(term),
                    )
                )
            if status:
                filters.append(RecruitmentSchool.status == status)
            else:
                filters.append(RecruitmentSchool.status != "deleted")
            orders = {
                "updated_desc": (RecruitmentSchool.updated_at.desc(), RecruitmentSchool.id.desc()),
                "created_desc": (RecruitmentSchool.created_at.desc(), RecruitmentSchool.id.desc()),
                "name_asc": (RecruitmentSchool.employment_center_name.asc(), RecruitmentSchool.id.asc()),
                "name_desc": (RecruitmentSchool.employment_center_name.desc(), RecruitmentSchool.id.desc()),
                "source_count_desc": (source_count.desc(), RecruitmentSchool.updated_at.desc()),
            }
            total = int(
                session.scalar(select(func.count(RecruitmentSchool.id)).where(*filters)) or 0
            )
            rows = session.execute(
                select(
                    RecruitmentSchool,
                    source_count.label("source_count"),
                    enabled_source_count.label("enabled_source_count"),
                    raw_record_count.label("raw_record_count"),
                )
                .where(*filters)
                .order_by(*orders[sort_by])
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return SchoolList(
                items=[
                    _school_view(school, int(sources or 0), int(enabled or 0), int(raw or 0))
                    for school, sources, enabled, raw in rows
                ],
                total=total,
                page=page,
                page_size=page_size,
                total_pages=(total + page_size - 1) // page_size,
                sort_by=sort_by,
            )

    def create_school(self, request: SchoolCreate) -> SchoolView:
        with self.session_factory() as session:
            name = request.name.strip()
            center_name = request.employment_center_name.strip()
            duplicate = session.scalar(
                select(RecruitmentSchool.id).where(
                    RecruitmentSchool.employment_center_name == center_name,
                    RecruitmentSchool.status != "deleted",
                )
            )
            if duplicate:
                raise ValueError("学校或就业服务机构名称已存在")
            school = RecruitmentSchool(
                code=f"school-manual-{uuid4().hex[:24]}",
                origin="manual",
                **request.model_dump(exclude={"actor", "name", "employment_center_name"}),
                name=name,
                employment_center_name=center_name,
            )
            session.add(school)
            session.flush()
            self._audit(session, school, "create", request.actor, None, _school_payload(school))
            session.commit()
            session.refresh(school)
            return _school_view(school, 0, 0, 0)

    def update_school(self, school_id: int, request: SchoolUpdate) -> SchoolView:
        with self.session_factory() as session:
            school = session.get(RecruitmentSchool, school_id)
            if school is None:
                raise LookupError("学校不存在")
            before = _school_payload(school)
            values = request.model_dump(exclude={"actor"}, exclude_unset=True)
            if values.get("name"):
                values["name"] = values["name"].strip()
            if values.get("employment_center_name"):
                values["employment_center_name"] = values["employment_center_name"].strip()
                duplicate = session.scalar(
                    select(RecruitmentSchool.id).where(
                        RecruitmentSchool.employment_center_name == values["employment_center_name"],
                        RecruitmentSchool.id != school_id,
                        RecruitmentSchool.status != "deleted",
                    )
                )
                if duplicate:
                    raise ValueError("学校或就业服务机构名称已存在")
            for key, value in values.items():
                setattr(school, key, value)
            session.flush()
            source_count, enabled_source_count, raw_record_count = self._count_one(session, school.id)
            self._audit(session, school, "update", request.actor, before, _school_payload(school))
            session.commit()
            session.refresh(school)
            return _school_view(school, source_count, enabled_source_count, raw_record_count)

    def delete_school(self, school_id: int, actor: str) -> SchoolView:
        with self.session_factory() as session:
            school = session.get(RecruitmentSchool, school_id)
            if school is None:
                raise LookupError("学校不存在")
            before = _school_payload(school)
            school.status = "deleted"
            session.flush()
            source_count, enabled_source_count, raw_record_count = self._count_one(session, school.id)
            self._audit(session, school, "delete", actor, before, _school_payload(school))
            session.commit()
            session.refresh(school)
            return _school_view(school, source_count, enabled_source_count, raw_record_count)

    def list_audit_logs(self, limit: int = 50) -> SchoolAuditList:
        with self.session_factory() as session:
            total = int(session.scalar(select(func.count(SchoolAdminAuditLog.id))) or 0)
            rows = session.scalars(
                select(SchoolAdminAuditLog)
                .order_by(SchoolAdminAuditLog.created_at.desc(), SchoolAdminAuditLog.id.desc())
                .limit(limit)
            ).all()
            return SchoolAuditList(
                items=[
                    SchoolAuditView(
                        id=row.id,
                        school_id=row.school_id,
                        entity_id=row.entity_id,
                        action=row.action,
                        actor=row.actor,
                        before_payload=row.before_payload,
                        after_payload=row.after_payload,
                        created_at=row.created_at,
                    )
                    for row in rows
                ],
                total=total,
            )

    @staticmethod
    def _count_one(session: Session, school_id: int) -> tuple[int, int, int]:
        source_count = int(
            session.scalar(select(func.count(DataSource.id)).where(DataSource.school_id == school_id)) or 0
        )
        enabled_source_count = int(
            session.scalar(
                select(func.count(DataSource.id)).where(
                    DataSource.school_id == school_id,
                    DataSource.enabled.is_(True),
                )
            )
            or 0
        )
        raw_record_count = int(
            session.scalar(
                select(func.count(RawRecord.id))
                .join(DataSource, DataSource.id == RawRecord.source_id)
                .where(DataSource.school_id == school_id)
            )
            or 0
        )
        return source_count, enabled_source_count, raw_record_count

    @staticmethod
    def _audit(
        session: Session,
        school: RecruitmentSchool,
        action: str,
        actor: str,
        before: dict | None,
        after: dict | None,
    ) -> None:
        session.add(
            SchoolAdminAuditLog(
                school_id=school.id,
                entity_id=str(school.id),
                action=action,
                actor=actor,
                before_payload=_json_safe(before),
                after_payload=_json_safe(after),
            )
        )
