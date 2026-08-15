from __future__ import annotations

import hashlib
import json
from collections import Counter

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from market_data.models.core import (
    City,
    Company,
    CorePromotionBatch,
    Job,
    JobFamily,
    JobSkill,
    JobSource,
    RecruitmentType,
    RejectedLegacyJob,
    Skill,
)
from market_data.models.staging import (
    LegacyCompanyRecord,
    LegacyImportBatch,
    LegacyJobRecord,
    LegacyJobSourceRecord,
)
from market_data.quality_gate import (
    JobGateCandidate,
    JobQualityGate,
    normalized_key,
    normalized_text,
    resolve_salary,
    utc_now_naive,
    valid_url,
)


JOB_GATE = JobQualityGate()
PIPELINE_VERSION = JOB_GATE.policy.policy_version


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reconcile_promotion_counts(
    staging_session: Session,
    core_session: Session,
    staging_batch_id: int,
    promotion: CorePromotionBatch,
) -> CorePromotionBatch:
    staging_ids = set(
        staging_session.scalars(
            select(LegacyJobRecord.legacy_job_id).where(
                LegacyJobRecord.batch_id == staging_batch_id
            )
        )
    )
    core_rows = core_session.execute(
        select(Job.legacy_job_id, Job.quality_grade).where(Job.legacy_job_id.is_not(None))
    ).all()
    promoted_rows = [(legacy_id, grade) for legacy_id, grade in core_rows if legacy_id in staging_ids]
    rejected_ids = set(
        core_session.scalars(
            select(RejectedLegacyJob.legacy_job_id).where(
                RejectedLegacyJob.promotion_batch_id == promotion.id
            )
        )
    )
    grade_counts = Counter(grade for _, grade in promoted_rows)
    promotion.promoted_count = len(promoted_rows)
    promotion.rejected_count = len(rejected_ids)
    promotion.duplicate_count = max(
        len(staging_ids) - promotion.promoted_count - promotion.rejected_count,
        0,
    )
    pipeline_summary = {
        key: value
        for key, value in (promotion.summary or {}).items()
        if key.startswith("salary_") or key.startswith("gate_")
    }
    promotion.summary = {
        "promoted": promotion.promoted_count,
        "rejected": promotion.rejected_count,
        "duplicate": promotion.duplicate_count,
        **{f"grade_{grade}": count for grade, count in sorted(grade_counts.items())},
        **pipeline_summary,
        "reconciled_from_final_state": True,
    }
    core_session.commit()
    core_session.refresh(promotion)
    return promotion


