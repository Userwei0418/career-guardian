from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Sequence

from fastapi import HTTPException
from sqlalchemy import func, or_, tuple_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.schemas.cashflow_import import (
    FinancialImportCandidateUpdate,
    FinancialImportConfirmRequest,
)
from app.services.cashflow_import_parser import (
    PARSER_VERSION,
    CashflowImportError,
    ImportTable,
    ParsedCandidate,
    build_candidate_fingerprint,
    duplicate_signatures_are_similar,
    duplicate_text_signature,
    duplicate_text_is_similar,
    parse_candidate_rows,
    read_import_table,
)
from app.services.cashflow_privacy import redact_cashflow_text
from app.services.cashflow_recognition_artifact_service import (
    CashflowRecognitionArtifactError,
    load_import_table_artifact,
    load_ocr_text_artifact,
    persist_import_table_artifacts,
    persist_ocr_text_artifact,
)
from app.services.cashflow_service import (
    get_available_category,
    lock_financial_ledger_owner,
    record_transaction_ledger_revision,
)
from app.services.economic_fact_service import sync_transaction_fact
from app.services.personal_attachment_service import (
    enqueue_attachment_cleanup,
    resolve_attachment_path,
)


ACTIONABLE_CANDIDATE_STATUSES = {
    "ready",
    "needs_review",
    "possible_duplicate",
    "invalid",
}
# Only unresolved rows that assert a complete-enough financial fact may be a
# duplicate baseline. Invalid rows are editable by the user, but they must not
# reserve an external key or fuzzy identity for later imports.
DUPLICATE_CLAIM_CANDIDATE_STATUSES = {
    "ready",
    "needs_review",
    "possible_duplicate",
}
FINAL_CANDIDATE_STATUSES = {"exact_duplicate", "excluded", "confirmed"}
EDITABLE_CANDIDATE_STATUSES = ACTIONABLE_CANDIDATE_STATUSES | {"excluded"}
SENSITIVE_HEADER_PATTERN = re.compile(
    r"(卡号|账号|账户号|银行卡|身份证|手机号|余额|交易单号|交易号|流水号|订单号|account)",
    re.I,
)
MAX_EXACT_FUZZY_BUCKET_SCAN = 100
MAX_TOTAL_FUZZY_ROWS = 5_000
SOURCE_ERROR_EDIT_FIELDS: dict[str, frozenset[str]] = {
    "DIRECTION_COLUMN_CONFLICT": frozenset({"direction"}),
    "DIRECTION_REQUIRED": frozenset({"direction"}),
    "SIGN_DIRECTION_CONFLICT": frozenset({"direction", "amount"}),
    "BOTH_SIDES_HAVE_AMOUNT": frozenset({"direction", "amount"}),
    "AMOUNT_INVALID": frozenset({"amount"}),
    "AMOUNT_NOT_POSITIVE": frozenset({"amount"}),
    "AMOUNT_TOO_LARGE": frozenset({"amount"}),
    "AMOUNT_SCALE": frozenset({"amount"}),
    "DATE_INVALID": frozenset({"transaction_date"}),
    "DATE_OUT_OF_RANGE": frozenset({"transaction_date"}),
}


@dataclass(frozen=True)
class _DuplicateBucketWatermark:
    count: int
    max_transaction_id: int

    def as_evidence(self) -> dict[str, int | str]:
        return {
            "scan_mode": "bounded_coarse_bucket",
            "count": self.count,
            "max_transaction_id": self.max_transaction_id,
        }


@dataclass(frozen=True)
class _SameSourceReplayDecision:
    strength: str
    transactions: tuple[FinancialTransaction, ...]
    source_batch_ids: tuple[int, ...]
    reason_code: str
    reason: str


_REPLAY_UNCERTAIN_DATE_CODES = {
    "DATE_CONTEXT_INHERITED",
    "DATE_INVALID",
    "DATE_OUT_OF_RANGE",
    "PROGRAM_YEAR_INFERRED",
}

# These identifiers must name one transaction row/anchor inside the immutable
# source, not merely a whole image slice.  Slice numbers and candidate indexes
# can shift when OCR/parser versions change, so they are intentionally excluded.
_REPLAY_STABLE_SOURCE_ID_KEYS = (
    "source_row_id",
    "source_anchor_id",
    "transaction_anchor_id",
    "ocr_anchor_id",
)

# A payment channel is not a merchant identity. Treating these labels as an
# explicit counterparty could hide a second real transaction that happens to
# share the same day and amount with an already confirmed row.
_REPLAY_LOW_INFORMATION_MERCHANT_SIGNATURES = frozenset(
    duplicate_text_signature(value, None)
    for value in (
        "微信",
        "微信支付",
        "支付宝",
        "财付通",
        "云闪付",
        "银联",
        "快捷支付",
        "扫码支付",
        "二维码支付",
        "商户消费",
        "消费",
        "付款",
        "收款",
        "交易",
    )
)


def _coarse_duplicate_key(
    direction: str | None,
    amount: Decimal | None,
    transaction_date: date | None,
) -> tuple[str, Decimal, date] | None:
    if direction is None or amount is None or transaction_date is None:
        return None
    return direction, Decimal(amount), transaction_date


def _replay_date_is_uncertain(candidate: ParsedCandidate) -> bool:
    if candidate.transaction_date is None:
        return True
    return any(
        issue.get("code") in _REPLAY_UNCERTAIN_DATE_CODES
        for issue in [*candidate.validation_errors, *candidate.warnings]
    )


def _nonempty_duplicate_text_matches(
    merchant_a: str | None,
    description_a: str | None,
    merchant_b: str | None,
    description_b: str | None,
) -> bool:
    left = duplicate_text_signature(merchant_a, description_a)
    right = duplicate_text_signature(merchant_b, description_b)
    return bool(left and right and duplicate_signatures_are_similar(left, right))


def _explicit_replay_merchant_matches(
    candidate_merchant: str | None,
    transaction_merchant: str | None,
) -> bool:
    """Require the current ledger merchant identity, not any shared memo."""

    candidate_signature = duplicate_text_signature(candidate_merchant, None)
    transaction_signature = duplicate_text_signature(transaction_merchant, None)
    return bool(
        candidate_signature
        and transaction_signature
        and candidate_signature not in _REPLAY_LOW_INFORMATION_MERCHANT_SIGNATURES
        and candidate_signature == transaction_signature
    )


def _replay_source_identities(evidence: dict | None) -> set[tuple[str, str]]:
    if not isinstance(evidence, dict):
        return set()
    containers = [evidence]
    source_locator = evidence.get("source_locator")
    if isinstance(source_locator, dict):
        containers.append(source_locator)
    identities: set[tuple[str, str]] = set()
    for container in containers:
        for key in _REPLAY_STABLE_SOURCE_ID_KEYS:
            value = container.get(key)
            if isinstance(value, bool) or value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                identities.add((key, normalized))
    return identities


def _same_stable_replay_source_identity(
    candidate: ParsedCandidate,
    old_candidate: FinancialTransactionCandidate,
) -> bool:
    current = _replay_source_identities(candidate.evidence)
    previous = _replay_source_identities(old_candidate.evidence)
    return bool(current and previous and current.intersection(previous))


def _same_source_replay_relation(
    candidate: ParsedCandidate,
    old_candidate: FinancialTransactionCandidate,
    transaction: FinancialTransaction,
) -> tuple[str, str, str] | None:
    """Classify one replay edge without ever matching on amount alone."""

    direction_matches = candidate.direction == transaction.direction
    direction_is_uncertain = (
        candidate.direction is None
        and any(
            issue.get("field") == "direction"
            for issue in candidate.validation_errors
        )
    )
    currency_matches = candidate.currency == transaction.currency
    currency_is_uncertain = (
        candidate.currency in {None, "", "UNK"}
        or any(
            issue.get("field") == "currency"
            for issue in candidate.validation_errors
        )
    )
    if (
        candidate.amount is None
        or any(issue.get("field") == "amount" for issue in candidate.validation_errors)
        or (not direction_matches and not direction_is_uncertain)
        or Decimal(candidate.amount) != Decimal(transaction.amount)
        or (not currency_matches and not currency_is_uncertain)
    ):
        return None

    candidate_slice = (candidate.evidence or {}).get("slice_sequence")
    old_slice = (old_candidate.evidence or {}).get("slice_sequence")
    same_source_slice = (
        isinstance(candidate_slice, int)
        and isinstance(old_slice, int)
        and candidate_slice == old_slice
    )
    if direction_is_uncertain or currency_is_uncertain:
        if same_source_slice:
            return (
                "weak",
                "same_source_slice_amount_core_uncertain",
                "同一原图、同一识别片段中存在同金额的已确认记录；当前方向或币种不明确，只能提示人工确认是否为重复",
            )
        return None

    current_merchant_matches = _explicit_replay_merchant_matches(
        candidate.merchant,
        transaction.merchant,
    )
    current_description_matches = _nonempty_duplicate_text_matches(
        None,
        candidate.description,
        None,
        transaction.description,
    )
    old_text_matches = _nonempty_duplicate_text_matches(
        candidate.merchant,
        candidate.description,
        old_candidate.merchant,
        old_candidate.description,
    )
    quote_matches = _nonempty_duplicate_text_matches(
        None,
        (candidate.evidence or {}).get("evidence_quote"),
        None,
        (old_candidate.evidence or {}).get("evidence_quote"),
    )
    stable_source_identity = _same_stable_replay_source_identity(
        candidate,
        old_candidate,
    )
    review_text_matches = (
        current_merchant_matches
        or current_description_matches
        or old_text_matches
        or quote_matches
    )
    dates_match = (
        candidate.transaction_date is not None
        and candidate.transaction_date == transaction.transaction_date
    )
    date_is_uncertain = _replay_date_is_uncertain(candidate)

    if stable_source_identity and date_is_uncertain:
        return (
            "strong",
            "same_source_anchor_date_relaxed",
            "同一原图的旧解析版本中，稳定来源行标识和已确认记录一致；当前日期为推断或缺失，已保守阻止重复入账",
        )
    if date_is_uncertain and review_text_matches:
        return (
            "weak",
            "same_source_identity_date_uncertain",
            "同一原图中存在同方向、同金额且文本相近的已确认记录，但当前日期为推断或缺失，需要人工确认",
        )
    if (current_merchant_matches or stable_source_identity) and dates_match:
        return (
            "strong",
            (
                "same_source_anchor_date_exact"
                if stable_source_identity
                else "same_source_merchant_date_exact"
            ),
            "同一原图的旧解析版本中，方向、金额、日期和明确交易身份均与已确认记录一致",
        )
    if dates_match and review_text_matches:
        return (
            "weak",
            "same_source_core_identity_weak",
            "同一原图中存在同方向、同金额、同日期且部分文本相近的已确认记录，但缺少明确商户或稳定来源行身份，需要人工确认",
        )
    if dates_match:
        return (
            "weak",
            "same_source_core_text_changed",
            "同一原图中存在同方向、同金额、同日期的已确认记录，但交易文本不足以确认为同一笔",
        )
    if review_text_matches or stable_source_identity:
        return (
            "weak",
            "same_source_text_date_conflict",
            "同一原图中存在同方向、同金额且文本相近的已确认记录，但日期冲突，需要人工确认",
        )
    if (
        date_is_uncertain
        and same_source_slice
    ):
        return (
            "weak",
            "same_source_slice_amount_date_uncertain",
            "同一原图、同一识别片段中存在同方向同金额的已确认记录；当前日期和文字不足以自动认定，请人工确认是否为重复",
        )
    return None


