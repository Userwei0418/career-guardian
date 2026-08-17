from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.utils import parse_datetime, value_at_path
from market_data.errors import QualityGateError
from market_data.models.raw import CrawlLogEntry, CrawlTask, DataSource, RawRecord
from market_data.schemas import CorePromotionInput
from market_data.services.core import promote_raw_candidate
from market_data.services.raw_processing import (
    SemanticNormalizer,
    prepare_raw_candidate,
    record_gate_attempt,
)


@dataclass(frozen=True)
class RawPromotionSummary:
    promoted: int = 0
    quarantined: int = 0


def _mapped_value(mapping: dict, field: str, payload: dict[str, Any]) -> Any:
    spec = mapping.get(field)
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError(f"mapping for {field} must be an object")
    if "literal" in spec:
        return spec["literal"]
    paths = spec.get("paths") or ([spec["path"]] if spec.get("path") else [])
    for path in paths:
        try:
            value = value_at_path(payload, str(path))
        except (KeyError, IndexError, TypeError):
            continue
        if value not in (None, "", []):
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("Name") or item.get("name") or item.get("Label") or item.get("label")
            if item not in (None, ""):
                parts.append(str(item).strip())
        return "、".join(part for part in parts if part) or None
    text = str(value).strip()
    return text or None


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "campus", "intern"}


def map_raw_record(source: DataSource, raw: RawRecord) -> CorePromotionInput:
    mapping = (source.config or {}).get("promotion_mapping")
    if not isinstance(mapping, dict):
        raise ValueError("promotion_mapping_missing")
    effective_payload = raw.normalized_payload or raw.raw_payload
    if not isinstance(effective_payload, dict):
        raise ValueError("structured_raw_payload_required")
    payload = effective_payload
    company_name = _text(_mapped_value(mapping, "company_name", payload))
    title = _text(_mapped_value(mapping, "title", payload))
    if not company_name or not title:
        raise ValueError("company_name_or_title_missing")
    skill_value = _mapped_value(mapping, "skill_tags", payload)
    skill_tags = []
    if isinstance(skill_value, list):
        skill_tags = [value for value in (_text(item) for item in skill_value) if value]
    elif _text(skill_value):
        skill_tags = [item.strip() for item in str(skill_value).replace("，", ",").split(",") if item.strip()]
    return CorePromotionInput(
        company_name=company_name,
        company_website_url=_text(_mapped_value(mapping, "company_website_url", payload)),
        title=title,
        normalized_title=_text(_mapped_value(mapping, "normalized_title", payload)),
        city=_text(_mapped_value(mapping, "city", payload)),
        location_text=_text(_mapped_value(mapping, "location_text", payload)),
        department=_text(_mapped_value(mapping, "department", payload)),
        province=_text(_mapped_value(mapping, "province", payload)),
        district=_text(_mapped_value(mapping, "district", payload)),
        address=_text(_mapped_value(mapping, "address", payload)),
        education_requirement=_text(_mapped_value(mapping, "education_requirement", payload)),
        education_level=_text(_mapped_value(mapping, "education_level", payload)),
        experience_requirement=_text(_mapped_value(mapping, "experience_requirement", payload)),
        experience_min_months=_integer(_mapped_value(mapping, "experience_min_months", payload)),
        experience_max_months=_integer(_mapped_value(mapping, "experience_max_months", payload)),
        description=_text(_mapped_value(mapping, "description", payload)),
        requirements=_text(_mapped_value(mapping, "requirements", payload)),
        responsibilities=_text(_mapped_value(mapping, "responsibilities", payload)),
        benefits=_text(_mapped_value(mapping, "benefits", payload)),
        major_requirement=_text(_mapped_value(mapping, "major_requirement", payload)),
        language_requirement=_text(_mapped_value(mapping, "language_requirement", payload)),
        certificate_requirement=_text(_mapped_value(mapping, "certificate_requirement", payload)),
        work_time=_text(_mapped_value(mapping, "work_time", payload)),
        salary_payment=_text(_mapped_value(mapping, "salary_payment", payload)),
        industry_requirement=_text(_mapped_value(mapping, "industry_requirement", payload)),
        job_level=_text(_mapped_value(mapping, "job_level", payload)),
        job_category=_text(_mapped_value(mapping, "job_category", payload)),
        employment_type=_text(_mapped_value(mapping, "employment_type", payload)),
        is_campus=_boolean(_mapped_value(mapping, "is_campus", payload)),
        is_intern=_boolean(_mapped_value(mapping, "is_intern", payload)),
        salary_text=_text(_mapped_value(mapping, "salary_text", payload)),
        salary_min=_integer(_mapped_value(mapping, "salary_min", payload)),
        salary_max=_integer(_mapped_value(mapping, "salary_max", payload)),
        salary_unit=_text(_mapped_value(mapping, "salary_unit", payload)),
        salary_months=_integer(_mapped_value(mapping, "salary_months", payload)),
        apply_url=_text(_mapped_value(mapping, "apply_url", payload)) or raw.source_url,
        detail_url=_text(_mapped_value(mapping, "detail_url", payload)) or raw.source_url,
        skill_tags=skill_tags,
        deadline_at=parse_datetime(_mapped_value(mapping, "deadline_at", payload)),
        published_at=parse_datetime(_mapped_value(mapping, "published_at", payload)) or raw.source_published_at,
        raw_record_id=raw.id,
        data_source_id=source.id,
        source_job_id=raw.external_id,
        source_url=raw.source_url,
        content_hash=raw.content_hash,
        fetched_at=raw.fetched_at,
        first_seen_at=raw.first_seen_at,
        last_seen_at=raw.last_seen_at,
    )