def recertify_promoted_jobs(
    staging_session: Session,
    core_session: Session,
    staging_batch_id: int,
    promotion: CorePromotionBatch,
) -> None:
    core_by_legacy_id = {
        legacy_id: (job_id, company_name, source_url, content_hash, last_seen_at)
        for job_id, legacy_id, company_name, source_url, content_hash, last_seen_at in core_session.execute(
            select(
                Job.id,
                Job.legacy_job_id,
                Company.name,
                JobSource.source_url,
                JobSource.content_hash,
                JobSource.last_seen_at,
            )
            .join(Company, Company.id == Job.company_id)
            .join(JobSource, JobSource.job_id == Job.id)
            .where(Job.legacy_job_id.is_not(None))
        )
    }
    updates: list[dict] = []
    quarantined_job_ids: list[int] = []
    gate_stats: Counter[str] = Counter()
    rows = staging_session.execute(
        select(LegacyJobRecord.legacy_job_id, LegacyJobRecord.legacy_payload).where(
            LegacyJobRecord.batch_id == staging_batch_id
        )
    ).yield_per(1000)
    for legacy_job_id, payload in rows:
        current = core_by_legacy_id.get(legacy_job_id)
        if current is None:
            continue
        job_id, company_name, source_url, content_hash, last_seen_at = current
        gate = JOB_GATE.evaluate(
            JobGateCandidate(
                payload=payload,
                company_name=company_name,
                source_url=source_url,
                content_hash=content_hash,
                observed_at=last_seen_at,
                provenance_type="legacy_staging",
            )
        )
        if not gate.accepted:
            quarantined_job_ids.append(job_id)
            core_session.add(
                RejectedLegacyJob(
                    promotion_batch_id=promotion.id,
                    legacy_job_id=legacy_job_id,
                    quality_score=gate.score,
                    decision=gate.decision,
                    policy_version=gate.policy_version,
                    reason_codes=list(gate.reason_codes),
                )
            )
            gate_stats["gate_quarantined"] += 1
            continue
        updates.append(
            {
                "id": job_id,
                "salary_min": gate.salary_min,
                "salary_max": gate.salary_max,
                "salary_period": gate.salary_period,
                "salary_months": gate.salary_months,
                "salary_currency": gate.salary_currency,
                "status": gate.status,
                "quality_score": gate.score,
                "quality_grade": gate.grade,
                "quality_reasons": list(gate.reason_codes),
                "gate_policy_version": gate.policy_version,
                "gate_evaluated_at": gate.evaluated_at,
            }
        )
        gate_stats["gate_accepted"] += 1
        gate_stats[
            "salary_valid" if gate.salary_min is not None else "salary_unknown"
        ] += 1
        for reason in gate.reason_codes:
            if reason.startswith("salary_"):
                gate_stats[reason] += 1
        if len(updates) >= 500:
            core_session.bulk_update_mappings(Job, updates)
            core_session.commit()
            updates.clear()
    if updates:
        core_session.bulk_update_mappings(Job, updates)
        core_session.commit()
    if quarantined_job_ids:
        for offset in range(0, len(quarantined_job_ids), 500):
            core_session.execute(
                delete(Job).where(Job.id.in_(quarantined_job_ids[offset : offset + 500]))
            )
            core_session.commit()
    promotion.pipeline_version = PIPELINE_VERSION
    promotion.summary = {**(promotion.summary or {}), **dict(gate_stats)}
    core_session.commit()