def _same_source_confirmed_replay_decisions(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: Sequence[ParsedCandidate],
) -> list[_SameSourceReplayDecision | None]:
    """Match confirmed rows from older parsers of the exact same source.

    Unconfirmed candidates never participate here. A hard duplicate requires
    one unambiguous confirmed transaction and non-amount evidence; every
    ambiguous edge is deliberately downgraded to explicit human review.
    """

    decisions: list[_SameSourceReplayDecision | None] = [None] * len(parsed)
    if not parsed:
        return decisions
    old_rows = db.query(
        FinancialTransactionCandidate,
        FinancialTransaction,
        FinancialImportBatch,
    ).join(
        FinancialImportBatch,
        FinancialImportBatch.id == FinancialTransactionCandidate.batch_id,
    ).join(
        FinancialTransaction,
        FinancialTransaction.id == FinancialTransactionCandidate.transaction_id,
    ).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.status == "confirmed",
        FinancialImportBatch.id != batch.id,
        FinancialImportBatch.user_id == batch.user_id,
        FinancialImportBatch.origin_type == batch.origin_type,
        FinancialImportBatch.source_type == batch.source_type,
        FinancialImportBatch.content_hash == batch.content_hash,
        FinancialTransaction.user_id == batch.user_id,
    ).order_by(
        FinancialImportBatch.id.desc(),
        FinancialTransactionCandidate.id.asc(),
    ).all()
    if not old_rows:
        return decisions

    matches: list[dict[int, dict]] = [dict() for _ in parsed]
    for index, candidate in enumerate(parsed):
        for old_candidate, transaction, old_batch in old_rows:
            relation = _same_source_replay_relation(
                candidate,
                old_candidate,
                transaction,
            )
            if relation is None:
                continue
            strength, reason_code, reason = relation
            existing = matches[index].get(transaction.id)
            if existing is None or (
                existing["strength"] == "weak" and strength == "strong"
            ):
                matches[index][transaction.id] = {
                    "strength": strength,
                    "reason_code": reason_code,
                    "reason": reason,
                    "transaction": transaction,
                    "source_batch_ids": {old_batch.id},
                }
            else:
                existing["source_batch_ids"].add(old_batch.id)

    strong_claimants: Counter[int] = Counter(
        transaction_id
        for candidate_matches in matches
        for transaction_id, match in candidate_matches.items()
        if match["strength"] == "strong"
    )
    for index, candidate_matches in enumerate(matches):
        if not candidate_matches:
            continue
        strong = [
            match for match in candidate_matches.values()
            if match["strength"] == "strong"
        ]
        if (
            len(strong) == 1
            and len(candidate_matches) == 1
            and strong_claimants[strong[0]["transaction"].id] == 1
        ):
            match = strong[0]
            decisions[index] = _SameSourceReplayDecision(
                strength="strong",
                transactions=(match["transaction"],),
                source_batch_ids=tuple(sorted(match["source_batch_ids"])),
                reason_code=match["reason_code"],
                reason=match["reason"],
            )
            continue
        ordered = sorted(
            candidate_matches.values(),
            key=lambda match: match["transaction"].id,
        )
        source_batch_ids = sorted({
            source_batch_id
            for match in ordered
            for source_batch_id in match["source_batch_ids"]
        })
        ambiguous = (
            len(strong) > 1
            or (bool(strong) and len(candidate_matches) > 1)
            or any(
                strong_claimants[match["transaction"].id] > 1 for match in strong
            )
        )
        decisions[index] = _SameSourceReplayDecision(
            strength="weak",
            transactions=tuple(match["transaction"] for match in ordered),
            source_batch_ids=tuple(source_batch_ids),
            reason_code=(
                "same_source_confirmed_match_ambiguous"
                if ambiguous
                else ordered[0]["reason_code"]
            ),
            reason=(
                "同一原图中存在多个已确认对应，或多个新候选指向同一记录，需要人工确认"
                if ambiguous
                else ordered[0]["reason"]
            ),
        )
    return decisions


def _same_source_replay_payload(
    decision: _SameSourceReplayDecision,
) -> dict[str, object]:
    return {
        "strength": decision.strength,
        "reason_code": decision.reason_code,
        "reason": decision.reason,
        "source_batch_ids": list(decision.source_batch_ids),
        "transaction_ids": [
            transaction.id for transaction in decision.transactions
        ],
    }


def _persisted_candidate_as_parsed(
    candidate: FinancialTransactionCandidate,
) -> ParsedCandidate:
    return ParsedCandidate(
        row_number=candidate.row_number,
        direction=candidate.direction,
        amount=Decimal(candidate.amount) if candidate.amount is not None else None,
        currency=candidate.currency or "UNK",
        transaction_date=candidate.transaction_date,
        occurred_at=candidate.occurred_at,
        category_name=candidate.category_name,
        merchant=candidate.merchant,
        description=candidate.description,
        nature=candidate.nature,
        external_key=candidate.external_key or "",
        fingerprint=candidate.fingerprint or "",
        original_payload=dict(candidate.original_payload or {}),
        evidence=dict(candidate.evidence or {}),
        validation_errors=[dict(issue) for issue in (candidate.validation_errors or [])],
        warnings=[dict(issue) for issue in (candidate.warnings or [])],
    )


