from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_data.models.core import (
    City,
    Company,
    Job,
    JobSkill,
    JobSource,
    QualityGatePolicy,
    RecruitmentType,
    Skill,
)
from market_data.quality_gate import (
    GatePolicy,
    IMMUTABLE_REQUIRED_FACTS,
    JobGateCandidate,
    JobQualityGate,
    SUPPORTED_REQUIRED_FACTS,
    utc_now_naive,
)


DEFAULT_POLICY = GatePolicy.load()
SCORE_DIMENSIONS = [
    "identity",
    "source_url",
    "content_hash",
    "description",
    "city",
    "published_at",
    "observed_at",
    "skills",
    "salary",
]


def ensure_default_policy(session: Session) -> QualityGatePolicy:
    active = session.scalar(
        select(QualityGatePolicy)
        .where(QualityGatePolicy.status == "active")
        .order_by(QualityGatePolicy.id.desc())
        .limit(1)
    )
    if active is not None:
        return active
    active = QualityGatePolicy(
        policy_version=DEFAULT_POLICY.policy_version,
        status="active",
        configuration=DEFAULT_POLICY.to_dict(),
        change_note="系统初始岗位准入标准",
        created_by="system",
        published_by="system",
        published_at=utc_now_naive(),
    )
    session.add(active)
    session.commit()
    session.refresh(active)
    return active


def active_gate_policy(session: Session) -> GatePolicy:
    record = ensure_default_policy(session)
    return GatePolicy.from_dict(record.configuration)


def next_policy_version(session: Session) -> str:
    versions = session.scalars(select(QualityGatePolicy.policy_version)).all()
    numbers = [
        int(match.group(1))
        for version in versions
        if (match := re.fullmatch(r"career-guardian-job-core-v(\d+)", version))
    ]
    return f"career-guardian-job-core-v{max(numbers, default=0) + 1}"


def policy_view(session: Session, record: QualityGatePolicy | None) -> dict | None:
    if record is None:
        return None
    certified_jobs = int(
        session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.gate_policy_version == record.policy_version)
        )
        or 0
    )
    return {
        "id": record.id,
        "policy_version": record.policy_version,
        "status": record.status,
        "configuration": record.configuration,
        "change_note": record.change_note,
        "created_by": record.created_by,
        "published_by": record.published_by,
        "preview_summary": record.preview_summary,
        "previewed_at": record.previewed_at,
        "published_at": record.published_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "certified_jobs": certified_jobs,
    }


def gate_settings(session: Session) -> dict:
    active = ensure_default_policy(session)
    draft = session.scalar(
        select(QualityGatePolicy)
        .where(QualityGatePolicy.status == "draft")
        .order_by(QualityGatePolicy.id.desc())
        .limit(1)
    )
    counts = {
        version: int(count)
        for version, count in session.execute(
            select(Job.gate_policy_version, func.count(Job.id)).group_by(Job.gate_policy_version)
        )
    }
    return {
        "active": policy_view(session, active),
        "draft": policy_view(session, draft),
        "certified_job_counts": counts,
        "supported_required_facts": list(SUPPORTED_REQUIRED_FACTS),
        "immutable_required_facts": list(IMMUTABLE_REQUIRED_FACTS),
        "score_dimensions": SCORE_DIMENSIONS,
        "publish_scope": "future_ingestion",
    }


def save_draft(
    session: Session,
    configuration: dict,
    change_note: str,
    actor: str,
) -> dict:
    draft = session.scalar(
        select(QualityGatePolicy)
        .where(QualityGatePolicy.status == "draft")
        .order_by(QualityGatePolicy.id.desc())
        .limit(1)
    )
    version = draft.policy_version if draft is not None else next_policy_version(session)
    candidate = {**configuration, "policy_version": version}
    policy = GatePolicy.from_dict(candidate)
    if draft is None:
        draft = QualityGatePolicy(
            policy_version=version,
            status="draft",
            configuration=policy.to_dict(),
            change_note=change_note.strip() or None,
            created_by=actor[:100],
        )
        session.add(draft)
    else:
        draft.configuration = policy.to_dict()
        draft.change_note = change_note.strip() or None
        draft.created_by = actor[:100]
        draft.preview_summary = None
        draft.previewed_at = None
    session.commit()
    return gate_settings(session)