def promote_task_records(
    raw_session: Session,
    core_session: Session,
    source: DataSource,
    task_id: int,
    semantic_normalizer: SemanticNormalizer | None = None,
) -> RawPromotionSummary:
    task = raw_session.get(CrawlTask, task_id)
    if task is None:
        raise LookupError(f"unknown crawl task: {task_id}")
    records = list(
        raw_session.scalars(
            select(RawRecord)
            .where(
                RawRecord.source_id == source.id,
                RawRecord.crawl_task_id == task_id,
                RawRecord.validation_status == "pending_gate",
            )
            .order_by(RawRecord.id)
        )
    )
    promoted = 0
    quarantined = 0
    for raw in records:
        try:
            prepare_raw_candidate(raw_session, source, raw, semantic_normalizer)
            candidate = map_raw_record(source, raw)
            promote_raw_candidate(raw_session, core_session, candidate)
            record_gate_attempt(raw_session, raw, accepted=True)
            promoted += 1
        except QualityGateError as exc:
            record_gate_attempt(
                raw_session,
                raw,
                accepted=False,
                reason_codes=list(exc.reason_codes),
            )
            quarantined += 1
        except (TypeError, ValueError) as exc:
            raw.validation_status = "quarantined"
            raw.validation_error = json.dumps(
                ["candidate_mapping_invalid", str(exc)], ensure_ascii=False
            )
            raw_session.commit()
            record_gate_attempt(
                raw_session,
                raw,
                accepted=False,
                reason_codes=["candidate_mapping_invalid", str(exc)],
            )
            quarantined += 1
    raw_session.add(
        CrawlLogEntry(
            crawl_task_id=task_id,
            level="info" if quarantined == 0 else "warning",
            event_code="quality_gate_completed",
            message="new raw records passed through mapping and the quality gate",
            context={"promoted": promoted, "quarantined": quarantined},
        )
    )
    task.promoted_records = promoted
    task.quarantined_records = quarantined
    raw_session.commit()
    return RawPromotionSummary(promoted=promoted, quarantined=quarantined)