def _same_source_replay_was_explicitly_accepted(
    candidate: FinancialTransactionCandidate,
    decision: _SameSourceReplayDecision,
) -> bool:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    presented = evidence.get("same_source_replay_match")
    if not isinstance(presented, dict):
        return False
    transaction_ids = sorted(transaction.id for transaction in decision.transactions)
    presented_ids = sorted(
        int(value)
        for value in presented.get("transaction_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    )
    if (
        presented.get("strength") != decision.strength
        or presented.get("reason_code") != decision.reason_code
        or presented_ids != transaction_ids
    ):
        return False
    if decision.strength == "strong":
        overridden_ids = sorted(
            int(value)
            for value in evidence.get("duplicate_override_transaction_ids", [])
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        )
        return bool(evidence.get("duplicate_override_at")) and overridden_ids == transaction_ids
    return bool(evidence.get("review_accepted_at"))


class _DuplicateTextIndex:
    """Bounded deterministic sibling matcher.

    Small coarse buckets are scanned exactly. Once a bucket grows beyond the
    explicit budget, later rows conservatively require review; this bounds both
    CPU and memory without allowing an adversarial same-day/same-amount file to
    bypass duplicate protection.
    """

    MAX_EXACT_SIGNATURES = 100

    def __init__(self) -> None:
        self._signatures: list[tuple[str, ...]] = []
        self._overflowed = False

    def has_match(self, merchant: str | None, description: str | None) -> bool:
        if not self._signatures and not self._overflowed:
            return False
        if self._overflowed:
            return True
        signature = duplicate_text_signature(merchant, description)
        return any(
            duplicate_signatures_are_similar(signature, existing)
            for existing in self._signatures
        )

    def add(self, merchant: str | None, description: str | None) -> None:
        if self._overflowed:
            return
        if len(self._signatures) >= self.MAX_EXACT_SIGNATURES:
            self._signatures.clear()
            self._overflowed = True
            return
        self._signatures.append(duplicate_text_signature(merchant, description))


def import_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _is_retryable_mysql_conflict(exc: OperationalError) -> bool:
    original = getattr(exc, "orig", None)
    args = getattr(original, "args", ())
    return bool(args and args[0] in {1205, 1213})


def _formal_source_type(source_type: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", source_type.lower()).strip("_") or "generic"
    return f"import_{normalized}"[:30]


def _public_headers(raw_headers: Sequence[str]) -> list[str]:
    """Return stable, unique labels that never duplicate header PII into JSON."""
    result: list[str] = []
    used: set[str] = set()
    for index, raw_header in enumerate(raw_headers, start=1):
        base = redact_cashflow_text(str(raw_header or ""), max_length=80).strip()
        base = base or f"未命名列{index}"
        candidate = base
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{base}（第 {index} 列-{suffix}）"
        result.append(candidate)
        used.add(candidate)
    return result


def _public_column_mapping(
    table: ImportTable,
    public_headers: Sequence[str],
) -> dict[str, str]:
    raw_to_public = dict(zip(table.headers, public_headers))
    return {
        field: raw_to_public[raw_header]
        for field, raw_header in table.mapping.items()
        if raw_header in raw_to_public
    }


def _safe_sample_rows(
    table: ImportTable,
    public_headers: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    safe_headers = list(public_headers or _public_headers(table.headers))
    samples: list[dict[str, str]] = []
    for row in table.rows[:3]:
        sample: dict[str, str] = {}
        for header, public_header in zip(table.headers, safe_headers):
            value = str(row.get(header, "") or "")[:120]
            sensitive_value = redact_cashflow_text(value) != value
            sample[public_header] = (
                "已隐藏"
                if value and (SENSITIVE_HEADER_PATTERN.search(header) or sensitive_value)
                else value
            )
        samples.append(sample)
    return samples


def _public_table_metadata(
    table: ImportTable,
) -> tuple[list[str], dict[str, str], list[dict[str, str]]]:
    headers = _public_headers(table.headers)
    return (
        headers,
        _public_column_mapping(table, headers),
        _safe_sample_rows(table, headers),
    )


def batch_payload(batch: FinancialImportBatch, *, reused: bool = False) -> dict:
    hints = batch.parse_hints or {}
    original_file_retained = batch.attachment_version_id is not None
    if original_file_retained:
        resume_source = "legacy_original"
    elif batch.origin_type in {"file", "ocr"}:
        resume_source = "recognition_artifacts"
    else:
        resume_source = "structured_candidates"
    return {
        "id": batch.id,
        "origin_type": batch.origin_type,
        "source_type": batch.source_type,
        "attachment_version_id": batch.attachment_version_id,
        "original_file_retained": original_file_retained,
        "resume_source": resume_source,
        "original_filename": batch.original_filename,
        "content_type": batch.content_type,
        "file_size": batch.file_size,
        "parser_version": batch.parser_version,
        "status": batch.status,
        "column_mapping": batch.column_mapping or {},
        "headers": list(hints.get("headers") or []),
        "sample_rows": list(hints.get("sample_rows") or []),
        "recognition_progress": hints.get("recognition_progress"),
        "supersedes_batch_id": hints.get("supersedes_batch_id"),
        "total_count": batch.total_count,
        "ready_count": batch.ready_count,
        "review_count": batch.review_count,
        "duplicate_count": batch.duplicate_count,
        "exact_duplicate_count": batch.exact_duplicate_count,
        "possible_duplicate_count": batch.possible_duplicate_count,
        "invalid_count": batch.invalid_count,
        "excluded_count": batch.excluded_count,
        "confirmed_count": batch.confirmed_count,
        "version": batch.version,
        "parsed_at": batch.parsed_at,
        "confirmed_at": batch.confirmed_at,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "reused": reused,
    }


def get_owned_batch(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    lock: bool = False,
) -> FinancialImportBatch:
    query = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.id == batch_id,
        FinancialImportBatch.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    batch = query.first()
    if batch is None:
        raise import_error(404, "cashflow_import_not_found", "导入批次不存在")
    return batch


def list_owned_batches(
    db: Session,
    *,
    user_id: int,
    offset: int,
    limit: int,
    unfinished_only: bool = False,
) -> tuple[list[FinancialImportBatch], int]:
    query = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.status != "cancelled",
    )
    if unfinished_only:
        query = query.filter(
            FinancialImportBatch.status.notin_({"completed", "cancelled"})
        )
    total = query.count()
    rows = query.order_by(
        FinancialImportBatch.created_at.desc(),
        FinancialImportBatch.id.desc(),
    ).offset(offset).limit(limit).all()
    return rows, total


def list_owned_candidates(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    status: str | None,
    offset: int,
    limit: int,
) -> tuple[list[FinancialTransactionCandidate], int]:
    get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    query = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    )
    if status:
        query = query.filter(FinancialTransactionCandidate.status == status)
    total = query.count()
    rows = query.order_by(
        FinancialTransactionCandidate.row_number.asc(),
        FinancialTransactionCandidate.id.asc(),
    ).offset(offset).limit(limit).all()
    return rows, total


def _available_category_map(db: Session, user_id: int) -> dict[tuple[str, str], FinancialCategory]:
    categories = (
        db.query(FinancialCategory)
        .filter(
            FinancialCategory.is_active.is_(True),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user_id),
        )
        .order_by(FinancialCategory.user_id.desc(), FinancialCategory.id.asc())
        .all()
    )
    result: dict[tuple[str, str], FinancialCategory] = {}
    for category in categories:
        key = (category.direction, category.name.strip().lower())
        result.setdefault(key, category)
    return result


def _load_formal_duplicate_buckets(
    db: Session,
    *,
    user_id: int,
    coarse_keys: Iterable[tuple[str, Decimal, date]],
) -> tuple[
    dict[tuple[str, Decimal, date], list[FinancialTransaction]],
    dict[tuple[str, Decimal, date], _DuplicateBucketWatermark],
]:
    """Load fuzzy-comparison rows under explicit per-bucket and total budgets.

    The aggregate query returns only one row per coarse key. Buckets that would
    exceed either budget are represented by a count/max-id watermark instead
    of materializing their transactions. A user can accept that conservative
    warning, but any later insert/delete changes the watermark and forces a new
    review during confirmation.
    """
    ordered_keys = sorted(
        set(coarse_keys),
        key=lambda item: (item[0], item[1], item[2]),
    )
    aggregates: dict[tuple[str, Decimal, date], _DuplicateBucketWatermark] = {}
    for offset in range(0, len(ordered_keys), 500):
        key_chunk = ordered_keys[offset:offset + 500]
        rows = db.query(
            FinancialTransaction.direction,
            FinancialTransaction.amount,
            FinancialTransaction.transaction_date,
            func.count(FinancialTransaction.id),
            func.max(FinancialTransaction.id),
        ).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.deleted_at.is_(None),
            tuple_(
                FinancialTransaction.direction,
                FinancialTransaction.amount,
                FinancialTransaction.transaction_date,
            ).in_(key_chunk),
        ).group_by(
            FinancialTransaction.direction,
            FinancialTransaction.amount,
            FinancialTransaction.transaction_date,
        ).all()
        for direction, amount, transaction_date, count, max_id in rows:
            key = _coarse_duplicate_key(
                direction,
                Decimal(amount),
                transaction_date,
            )
            if key is not None and count and max_id is not None:
                aggregates[key] = _DuplicateBucketWatermark(
                    count=int(count),
                    max_transaction_id=int(max_id),
                )

    scan_keys: list[tuple[str, Decimal, date]] = []
    overflow: dict[tuple[str, Decimal, date], _DuplicateBucketWatermark] = {}
    scanned_rows = 0
    for key in ordered_keys:
        watermark = aggregates.get(key)
        if watermark is None:
            continue
        if (
            watermark.count > MAX_EXACT_FUZZY_BUCKET_SCAN
            or scanned_rows + watermark.count > MAX_TOTAL_FUZZY_ROWS
        ):
            overflow[key] = watermark
            continue
        scan_keys.append(key)
        scanned_rows += watermark.count

    row_buckets: dict[tuple[str, Decimal, date], list[FinancialTransaction]] = {}
    for offset in range(0, len(scan_keys), 500):
        key_chunk = scan_keys[offset:offset + 500]
        rows = db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.deleted_at.is_(None),
            tuple_(
                FinancialTransaction.direction,
                FinancialTransaction.amount,
                FinancialTransaction.transaction_date,
            ).in_(key_chunk),
        ).order_by(FinancialTransaction.id.asc()).limit(MAX_TOTAL_FUZZY_ROWS).all()
        for row in rows:
            key = _coarse_duplicate_key(
                row.direction,
                Decimal(row.amount),
                row.transaction_date,
            )
            if key is not None:
                row_buckets.setdefault(key, []).append(row)
    return row_buckets, overflow


def _existing_matches(
    db: Session,
    *,
    user_id: int,
    source_type: str,
    parsed: Sequence[ParsedCandidate],
) -> tuple[
    dict[str, FinancialTransaction],
    dict[str, list[FinancialTransaction]],
    dict[str, _DuplicateBucketWatermark],
]:
    external_keys = {item.external_key for item in parsed if item.external_key}
    exact: dict[str, FinancialTransaction] = {}
    if external_keys:
        rows = db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source_type == _formal_source_type(source_type),
            FinancialTransaction.external_key.in_(external_keys),
        ).all()
        exact = {row.external_key: row for row in rows if row.external_key}

    coarse_keys = {
        key
        for item in parsed
        if (key := _coarse_duplicate_key(item.direction, item.amount, item.transaction_date)) is not None
    }
    possible: dict[str, list[FinancialTransaction]] = {}
    overflow_by_fingerprint: dict[str, _DuplicateBucketWatermark] = {}
    if coarse_keys:
        row_buckets, overflow = _load_formal_duplicate_buckets(
            db,
            user_id=user_id,
            coarse_keys=coarse_keys,
        )
        for item in parsed:
            key = _coarse_duplicate_key(item.direction, item.amount, item.transaction_date)
            if key is not None and key in overflow:
                overflow_by_fingerprint[item.fingerprint] = overflow[key]
                continue
            bucket = row_buckets.get(key, []) if key is not None else []
            matches = [
                row
                for row in bucket
                if duplicate_text_is_similar(
                    item.merchant,
                    item.description,
                    merchant_b=row.merchant,
                    description_b=row.description,
                )
            ]
            if matches:
                possible[item.fingerprint] = matches
    return exact, possible, overflow_by_fingerprint


def _append_issue(issues: list[dict], *, field: str, code: str, message: str) -> None:
    if not any(issue.get("code") == code for issue in issues):
        issues.append({"field": field, "code": code, "message": message})