def _preview_rows(session: Session, limit: int):
    return session.execute(
        select(Job, Company, City, RecruitmentType, JobSource)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(City, City.id == Job.city_id)
        .outerjoin(RecruitmentType, RecruitmentType.id == Job.recruitment_type_id)
        .join(JobSource, JobSource.job_id == Job.id)
        .order_by(Job.last_seen_at.desc(), Job.id.desc(), JobSource.id.asc())
        .limit(limit)
    ).all()


def preview_draft(session: Session, sample_limit: int = 500) -> dict:
    draft = session.scalar(
        select(QualityGatePolicy)
        .where(QualityGatePolicy.status == "draft")
        .order_by(QualityGatePolicy.id.desc())
        .limit(1)
    )
    if draft is None:
        raise LookupError("请先保存准入标准草稿")
    policy = GatePolicy.from_dict(draft.configuration)
    gate = JobQualityGate(policy)
    rows = _preview_rows(session, sample_limit)
    job_ids = {job.id for job, *_ in rows}
    skills: dict[int, list[str]] = {job_id: [] for job_id in job_ids}
    if job_ids:
        for job_id, name in session.execute(
            select(JobSkill.job_id, Skill.name)
            .join(Skill, Skill.id == JobSkill.skill_id)
            .where(JobSkill.job_id.in_(job_ids))
        ):
            skills[job_id].append(name)
    decisions: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    seen_jobs: set[int] = set()
    for job, company, city, recruitment, source in rows:
        if job.id in seen_jobs:
            continue
        seen_jobs.add(job.id)
        result = gate.evaluate(
            JobGateCandidate(
                payload={
                    "title": job.title,
                    "normalized_title": job.normalized_title,
                    "city": city.name if city else None,
                    "location_text": job.location_text,
                    "job_description": job.description,
                    "job_requirements": job.requirements,
                    "employment_type": recruitment.name if recruitment else None,
                    "is_campus": bool(recruitment and recruitment.code == "campus"),
                    "is_intern": bool(recruitment and recruitment.code == "internship"),
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "salary_unit": job.salary_period,
                    "salary_months": job.salary_months,
                    "salary_currency": job.salary_currency,
                    "skill_tags": skills.get(job.id, []),
                    "published_at": job.published_at,
                    "first_seen_at": job.first_seen_at,
                    "last_seen_at": job.last_seen_at,
                    "status": job.status,
                },
                company_name=company.name,
                source_url=source.source_url,
                content_hash=source.content_hash,
                observed_at=source.last_seen_at,
                provenance_type=(
                    "live_raw" if source.provenance_type == "live_raw" else "legacy_staging"
                ),
            )
        )
        decisions[result.decision] += 1
        if not result.accepted:
            reasons.update(result.reason_codes)
    total = len(seen_jobs)
    summary = {
        "sample_size": total,
        "accepted": decisions["accepted"],
        "quarantined": decisions["quarantined"],
        "acceptance_rate": round(decisions["accepted"] / total, 4) if total else 0,
        "top_reasons": [
            {"code": code, "count": count}
            for code, count in reasons.most_common(8)
        ],
    }
    draft.preview_summary = summary
    draft.previewed_at = utc_now_naive()
    session.commit()
    return gate_settings(session)


def publish_draft(session: Session, actor: str) -> dict:
    draft = session.scalar(
        select(QualityGatePolicy)
        .where(QualityGatePolicy.status == "draft")
        .order_by(QualityGatePolicy.id.desc())
        .limit(1)
    )
    if draft is None:
        raise LookupError("没有可发布的准入标准草稿")
    if draft.previewed_at is None or draft.preview_summary is None:
        raise ValueError("发布前必须先完成影响预检")
    GatePolicy.from_dict(draft.configuration)
    for active in session.scalars(
        select(QualityGatePolicy).where(QualityGatePolicy.status == "active")
    ):
        active.status = "archived"
    draft.status = "active"
    draft.published_by = actor[:100]
    draft.published_at = utc_now_naive()
    session.commit()
    return gate_settings(session)
