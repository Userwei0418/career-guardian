from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_data.detail_content import html_to_detail_text, split_detail_sections
from market_data.models.raw import DataSource, RawProcessingAttempt, RawRecord


PROCESSING_VERSION = "raw-processing-v1"
SEMANTIC_PROMPT_VERSION = "market-detail-evidence-v1"

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SemanticNormalizationResult:
    responsibilities: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    skill_tags: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    prompt_version: str = SEMANTIC_PROMPT_VERSION


class SemanticNormalizer(Protocol):
    def normalize(
        self, *, text: str, title: str | None, company_name: str | None, source_code: str
    ) -> SemanticNormalizationResult: ...


class BackendSemanticNormalizer:
    def __init__(self, endpoint: str, token: str, timeout_seconds: float = 35.0):
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = timeout_seconds

    def normalize(
        self, *, text: str, title: str | None, company_name: str | None, source_code: str
    ) -> SemanticNormalizationResult:
        response = httpx.post(
            self.endpoint,
            headers={"X-Market-Admin-Token": self.token},
            json={
                "text": text[:20_000],
                "title": title,
                "company_name": company_name,
                "source_code": source_code,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return SemanticNormalizationResult(
            responsibilities=tuple(str(item) for item in payload.get("responsibilities", [])),
            requirements=tuple(str(item) for item in payload.get("requirements", [])),
            skill_tags=tuple(str(item) for item in payload.get("skill_tags", [])),
            provider=payload.get("provider"),
            model=payload.get("model"),
            prompt_version=str(payload.get("prompt_version") or SEMANTIC_PROMPT_VERSION),
        )


def _source_supported(value: str, source_text: str) -> bool:
    compact_value = re.sub(r"\s+", "", value)
    compact_source = re.sub(r"\s+", "", source_text)
    return bool(compact_value) and compact_value in compact_source


def _derive_school_employer(title: str) -> str:
    """Conservatively recover an employer explicitly present in an announcement title."""

    text = _clean_text(title)
    if not text:
        return ""
    for separator in ("---", "——", "|", "｜"):
        if separator in text:
            text = text.split(separator)[-1].strip()
    text = re.sub(r"^[【\[].*?[】\]]\s*", "", text)
    text = re.sub(r"^(?:招聘信息|招聘公告|宣讲会|空中宣讲会)\s*[:：-]?\s*", "", text)
    match = re.match(
        r"(?P<company>.{2,80}?)(?:20\d{2}(?:届)?|校园招聘|社会招聘|招聘|招募|宣讲)",
        text,
    )
    if not match:
        return ""
    company = re.sub(r"\s+", " ", match.group("company")).strip(" -—_:：，,。")
    if not company or company in {"春季", "秋季", "春招", "秋招", "校园"}:
        return ""
    return company


def _new_attempt(
    session: Session,
    raw: RawRecord,
    *,
    stage: str,
    status: str,
    processor_type: str,
    input_hash: str | None,
    output_hash: str | None = None,
    reason_codes: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> RawProcessingAttempt:
    attempt_no = int(
        session.scalar(
            select(func.count())
            .select_from(RawProcessingAttempt)
            .where(RawProcessingAttempt.raw_record_id == raw.id)
        )
        or 0
    ) + 1
    now = _now()
    attempt = RawProcessingAttempt(
        raw_record_id=raw.id,
        crawl_task_id=raw.crawl_task_id,
        source_id=raw.source_id,
        stage=stage,
        status=status,
        attempt_no=attempt_no,
        processor_type=processor_type,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_hash=input_hash,
        output_hash=output_hash,
        reason_codes=reason_codes or [],
        metrics=metrics or {},
        started_at=now,
        completed_at=now,
    )
    session.add(attempt)
    raw.processing_attempts = attempt_no
    return attempt


def prepare_raw_candidate(
    session: Session,
    source: DataSource,
    raw: RawRecord,
    semantic_normalizer: SemanticNormalizer | None = None,
) -> dict[str, Any]:
    """Prepare a source-grounded payload and persist every processing decision."""

    if not isinstance(raw.raw_payload, dict):
        raw.processing_status = "failed"
        raw.processing_version = PROCESSING_VERSION
        _new_attempt(
            session,
            raw,
            stage="deterministic_normalization",
            status="failed",
            processor_type="deterministic",
            input_hash=_hash(raw.raw_payload),
            reason_codes=["structured_raw_payload_required"],
        )
        session.commit()
        raise ValueError("structured_raw_payload_required")

    normalized = dict(raw.raw_payload)
    if source.source_kind == "school_announcement" and not any(
        _clean_text(normalized.get(key))
        for key in ("hd_company", "company_name", "employer_name")
    ):
        derived_company = _derive_school_employer(
            _clean_text(normalized.get("announcement_name") or normalized.get("title"))
        )
        if derived_company:
            normalized["_derived_company_name"] = derived_company
    source_detail = _clean_text(
        normalized.get("_detail_text")
        or normalized.get("job_description")
        or normalized.get("description")
        or ""
    )
    detail_source = "structured_payload"
    if not source_detail and raw.raw_text:
        source_detail = html_to_detail_text(raw.raw_text)
        detail_source = "rendered_html_fallback"
    if source_detail:
        normalized["_detail_text"] = source_detail
    sections = split_detail_sections(source_detail)
    added_fields: list[str] = []
    for key in ("responsibilities", "requirements", "benefits"):
        existing = _clean_text(normalized.get(key))
        if existing:
            normalized[key] = existing
        elif sections.get(key):
            normalized[key] = sections[key]
            added_fields.append(key)
    if source_detail and not _clean_text(normalized.get("description")):
        normalized["description"] = source_detail
        added_fields.append("description")
    _new_attempt(
        session,
        raw,
        stage="deterministic_normalization",
        status="succeeded",
        processor_type="deterministic",
        input_hash=_hash(raw.raw_payload),
        output_hash=_hash(normalized),
        metrics={
            "source_chars": len(source_detail),
            "source": detail_source,
            "fields_added": added_fields,
        },
    )

    semantic_config = (source.config or {}).get("semantic_cleaning") or {}
    semantic_enabled = bool(semantic_config.get("enabled", True))
    needs_semantic = bool(
        source_detail
        and semantic_enabled
        and (
            not _clean_text(normalized.get("responsibilities"))
            or not _clean_text(normalized.get("requirements"))
        )
    )
    if needs_semantic and semantic_normalizer is not None:
        try:
            result = semantic_normalizer.normalize(
                text=source_detail,
                title=_clean_text(normalized.get("title") or normalized.get("announcement_name")) or None,
                company_name=None,
                source_code=source.code,
            )
            rejected = 0
            accepted_fields: list[str] = []
            for key, values in (
                ("responsibilities", result.responsibilities),
                ("requirements", result.requirements),
            ):
                supported = [_clean_text(item) for item in values if _source_supported(item, source_detail)]
                rejected += len(values) - len(supported)
                if supported and not _clean_text(normalized.get(key)):
                    normalized[key] = "\n".join(supported)
                    accepted_fields.append(key)
            supported_skills = [
                _clean_text(item) for item in result.skill_tags if _source_supported(item, source_detail)
            ]
            rejected += len(result.skill_tags) - len(supported_skills)
            if supported_skills and not normalized.get("skill_tags"):
                normalized["skill_tags"] = supported_skills
                accepted_fields.append("skill_tags")
            _new_attempt(
                session,
                raw,
                stage="semantic_normalization",
                status="succeeded" if accepted_fields else "skipped",
                processor_type="llm",
                input_hash=_hash(source_detail),
                output_hash=_hash({key: normalized.get(key) for key in accepted_fields}),
                reason_codes=(
                    ["deterministic_fields_incomplete", "unsupported_ai_evidence_rejected"]
                    if rejected
                    else ["deterministic_fields_incomplete"]
                ),
                metrics={
                    "accepted_fields": accepted_fields,
                    "rejected_items": rejected,
                    "source": detail_source,
                },
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
            )
        except Exception as exc:
            _new_attempt(
                session,
                raw,
                stage="semantic_normalization",
                status="failed",
                processor_type="llm",
                input_hash=_hash(source_detail),
                reason_codes=[
                    "deterministic_fields_incomplete",
                    "semantic_normalizer_unavailable",
                    type(exc).__name__,
                ],
                prompt_version=SEMANTIC_PROMPT_VERSION,
            )
    else:
        reasons = []
        if not source_detail:
            reasons.append("source_detail_missing")
        elif not needs_semantic:
            reasons.append("deterministic_result_sufficient")
        elif semantic_normalizer is None:
            reasons.append("semantic_normalizer_not_configured")
        _new_attempt(
            session,
            raw,
            stage="semantic_normalization",
            status="skipped",
            processor_type="llm",
            input_hash=_hash(source_detail) if source_detail else None,
            reason_codes=reasons,
            prompt_version=SEMANTIC_PROMPT_VERSION,
        )

    meaningful = "\n".join(
        _clean_text(normalized.get(key))
        for key in ("description", "responsibilities", "requirements")
        if _clean_text(normalized.get(key))
    )
    post_reasons = [] if meaningful else ["source_detail_missing"]
    _new_attempt(
        session,
        raw,
        stage="post_validation",
        status="succeeded" if meaningful else "failed",
        processor_type="deterministic",
        input_hash=_hash(normalized),
        output_hash=_hash(normalized),
        reason_codes=post_reasons,
        metrics={"meaningful_detail_chars": len(meaningful)},
    )
    raw.normalized_payload = normalized
    raw.processing_status = "prepared" if meaningful else "insufficient_source_detail"
    raw.processing_version = PROCESSING_VERSION
    session.commit()
    return normalized


def record_gate_attempt(
    session: Session,
    raw: RawRecord,
    *,
    accepted: bool,
    reason_codes: list[str] | None = None,
) -> None:
    _new_attempt(
        session,
        raw,
        stage="quality_gate",
        status="succeeded" if accepted else "quarantined",
        processor_type="gate",
        input_hash=_hash(raw.normalized_payload or raw.raw_payload),
        reason_codes=reason_codes or [],
        metrics={"decision": "promoted" if accepted else "quarantined"},
    )
    raw.processing_status = "promoted" if accepted else "quarantined"
    session.commit()