def _populate_candidates(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: Sequence[ParsedCandidate],
) -> None:
    category_map = _available_category_map(db, batch.user_id)
    exact_transactions, possible_transactions, overflow_transactions = _existing_matches(
        db,
        user_id=batch.user_id,
        source_type=batch.source_type,
        parsed=parsed,
    )
    same_source_replays = _same_source_confirmed_replay_decisions(
        db,
        batch=batch,
        parsed=parsed,
    )
    existing_candidates = db.query(FinancialTransactionCandidate).join(
        FinancialImportBatch,
        FinancialImportBatch.id == FinancialTransactionCandidate.batch_id,
    ).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.status.in_(DUPLICATE_CLAIM_CANDIDATE_STATUSES),
        # Re-running the same source with a newer parser is a replacement
        # interpretation, not a second piece of evidence. Keep current-batch
        # sibling detection, but do not let older unconfirmed candidates from
        # the identical upload pollute the new review. Confirmed transactions
        # still participate through _existing_matches above.
        or_(
            FinancialTransactionCandidate.batch_id == batch.id,
            FinancialImportBatch.content_hash != batch.content_hash,
        ),
    ).all()
    external_candidate_ids: dict[str, list[int]] = {}
    candidate_buckets: dict[tuple[str, Decimal, date], list[FinancialTransactionCandidate]] = {}
    for row in existing_candidates:
        if row.external_key:
            external_candidate_ids.setdefault(row.external_key, []).append(row.id)
        coarse_key = _coarse_duplicate_key(
            row.direction,
            Decimal(row.amount) if row.amount is not None else None,
            row.transaction_date,
        )
        if coarse_key is not None:
            candidate_buckets.setdefault(coarse_key, []).append(row)
    seen_external_keys: set[str] = {
        row.external_key for row in existing_candidates if row.external_key
    }
    seen_fuzzy: dict[tuple[str, Decimal, date], _DuplicateTextIndex] = {}
    for row in existing_candidates:
        coarse_key = _coarse_duplicate_key(
            row.direction,
            Decimal(row.amount) if row.amount is not None else None,
            row.transaction_date,
        )
        if coarse_key is not None:
            seen_fuzzy.setdefault(coarse_key, _DuplicateTextIndex()).add(
                row.merchant,
                row.description,
            )

    for item_index, item in enumerate(parsed):
        errors = [dict(issue) for issue in item.validation_errors]
        warnings = [dict(issue) for issue in item.warnings]
        same_source_replay = same_source_replays[item_index]
        persisted_amount = (
            None
            if any(issue.get("field") == "amount" for issue in errors)
            else item.amount
        )
        category = None
        if item.direction in {"income", "expense"}:
            if item.category_name:
                category = category_map.get((item.direction, item.category_name.strip().lower()))
            if category is None:
                _append_issue(
                    warnings,
                    field="category_id",
                    code="CATEGORY_REVIEW_REQUIRED",
                    message="请确认这笔收支的分类",
                )

        exact_transaction = exact_transactions.get(item.external_key)
        repeated_external_key = item.external_key in seen_external_keys
        possible_matches = possible_transactions.get(item.fingerprint, [])
        overflow_watermark = overflow_transactions.get(item.fingerprint)
        possible_transaction = possible_matches[0] if possible_matches else None
        coarse_key = _coarse_duplicate_key(
            item.direction,
            persisted_amount,
            item.transaction_date,
        )
        fuzzy_index = seen_fuzzy.setdefault(coarse_key, _DuplicateTextIndex()) if coarse_key else None
        repeated_fingerprint = (
            fuzzy_index.has_match(item.merchant, item.description)
            if fuzzy_index is not None
            else False
        )
        matching_candidate_ids = [
            row.id
            for row in candidate_buckets.get(coarse_key, [])
            if duplicate_text_is_similar(
                item.merchant,
                item.description,
                row.merchant,
                row.description,
            )
        ] if coarse_key is not None else []
        status = "ready"
        duplicate_transaction_id = None
        if same_source_replay is not None and same_source_replay.strength == "strong":
            status = "exact_duplicate"
            duplicate_transaction_id = same_source_replay.transactions[0].id
            _append_issue(
                warnings,
                field="same_source_replay",
                code="EXACT_DUPLICATE",
                message=same_source_replay.reason,
            )
        elif same_source_replay is not None:
            status = "possible_duplicate"
            duplicate_transaction_id = same_source_replay.transactions[0].id
            _append_issue(
                warnings,
                field="same_source_replay",
                code="POSSIBLE_DUPLICATE",
                message=same_source_replay.reason,
            )
        elif errors:
            status = "invalid"
        elif exact_transaction is not None or repeated_external_key:
            status = "exact_duplicate"
            duplicate_transaction_id = exact_transaction.id if exact_transaction is not None else None
            _append_issue(
                warnings,
                field="external_key",
                code="EXACT_DUPLICATE",
                message=(
                    "这笔交易已经导入过，且原记录已删除，不能静默重新入账"
                    if exact_transaction is not None and exact_transaction.deleted_at is not None
                    else "其他待处理截图或文件中已有相同流水，已默认排除"
                    if repeated_external_key and exact_transaction is None
                    else "这笔交易已经存在，已默认排除"
                ),
            )
        elif possible_matches or overflow_watermark is not None or repeated_fingerprint:
            status = "possible_duplicate"
            duplicate_transaction_id = possible_transaction.id if possible_transaction is not None else None
            _append_issue(
                warnings,
                field="fingerprint",
                code="POSSIBLE_DUPLICATE",
                message=(
                    (
                        f"同日同金额已有 {overflow_watermark.count} 笔记录，"
                        "已触发有界查重，请人工核对后决定是否入账"
                    )
                    if overflow_watermark is not None
                    else
                    f"发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请核对后决定是否入账"
                    if possible_matches
                    else "发现其他待处理截图或同批次中同日同额且描述相近的候选，请核对后决定是否入账"
                ),
            )

        evidence = dict(item.evidence or {})
        evidence["source_validation_errors"] = [dict(issue) for issue in errors]
        if same_source_replay is not None:
            replay_match = _same_source_replay_payload(same_source_replay)
            replay_transaction_ids = list(replay_match["transaction_ids"])
            evidence["same_source_replay_match"] = replay_match
            if same_source_replay.strength == "weak":
                evidence["possible_duplicate_transaction_ids"] = replay_transaction_ids
        if possible_matches:
            evidence["possible_duplicate_transaction_ids"] = sorted({
                *evidence.get("possible_duplicate_transaction_ids", []),
                *(row.id for row in possible_matches),
            })
        repeated_candidate_ids = external_candidate_ids.get(item.external_key, [])
        if repeated_candidate_ids:
            evidence["exact_duplicate_candidate_ids"] = repeated_candidate_ids
        if matching_candidate_ids:
            evidence["possible_duplicate_candidate_ids"] = matching_candidate_ids
        if overflow_watermark is not None:
            evidence["possible_duplicate_bucket_watermark"] = (
                overflow_watermark.as_evidence()
            )
        if status == "ready" and warnings:
            status = "needs_review"

        candidate = FinancialTransactionCandidate(
            user_id=batch.user_id,
            batch_id=batch.id,
            row_number=item.row_number,
            direction=item.direction,
            amount=persisted_amount,
            currency=item.currency,
            transaction_date=item.transaction_date,
            occurred_at=item.occurred_at,
            category_id=category.id if category is not None else None,
            category_name=category.name if category is not None else item.category_name,
            merchant=item.merchant,
            description=item.description,
            nature=item.nature,
            status=status,
            external_key=item.external_key,
            fingerprint=item.fingerprint,
            duplicate_transaction_id=duplicate_transaction_id,
            original_payload=item.original_payload,
            evidence=evidence,
            validation_errors=errors,
            warnings=warnings,
        )
        db.add(candidate)
        # An invalid source row is not a valid claim on an external key or
        # fuzzy fingerprint. Otherwise one malformed row could poison a later
        # valid row in the same file and leave the whole transaction unusable.
        if status != "invalid":
            seen_external_keys.add(item.external_key)
            if fuzzy_index is not None:
                fuzzy_index.add(item.merchant, item.description)

    db.flush()
    refresh_batch_counts(db, batch)


def refresh_batch_counts(db: Session, batch: FinancialImportBatch) -> None:
    statuses = Counter(
        status
        for (status,) in db.query(FinancialTransactionCandidate.status).filter(
            FinancialTransactionCandidate.batch_id == batch.id,
            FinancialTransactionCandidate.user_id == batch.user_id,
        ).all()
    )
    batch.total_count = sum(statuses.values())
    batch.ready_count = statuses["ready"]
    batch.review_count = statuses["needs_review"]
    batch.exact_duplicate_count = statuses["exact_duplicate"]
    batch.possible_duplicate_count = statuses["possible_duplicate"]
    batch.duplicate_count = batch.exact_duplicate_count + batch.possible_duplicate_count
    batch.invalid_count = statuses["invalid"]
    batch.excluded_count = statuses["excluded"]
    batch.confirmed_count = statuses["confirmed"]

    if batch.status not in {"mapping_required", "failed", "cancelled"}:
        actionable_count = sum(statuses[state] for state in ACTIONABLE_CANDIDATE_STATUSES)
        batch.status = "completed" if actionable_count == 0 else "review_ready"
        batch.confirmed_at = datetime.utcnow() if batch.status == "completed" else None


def _find_reusable_batch(
    db: Session,
    *,
    user_id: int,
    origin_type: str,
    source_type: str,
    content_hash: str,
    parser_version: str,
) -> FinancialImportBatch | None:
    return db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == origin_type,
        FinancialImportBatch.source_type == source_type,
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == parser_version,
        FinancialImportBatch.status != "cancelled",
    ).first()


def _verify_batch_after_ambiguous_commit(
    db: Session,
    *,
    user_id: int,
    origin_type: str,
    source_type: str,
    content_hash: str,
    parser_version: str,
) -> tuple[FinancialImportBatch | None, bool]:
    """Check commit outcome through a fresh Session.

    A lost ACK can make ``commit()`` raise even though MySQL made the rows
    durable. The second return value tells callers whether reconciliation
    itself succeeded; on an unavailable database we keep the exact file for a
    later orphan sweep instead of risking a committed-row/file disconnect.
    """
    try:
        verification_factory = sessionmaker(
            bind=db.get_bind(),
            expire_on_commit=False,
        )
        with verification_factory() as verification_db:
            row = verification_db.query(FinancialImportBatch).filter(
                FinancialImportBatch.user_id == user_id,
                FinancialImportBatch.origin_type == origin_type,
                FinancialImportBatch.source_type == source_type,
                FinancialImportBatch.content_hash == content_hash,
                FinancialImportBatch.parser_version == parser_version,
            ).first()
            if row is not None:
                verification_db.expunge(row)
            return row, True
    except Exception:
        return None, False


def _rollback_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        return


def _normalized_content_type(filename: str) -> str:
    return {
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(Path(filename).suffix.lower(), "application/octet-stream")


def _retire_legacy_batch_attachment(
    db: Session,
    *,
    batch: FinancialImportBatch,
    user_id: int,
) -> bool:
    """Detach one legacy whole upload and schedule its physical deletion."""

    attachment_id = batch.attachment_version_id
    if attachment_id is None:
        return False
    attachment = db.query(PersonalAttachmentVersion).filter(
        PersonalAttachmentVersion.id == attachment_id,
        PersonalAttachmentVersion.user_id == user_id,
        PersonalAttachmentVersion.document_type == "cashflow_import",
    ).first()
    batch.attachment_version_id = None
    if attachment is None:
        return True
    still_referenced = db.query(FinancialImportBatch.id).filter(
        FinancialImportBatch.id != batch.id,
        FinancialImportBatch.attachment_version_id == attachment_id,
    ).first()
    if still_referenced is None:
        enqueue_attachment_cleanup(db, attachment)
        db.delete(attachment)
    return True


def _upgrade_reusable_table_batch(
    db: Session,
    *,
    batch: FinancialImportBatch,
    user_id: int,
    table: ImportTable,
) -> FinancialImportBatch:
    changed = False
    try:
        load_import_table_artifact(db, user_id=user_id, batch_id=batch.id)
    except CashflowRecognitionArtifactError:
        db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch.id,
            FinancialRecognitionArtifact.artifact_type.in_(
                {"tabular_manifest", "normalized_rows"}
            ),
        ).delete(synchronize_session="fetch")
        persist_import_table_artifacts(db, batch=batch, table=table)
        changed = True
    if _retire_legacy_batch_attachment(db, batch=batch, user_id=user_id):
        changed = True
    if changed:
        batch.version += 1
        db.commit()
        db.refresh(batch)
    return batch


def _upgrade_reusable_generated_batch(
    db: Session,
    *,
    batch: FinancialImportBatch,
    user_id: int,
    ocr_text: str | None,
) -> FinancialImportBatch:
    changed = False
    if ocr_text:
        try:
            load_ocr_text_artifact(db, user_id=user_id, batch_id=batch.id)
        except CashflowRecognitionArtifactError:
            db.query(FinancialRecognitionArtifact).filter(
                FinancialRecognitionArtifact.user_id == user_id,
                FinancialRecognitionArtifact.batch_id == batch.id,
                FinancialRecognitionArtifact.artifact_type == "ocr_text",
            ).delete(synchronize_session="fetch")
            persist_ocr_text_artifact(db, batch=batch, ocr_text=ocr_text)
            changed = True
    if _retire_legacy_batch_attachment(db, batch=batch, user_id=user_id):
        changed = True
    if changed:
        batch.version += 1
        db.commit()
        db.refresh(batch)
    return batch


