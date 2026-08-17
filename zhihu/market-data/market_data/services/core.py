from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.errors import QualityGateError
from market_data.models.core import (
    City,
    Company,
    Job,
    JobFamily,
    JobSkill,
    JobSource,
    RecruitmentType,
    Skill,
)
from market_data.models.raw import RawRecord
from market_data.quality_gate import JobGateCandidate, JobQualityGate, normalized_key
from market_data.schemas import CorePromotionInput
from market_data.services.gate_policy import active_gate_policy


def promote_validated_job(session: Session, payload: CorePromotionInput) -> Job:
    """The only Raw-to-Core write boundary; every candidate passes the shared gate."""

    candidate_payload = {
        "title": payload.title,
        "normalized_title": payload.normalized_title,
        "city": payload.city,
        "location_text": payload.location_text,
        "job_description": payload.description,
        "job_requirements": payload.requirements,
        "job_responsibilities": payload.responsibilities,
        "job_category": payload.job_category,
        "employment_type": payload.employment_type,
        "is_campus": payload.is_campus,
        "is_intern": payload.is_intern,
        "salary_text": payload.salary_text,
        "salary_min": payload.salary_min,
        "salary_max": payload.salary_max,
        "salary_unit": payload.salary_unit,
        "salary_months": payload.salary_months,
        "salary_currency": payload.salary_currency,
        "skill_tags": payload.skill_tags,
        "published_at": payload.published_at,
        "deadline_at": payload.deadline_at,
        "first_seen_at": payload.first_seen_at,
        "last_seen_at": payload.last_seen_at,
        "status": payload.status,
    }
    gate = JobQualityGate(active_gate_policy(session)).evaluate(
        JobGateCandidate(
            payload=candidate_payload,
            company_name=payload.company_name,
            source_url=str(payload.source_url),
            content_hash=payload.content_hash,
            observed_at=payload.last_seen_at,
            provenance_type="live_raw",
        )
    )
    if not gate.accepted:
        raise QualityGateError(gate.reason_codes)

    normalized_company = normalized_key(gate.company_name)
    company = session.scalar(
        select(Company).where(Company.normalized_name == normalized_company)
    )
    if company is None:
        company = Company(
            name=gate.company_name,
            normalized_name=normalized_company,
            website_url=payload.company_website_url,
        )
        session.add(company)
        session.flush()

    existing = session.scalar(select(Job).where(Job.identity_key == gate.identity_key))
    if existing is not None:
        lineage = session.scalar(
            select(JobSource).where(
                JobSource.job_id == existing.id,
                JobSource.raw_record_id == payload.raw_record_id,
                JobSource.data_source_id == payload.data_source_id,
            )
        )
        if lineage is None:
            session.add(
                JobSource(
                    job_id=existing.id,
                    provenance_type="live_raw",
                    data_source_id=payload.data_source_id,
                    raw_record_id=payload.raw_record_id,
                    source_job_id=payload.source_job_id,
                    source_url=gate.source_url,
                    content_hash=gate.content_hash,
                    fetched_at=payload.fetched_at,
                    published_at=gate.published_at,
                    first_seen_at=gate.first_seen_at,
                    last_seen_at=gate.last_seen_at,
                )
            )
            session.commit()
        return existing

    city = None
    if gate.city_name:
        city = session.scalar(select(City).where(City.name == gate.city_name))
        if city is None:
            city = City(
                code=f"city-{hashlib.sha256(gate.city_name.encode()).hexdigest()[:16]}",
                name=gate.city_name,
                version=gate.policy_version,
            )
            session.add(city)
            session.flush()
    family = session.scalar(select(JobFamily).where(JobFamily.code == gate.family_code))
    if family is None:
        family = JobFamily(
            code=gate.family_code, name=gate.family_name, version=gate.policy_version
        )
        session.add(family)
        session.flush()
    recruitment = session.scalar(
        select(RecruitmentType).where(RecruitmentType.code == gate.recruitment_code)
    )
    if recruitment is None:
        recruitment = RecruitmentType(
            code=gate.recruitment_code,
            name=gate.recruitment_name,
            version=gate.policy_version,
        )
        session.add(recruitment)
        session.flush()

    job = Job(
        company_id=company.id,
        identity_key=gate.identity_key,
        title=gate.title,
        normalized_title=gate.normalized_title,
        job_family_id=family.id,
        city_id=city.id if city else None,
        recruitment_type_id=recruitment.id,
        location_text=gate.location_text,
        department=payload.department,
        job_category=payload.job_category,
        employment_type=payload.employment_type,
        province=payload.province,
        district=payload.district,
        address=payload.address,
        education_requirement=payload.education_requirement,
        education_level=payload.education_level,
        experience_requirement=payload.experience_requirement,
        experience_min_months=payload.experience_min_months,
        experience_max_months=payload.experience_max_months,
        description=gate.description,
        requirements=gate.requirements,
        responsibilities=payload.responsibilities,
        benefits=payload.benefits,
        major_requirement=payload.major_requirement,
        language_requirement=payload.language_requirement,
        certificate_requirement=payload.certificate_requirement,
        work_time=payload.work_time,
        salary_payment=payload.salary_payment,
        industry_requirement=payload.industry_requirement,
        job_level=payload.job_level,
        salary_min=gate.salary_min,
        salary_max=gate.salary_max,
        salary_period=gate.salary_period,
        salary_months=gate.salary_months,
        salary_currency=gate.salary_currency,
        apply_url=payload.apply_url,
        detail_url=payload.detail_url or gate.source_url,
        published_at=gate.published_at,
        first_seen_at=gate.first_seen_at,
        last_seen_at=gate.last_seen_at,
        status=gate.status,
        quality_score=gate.score,
        quality_grade=gate.grade,
        quality_reasons=list(gate.reason_codes),
        gate_policy_version=gate.policy_version,
        gate_evaluated_at=gate.evaluated_at,
    )
    session.add(job)
    session.flush()
    session.add(
        JobSource(
            job_id=job.id,
            provenance_type="live_raw",
            data_source_id=payload.data_source_id,
            raw_record_id=payload.raw_record_id,
            source_job_id=payload.source_job_id,
            source_url=gate.source_url,
            content_hash=gate.content_hash,
            fetched_at=payload.fetched_at,
            published_at=gate.published_at,
            first_seen_at=gate.first_seen_at,
            last_seen_at=gate.last_seen_at,
        )
    )
    for skill_name in gate.skills:
        skill_code = f"skill-{hashlib.sha256(normalized_key(skill_name).encode()).hexdigest()[:20]}"
        skill = session.scalar(select(Skill).where(Skill.code == skill_code))
        if skill is None:
            skill = Skill(
                code=skill_code,
                name=skill_name,
                aliases=[],
                version=gate.policy_version,
            )
            session.add(skill)
            session.flush()
        session.add(JobSkill(job_id=job.id, skill_id=skill.id))
    session.commit()
    session.refresh(job)
    return job


def promote_raw_candidate(
    raw_session: Session,
    core_session: Session,
    payload: CorePromotionInput,
) -> Job:
    """Audited Raw→Gate→Core state transition across isolated database domains."""

    raw = raw_session.get(RawRecord, payload.raw_record_id)
    lineage_matches = raw is not None and all(
        [
            raw.source_id == payload.data_source_id,
            raw.content_hash == payload.content_hash,
            raw.source_url == str(payload.source_url),
        ]
    )
    if not lineage_matches:
        if raw is not None:
            raw.validation_status = "quarantined"
            raw.validation_error = json.dumps(
                ["raw_lineage_mismatch"], ensure_ascii=False
            )
            raw_session.commit()
        raise QualityGateError(["raw_lineage_mismatch"])
    try:
        job = promote_validated_job(core_session, payload)
    except QualityGateError as exc:
        raw.validation_status = "quarantined"
        raw.validation_error = json.dumps(exc.reason_codes, ensure_ascii=False)
        raw_session.commit()
        raise
    raw.validation_status = "promoted"
    raw.validation_error = None
    raw_session.commit()
    return job
