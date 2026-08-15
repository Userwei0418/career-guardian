from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.models.core import Company, Job, JobSource
from market_data.schemas import CorePromotionInput


def promote_validated_job(session: Session, payload: CorePromotionInput) -> Job:
    """Explicit Raw-to-Core boundary. FP-03 will own normalization and quality gates."""

    normalized_company = " ".join(payload.company_name.lower().split())
    company = session.scalar(
        select(Company).where(Company.normalized_name == normalized_company)
    )
    if company is None:
        company = Company(
            name=payload.company_name.strip(),
            normalized_name=normalized_company,
            website_url=payload.company_website_url,
        )
        session.add(company)
        session.flush()

    job = Job(
        company_id=company.id,
        title=payload.title.strip(),
        normalized_title=payload.normalized_title,
        location_text=payload.location_text,
        description=payload.description,
        requirements=payload.requirements,
        published_at=payload.published_at,
        first_seen_at=payload.first_seen_at,
        last_seen_at=payload.last_seen_at,
    )
    session.add(job)
    session.flush()
    session.add(
        JobSource(
            job_id=job.id,
            data_source_id=payload.data_source_id,
            raw_record_id=payload.raw_record_id,
            source_job_id=payload.source_job_id,
            source_url=str(payload.source_url),
            content_hash=payload.content_hash,
            fetched_at=payload.fetched_at,
            published_at=payload.published_at,
            first_seen_at=payload.first_seen_at,
            last_seen_at=payload.last_seen_at,
        )
    )
    session.commit()
    session.refresh(job)
    return job