def create_file_import(
    db: Session,
    *,
    user_id: int,
    filename: str,
    content: bytes,
    source_hint: str,
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    table = read_import_table(content, filename, source_hint=source_hint)
    content_hash = hashlib.sha256(content).hexdigest()
    parsed = (
        None
        if table.mapping_required
        else parse_candidate_rows(table, content_hash=content_hash)
    )
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if (
        expected_data_epoch is not None
        and owner.business_data_epoch != expected_data_epoch
    ):
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "识别期间账户数据已被清空，本次结果未保存，请重新导入",
        )
    reusable = _find_reusable_batch(
        db,
        user_id=user_id,
        origin_type="file",
        source_type=table.source_type,
        content_hash=content_hash,
        parser_version=PARSER_VERSION,
    )
    if reusable is not None:
        reusable = _upgrade_reusable_table_batch(
            db,
            batch=reusable,
            user_id=user_id,
            table=table,
        )
        return reusable, True

    try:
        public_headers, public_mapping, safe_samples = _public_table_metadata(table)
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type="file",
            source_type=table.source_type,
            attachment_version_id=None,
            original_filename=Path(filename).name[:255],
            content_type=_normalized_content_type(filename),
            file_size=len(content),
            content_hash=content_hash,
            parser_version=PARSER_VERSION,
            status="mapping_required" if table.mapping_required else "created",
            column_mapping=public_mapping,
            parse_hints={"headers": public_headers, "sample_rows": safe_samples},
            parsed_at=None if table.mapping_required else datetime.utcnow(),
        )
        db.add(batch)
        db.flush()
        persist_import_table_artifacts(db, batch=batch, table=table)
        if not table.mapping_required:
            _populate_candidates(
                db,
                batch=batch,
                parsed=parsed or [],
            )
    except IntegrityError as exc:
        db.rollback()
        reusable = _find_reusable_batch(
            db,
            user_id=user_id,
            origin_type="file",
            source_type=table.source_type,
            content_hash=content_hash,
            parser_version=PARSER_VERSION,
        )
        if reusable is not None:
            return (
                _upgrade_reusable_table_batch(
                    db,
                    batch=reusable,
                    user_id=user_id,
                    table=table,
                ),
                True,
            )
        raise import_error(409, "cashflow_import_conflict", "相同账单正在导入，请刷新后重试") from exc
    except Exception:
        db.rollback()
        raise

    batch_id = batch.id
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        verified, verification_succeeded = _verify_batch_after_ambiguous_commit(
            db,
            user_id=user_id,
            origin_type="file",
            source_type=table.source_type,
            content_hash=content_hash,
            parser_version=PARSER_VERSION,
        )
        if verification_succeeded and verified is not None:
            committed_by_this_call = verified.id == batch_id
            return verified, not committed_by_this_call
        raise

    # The request bytes were parsed in memory and are no longer needed. Only
    # the user-owned recognition artifacts and candidates survive this point.
    db.refresh(batch)
    return batch, False


def create_generated_import(
    db: Session,
    *,
    user_id: int,
    origin_type: str,
    source_type: str,
    content_hash: str,
    parser_version: str,
    parsed: Sequence[ParsedCandidate],
    original_filename: str | None = None,
    original_content_type: str | None = None,
    original_file_size: int | None = None,
    ocr_text: str | None = None,
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    """Persist generated candidates without receiving or retaining source bytes."""
    if origin_type not in {"ocr", "ai_text"}:
        raise ValueError("origin_type must be ocr or ai_text")
    normalized_parser_version = parser_version[:80]
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if (
        expected_data_epoch is not None
        and owner.business_data_epoch != expected_data_epoch
    ):
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "识别期间账户数据已被清空，本次结果未保存，请重新识别",
        )
    reusable = _find_reusable_batch(
        db,
        user_id=user_id,
        origin_type=origin_type,
        source_type=source_type,
        content_hash=content_hash,
        parser_version=normalized_parser_version,
    )
    if reusable is not None:
        reusable = _upgrade_reusable_generated_batch(
            db,
            batch=reusable,
            user_id=user_id,
            ocr_text=ocr_text,
        )
        return reusable, True

    try:
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type=origin_type,
            source_type=source_type,
            attachment_version_id=None,
            original_filename=Path(original_filename).name[:255] if original_filename else None,
            content_type=(original_content_type or _normalized_content_type(original_filename)) if original_filename else None,
            file_size=original_file_size,
            content_hash=content_hash,
            parser_version=normalized_parser_version,
            status="created",
            column_mapping={},
            parse_hints={"intake": origin_type},
            parsed_at=datetime.utcnow(),
        )
        db.add(batch)
        db.flush()
        if origin_type == "ocr":
            if not ocr_text:
                raise ValueError("ocr_text is required for OCR recognition artifacts")
            persist_ocr_text_artifact(db, batch=batch, ocr_text=ocr_text)
        _populate_candidates(db, batch=batch, parsed=parsed)
    except IntegrityError as exc:
        db.rollback()
        reusable = _find_reusable_batch(
            db,
            user_id=user_id,
            origin_type=origin_type,
            source_type=source_type,
            content_hash=content_hash,
            parser_version=normalized_parser_version,
        )
        if reusable is not None:
            return (
                _upgrade_reusable_generated_batch(
                    db,
                    batch=reusable,
                    user_id=user_id,
                    ocr_text=ocr_text,
                ),
                True,
            )
        raise import_error(409, "cashflow_import_conflict", "相同内容正在识别，请刷新后重试") from exc
    except Exception:
        db.rollback()
        raise

    batch_id = batch.id
    try:
        db.commit()
    except Exception:
        _rollback_quietly(db)
        verified, verification_succeeded = _verify_batch_after_ambiguous_commit(
            db,
            user_id=user_id,
            origin_type=origin_type,
            source_type=source_type,
            content_hash=content_hash,
            parser_version=normalized_parser_version,
        )
        if verification_succeeded and verified is not None:
            committed_by_this_call = verified.id == batch_id
            return verified, not committed_by_this_call
        raise

    # Only the structured output and, for OCR, complete local OCR text remain.
    db.refresh(batch)
    return batch, False


def apply_mapping(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    expected_batch_version: int,
    mapping: dict[str, str],
) -> FinancialImportBatch:
    snapshot = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    if snapshot.status != "mapping_required":
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不需要字段映射")
    if snapshot.version != expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    attachment_version_id = snapshot.attachment_version_id
    original_filename = snapshot.original_filename or "cashflow.csv"
    source_type = snapshot.source_type
    content_hash = snapshot.content_hash

    # New batches reconstruct mapping entirely from private recognition
    # artifacts. A legacy attachment is read only as a one-time compatibility
    # fallback, converted to artifacts, then retired in the same DB commit.
    unmapped_table: ImportTable | None = None
    artifact_error: CashflowRecognitionArtifactError | None = None
    try:
        unmapped_table = load_import_table_artifact(
            db,
            user_id=user_id,
            batch_id=batch_id,
        )
    except CashflowRecognitionArtifactError as exc:
        artifact_error = exc
        unmapped_table = None

    attachment: PersonalAttachmentVersion | None = None
    attachment_path: Path | None = None
    if unmapped_table is None and attachment_version_id is not None:
        attachment = db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.id == attachment_version_id,
            PersonalAttachmentVersion.user_id == user_id,
            PersonalAttachmentVersion.document_type == "cashflow_import",
        ).first()
        if attachment is not None:
            original_filename = snapshot.original_filename or attachment.original_filename
            try:
                attachment_path = resolve_attachment_path(attachment)
            except FileNotFoundError:
                attachment_path = None
            except OSError as exc:
                db.rollback()
                raise import_error(
                    409,
                    "cashflow_import_artifact_unavailable",
                    "识别产物暂时不可读取，请稍后重试或重新上传",
                ) from exc

    if unmapped_table is None and attachment_path is None:
        db.rollback()
        code = (
            "cashflow_import_artifact_corrupt"
            if artifact_error is not None and artifact_error.code == "corrupt"
            else "cashflow_import_artifact_missing"
        )
        message = (
            "表格识别产物完整性校验失败，请重新上传"
            if code == "cashflow_import_artifact_corrupt"
            else "可续办的表格识别产物不可用，请重新上传"
        )
        raise import_error(
            409,
            code,
            message,
        )

    try:
        if unmapped_table is None:
            # Release the authentication/snapshot transaction before legacy
            # local I/O and CPU work, then re-lock immediately before writing.
            db.rollback()
            try:
                content = attachment_path.read_bytes()  # type: ignore[union-attr]
            except FileNotFoundError as exc:
                raise import_error(
                    409,
                    "cashflow_import_artifact_missing",
                    "可续办的表格识别产物不可用，请重新上传",
                ) from exc
            except OSError as exc:
                raise import_error(
                    409,
                    "cashflow_import_artifact_unavailable",
                    "识别产物暂时不可读取，请稍后重试或重新上传",
                ) from exc
            if hashlib.sha256(content).hexdigest() != content_hash:
                raise import_error(
                    409,
                    "cashflow_import_artifact_corrupt",
                    "旧导入原件完整性校验失败，请重新上传",
                )
            unmapped_table = read_import_table(
                content,
                original_filename,
                source_hint=source_type,
            )
        else:
            # Plain dataclasses remain usable after releasing the read-only DB
            # snapshot; no original filesystem object is involved.
            db.rollback()
    except Exception:
        db.rollback()
        raise

    public_headers = _public_headers(unmapped_table.headers)
    public_to_raw = dict(zip(public_headers, unmapped_table.headers))
    invalid_public_headers = [
        header for header in mapping.values() if header not in public_to_raw
    ]
    if invalid_public_headers:
        raise CashflowImportError(
            f"字段映射引用了不存在的列：{invalid_public_headers[0]}"
        )
    raw_mapping = {
        field: public_to_raw[public_header]
        for field, public_header in mapping.items()
    }
    if (
        "transaction_date" not in raw_mapping
        or not ({"amount", "income_amount", "expense_amount"} & set(raw_mapping))
        or (
            "direction" not in raw_mapping
            and not {"income_amount", "expense_amount"}.issubset(raw_mapping)
        )
    ):
        raise import_error(422, "cashflow_import_mapping_incomplete", "字段映射不完整")
    table = replace(
        unmapped_table,
        mapping=raw_mapping,
        mapping_required=False,
    )
    parsed = parse_candidate_rows(table, content_hash=content_hash)

    owner = lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if (
        batch.status != "mapping_required"
        or batch.version != expected_batch_version
        or batch.content_hash != content_hash
    ):
        db.rollback()
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    public_headers, public_mapping, safe_samples = _public_table_metadata(table)
    batch.source_type = table.source_type
    batch.column_mapping = public_mapping
    batch.parse_hints = {"headers": public_headers, "sample_rows": safe_samples}
    batch.status = "created"
    batch.parsed_at = datetime.utcnow()
    if attachment_version_id is not None:
        if artifact_error is not None:
            db.query(FinancialRecognitionArtifact).filter(
                FinancialRecognitionArtifact.user_id == user_id,
                FinancialRecognitionArtifact.batch_id == batch.id,
                FinancialRecognitionArtifact.artifact_type.in_(
                    {"tabular_manifest", "normalized_rows"}
                ),
            ).delete(synchronize_session="fetch")
        persist_import_table_artifacts(db, batch=batch, table=unmapped_table)
        _retire_legacy_batch_attachment(db, batch=batch, user_id=user_id)
    _populate_candidates(
        db,
        batch=batch,
        parsed=parsed,
    )
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续") from exc
    db.refresh(batch)
    return batch