def promote_legacy_batch(
    staging_session: Session,
    core_session: Session,
    staging_batch_id: int,
    chunk_size: int = 500,
) -> CorePromotionBatch:
    staging_batch = staging_session.get(LegacyImportBatch, staging_batch_id)
    if staging_batch is None or staging_batch.status != "completed":
        raise RuntimeError("staging batch is missing or incomplete")
    existing = core_session.scalar(
        select(CorePromotionBatch).where(CorePromotionBatch.staging_batch_id == staging_batch_id)
    )
    if existing is not None:
        if existing.status == "completed":
            if existing.pipeline_version != PIPELINE_VERSION:
                recertify_promoted_jobs(
                    staging_session, core_session, staging_batch_id, existing
                )
            return reconcile_promotion_counts(
                staging_session, core_session, staging_batch_id, existing
            )
        if existing.status != "failed":
            raise RuntimeError(f"staging batch has an active core batch {existing.id}")
        promotion = existing
        promotion.status = "running"
        promotion.error_message = None
        promotion.completed_at = None
    else:
        promotion = CorePromotionBatch(
            staging_batch_id=staging_batch_id,
            pipeline_version=PIPELINE_VERSION,
            status="running",
        )
        core_session.add(promotion)
    core_session.commit()

    company_rows = staging_session.scalars(
        select(LegacyCompanyRecord).where(LegacyCompanyRecord.batch_id == staging_batch_id)
    ).all()
    legacy_companies = {row.legacy_company_id: row for row in company_rows}

    companies = {
        normalized_key(row.normalized_name or row.name): row
        for row in core_session.scalars(select(Company)).all()
    }
    cities = {row.name: row for row in core_session.scalars(select(City)).all()}
    families = {row.code: row for row in core_session.scalars(select(JobFamily)).all()}
    recruitments = {row.code: row for row in core_session.scalars(select(RecruitmentType)).all()}
    skills = {normalized_key(row.name): row for row in core_session.scalars(select(Skill)).all()}
    identities = set(core_session.scalars(select(Job.identity_key)))
    stats: Counter[str] = Counter(
        {
            "promoted": promotion.promoted_count,
            "rejected": promotion.rejected_count,
            "duplicate": promotion.duplicate_count,
        }
    )
    promoted_legacy_ids = set(
        core_session.scalars(select(Job.legacy_job_id).where(Job.legacy_job_id.is_not(None)))
    )
    rejected_legacy_ids = set(
        core_session.scalars(
            select(RejectedLegacyJob.legacy_job_id).where(
                RejectedLegacyJob.promotion_batch_id == promotion.id
            )
        )
    )
    last_staging_id = 0

    def get_legacy_company(legacy_id: int | None) -> tuple[LegacyCompanyRecord | None, str]:
        legacy = legacy_companies.get(legacy_id or 0)
        if legacy is None:
            return None, ""
        name = normalized_text(legacy.name)
        return legacy, name

    def get_or_create_company(legacy: LegacyCompanyRecord, name: str) -> Company:
        key = normalized_key(name)
        company = companies.get(key)
        if company is None:
            payload = legacy.legacy_payload
            company = Company(
                name=name[:255],
                normalized_name=key[:255],
                legacy_company_id=legacy.legacy_company_id,
                alias_name=normalized_text(payload.get("alias_name"))[:255] or None,
                short_name=normalized_text(payload.get("short_name"))[:100] or None,
                website_url=valid_url(payload.get("website_url")),
                career_page_url=valid_url(payload.get("career_page_url")),
                industry=normalized_text(payload.get("industry"))[:100] or None,
                company_type=normalized_text(payload.get("company_type"))[:100] or None,
                size_range=normalized_text(payload.get("size_range"))[:100] or None,
                headquarters=normalized_text(payload.get("headquarters"))[:255] or None,
                description=normalized_text(payload.get("description")) or None,
                status="active" if legacy.status != 0 else "inactive",
            )
            core_session.add(company)
            core_session.flush()
            companies[key] = company
        return company

    try:
        while True:
            source_min = (
                select(
                    LegacyJobSourceRecord.legacy_job_id,
                    func.min(LegacyJobSourceRecord.id).label("source_row_id"),
                )
                .where(LegacyJobSourceRecord.batch_id == staging_batch_id)
                .group_by(LegacyJobSourceRecord.legacy_job_id)
                .subquery()
            )
            rows = staging_session.execute(
                select(LegacyJobRecord, LegacyJobSourceRecord)
                .outerjoin(source_min, source_min.c.legacy_job_id == LegacyJobRecord.legacy_job_id)
                .outerjoin(LegacyJobSourceRecord, LegacyJobSourceRecord.id == source_min.c.source_row_id)
                .where(
                    LegacyJobRecord.batch_id == staging_batch_id,
                    LegacyJobRecord.id > last_staging_id,
                )
                .order_by(LegacyJobRecord.id)
                .limit(chunk_size)
            ).all()
            if not rows:
                break

            for legacy_job, legacy_source in rows:
                last_staging_id = legacy_job.id
                if legacy_job.legacy_job_id in promoted_legacy_ids or (
                    legacy_job.legacy_job_id in rejected_legacy_ids
                ):
                    continue
                payload = legacy_job.legacy_payload
                legacy_company, company_name = get_legacy_company(legacy_job.company_id)
                source_payload = legacy_source.legacy_payload if legacy_source else {}
                source_url = valid_url(
                    source_payload.get("source_url"),
                    payload.get("detail_url"),
                    payload.get("apply_url"),
                )
                content_hash = hash_value(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
                )
                gate = JOB_GATE.evaluate(
                    JobGateCandidate(
                        payload=payload,
                        company_name=company_name,
                        source_url=source_url,
                        content_hash=content_hash,
                        observed_at=(
                            legacy_source.last_seen_at
                            if legacy_source
                            else legacy_job.published_at
                        ),
                        provenance_type="legacy_staging",
                    )
                )
                if legacy_company is None or not gate.accepted:
                    rejection_reasons = list(gate.reason_codes)
                    if legacy_company is None:
                        rejection_reasons.append("company_unresolved")
                    core_session.add(
                        RejectedLegacyJob(
                            promotion_batch_id=promotion.id,
                            legacy_job_id=legacy_job.legacy_job_id,
                            quality_score=gate.score,
                            decision="quarantined",
                            policy_version=gate.policy_version,
                            reason_codes=sorted(set(rejection_reasons)),
                        )
                    )
                    stats["rejected"] += 1
                    continue

                company = get_or_create_company(legacy_company, gate.company_name)
                city_name = gate.city_name
                city = None
                if city_name:
                    city = cities.get(city_name)
                    if city is None:
                        city = City(
                            code=f"city-{hash_value(city_name)[:16]}",
                            name=city_name,
                            province=normalized_text(payload.get("province"))[:100] or None,
                            version=PIPELINE_VERSION,
                        )
                        core_session.add(city)
                        core_session.flush()
                        cities[city_name] = city

                family = families.get(gate.family_code)
                if family is None:
                    family = JobFamily(
                        code=gate.family_code,
                        name=gate.family_name,
                        version=gate.policy_version,
                    )
                    core_session.add(family)
                    core_session.flush()
                    families[gate.family_code] = family

                recruitment = recruitments.get(gate.recruitment_code)
                if recruitment is None:
                    recruitment = RecruitmentType(
                        code=gate.recruitment_code,
                        name=gate.recruitment_name,
                        version=gate.policy_version,
                    )
                    core_session.add(recruitment)
                    core_session.flush()
                    recruitments[gate.recruitment_code] = recruitment

                if gate.identity_key in identities:
                    stats["duplicate"] += 1
                    continue

                job = Job(
                    company_id=company.id,
                    identity_key=gate.identity_key,
                    legacy_job_id=legacy_job.legacy_job_id,
                    title=gate.title,
                    normalized_title=gate.normalized_title,
                    job_family_id=family.id,
                    city_id=city.id if city else None,
                    recruitment_type_id=recruitment.id,
                    location_text=gate.location_text,
                    description=gate.description,
                    requirements=gate.requirements,
                    salary_min=gate.salary_min,
                    salary_max=gate.salary_max,
                    salary_period=gate.salary_period,
                    salary_months=gate.salary_months,
                    salary_currency=gate.salary_currency,
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
                core_session.add(job)
                core_session.flush()
                core_session.add(
                    JobSource(
                        job_id=job.id,
                        provenance_type="legacy_staging",
                        legacy_source_record_id=legacy_source.id if legacy_source else None,
                        source_job_id=(legacy_source.source_job_id if legacy_source else legacy_job.source_job_id),
                        source_url=gate.source_url,
                        content_hash=gate.content_hash,
                        fetched_at=gate.last_seen_at,
                        published_at=gate.published_at,
                        first_seen_at=gate.first_seen_at,
                        last_seen_at=gate.last_seen_at,
                        is_official=bool(source_payload.get("is_official", True)),
                    )
                )

                job_skill_ids: set[int] = set()
                for skill_name in gate.skills[:30]:
                    skill_key = normalized_key(skill_name)
                    if not skill_key:
                        continue
                    skill = skills.get(skill_key)
                    if skill is None:
                        skill = Skill(
                            code=f"skill-{hash_value(skill_key)[:20]}",
                            name=skill_name[:100],
                            aliases=[],
                            version=PIPELINE_VERSION,
                        )
                        core_session.add(skill)
                        core_session.flush()
                        skills[skill_key] = skill
                    if skill.id in job_skill_ids:
                        continue
                    core_session.add(JobSkill(job_id=job.id, skill_id=skill.id))
                    job_skill_ids.add(skill.id)
                identities.add(gate.identity_key)
                promoted_legacy_ids.add(legacy_job.legacy_job_id)
                stats["promoted"] += 1
                stats[f"grade_{gate.grade}"] += 1

            promotion.promoted_count = stats["promoted"]
            promotion.rejected_count = stats["rejected"]
            promotion.duplicate_count = stats["duplicate"]
            core_session.commit()

        promotion.status = "completed"
        promotion.summary = dict(stats)
        promotion.completed_at = utc_now_naive()
        core_session.commit()
        return reconcile_promotion_counts(
            staging_session, core_session, staging_batch_id, promotion
        )
    except Exception as exc:
        core_session.rollback()
        failed = core_session.get(CorePromotionBatch, promotion.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            failed.completed_at = utc_now_naive()
            core_session.commit()
        raise