def _candidate_validation(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
    user_id: int,
    available_categories: dict[int, FinancialCategory] | None = None,
    resolved_fields: set[str] | None = None,
) -> tuple[list[dict], FinancialCategory | None]:
    reviewed_fields = resolved_fields or set()
    evidence = dict(candidate.evidence or {})
    source_errors = evidence.get("source_validation_errors")
    if not isinstance(source_errors, list):
        # Compatibility for candidates created before source errors were
        # separately retained. Unknown source errors remain fail-closed.
        source_errors = candidate.validation_errors or []
    errors: list[dict] = []
    for source_issue in source_errors:
        if not isinstance(source_issue, dict):
            continue
        code = str(source_issue.get("code") or "")
        editable_fields = SOURCE_ERROR_EDIT_FIELDS.get(code)
        resolved = (
            editable_fields.issubset(reviewed_fields)
            if code == "BOTH_SIDES_HAVE_AMOUNT" and editable_fields is not None
            else bool(editable_fields and editable_fields.intersection(reviewed_fields))
        )
        if not resolved:
            errors.append(dict(source_issue))
    if candidate.direction not in {"income", "expense", "transfer"}:
        _append_issue(errors, field="direction", code="DIRECTION_REQUIRED", message="请选择收入、支出或转账")
    amount = Decimal(candidate.amount) if candidate.amount is not None else None
    if amount is None or amount <= 0 or amount > Decimal("999999999999.99"):
        _append_issue(errors, field="amount", code="AMOUNT_INVALID", message="请输入有效金额")
    if candidate.transaction_date is None:
        _append_issue(errors, field="transaction_date", code="DATE_INVALID", message="请选择交易日期")
    if candidate.currency != "CNY":
        _append_issue(
            errors,
            field="currency",
            code="UNSUPPORTED_CURRENCY",
            message="当前仅支持人民币 CNY，其他币种不能直接入账",
        )
    category = None
    if candidate.direction in {"income", "expense"}:
        if available_categories is None:
            try:
                category = get_available_category(
                    db,
                    user_id=user_id,
                    category_id=candidate.category_id,
                    direction=candidate.direction,
                )
            except HTTPException as exc:
                _append_issue(
                    errors,
                    field="category_id",
                    code="CATEGORY_INVALID",
                    message=str(exc.detail),
                )
        else:
            category = available_categories.get(candidate.category_id or -1)
            if category is None:
                _append_issue(
                    errors,
                    field="category_id",
                    code="CATEGORY_INVALID",
                    message="收支分类不存在、已停用或不属于当前用户",
                )
            elif category.direction != candidate.direction:
                category = None
                _append_issue(
                    errors,
                    field="category_id",
                    code="CATEGORY_INVALID",
                    message="分类方向与流水方向不一致",
                )
    elif candidate.direction == "transfer":
        candidate.category_id = None
        candidate.category_name = None
        candidate.nature = None
    return errors, category


def _find_possible_duplicates_for_candidate(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
) -> tuple[list[FinancialTransaction], _DuplicateBucketWatermark | None]:
    if candidate.direction is None or candidate.amount is None or candidate.transaction_date is None:
        return [], None
    key = _coarse_duplicate_key(
        candidate.direction,
        Decimal(candidate.amount),
        candidate.transaction_date,
    )
    if key is None:
        return [], None
    fingerprint = build_candidate_fingerprint(
        direction=candidate.direction,
        amount=Decimal(candidate.amount),
        transaction_date=candidate.transaction_date,
        merchant=candidate.merchant,
        description=candidate.description,
    )
    candidate.fingerprint = fingerprint
    row_buckets, overflow = _load_formal_duplicate_buckets(
        db,
        user_id=candidate.user_id,
        coarse_keys=[key],
    )
    overflow_watermark = overflow.get(key)
    if overflow_watermark is not None:
        return [], overflow_watermark
    return [
        row
        for row in row_buckets.get(key, [])
        if duplicate_text_is_similar(
            candidate.merchant,
            candidate.description,
            row.merchant,
            row.description,
        )
    ], None


def _has_active_sibling_fingerprint(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
) -> bool:
    if not candidate.fingerprint:
        return False
    siblings = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == candidate.user_id,
        FinancialTransactionCandidate.id != candidate.id,
        FinancialTransactionCandidate.direction == candidate.direction,
        FinancialTransactionCandidate.amount == candidate.amount,
        FinancialTransactionCandidate.transaction_date == candidate.transaction_date,
        FinancialTransactionCandidate.status.in_({"ready", "needs_review", "possible_duplicate"}),
    ).all()
    return any(
        duplicate_text_is_similar(
            candidate.merchant,
            candidate.description,
            sibling.merchant,
            sibling.description,
        )
        for sibling in siblings
    )


def update_candidate(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    candidate_id: int,
    data: FinancialImportCandidateUpdate,
) -> tuple[FinancialTransactionCandidate, FinancialImportBatch]:
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能编辑")
    candidate = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id == candidate_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.user_id == user_id,
    ).with_for_update().first()
    if candidate is None:
        raise import_error(404, "cashflow_import_candidate_not_found", "导入候选不存在")
    if candidate.version != data.expected_version:
        raise import_error(409, "cashflow_import_stale_candidate", "候选已更新，请刷新后继续")
    exact_duplicate_override = (
        candidate.status == "exact_duplicate" and data.action == "record_duplicate"
    )
    if not exact_duplicate_override and candidate.status not in EDITABLE_CANDIDATE_STATUSES:
        raise import_error(409, "cashflow_import_candidate_locked", "该候选已确认或已被精确去重")
    status_before_update = candidate.status
    fingerprint_before_update = candidate.fingerprint
    duplicate_before_update = candidate.duplicate_transaction_id
    transaction_date_before_update = candidate.transaction_date
    evidence_before_update = dict(candidate.evidence or {})
    presented_duplicate_ids = {
        int(value)
        for value in evidence_before_update.get("possible_duplicate_transaction_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    }
    presented_bucket_watermark = evidence_before_update.get(
        "possible_duplicate_bucket_watermark"
    )

    if data.action == "record_duplicate":
        if candidate.status != "exact_duplicate":
            raise import_error(
                409,
                "cashflow_import_state_conflict",
                "只有已被精确去重的候选才能选择仍要记录",
            )
        original_external_key = candidate.external_key
        exact_duplicate_id = candidate.duplicate_transaction_id
        # A new formal row must not reuse the provider's unique identity. The
        # original key itself is not copied into audit evidence; a hash is
        # enough to prove what the user overrode without widening exposure.
        candidate.external_key = None
        errors, category = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            resolved_fields=set(evidence_before_update.get("user_modified_fields") or []),
        )
        candidate.validation_errors = errors
        if category is not None:
            candidate.category_name = category.name
        possible_matches, overflow_watermark = _find_possible_duplicates_for_candidate(
            db,
            candidate=candidate,
        )
        possible_ids = sorted(row.id for row in possible_matches)
        sibling_possible = _has_active_sibling_fingerprint(db, candidate=candidate)
        evidence = dict(candidate.evidence or {})
        evidence["duplicate_override_at"] = datetime.utcnow().isoformat()
        evidence["duplicate_override_reason"] = data.duplicate_override_reason
        evidence["duplicate_override_transaction_ids"] = (
            [exact_duplicate_id] if exact_duplicate_id is not None else []
        )
        if original_external_key:
            evidence["duplicate_override_original_external_key_hash"] = hashlib.sha256(
                original_external_key.encode("utf-8")
            ).hexdigest()
        evidence["duplicate_review_fingerprint"] = candidate.fingerprint
        evidence["duplicate_review_transaction_ids"] = possible_ids
        evidence["possible_duplicate_transaction_ids"] = possible_ids
        evidence["duplicate_review_sibling"] = bool(sibling_possible)
        if overflow_watermark is not None:
            bucket_watermark = overflow_watermark.as_evidence()
            evidence["duplicate_review_bucket_watermark"] = bucket_watermark
            evidence["possible_duplicate_bucket_watermark"] = bucket_watermark
        else:
            evidence.pop("duplicate_review_bucket_watermark", None)
            evidence.pop("possible_duplicate_bucket_watermark", None)
        candidate.evidence = evidence
        candidate.duplicate_transaction_id = None
        candidate.warnings = [
            issue
            for issue in (candidate.warnings or [])
            if issue.get("code") not in {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"}
        ]
        if errors:
            candidate.status = "invalid"
        elif candidate.warnings:
            candidate.status = "needs_review"
        else:
            candidate.status = "ready"
    elif data.action == "exclude":
        candidate.status = "excluded"
    elif data.action == "restore":
        if candidate.status != "excluded":
            raise import_error(409, "cashflow_import_state_conflict", "只有已排除候选可以恢复")
        errors, _ = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            resolved_fields=set(evidence_before_update.get("user_modified_fields") or []),
        )
        candidate.validation_errors = errors
        candidate.status = "invalid" if errors else ("needs_review" if candidate.warnings else "ready")
    else:
        changes = data.model_dump(
            exclude={"expected_version", "action", "duplicate_override_reason"},
            exclude_unset=True,
        )
        resolved_fields = set(evidence_before_update.get("user_modified_fields") or [])
        resolved_fields.update(changes)
        for field, value in changes.items():
            setattr(candidate, field, value)
        if (
            "transaction_date" in changes
            and candidate.transaction_date != transaction_date_before_update
            and candidate.occurred_at is not None
        ):
            # The editor confirms only the calendar date. Keeping the old
            # timestamp would persist two contradictory dates as formal facts.
            candidate.occurred_at = None
        if candidate.direction == "transfer":
            candidate.category_id = None
            candidate.category_name = None
            candidate.nature = None
        errors, category = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            resolved_fields=resolved_fields,
        )
        candidate.validation_errors = errors
        if category is not None:
            candidate.category_name = category.name
        possible_matches, overflow_watermark = _find_possible_duplicates_for_candidate(
            db,
            candidate=candidate,
        )
        possible = possible_matches[0] if possible_matches else None
        possible_ids = {row.id for row in possible_matches}
        current_bucket_watermark = (
            overflow_watermark.as_evidence()
            if overflow_watermark is not None
            else None
        )
        formal_possible = possible is not None or current_bucket_watermark is not None
        sibling_possible = _has_active_sibling_fingerprint(db, candidate=candidate)
        retained_warnings = [
            issue for issue in (candidate.warnings or [])
            if issue.get("code") not in {"CATEGORY_REVIEW_REQUIRED", "POSSIBLE_DUPLICATE"}
        ]
        visible_duplicate_is_unchanged = (
            status_before_update == "possible_duplicate"
            and fingerprint_before_update == candidate.fingerprint
            and (
                (
                    possible is not None
                    and possible_ids == presented_duplicate_ids
                    and duplicate_before_update in possible_ids
                )
                or (
                    current_bucket_watermark is not None
                    and current_bucket_watermark == presented_bucket_watermark
                    and duplicate_before_update is None
                )
                or (
                    not formal_possible
                    and sibling_possible
                    and duplicate_before_update is None
                    and not presented_duplicate_ids
                )
            )
        )
        accept_review_now = data.action == "accept_review" and (
            not (formal_possible or sibling_possible)
            or visible_duplicate_is_unchanged
        )
        if accept_review_now:
            accepted_possible_ids = sorted(possible_ids)
            accepted_sibling = sibling_possible
            retained_warnings = []
            possible_matches = []
            possible = None
            formal_possible = False
            sibling_possible = False
            evidence = dict(candidate.evidence or {})
            evidence["review_accepted_at"] = datetime.utcnow().isoformat()
            if accepted_possible_ids and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = accepted_possible_ids
                evidence["possible_duplicate_transaction_ids"] = accepted_possible_ids
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence["duplicate_review_sibling"] = bool(accepted_sibling)
            elif current_bucket_watermark is not None and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = []
                evidence["possible_duplicate_transaction_ids"] = []
                evidence["duplicate_review_bucket_watermark"] = current_bucket_watermark
                evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
                evidence["duplicate_review_sibling"] = bool(accepted_sibling)
            elif accepted_sibling and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = []
                evidence["possible_duplicate_transaction_ids"] = []
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence["duplicate_review_sibling"] = True
            else:
                evidence.pop("duplicate_review_fingerprint", None)
                evidence.pop("duplicate_review_transaction_ids", None)
                evidence.pop("possible_duplicate_transaction_ids", None)
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence.pop("duplicate_review_sibling", None)
            candidate.evidence = evidence
        elif formal_possible or sibling_possible:
            _append_issue(
                retained_warnings,
                field="fingerprint",
                code="POSSIBLE_DUPLICATE",
                message=(
                    (
                        f"同日同金额已有 {overflow_watermark.count} 笔记录，"
                        "已触发有界查重，请人工核对后决定是否入账"
                    )
                    if overflow_watermark is not None
                    else
                    f"发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请核对后决定是否入账"
                    if possible_matches
                    else "发现其他待处理批次或同批次中同日同额且描述相近的候选，请核对后决定是否入账"
                ),
            )
            evidence = dict(candidate.evidence or {})
            evidence["possible_duplicate_transaction_ids"] = sorted(possible_ids)
            if current_bucket_watermark is not None:
                evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
            else:
                evidence.pop("possible_duplicate_bucket_watermark", None)
            candidate.evidence = evidence
        candidate.warnings = retained_warnings
        candidate.duplicate_transaction_id = possible.id if possible is not None else None
        if errors:
            candidate.status = "invalid"
        elif formal_possible or sibling_possible:
            candidate.status = "possible_duplicate"
        elif retained_warnings:
            candidate.status = "needs_review"
        else:
            candidate.status = "ready"

    evidence = dict(candidate.evidence or {})
    modified = set(evidence.get("user_modified_fields") or [])
    modified.update(
        data.model_fields_set
        & {"direction", "amount", "transaction_date", "category_id", "merchant", "description", "nature"}
    )
    evidence["user_modified_fields"] = sorted(modified)
    candidate.evidence = evidence
    batch.updated_at = datetime.utcnow()
    db.flush()
    refresh_batch_counts(db, batch)
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_stale_candidate", "候选已更新，请刷新后继续") from exc
    db.refresh(candidate)
    db.refresh(batch)
    return candidate, batch


def _confirmation_report(
    batch: FinancialImportBatch,
    candidates: Iterable[FinancialTransactionCandidate],
) -> dict:
    items = list(candidates)
    confirmed = [item for item in items if item.status == "confirmed" and item.transaction_id]
    duplicates = [item for item in items if item.status == "exact_duplicate"]
    return {
        "batch": batch_payload(batch),
        "confirmed_candidate_ids": [item.id for item in confirmed],
        "transaction_ids": [item.transaction_id for item in confirmed],
        "duplicate_candidate_ids": [item.id for item in duplicates],
        "confirmed_count": len(confirmed),
        "duplicate_count": len(duplicates),
    }


def _prefetch_confirmation_context(
    db: Session,
    *,
    user_id: int,
    formal_source_type: str,
    candidates: Sequence[FinancialTransactionCandidate],
) -> tuple[
    dict[int, FinancialCategory],
    dict[str, FinancialTransaction],
    dict[str, list[FinancialTransaction]],
    dict[str, _DuplicateBucketWatermark],
]:
    category_ids = {
        item.category_id
        for item in candidates
        if item.category_id is not None and item.direction in {"income", "expense"}
    }
    available_categories: dict[int, FinancialCategory] = {}
    if category_ids:
        rows = db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            FinancialCategory.is_active.is_(True),
            or_(
                FinancialCategory.user_id.is_(None),
                FinancialCategory.user_id == user_id,
            ),
        ).all()
        available_categories = {row.id: row for row in rows}

    external_keys = {item.external_key for item in candidates if item.external_key}
    exact_by_key: dict[str, FinancialTransaction] = {}
    if external_keys:
        rows = db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source_type == formal_source_type,
            FinancialTransaction.external_key.in_(external_keys),
        ).all()
        exact_by_key = {row.external_key: row for row in rows if row.external_key}

    coarse_keys: set[tuple[str, Decimal, date]] = set()
    for candidate in candidates:
        if (
            candidate.direction is None
            or candidate.amount is None
            or candidate.transaction_date is None
        ):
            continue
        candidate.fingerprint = build_candidate_fingerprint(
            direction=candidate.direction,
            amount=Decimal(candidate.amount),
            transaction_date=candidate.transaction_date,
            merchant=candidate.merchant,
            description=candidate.description,
        )
        key = _coarse_duplicate_key(
            candidate.direction,
            Decimal(candidate.amount),
            candidate.transaction_date,
        )
        if key is not None:
            coarse_keys.add(key)

    possible_by_fingerprint: dict[str, list[FinancialTransaction]] = {}
    overflow_by_fingerprint: dict[str, _DuplicateBucketWatermark] = {}
    if coarse_keys:
        row_buckets, overflow = _load_formal_duplicate_buckets(
            db,
            user_id=user_id,
            coarse_keys=coarse_keys,
        )
        for candidate in candidates:
            key = _coarse_duplicate_key(
                candidate.direction,
                Decimal(candidate.amount) if candidate.amount is not None else None,
                candidate.transaction_date,
            )
            if key is not None and key in overflow:
                if candidate.fingerprint:
                    overflow_by_fingerprint[candidate.fingerprint] = overflow[key]
                continue
            bucket = row_buckets.get(key, []) if key is not None else []
            matches = [
                row
                for row in bucket
                if duplicate_text_is_similar(
                    candidate.merchant,
                    candidate.description,
                    merchant_b=row.merchant,
                    description_b=row.description,
                )
            ]
            if matches and candidate.fingerprint:
                possible_by_fingerprint[candidate.fingerprint] = matches

    return (
        available_categories,
        exact_by_key,
        possible_by_fingerprint,
        overflow_by_fingerprint,
    )


def _confirm_candidates_locked(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportConfirmRequest,
) -> dict:
    # Lock order is always user -> batch -> candidates. This serializes fuzzy
    # duplicate rechecks across import batches and every manual ledger mutation.
    owner = lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_confirmation_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    requested = {item.candidate_id: item.expected_version for item in data.candidates}
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.id.in_(requested),
    ).with_for_update().all()
    if len(candidates) != len(requested):
        raise import_error(404, "cashflow_import_candidate_not_found", "部分导入候选不存在")

    if all(
        item.status == "confirmed"
        or (
            item.status == "exact_duplicate"
            and (item.evidence or {}).get("confirmation_resolved_at")
        )
        for item in candidates
    ):
        return _confirmation_report(batch, candidates)
    if batch.version != data.expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    for candidate in candidates:
        if candidate.version != requested[candidate.id]:
            raise import_error(409, "cashflow_import_stale_candidate", "候选已更新，请刷新后继续")
        if candidate.status != "ready":
            raise import_error(409, "cashflow_import_candidate_not_ready", "只能确认已核对且可导入的候选")

    # A replacement parser may have created this preview before an older batch
    # from the exact same source was confirmed. Re-run the same-source guard
    # while the ledger owner and candidates are locked; otherwise changed OCR
    # dates/text could bypass the ordinary same-day fuzzy check at final write.
    replay_decisions = _same_source_confirmed_replay_decisions(
        db,
        batch=batch,
        parsed=[_persisted_candidate_as_parsed(candidate) for candidate in candidates],
    )
    replay_review_required = False
    for candidate, decision in zip(candidates, replay_decisions):
        if decision is None or _same_source_replay_was_explicitly_accepted(
            candidate,
            decision,
        ):
            continue
        evidence = dict(candidate.evidence or {})
        replay_match = _same_source_replay_payload(decision)
        replay_transaction_ids = list(replay_match["transaction_ids"])
        evidence["same_source_replay_match"] = replay_match
        # Any earlier acceptance referred to a different visible match set.
        # Leave its reason/hash as audit evidence, but invalidate the gates that
        # could otherwise make this newly discovered replay look accepted.
        for key in (
            "review_accepted_at",
            "duplicate_override_at",
            "duplicate_review_fingerprint",
            "duplicate_review_transaction_ids",
            "duplicate_review_bucket_watermark",
            "duplicate_review_sibling",
        ):
            evidence.pop(key, None)
        warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") not in {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"}
        ]
        if decision.strength == "strong":
            candidate.status = "exact_duplicate"
            evidence.pop("possible_duplicate_transaction_ids", None)
            _append_issue(
                warnings,
                field="same_source_replay",
                code="EXACT_DUPLICATE",
                message=decision.reason,
            )
        else:
            candidate.status = "possible_duplicate"
            evidence["possible_duplicate_transaction_ids"] = replay_transaction_ids
            _append_issue(
                warnings,
                field="same_source_replay",
                code="POSSIBLE_DUPLICATE",
                message=decision.reason,
            )
        candidate.duplicate_transaction_id = decision.transactions[0].id
        candidate.evidence = evidence
        candidate.warnings = warnings
        replay_review_required = True

    if replay_review_required:
        batch.updated_at = datetime.utcnow()
        db.flush()
        refresh_batch_counts(db, batch)
        try:
            db.commit()
        except (IntegrityError, StaleDataError) as exc:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_confirmation_conflict",
                "确认前候选状态发生变化，请刷新后重新核对",
            ) from exc
        raise import_error(
            409,
            "cashflow_import_possible_duplicate",
            "确认前发现同一原图已有确认记录，请刷新并明确核对",
        )

    formal_source_type = _formal_source_type(batch.source_type)
    categories: dict[int, FinancialCategory | None] = {}
    invalidated = False
    possible_duplicate_found = False

    # Revalidate the whole selection before creating any formal row. Besides
    # category changes, this catches a fuzzy duplicate created after preview.
    # A previous generic AI review is not enough: the user must have accepted
    # this exact fingerprint against the duplicate transaction then shown.
    ordered_candidates = sorted(
        candidates,
        key=lambda item: (item.external_key or "", item.id),
    )
    (
        available_categories,
        exact_by_key,
        possible_by_fingerprint,
        overflow_by_fingerprint,
    ) = (
        _prefetch_confirmation_context(
            db,
            user_id=user_id,
            formal_source_type=formal_source_type,
            candidates=ordered_candidates,
        )
    )
    selected_fuzzy: dict[tuple[str, Decimal, date], _DuplicateTextIndex] = {}
    selected_sibling_possible_ids: set[int] = set()
    for selected in sorted(candidates, key=lambda item: item.id):
        key = _coarse_duplicate_key(
            selected.direction,
            Decimal(selected.amount) if selected.amount is not None else None,
            selected.transaction_date,
        )
        if key is None:
            continue
        index = selected_fuzzy.setdefault(key, _DuplicateTextIndex())
        if index.has_match(selected.merchant, selected.description):
            selected_sibling_possible_ids.add(selected.id)
        index.add(selected.merchant, selected.description)
    for candidate in ordered_candidates:
        errors, category = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            available_categories=available_categories,
            resolved_fields=set(
                (candidate.evidence or {}).get("user_modified_fields") or []
            ),
        )
        if errors:
            candidate.validation_errors = errors
            candidate.status = "invalid"
            invalidated = True
            continue
        categories[candidate.id] = category
        exact_existing = exact_by_key.get(candidate.external_key or "")
        if exact_existing is not None:
            continue
        sibling_possible = candidate.id in selected_sibling_possible_ids
        possible_matches = possible_by_fingerprint.get(candidate.fingerprint or "", [])
        overflow_watermark = overflow_by_fingerprint.get(candidate.fingerprint or "")
        current_bucket_watermark = (
            overflow_watermark.as_evidence()
            if overflow_watermark is not None
            else None
        )
        if not possible_matches and current_bucket_watermark is None and not sibling_possible:
            continue
        possible_ids = {row.id for row in possible_matches}
        evidence = dict(candidate.evidence or {})
        accepted_ids = {
            int(value)
            for value in evidence.get("duplicate_review_transaction_ids", [])
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        }
        if current_bucket_watermark is not None:
            formal_duplicate_was_accepted = (
                evidence.get("duplicate_review_fingerprint") == candidate.fingerprint
                and evidence.get("duplicate_review_bucket_watermark")
                == current_bucket_watermark
            )
        else:
            formal_duplicate_was_accepted = (
                not possible_matches
                or (
                    evidence.get("duplicate_review_fingerprint") == candidate.fingerprint
                    and possible_ids == accepted_ids
                )
            )
        sibling_duplicate_was_accepted = (
            not sibling_possible
            or (
                evidence.get("duplicate_review_fingerprint") == candidate.fingerprint
                and evidence.get("duplicate_review_sibling") is True
            )
        )
        duplicate_was_accepted = (
            formal_duplicate_was_accepted and sibling_duplicate_was_accepted
        )
        if duplicate_was_accepted:
            continue
        warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") != "POSSIBLE_DUPLICATE"
        ]
        _append_issue(
            warnings,
            field="fingerprint",
            code="POSSIBLE_DUPLICATE",
            message=(
                (
                    f"确认前发现同日同金额已有 {overflow_watermark.count} 笔记录，"
                    "已触发有界查重，请再次人工核对"
                )
                if overflow_watermark is not None
                else
                f"确认前发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请再次核对后决定是否入账"
                if possible_matches
                else "确认前发现待处理批次中有同日同额且描述相近的候选，请再次核对"
            ),
        )
        candidate.warnings = warnings
        candidate.status = "possible_duplicate"
        candidate.duplicate_transaction_id = possible_matches[0].id if possible_matches else None
        evidence["possible_duplicate_transaction_ids"] = sorted(possible_ids)
        if current_bucket_watermark is not None:
            evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
        else:
            evidence.pop("possible_duplicate_bucket_watermark", None)
        candidate.evidence = evidence
        possible_duplicate_found = True

    if invalidated or possible_duplicate_found:
        batch.updated_at = datetime.utcnow()
        db.flush()
        refresh_batch_counts(db, batch)
        try:
            db.commit()
        except (IntegrityError, StaleDataError) as exc:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_confirmation_conflict",
                "确认前候选状态发生变化，请刷新后重新核对",
            ) from exc
        if invalidated:
            raise import_error(
                409,
                "cashflow_import_confirmation_conflict",
                "候选数据已失效，请刷新并重新核对",
            )
        raise import_error(
            409,
            "cashflow_import_possible_duplicate",
            "确认前发现新的疑似重复记录，请刷新并明确核对",
        )

    batch.status = "confirming"
    # A stable global key order prevents overlapping batches from acquiring
    # InnoDB unique-index locks in opposite x→y / y→x order.
    for candidate in ordered_candidates:
        category = categories[candidate.id]

        existing = exact_by_key.get(candidate.external_key or "")
        if existing is not None:
            candidate.status = "exact_duplicate"
            candidate.duplicate_transaction_id = existing.id
            evidence = dict(candidate.evidence or {})
            evidence["confirmation_resolved_at"] = datetime.utcnow().isoformat()
            candidate.evidence = evidence
            warnings = [dict(issue) for issue in (candidate.warnings or [])]
            _append_issue(
                warnings,
                field="external_key",
                code="EXACT_DUPLICATE",
                message="确认时发现该交易已经存在，未重复入账",
            )
            candidate.warnings = warnings
            continue

        transaction = FinancialTransaction(
            user_id=user_id,
            category_id=category.id if category is not None else None,
            direction=candidate.direction,
            amount=candidate.amount,
            currency=candidate.currency or "CNY",
            transaction_date=candidate.transaction_date,
            # The current review UI confirms a date, not an exact clock time.
            # Keep source time on the candidate as evidence, but do not promote
            # an unreviewed timestamp into the formal ledger.
            occurred_at=None,
            merchant=candidate.merchant,
            description=candidate.description,
            nature=candidate.nature if candidate.direction == "expense" else None,
            source_type=formal_source_type,
            source_ref=f"cashflow-import:{batch.id}:{candidate.id}",
            external_key=candidate.external_key,
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        try:
            with db.begin_nested():
                db.add(transaction)
                db.flush()
                sync_transaction_fact(
                    db,
                    transaction=transaction,
                    user_id=user_id,
                    assume_missing=True,
                )
                record_transaction_ledger_revision(
                    db,
                    owner=owner,
                    transaction=transaction,
                    operation="create",
                    before_snapshot=None,
                    reason=f"用户确认导入候选 #{candidate.id}",
                )
        except IntegrityError:
            existing = db.query(FinancialTransaction).filter(
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.source_type == formal_source_type,
                FinancialTransaction.external_key == candidate.external_key,
            ).first()
            if existing is None:
                db.rollback()
                raise import_error(409, "cashflow_import_confirmation_conflict", "确认发生并发冲突，请刷新后重试")
            candidate.status = "exact_duplicate"
            candidate.duplicate_transaction_id = existing.id
            evidence = dict(candidate.evidence or {})
            evidence["confirmation_resolved_at"] = datetime.utcnow().isoformat()
            candidate.evidence = evidence
            warnings = [dict(issue) for issue in (candidate.warnings or [])]
            _append_issue(
                warnings,
                field="external_key",
                code="EXACT_DUPLICATE",
                message="并发确认时发现该交易已经存在，未重复入账",
            )
            candidate.warnings = warnings
            continue
        except OperationalError as exc:
            db.rollback()
            if _is_retryable_mysql_conflict(exc):
                raise import_error(
                    409,
                    "cashflow_import_confirmation_conflict",
                    "并发确认繁忙，请刷新后重试",
                ) from exc
            raise
        candidate.status = "confirmed"
        candidate.transaction_id = transaction.id
        candidate.confirmed_at = datetime.utcnow()
        if candidate.external_key:
            exact_by_key[candidate.external_key] = transaction

    batch.updated_at = datetime.utcnow()
    db.flush()
    refresh_batch_counts(db, batch)
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_confirmation_conflict", "确认发生并发冲突，请刷新后重试") from exc
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_mysql_conflict(exc):
            raise import_error(
                409,
                "cashflow_import_confirmation_conflict",
                "并发确认繁忙，请刷新后重试",
            ) from exc
        raise
    db.refresh(batch)
    refreshed = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id.in_(requested),
        FinancialTransactionCandidate.user_id == user_id,
    ).all()
    return _confirmation_report(batch, refreshed)


def confirm_candidates(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportConfirmRequest,
) -> dict:
    try:
        return _confirm_candidates_locked(
            db,
            user_id=user_id,
            batch_id=batch_id,
            data=data,
        )
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_mysql_conflict(exc):
            raise import_error(
                409,
                "cashflow_import_confirmation_conflict",
                "同一账本正在写入，请刷新后重试",
            ) from exc
        raise
