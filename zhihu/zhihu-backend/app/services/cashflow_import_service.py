from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, tuple_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.models.cashflow import (
    EconomicFact,
    EconomicFactAllocation,
    FinancialCategory,
    FinancialTransaction,
)
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.contract import Contract, ContractReviewSnapshot
from app.models.offer import Offer
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.resume import ResumeVersion
from app.schemas.cashflow_import import (
    FinancialImportCandidateGroupMergeRequest,
    FinancialImportCandidateMergeRequest,
    FinancialImportCandidateMergeUndoRequest,
    FinancialImportCandidateUpdate,
    FinancialImportConfirmRequest,
    FinancialTransactionCandidateResponse,
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
    economic_fact_snapshot,
    get_available_category,
    lock_financial_ledger_owner,
    record_economic_fact_revision,
    record_transaction_ledger_revision,
)
from app.services.economic_fact_service import (
    merge_fact_evidence_locked,
    sync_transaction_fact,
)
from app.services.personal_attachment_service import (
    enqueue_attachment_cleanup,
    process_attachment_cleanup_jobs,
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
FORMAL_DUPLICATE_AI_REVIEW_VERSION = "cashflow-import-formal-duplicate-ai-v2"
CANDIDATE_DUPLICATE_AI_REVIEW_VERSION = "cashflow-import-candidate-duplicate-ai-v1"
MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL = 30
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
class _FormalFactDuplicateTarget:
    transaction: FinancialTransaction
    fact: EconomicFact


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


def _positive_ocr_locator_int(value: object, *, default: int | None = None) -> int | None:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _ocr_row_locations(evidence: object) -> set[tuple[int, int, int]]:
    """Return explicit ``(image, slice, OCR line)`` source positions.

    Long-image candidates normally carry the position inside ``source_slices``.
    Older candidates only have the same fields at the evidence root, so both
    shapes must participate in the guard.
    """

    if not isinstance(evidence, dict):
        return set()
    raw_sources = evidence.get("source_slices")
    sources = [
        source
        for source in (raw_sources if isinstance(raw_sources, list) else [])
        if isinstance(source, dict)
    ]
    sources.append(evidence)
    locations: set[tuple[int, int, int]] = set()
    for source in sources:
        locator = source.get("source_locator")
        locator = locator if isinstance(locator, dict) else {}
        slice_sequence = _positive_ocr_locator_int(source.get("slice_sequence"))
        line_index = _positive_ocr_locator_int(source.get("ocr_line_index"))
        if slice_sequence is None or line_index is None:
            continue
        image_sequence = _positive_ocr_locator_int(
            source.get("source_image_sequence"),
            default=_positive_ocr_locator_int(
                locator.get("source_image_sequence"),
                default=1,
            ),
        )
        locations.add((image_sequence or 1, slice_sequence, line_index))
    return locations


def _same_batch_distinct_source_ocr_rows(
    *,
    left_batch_id: int | None,
    left_evidence: object,
    right_batch_id: int | None,
    right_evidence: object,
) -> bool:
    """Prove two sibling candidates are different rows in one source slice.

    An exact shared OCR-row location remains eligible for duplicate handling.
    Candidates from adjacent slices also remain eligible because overlap
    recognition intentionally represents one source row in two slices.
    """

    return _same_batch_distinct_source_ocr_row_locations(
        left_batch_id=left_batch_id,
        left_locations=_ocr_row_locations(left_evidence),
        right_batch_id=right_batch_id,
        right_locations=_ocr_row_locations(right_evidence),
    )


def _same_batch_distinct_source_ocr_row_locations(
    *,
    left_batch_id: int | None,
    left_locations: set[tuple[int, int, int]] | frozenset[tuple[int, int, int]],
    right_batch_id: int | None,
    right_locations: set[tuple[int, int, int]] | frozenset[tuple[int, int, int]],
) -> bool:
    if left_batch_id is None or left_batch_id != right_batch_id:
        return False
    if not left_locations or not right_locations:
        return False
    if left_locations.intersection(right_locations):
        return False
    return any(
        left_image == right_image
        and left_slice == right_slice
        and left_line != right_line
        for left_image, left_slice, left_line in left_locations
        for right_image, right_slice, right_line in right_locations
    )


class _DuplicateTextIndex:
    """Bounded deterministic sibling matcher.

    Small coarse buckets are scanned exactly. Once a bucket grows beyond the
    explicit budget, later rows conservatively require review; this bounds both
    CPU and memory without allowing an adversarial same-day/same-amount file to
    bypass duplicate protection.
    """

    MAX_EXACT_SIGNATURES = 100

    def __init__(self) -> None:
        self._signatures: list[
            tuple[tuple[str, ...], int | None, frozenset[tuple[int, int, int]]]
        ] = []
        self._source_rows: list[
            tuple[int | None, frozenset[tuple[int, int, int]]]
        ] = []
        self._overflowed = False

    def has_match(
        self,
        merchant: str | None,
        description: str | None,
        *,
        batch_id: int | None = None,
        evidence: object = None,
    ) -> bool:
        if not self._signatures and not self._overflowed:
            return False
        locations = frozenset(_ocr_row_locations(evidence))
        if self._overflowed:
            # Overflow remains conservative, except where every prior entry is
            # independently proven to be a different OCR row in this slice.
            return any(
                not _same_batch_distinct_source_ocr_row_locations(
                    left_batch_id=batch_id,
                    left_locations=locations,
                    right_batch_id=existing_batch_id,
                    right_locations=existing_locations,
                )
                for existing_batch_id, existing_locations in self._source_rows
            )
        signature = duplicate_text_signature(merchant, description)
        return any(
            duplicate_signatures_are_similar(signature, existing)
            and not _same_batch_distinct_source_ocr_row_locations(
                left_batch_id=batch_id,
                left_locations=locations,
                right_batch_id=existing_batch_id,
                right_locations=existing_locations,
            )
            for existing, existing_batch_id, existing_locations in self._signatures
        )

    def add(
        self,
        merchant: str | None,
        description: str | None,
        *,
        batch_id: int | None = None,
        evidence: object = None,
    ) -> None:
        locations = frozenset(_ocr_row_locations(evidence))
        self._source_rows.append((batch_id, locations))
        if self._overflowed:
            return
        if len(self._signatures) >= self.MAX_EXACT_SIGNATURES:
            self._signatures.clear()
            self._overflowed = True
            return
        self._signatures.append((
            duplicate_text_signature(merchant, description),
            batch_id,
            locations,
        ))


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
        # The shared batch table also backs payslip recognition.  Cashflow
        # endpoints must never expose or mutate that separate workflow.
        FinancialImportBatch.source_type != "payslip",
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
        FinancialImportBatch.source_type != "payslip",
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


def _non_cashflow_attachment_reference_ids(
    db: Session,
    attachment_ids: set[int],
) -> set[int]:
    """Return private attachments still referenced outside cashflow imports.

    These are every current model-level foreign key to
    ``personal_attachment_versions`` outside the cashflow batch/artifact
    tables.  Keeping this inventory together makes a later attachment-owning
    model visible in review instead of silently relying on ``ON DELETE SET
    NULL`` and destroying another module's source evidence.
    """

    if not attachment_ids:
        return set()
    references: set[int] = set()
    for query in (
        db.query(ResumeVersion.attachment_version_id).filter(
            ResumeVersion.attachment_version_id.in_(attachment_ids),
        ).with_for_update(),
        db.query(Offer.source_attachment_id).filter(
            Offer.source_attachment_id.in_(attachment_ids),
        ).with_for_update(),
        db.query(Contract.source_attachment_id).filter(
            Contract.source_attachment_id.in_(attachment_ids),
        ).with_for_update(),
        db.query(ContractReviewSnapshot.attachment_version_id).filter(
            ContractReviewSnapshot.attachment_version_id.in_(attachment_ids),
        ).with_for_update(),
    ):
        references.update(
            int(value)
            for (value,) in query.all()
            if value is not None
        )
    return references


def delete_import_batch(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    expected_version: int,
) -> dict:
    """Delete one resumable recognition batch while preserving formal ledger rows.

    Candidate-to-transaction links are provenance pointers, not ownership of the
    confirmed transaction.  The database phase therefore removes only the
    batch, its candidates, recognition artifacts and unshared private
    attachment metadata.  Every physical attachment gets a durable cleanup job
    in the same transaction; file deletion is attempted only after that
    transaction commits and may be retried by the existing cleanup worker.
    """

    # Confirmation takes this lock before locking the batch.  Keep the same
    # order so deletion cannot race a formal write or introduce a deadlock.
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.version != expected_version:
        raise import_error(
            409,
            "cashflow_import_stale_batch",
            "导入批次已更新，请刷新后再删除",
        )

    candidate_rows = db.query(
        FinancialTransactionCandidate.id,
        FinancialTransactionCandidate.transaction_id,
    ).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).all()
    transaction_ids = sorted({
        int(transaction_id)
        for _, transaction_id in candidate_rows
        if transaction_id is not None
    })
    preserved_transaction_count = (
        db.query(func.count(FinancialTransaction.id))
        .filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.id.in_(transaction_ids),
        )
        .scalar()
        if transaction_ids
        else 0
    )

    artifact_rows = db.query(
        FinancialRecognitionArtifact.id,
        FinancialRecognitionArtifact.attachment_version_id,
    ).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
    ).all()
    attachment_ids = {
        int(attachment_id)
        for _, attachment_id in artifact_rows
        if attachment_id is not None
    }
    if batch.attachment_version_id is not None:
        attachment_ids.add(int(batch.attachment_version_id))

    # Only attachment versions owned by this import domain may be retired.  A
    # malformed legacy FK must never let deleting a cashflow batch destroy a
    # resume, Offer, contract or another module's private source file.  Lock the
    # eligible parent rows before checking child references so concurrent FK
    # inserts either become visible to the locking reads below or wait until
    # this transaction commits.
    owned_cashflow_attachments = (
        db.query(PersonalAttachmentVersion)
        .filter(
            PersonalAttachmentVersion.user_id == user_id,
            PersonalAttachmentVersion.document_type == "cashflow_import",
            PersonalAttachmentVersion.id.in_(attachment_ids),
        )
        .with_for_update()
        .all()
        if attachment_ids
        else []
    )
    eligible_attachment_ids = {
        int(attachment.id) for attachment in owned_cashflow_attachments
    }

    # An attachment is normally unique to one derived slice.  Still avoid
    # retiring metadata if a legacy/shared import row references the same ID.
    externally_referenced_attachment_ids: set[int] = set()
    if eligible_attachment_ids:
        externally_referenced_attachment_ids.update(
            int(value)
            for (value,) in db.query(FinancialImportBatch.attachment_version_id)
            .filter(
                FinancialImportBatch.id != batch_id,
                FinancialImportBatch.attachment_version_id.in_(eligible_attachment_ids),
            )
            .with_for_update()
            .all()
            if value is not None
        )
        externally_referenced_attachment_ids.update(
            _non_cashflow_attachment_reference_ids(db, eligible_attachment_ids)
        )
        externally_referenced_attachment_ids.update(
            int(value)
            for (value,) in db.query(FinancialRecognitionArtifact.attachment_version_id)
            .filter(
                FinancialRecognitionArtifact.batch_id != batch_id,
                FinancialRecognitionArtifact.attachment_version_id.in_(eligible_attachment_ids),
            )
            .with_for_update()
            .all()
            if value is not None
        )
    retireable_attachment_ids = (
        eligible_attachment_ids - externally_referenced_attachment_ids
    )
    attachments = [
        attachment
        for attachment in owned_cashflow_attachments
        if int(attachment.id) in retireable_attachment_ids
    ]

    deleted_candidate_count = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).delete(synchronize_session=False)
    deleted_artifact_count = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
    ).delete(synchronize_session=False)
    # Clear the legacy direct reference before retiring its metadata.  Derived
    # artifact references were removed immediately above.
    batch.attachment_version_id = None
    db.flush()

    cleanup_job_ids: list[int] = []
    for attachment in attachments:
        cleanup_job_ids.append(enqueue_attachment_cleanup(db, attachment))
        db.delete(attachment)
    db.delete(batch)
    db.flush()
    db.commit()

    cleanup_job_ids = sorted(set(cleanup_job_ids))
    cleanup_completed_ids: list[int] = []
    cleanup_failed_ids: list[int] = []
    physical_cleanup_status = "not_needed"
    if cleanup_job_ids:
        try:
            cleanup = process_attachment_cleanup_jobs(db, cleanup_job_ids)
        except Exception:
            # The database deletion has already committed.  Roll back only the
            # failed cleanup attempt; durable pending jobs remain retryable.
            db.rollback()
            cleanup_failed_ids = cleanup_job_ids
            physical_cleanup_status = "retry_pending"
        else:
            cleanup_completed_ids = sorted(cleanup["completed_ids"])
            cleanup_failed_ids = sorted(cleanup["failed_ids"])
            physical_cleanup_status = (
                "retry_pending" if cleanup_failed_ids else "completed"
            )

    return {
        "batch_id": batch_id,
        "deleted_candidate_count": int(deleted_candidate_count or 0),
        "deleted_artifact_count": int(deleted_artifact_count or 0),
        "deleted_attachment_count": len(attachments),
        "preserved_transaction_count": int(preserved_transaction_count or 0),
        "cleanup_job_ids": cleanup_job_ids,
        "cleanup_completed_ids": cleanup_completed_ids,
        "cleanup_failed_ids": cleanup_failed_ids,
        "physical_cleanup_status": physical_cleanup_status,
    }


def _candidate_duplicate_transaction_ids(
    candidate: FinancialTransactionCandidate,
) -> list[int]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    raw_ids: list[object] = list(evidence.get("possible_duplicate_transaction_ids") or [])
    replay = evidence.get("same_source_replay_match")
    if isinstance(replay, dict):
        raw_ids.extend(replay.get("transaction_ids") or [])
    if candidate.duplicate_transaction_id is not None:
        raw_ids.append(candidate.duplicate_transaction_id)
    return sorted({
        int(value)
        for value in raw_ids
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    })[:MAX_EXACT_FUZZY_BUCKET_SCAN]


def _candidate_duplicate_fact_target_ids(
    candidate: FinancialTransactionCandidate,
) -> list[tuple[int, int]]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    rows = evidence.get("possible_duplicate_fact_targets")
    if not isinstance(rows, list):
        return []
    targets: set[tuple[int, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            transaction_id = int(row["transaction_id"])
            fact_id = int(row["fact_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if transaction_id > 0 and fact_id > 0:
            targets.add((transaction_id, fact_id))
    return sorted(targets)[:MAX_EXACT_FUZZY_BUCKET_SCAN]


def _candidate_duplicate_candidate_ids(
    candidate: FinancialTransactionCandidate,
) -> list[int]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    return sorted({
        int(value)
        for key in ("exact_duplicate_candidate_ids", "possible_duplicate_candidate_ids")
        for value in (evidence.get(key) or [])
        if (isinstance(value, int) or (isinstance(value, str) and value.isdigit()))
        and int(value) != candidate.id
    })[:MAX_EXACT_FUZZY_BUCKET_SCAN]


def _candidate_duplicate_ai_context_hash(
    *,
    batch: FinancialImportBatch,
    candidate: FinancialTransactionCandidate,
    matches: Sequence[tuple[FinancialTransactionCandidate, FinancialImportBatch]],
) -> str:
    def snapshot(row: FinancialTransactionCandidate, source_type: str) -> dict[str, object]:
        return {
            "id": row.id,
            "batch_id": row.batch_id,
            "source_type": source_type,
            "fingerprint": row.fingerprint,
            "external_key_hash": hashlib.sha256(row.external_key.encode("utf-8")).hexdigest() if row.external_key else None,
            "direction": row.direction,
            "amount": format(Decimal(row.amount), "f") if row.amount is not None else None,
            "currency": row.currency,
            "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
            "merchant": row.merchant,
            "description": row.description,
            "status": row.status,
        }

    context = {
        "version": CANDIDATE_DUPLICATE_AI_REVIEW_VERSION,
        "candidate": snapshot(candidate, batch.source_type),
        "matches": [
            snapshot(row, match_batch.source_type)
            for row, match_batch in sorted(matches, key=lambda item: item[0].id)
        ],
    }
    return hashlib.sha256(
        json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _candidate_duplicate_ai_review(candidate: FinancialTransactionCandidate) -> dict[str, object] | None:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    value = evidence.get("candidate_duplicate_ai_review")
    return value if isinstance(value, dict) else None


def _formal_duplicate_ai_context_hash(
    *,
    batch: FinancialImportBatch,
    candidate: FinancialTransactionCandidate,
    transactions: Sequence[FinancialTransaction],
    fact_targets: Sequence[_FormalFactDuplicateTarget] = (),
) -> str:
    """Bind one AI explanation to the exact program candidate/target facts."""

    context = {
        "version": FORMAL_DUPLICATE_AI_REVIEW_VERSION,
        "candidate": {
            "id": candidate.id,
            "source_type": batch.source_type,
            "fingerprint": candidate.fingerprint,
            "direction": candidate.direction,
            "amount": format(Decimal(candidate.amount), "f") if candidate.amount is not None else None,
            "currency": candidate.currency or "CNY",
            "transaction_date": candidate.transaction_date.isoformat() if candidate.transaction_date else None,
            "merchant": candidate.merchant,
            "description": candidate.description,
        },
        "targets": [
            {
                "transaction_id": transaction.id,
                "direction": transaction.direction,
                "amount": format(Decimal(transaction.amount), "f"),
                "currency": transaction.currency,
                "transaction_date": transaction.transaction_date.isoformat(),
                "merchant": transaction.merchant,
                "description": transaction.description,
                "source_type": transaction.source_type,
                "status": transaction.status,
                "deleted_at": transaction.deleted_at.isoformat() if transaction.deleted_at else None,
                "updated_at": transaction.updated_at.isoformat() if transaction.updated_at else None,
            }
            for transaction in sorted(transactions, key=lambda row: row.id)
        ],
        "fact_targets": [
            {
                "transaction_id": target.transaction.id,
                "fact_id": target.fact.id,
                "fact_type": target.fact.fact_type,
                "fact_title": target.fact.title,
                "fact_description": target.fact.description,
                "fact_amount": format(Decimal(target.fact.amount), "f"),
                "fact_date": target.fact.occurred_date.isoformat(),
                "fact_status": target.fact.status,
                "fact_updated_at": target.fact.updated_at.isoformat() if target.fact.updated_at else None,
            }
            for target in sorted(fact_targets, key=lambda item: (item.transaction.id, item.fact.id))
        ],
    }
    payload = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _formal_duplicate_ai_review(
    candidate: FinancialTransactionCandidate,
) -> dict[str, object] | None:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    value = evidence.get("formal_duplicate_ai_review")
    return value if isinstance(value, dict) else None


def _active_duplicate_transactions(
    transactions: Iterable[FinancialTransaction],
) -> list[FinancialTransaction]:
    return [
        transaction
        for transaction in transactions
        if transaction.status == "confirmed" and transaction.deleted_at is None
    ]


def _parse_duplicate_ai_output(output: str | None) -> dict[tuple[int, int], dict[str, str]]:
    if not output:
        return {}
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    rows = payload.get("assessments") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    result: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        transaction_id = row.get("transaction_id")
        assessment = row.get("assessment")
        if (
            not isinstance(candidate_id, int)
            or not isinstance(transaction_id, int)
            or assessment not in {"likely", "unlikely", "uncertain"}
        ):
            continue
        reason = re.sub(r"\s+", " ", str(row.get("reason") or "")).strip()
        result[(candidate_id, transaction_id)] = {
            "assessment": assessment,
            "reason": reason[:300] or "AI 未提供可核对理由",
        }
    return result


def _parse_candidate_duplicate_ai_output(output: str | None) -> dict[tuple[int, int], dict[str, str]]:
    if not output:
        return {}
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    rows = payload.get("assessments") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    result: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        matched_candidate_id = row.get("matched_candidate_id")
        assessment = row.get("assessment")
        if (
            not isinstance(candidate_id, int)
            or not isinstance(matched_candidate_id, int)
            or assessment not in {"likely", "unlikely", "uncertain"}
        ):
            continue
        reason = re.sub(r"\s+", " ", str(row.get("reason") or "")).strip()
        result[(candidate_id, matched_candidate_id)] = {
            "assessment": assessment,
            "reason": reason[:300] or "AI 未提供可核对理由",
        }
    return result


def _merge_target_block_reason(
    *,
    candidate: FinancialTransactionCandidate,
    candidate_source_type: str,
    transaction: FinancialTransaction,
    fact: EconomicFact | None,
) -> str | None:
    if candidate.status == "exact_duplicate":
        return "精确重复应复用或排除，不能作为第二份证据"
    if transaction.status != "confirmed" or transaction.deleted_at is not None:
        return "目标流水已撤销或删除"
    if transaction.source_type == candidate_source_type:
        return "同一来源重复应复用或排除，不能作为第二份证据"
    if transaction.direction != candidate.direction:
        return "资金方向不一致，不能并入同一经济事实"
    if transaction.currency != (candidate.currency or "CNY"):
        return "币种不一致，不能并入同一经济事实"
    if fact is None:
        return "目标流水尚未建立可核对的经济事实"
    if fact.status != "confirmed" or fact.primary_transaction_id not in {None, transaction.id}:
        return "目标经济事实已撤销或变更，请先在可信账本核对"
    if Decimal(fact.amount) <= Decimal("0.00"):
        return "目标经济事实已无可分配金额"
    return None


def candidate_payloads(
    db: Session,
    *,
    batch: FinancialImportBatch,
    candidates: Sequence[FinancialTransactionCandidate],
) -> list[FinancialTransactionCandidateResponse]:
    """Serialize candidates with bounded, user-owned duplicate fact summaries."""
    duplicate_ids = sorted({
        transaction_id
        for candidate in candidates
        for transaction_id in _candidate_duplicate_transaction_ids(candidate)
    })
    duplicate_candidate_ids = sorted({
        sibling_id
        for candidate in candidates
        for sibling_id in _candidate_duplicate_candidate_ids(candidate)
    })
    transactions = {
        row.id: row
        for row in db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == batch.user_id,
            FinancialTransaction.id.in_(duplicate_ids),
        ).all()
    } if duplicate_ids else {}
    primary_facts = {
        row.primary_transaction_id: row
        for row in db.query(EconomicFact).filter(
            EconomicFact.user_id == batch.user_id,
            EconomicFact.primary_transaction_id.in_(duplicate_ids),
        ).all()
    } if duplicate_ids else {}
    duplicate_fact_ids = sorted({
        fact_id
        for candidate in candidates
        for _, fact_id in _candidate_duplicate_fact_target_ids(candidate)
    })
    facts_by_id = {
        row.id: row
        for row in db.query(EconomicFact).filter(
            EconomicFact.user_id == batch.user_id,
            EconomicFact.id.in_(duplicate_fact_ids),
            EconomicFact.status == "confirmed",
        ).all()
    } if duplicate_fact_ids else {}
    sibling_candidates = {
        row.id: row
        for row in db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == batch.user_id,
            FinancialTransactionCandidate.id.in_(duplicate_candidate_ids),
            FinancialTransactionCandidate.status.in_({
                "ready", "needs_review", "possible_duplicate", "exact_duplicate",
            }),
        ).all()
    } if duplicate_candidate_ids else {}
    sibling_batch_ids = {row.batch_id for row in sibling_candidates.values()}
    sibling_batches = {
        row.id: row
        for row in db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == batch.user_id,
            FinancialImportBatch.id.in_(sibling_batch_ids),
        ).all()
    } if sibling_batch_ids else {}
    candidate_source_type = _formal_source_type(batch.source_type)
    payloads: list[FinancialTransactionCandidateResponse] = []
    for candidate in candidates:
        candidate_transactions = [
            transactions[transaction_id]
            for transaction_id in _candidate_duplicate_transaction_ids(candidate)
            if transaction_id in transactions
        ]
        active_ai_transactions = _active_duplicate_transactions(candidate_transactions)
        active_ai_fact_targets = [
            _FormalFactDuplicateTarget(
                transaction=transactions[transaction_id],
                fact=facts_by_id[fact_id],
            )
            for transaction_id, fact_id in _candidate_duplicate_fact_target_ids(candidate)
            if transaction_id in transactions and fact_id in facts_by_id
        ]
        current_ai_context_hash = (
            _formal_duplicate_ai_context_hash(
                batch=batch,
                candidate=candidate,
                transactions=active_ai_transactions,
                fact_targets=active_ai_fact_targets,
            )
            if active_ai_transactions
            else None
        )
        stored_ai_review = _formal_duplicate_ai_review(candidate)
        stored_ai_assessments = (
            stored_ai_review.get("assessments")
            if stored_ai_review
            and stored_ai_review.get("version") == FORMAL_DUPLICATE_AI_REVIEW_VERSION
            and stored_ai_review.get("context_hash") == current_ai_context_hash
            else None
        )
        if not isinstance(stored_ai_assessments, dict):
            stored_ai_assessments = {}
        candidate_match_rows = [
            (sibling_candidates[sibling_id], sibling_batches[sibling_candidates[sibling_id].batch_id])
            for sibling_id in _candidate_duplicate_candidate_ids(candidate)
            if sibling_id in sibling_candidates
            and sibling_candidates[sibling_id].batch_id in sibling_batches
        ]
        candidate_ai_context_hash = (
            _candidate_duplicate_ai_context_hash(
                batch=batch,
                candidate=candidate,
                matches=candidate_match_rows,
            )
            if candidate_match_rows
            else None
        )
        stored_candidate_review = _candidate_duplicate_ai_review(candidate)
        stored_candidate_assessments = (
            stored_candidate_review.get("assessments")
            if stored_candidate_review
            and stored_candidate_review.get("version") == CANDIDATE_DUPLICATE_AI_REVIEW_VERSION
            and stored_candidate_review.get("context_hash") == candidate_ai_context_hash
            else None
        )
        if not isinstance(stored_candidate_assessments, dict):
            stored_candidate_assessments = {}
        matches = []
        explicit_targets = _candidate_duplicate_fact_target_ids(candidate)
        target_pairs = list(explicit_targets)
        explicit_transaction_ids = {transaction_id for transaction_id, _ in explicit_targets}
        target_pairs.extend(
            (transaction_id, primary_facts[transaction_id].id)
            for transaction_id in _candidate_duplicate_transaction_ids(candidate)
            if transaction_id not in explicit_transaction_ids
            and transaction_id in primary_facts
        )
        for transaction_id, fact_id in sorted(set(target_pairs)):
            transaction = transactions.get(transaction_id)
            fact = facts_by_id.get(fact_id) or primary_facts.get(transaction_id)
            if transaction is None or fact is None or fact.id != fact_id:
                continue
            block_reason = _merge_target_block_reason(
                candidate=candidate,
                candidate_source_type=candidate_source_type,
                transaction=transaction,
                fact=fact,
            )
            reasons = ["同日同额或摘要相近，需要核对是否为同一笔钱"]
            if fact.primary_transaction_id is None:
                reasons.append("已精确定位到该流水拆分后的具体经济事实")
            if transaction.source_type != candidate_source_type:
                reasons.append("来自不同账单来源，可能是同一经济事实的多份证据")
            ai_value = stored_ai_assessments.get(str(transaction.id))
            if not isinstance(ai_value, dict):
                ai_value = {}
            ai_status = ai_value.get("status")
            if ai_status not in {"completed", "unavailable"}:
                ai_status = "not_requested"
            ai_assessment = ai_value.get("assessment")
            if ai_assessment not in {"likely", "unlikely", "uncertain"}:
                ai_assessment = None
            ai_reason = re.sub(r"\s+", " ", str(ai_value.get("reason") or "")).strip()[:300] or None
            matches.append({
                "transaction_id": transaction.id,
                "economic_fact_id": fact.id,
                "economic_fact_title": fact.title,
                "economic_fact_description": fact.description,
                "economic_fact_amount": fact.amount,
                "is_split_fact": fact.primary_transaction_id is None,
                "direction": transaction.direction,
                "amount": transaction.amount,
                "available_amount": (
                    max(Decimal("0.00"), Decimal(fact.amount))
                    if fact.status == "confirmed"
                    else Decimal("0.00")
                ),
                "currency": transaction.currency,
                "transaction_date": transaction.transaction_date,
                "merchant": transaction.merchant,
                "description": transaction.description,
                "source_type": transaction.source_type,
                "can_merge_as_evidence": block_reason is None,
                "merge_block_reason": block_reason,
                "reasons": reasons,
                "ai_status": ai_status,
                "ai_assessment": ai_assessment,
                "ai_reason": ai_reason,
            })
        base_payload = FinancialTransactionCandidateResponse.model_validate(candidate).model_dump()
        base_payload["duplicate_matches"] = matches
        base_payload["duplicate_candidate_matches"] = []
        for sibling, sibling_batch in candidate_match_rows:
            ai_value = stored_candidate_assessments.get(str(sibling.id))
            if not isinstance(ai_value, dict):
                ai_value = {}
            ai_status = ai_value.get("status")
            if ai_status not in {"completed", "unavailable"}:
                ai_status = "not_requested"
            ai_assessment = ai_value.get("assessment")
            if ai_assessment not in {"likely", "unlikely", "uncertain"}:
                ai_assessment = None
            ai_reason = re.sub(r"\s+", " ", str(ai_value.get("reason") or "")).strip()[:300] or None
            base_payload["duplicate_candidate_matches"].append({
                "candidate_id": sibling.id,
                "batch_id": sibling.batch_id,
                "row_number": sibling.row_number,
                "version": sibling.version,
                "direction": sibling.direction,
                "amount": sibling.amount,
                "currency": sibling.currency,
                "transaction_date": sibling.transaction_date,
                "merchant": sibling.merchant,
                "description": sibling.description,
                "source_type": sibling_batch.source_type,
                "status": sibling.status,
                "reasons": [
                    "其他未确认批次中存在同日同额且商户或说明相近的候选",
                    "两边都尚未进入正式账本，不能由系统自动选择保留哪一条",
                ],
                "can_merge_candidate": _manual_candidate_merge_eligibility(
                    candidate,
                    sibling,
                )[0],
                "merge_block_reason": _manual_candidate_merge_eligibility(
                    candidate,
                    sibling,
                )[1],
                "ai_status": ai_status,
                "ai_assessment": ai_assessment,
                "ai_reason": ai_reason,
            })
        payloads.append(FinancialTransactionCandidateResponse.model_validate(base_payload))
    return payloads


def candidate_payload(
    db: Session,
    *,
    batch: FinancialImportBatch,
    candidate: FinancialTransactionCandidate,
) -> FinancialTransactionCandidateResponse:
    return candidate_payloads(db, batch=batch, candidates=[candidate])[0]


def review_formal_duplicate_candidates_with_ai(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    expected_data_epoch: int | None,
) -> dict[str, int]:
    """Explain unresolved formal-transaction duplicates without deciding them.

    Program matching remains authoritative for the duplicate set.  The model
    receives only bounded, redacted pair summaries and may return a tendency
    plus reason.  Candidate status, confidence, merge target and the formal
    ledger are never changed here.  Results are persisted only after the same
    candidate/target context is revalidated under the user's ledger lock.
    """

    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.status == "possible_duplicate",
    ).order_by(
        FinancialTransactionCandidate.row_number.asc(),
        FinancialTransactionCandidate.id.asc(),
    ).all()
    duplicate_ids = sorted({
        transaction_id
        for candidate in candidates
        for transaction_id in _candidate_duplicate_transaction_ids(candidate)
    })
    transactions = {
        transaction.id: transaction
        for transaction in db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.id.in_(duplicate_ids),
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
        ).all()
    } if duplicate_ids else {}
    duplicate_fact_ids = sorted({
        fact_id
        for candidate in candidates
        for _, fact_id in _candidate_duplicate_fact_target_ids(candidate)
    })
    facts = {
        fact.id: fact
        for fact in db.query(EconomicFact).filter(
            EconomicFact.user_id == user_id,
            EconomicFact.id.in_(duplicate_fact_ids),
            EconomicFact.status == "confirmed",
        ).all()
    } if duplicate_fact_ids else {}

    eligible_contexts: list[dict[str, object]] = []
    for candidate in candidates:
        active_transactions = [
            transactions[transaction_id]
            for transaction_id in _candidate_duplicate_transaction_ids(candidate)
            if transaction_id in transactions
        ]
        if not active_transactions:
            continue
        active_fact_targets = [
            _FormalFactDuplicateTarget(
                transaction=transactions[transaction_id],
                fact=facts[fact_id],
            )
            for transaction_id, fact_id in _candidate_duplicate_fact_target_ids(candidate)
            if transaction_id in transactions and fact_id in facts
        ]
        context_hash = _formal_duplicate_ai_context_hash(
            batch=batch,
            candidate=candidate,
            transactions=active_transactions,
            fact_targets=active_fact_targets,
        )
        stored = _formal_duplicate_ai_review(candidate)
        if (
            stored
            and stored.get("version") == FORMAL_DUPLICATE_AI_REVIEW_VERSION
            and stored.get("context_hash") == context_hash
        ):
            continue
        eligible_contexts.append({
            "candidate_id": candidate.id,
            "context_hash": context_hash,
            "transaction_ids": [transaction.id for transaction in active_transactions],
            "fact_targets": [
                {"transaction_id": target.transaction.id, "fact_id": target.fact.id}
                for target in active_fact_targets
            ],
            "pairs": [
                {
                    "candidate_id": candidate.id,
                    "transaction_id": transaction.id,
                    "direction": candidate.direction,
                    "amount": format(Decimal(candidate.amount), "f") if candidate.amount is not None else None,
                    "date": candidate.transaction_date.isoformat() if candidate.transaction_date else None,
                    "same_date": candidate.transaction_date == transaction.transaction_date,
                    "same_amount": candidate.amount is not None and Decimal(candidate.amount) == Decimal(transaction.amount),
                    "candidate_source": batch.source_type,
                    "target_source": transaction.source_type,
                    "candidate_merchant": redact_cashflow_text(candidate.merchant or "", max_length=120),
                    "candidate_description": redact_cashflow_text(candidate.description or "", max_length=200),
                    "target_merchant": redact_cashflow_text(transaction.merchant or "", max_length=120),
                    "target_description": redact_cashflow_text(transaction.description or "", max_length=200),
                    "program_reason": "程序发现同日同金额且商户或说明相近",
                    "matched_facts": [
                        {
                            "fact_id": target.fact.id,
                            "title": redact_cashflow_text(target.fact.title or "", max_length=120),
                            "description": redact_cashflow_text(target.fact.description or "", max_length=200),
                            "amount": format(Decimal(target.fact.amount), "f"),
                            "date": target.fact.occurred_date.isoformat(),
                            "is_split_fact": target.fact.primary_transaction_id is None,
                        }
                        for target in active_fact_targets
                        if target.transaction.id == transaction.id
                    ],
                }
                for transaction in active_transactions
            ],
        })

    selected_contexts: list[dict[str, object]] = []
    selected_pair_count = 0
    for context in eligible_contexts:
        pair_count = len(context["pairs"])
        # Never review only part of one candidate while persisting the hash of
        # its full duplicate set.  A very wide ambiguous candidate stays for
        # human review instead of receiving a misleading partial AI verdict.
        if pair_count > MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            continue
        if selected_contexts and selected_pair_count + pair_count > MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            break
        selected_contexts.append(context)
        selected_pair_count += pair_count
        if selected_pair_count >= MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            break

    eligible_candidate_count = len(eligible_contexts)
    if not selected_contexts:
        db.rollback()
        return {
            "batch_id": batch_id,
            "eligible_candidate_count": eligible_candidate_count,
            "reviewed_candidate_count": 0,
            "completed_assessment_count": 0,
            "unavailable_candidate_count": 0,
            "remaining_candidate_count": eligible_candidate_count,
        }

    safe_pairs = [pair for context in selected_contexts for pair in context["pairs"]]
    db.rollback()
    from app.services.payslip_intake_service import _call_payslip_llm

    prompt = """你是收支守护的疑似重复判断助手。程序已筛出同日、同金额且商户或说明相近的候选和已有正式流水。
你只能辅助判断两条记录是否较可能代表同一笔钱；不能修改金额、不能选择合并目标、不能改变置信等级、不能确认、不能写账。
银行卡、微信、支付宝间的同一笔资金可能是多份证据；退款、报销和账户转账也要结合文字谨慎判断。证据不足必须输出 uncertain。
只输出严格 JSON：{"assessments":[{"candidate_id":1,"transaction_id":2,"assessment":"likely|unlikely|uncertain","reason":"一句可由用户核对的理由"}]}
待判断记录：
""" + json.dumps(safe_pairs, ensure_ascii=False)
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_import_duplicate_reasoning",
        max_tokens=2400,
    )
    parsed_assessments = _parse_duplicate_ai_output(output)

    owner = lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    if expected_data_epoch is not None and owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "AI 判断期间账户数据已被清空，本次判断未保存",
        )
    current_batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    selected_candidate_ids = [int(context["candidate_id"]) for context in selected_contexts]
    current_candidates = {
        candidate.id: candidate
        for candidate in db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.batch_id == batch_id,
            FinancialTransactionCandidate.id.in_(selected_candidate_ids),
        ).with_for_update().all()
    }
    selected_transaction_ids = sorted({
        int(transaction_id)
        for context in selected_contexts
        for transaction_id in context["transaction_ids"]
    })
    current_transactions = {
        transaction.id: transaction
        for transaction in db.query(FinancialTransaction).filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.id.in_(selected_transaction_ids),
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
        ).all()
    }
    selected_fact_ids = sorted({
        int(target["fact_id"])
        for context in selected_contexts
        for target in context["fact_targets"]
    })
    current_facts = {
        fact.id: fact
        for fact in db.query(EconomicFact).filter(
            EconomicFact.user_id == user_id,
            EconomicFact.id.in_(selected_fact_ids),
            EconomicFact.status == "confirmed",
        ).all()
    } if selected_fact_ids else {}

    reviewed_candidate_count = 0
    completed_assessment_count = 0
    unavailable_candidate_count = 0
    for context in selected_contexts:
        candidate_id = int(context["candidate_id"])
        candidate = current_candidates.get(candidate_id)
        target_rows = [
            current_transactions[transaction_id]
            for transaction_id in context["transaction_ids"]
            if transaction_id in current_transactions
        ]
        target_facts = [
            _FormalFactDuplicateTarget(
                transaction=current_transactions[int(target["transaction_id"])],
                fact=current_facts[int(target["fact_id"])],
            )
            for target in context["fact_targets"]
            if int(target["transaction_id"]) in current_transactions
            and int(target["fact_id"]) in current_facts
        ]
        if (
            candidate is None
            or candidate.status != "possible_duplicate"
            or len(target_rows) != len(context["transaction_ids"])
            or len(target_facts) != len(context["fact_targets"])
            or _formal_duplicate_ai_context_hash(
                batch=current_batch,
                candidate=candidate,
                transactions=target_rows,
                fact_targets=target_facts,
            ) != context["context_hash"]
        ):
            continue
        assessments: dict[str, dict[str, str]] = {}
        completed_for_candidate = 0
        for transaction_id in context["transaction_ids"]:
            assessment = parsed_assessments.get((candidate_id, int(transaction_id)))
            if assessment is None:
                assessments[str(transaction_id)] = {
                    "status": "unavailable",
                    "reason": "AI 本次未能给出稳定判断，仍需人工核对",
                }
                continue
            assessments[str(transaction_id)] = {
                "status": "completed",
                "assessment": assessment["assessment"],
                "reason": assessment["reason"],
            }
            completed_for_candidate += 1
        evidence = dict(candidate.evidence or {})
        evidence["formal_duplicate_ai_review"] = {
            "version": FORMAL_DUPLICATE_AI_REVIEW_VERSION,
            "context_hash": context["context_hash"],
            "reviewed_at": datetime.utcnow().isoformat(),
            "assessments": assessments,
        }
        candidate.evidence = evidence
        reviewed_candidate_count += 1
        completed_assessment_count += completed_for_candidate
        if completed_for_candidate == 0:
            unavailable_candidate_count += 1

    if reviewed_candidate_count:
        current_batch.updated_at = datetime.utcnow()
        db.commit()
    else:
        db.rollback()
    remaining_candidate_count = max(
        0,
        eligible_candidate_count - reviewed_candidate_count,
    )
    return {
        "batch_id": batch_id,
        "eligible_candidate_count": eligible_candidate_count,
        "reviewed_candidate_count": reviewed_candidate_count,
        "completed_assessment_count": completed_assessment_count,
        "unavailable_candidate_count": unavailable_candidate_count,
        "remaining_candidate_count": remaining_candidate_count,
    }


def review_candidate_duplicate_candidates_with_ai(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    expected_data_epoch: int | None,
) -> dict[str, int]:
    """Explain candidate-to-candidate matches; never select or confirm either side."""

    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.status == "possible_duplicate",
    ).order_by(
        FinancialTransactionCandidate.row_number.asc(),
        FinancialTransactionCandidate.id.asc(),
    ).all()
    sibling_ids = sorted({
        sibling_id
        for candidate in candidates
        for sibling_id in _candidate_duplicate_candidate_ids(candidate)
    })
    siblings = {
        row.id: row
        for row in db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.id.in_(sibling_ids),
            FinancialTransactionCandidate.status.in_({
                "ready", "needs_review", "possible_duplicate", "exact_duplicate",
            }),
        ).all()
    } if sibling_ids else {}
    sibling_batch_ids = {row.batch_id for row in siblings.values()}
    batches = {
        row.id: row
        for row in db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.id.in_({batch.id, *sibling_batch_ids}),
        ).all()
    }

    eligible_contexts: list[dict[str, object]] = []
    for candidate in candidates:
        match_rows = [
            (siblings[sibling_id], batches[siblings[sibling_id].batch_id])
            for sibling_id in _candidate_duplicate_candidate_ids(candidate)
            if sibling_id in siblings and siblings[sibling_id].batch_id in batches
        ]
        if not match_rows:
            continue
        context_hash = _candidate_duplicate_ai_context_hash(
            batch=batch,
            candidate=candidate,
            matches=match_rows,
        )
        stored = _candidate_duplicate_ai_review(candidate)
        if (
            stored
            and stored.get("version") == CANDIDATE_DUPLICATE_AI_REVIEW_VERSION
            and stored.get("context_hash") == context_hash
        ):
            continue
        eligible_contexts.append({
            "candidate_id": candidate.id,
            "context_hash": context_hash,
            "matched_candidate_ids": [row.id for row, _ in match_rows],
            "pairs": [
                {
                    "candidate_id": candidate.id,
                    "matched_candidate_id": row.id,
                    "same_date": candidate.transaction_date == row.transaction_date,
                    "same_amount": (
                        candidate.amount is not None
                        and row.amount is not None
                        and Decimal(candidate.amount) == Decimal(row.amount)
                    ),
                    "candidate_direction": candidate.direction,
                    "matched_direction": row.direction,
                    "candidate_source": batch.source_type,
                    "matched_source": match_batch.source_type,
                    "candidate_merchant": redact_cashflow_text(candidate.merchant or "", max_length=120),
                    "candidate_description": redact_cashflow_text(candidate.description or "", max_length=200),
                    "matched_merchant": redact_cashflow_text(row.merchant or "", max_length=120),
                    "matched_description": redact_cashflow_text(row.description or "", max_length=200),
                    "program_reason": "程序发现两个未确认候选同日同金额且商户或说明相近",
                }
                for row, match_batch in match_rows
            ],
        })

    selected_contexts: list[dict[str, object]] = []
    selected_pair_count = 0
    for context in eligible_contexts:
        pair_count = len(context["pairs"])
        if pair_count > MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            continue
        if selected_contexts and selected_pair_count + pair_count > MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            break
        selected_contexts.append(context)
        selected_pair_count += pair_count
        if selected_pair_count >= MAX_FORMAL_DUPLICATE_AI_PAIRS_PER_CALL:
            break

    eligible_candidate_count = len(eligible_contexts)
    if not selected_contexts:
        db.rollback()
        return {
            "batch_id": batch_id,
            "eligible_candidate_count": eligible_candidate_count,
            "reviewed_candidate_count": 0,
            "completed_assessment_count": 0,
            "unavailable_candidate_count": 0,
            "remaining_candidate_count": eligible_candidate_count,
        }

    safe_pairs = [pair for context in selected_contexts for pair in context["pairs"]]
    db.rollback()
    from app.services.payslip_intake_service import _call_payslip_llm

    prompt = """你是收支守护的跨批次候选重复判断助手。程序发现两条尚未入账的候选同日同额且文字相近。
你只能解释它们是否较可能来自同一笔交易；不能决定保留哪条、不能排除、不能确认、不能合并、不能写账。证据不足必须 uncertain。
只输出严格 JSON：{"assessments":[{"candidate_id":1,"matched_candidate_id":2,"assessment":"likely|unlikely|uncertain","reason":"一句可由用户核对的理由"}]}
待判断记录：
""" + json.dumps(safe_pairs, ensure_ascii=False)
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_import_candidate_duplicate_reasoning",
        max_tokens=2400,
    )
    parsed_assessments = _parse_candidate_duplicate_ai_output(output)

    owner = lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    if expected_data_epoch is not None and owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise import_error(409, "cashflow_import_data_cleared", "AI 判断期间账户数据已被清空，本次判断未保存")
    current_batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    all_candidate_ids = sorted({
        int(context["candidate_id"])
        for context in selected_contexts
    } | {
        int(match_id)
        for context in selected_contexts
        for match_id in context["matched_candidate_ids"]
    })
    current_rows = {
        row.id: row
        for row in db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.id.in_(all_candidate_ids),
        ).with_for_update().all()
    }
    current_batch_ids = {row.batch_id for row in current_rows.values()} | {current_batch.id}
    current_batches = {
        row.id: row
        for row in db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.id.in_(current_batch_ids),
        ).all()
    }

    reviewed_candidate_count = 0
    completed_assessment_count = 0
    unavailable_candidate_count = 0
    for context in selected_contexts:
        candidate_id = int(context["candidate_id"])
        candidate = current_rows.get(candidate_id)
        match_rows = [
            (current_rows[match_id], current_batches[current_rows[match_id].batch_id])
            for match_id in context["matched_candidate_ids"]
            if match_id in current_rows and current_rows[match_id].batch_id in current_batches
        ]
        if (
            candidate is None
            or candidate.status != "possible_duplicate"
            or len(match_rows) != len(context["matched_candidate_ids"])
            or _candidate_duplicate_ai_context_hash(
                batch=current_batch,
                candidate=candidate,
                matches=match_rows,
            ) != context["context_hash"]
        ):
            continue
        assessments: dict[str, dict[str, str]] = {}
        completed_for_candidate = 0
        for match_id in context["matched_candidate_ids"]:
            assessment = parsed_assessments.get((candidate_id, int(match_id)))
            if assessment is None:
                assessments[str(match_id)] = {
                    "status": "unavailable",
                    "reason": "AI 本次未能给出稳定判断，仍需人工核对",
                }
                continue
            assessments[str(match_id)] = {
                "status": "completed",
                "assessment": assessment["assessment"],
                "reason": assessment["reason"],
            }
            completed_for_candidate += 1
        evidence = dict(candidate.evidence or {})
        evidence["candidate_duplicate_ai_review"] = {
            "version": CANDIDATE_DUPLICATE_AI_REVIEW_VERSION,
            "context_hash": context["context_hash"],
            "reviewed_at": datetime.utcnow().isoformat(),
            "assessments": assessments,
        }
        candidate.evidence = evidence
        reviewed_candidate_count += 1
        completed_assessment_count += completed_for_candidate
        if completed_for_candidate == 0:
            unavailable_candidate_count += 1

    if reviewed_candidate_count:
        current_batch.updated_at = datetime.utcnow()
        db.commit()
    else:
        db.rollback()
    return {
        "batch_id": batch_id,
        "eligible_candidate_count": eligible_candidate_count,
        "reviewed_candidate_count": reviewed_candidate_count,
        "completed_assessment_count": completed_assessment_count,
        "unavailable_candidate_count": unavailable_candidate_count,
        "remaining_candidate_count": max(0, eligible_candidate_count - reviewed_candidate_count),
    }


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


def _load_formal_fact_duplicate_buckets(
    db: Session,
    *,
    user_id: int,
    coarse_keys: Iterable[tuple[str, Decimal, date]],
) -> tuple[
    dict[tuple[str, Decimal, date], list[_FormalFactDuplicateTarget]],
    dict[tuple[str, Decimal, date], _DuplicateBucketWatermark],
]:
    """Index cashflow-bearing facts, including split components, for dedup.

    Transaction-level matching cannot see a 30 yuan dining fact split out of a
    100 yuan mixed payment.  This index deliberately follows confirmed primary
    and split-component allocations back to their source transaction while
    retaining the fact amount/title used for the actual comparison.
    """
    ordered_keys = sorted(set(coarse_keys), key=lambda item: (item[0], item[1], item[2]))
    if not ordered_keys:
        return {}, {}
    rows = (
        db.query(EconomicFactAllocation, EconomicFact, FinancialTransaction)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .join(FinancialTransaction, FinancialTransaction.id == EconomicFactAllocation.transaction_id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role.in_({"primary", "split_component"}),
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
            tuple_(
                FinancialTransaction.direction,
                EconomicFact.amount,
                EconomicFact.occurred_date,
            ).in_(ordered_keys),
        )
        .order_by(EconomicFact.id.asc(), FinancialTransaction.id.asc())
        .limit(MAX_TOTAL_FUZZY_ROWS + 1)
        .all()
    )
    if len(rows) > MAX_TOTAL_FUZZY_ROWS:
        # A partial fact set would be actively misleading.  Mark every queried
        # key as overflow so the candidate remains a conservative human review.
        watermark = _DuplicateBucketWatermark(
            count=len(rows),
            max_transaction_id=max(int(fact.id) for _, fact, _ in rows),
        )
        return {}, {key: watermark for key in ordered_keys}
    buckets: dict[tuple[str, Decimal, date], list[_FormalFactDuplicateTarget]] = {}
    seen: set[tuple[int, int]] = set()
    for _, fact, transaction in rows:
        identity = (int(transaction.id), int(fact.id))
        if identity in seen:
            continue
        seen.add(identity)
        key = _coarse_duplicate_key(
            transaction.direction,
            Decimal(fact.amount),
            fact.occurred_date,
        )
        if key is not None:
            buckets.setdefault(key, []).append(
                _FormalFactDuplicateTarget(transaction=transaction, fact=fact)
            )
    overflow: dict[tuple[str, Decimal, date], _DuplicateBucketWatermark] = {}
    for key, targets in list(buckets.items()):
        if len(targets) <= MAX_EXACT_FUZZY_BUCKET_SCAN:
            continue
        overflow[key] = _DuplicateBucketWatermark(
            count=len(targets),
            max_transaction_id=max(target.fact.id for target in targets),
        )
        del buckets[key]
    return buckets, overflow


def _fact_target_text_is_similar(
    *,
    merchant: str | None,
    description: str | None,
    target: _FormalFactDuplicateTarget,
) -> bool:
    return duplicate_text_is_similar(
        merchant,
        description,
        target.fact.title,
        target.fact.description,
    ) or duplicate_text_is_similar(
        merchant,
        description,
        target.transaction.merchant,
        target.transaction.description,
    )


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


def _existing_fact_matches(
    db: Session,
    *,
    user_id: int,
    parsed: Sequence[ParsedCandidate],
) -> tuple[
    dict[str, list[_FormalFactDuplicateTarget]],
    dict[str, _DuplicateBucketWatermark],
]:
    coarse_keys = {
        key
        for item in parsed
        if (key := _coarse_duplicate_key(item.direction, item.amount, item.transaction_date)) is not None
    }
    if not coarse_keys:
        return {}, {}
    buckets, overflow = _load_formal_fact_duplicate_buckets(
        db,
        user_id=user_id,
        coarse_keys=coarse_keys,
    )
    possible: dict[str, list[_FormalFactDuplicateTarget]] = {}
    overflow_by_fingerprint: dict[str, _DuplicateBucketWatermark] = {}
    for item in parsed:
        key = _coarse_duplicate_key(item.direction, item.amount, item.transaction_date)
        if key is not None and key in overflow:
            overflow_by_fingerprint[item.fingerprint] = overflow[key]
            continue
        matches = [
            target
            for target in buckets.get(key, []) if key is not None
            if _fact_target_text_is_similar(
                merchant=item.merchant,
                description=item.description,
                target=target,
            )
        ]
        if matches:
            possible[item.fingerprint] = matches
    return possible, overflow_by_fingerprint


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
    possible_fact_targets, overflow_fact_targets = _existing_fact_matches(
        db,
        user_id=batch.user_id,
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
                batch_id=row.batch_id,
                evidence=row.evidence,
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
        fact_matches = possible_fact_targets.get(item.fingerprint, [])
        overflow_watermark = (
            overflow_transactions.get(item.fingerprint)
            or overflow_fact_targets.get(item.fingerprint)
        )
        possible_transaction = possible_matches[0] if possible_matches else None
        coarse_key = _coarse_duplicate_key(
            item.direction,
            persisted_amount,
            item.transaction_date,
        )
        fuzzy_index = seen_fuzzy.setdefault(coarse_key, _DuplicateTextIndex()) if coarse_key else None
        repeated_fingerprint = (
            fuzzy_index.has_match(
                item.merchant,
                item.description,
                batch_id=batch.id,
                evidence=item.evidence,
            )
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
            and not _same_batch_distinct_source_ocr_rows(
                left_batch_id=batch.id,
                left_evidence=item.evidence,
                right_batch_id=row.batch_id,
                right_evidence=row.evidence,
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
        elif possible_matches or fact_matches or overflow_watermark is not None or repeated_fingerprint:
            status = "possible_duplicate"
            duplicate_transaction_id = possible_transaction.id if possible_transaction is not None else None
            _append_issue(
                warnings,
                field="fingerprint",
                code="POSSIBLE_DUPLICATE",
                message=(
                    (
                        f"同日同金额已有 {(overflow_watermark or fact_overflow_watermark).count} 笔记录，"
                        "已触发有界查重，请人工核对后决定是否入账"
                    )
                    if overflow_watermark is not None
                    else
                    f"发现 {len({(target.transaction.id, target.fact.id) for target in fact_matches})} 个同日同金额且描述相近的已有经济事实，请核对后决定是否入账"
                    if fact_matches
                    else f"发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请核对后决定是否入账"
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
        if fact_matches:
            evidence["possible_duplicate_fact_targets"] = [
                {
                    "transaction_id": target.transaction.id,
                    "fact_id": target.fact.id,
                }
                for target in sorted(
                    {
                        (target.transaction.id, target.fact.id): target
                        for target in fact_matches
                    }.values(),
                    key=lambda target: (target.transaction.id, target.fact.id),
                )
            ]
            evidence["possible_duplicate_transaction_ids"] = sorted({
                *evidence.get("possible_duplicate_transaction_ids", []),
                *(target.transaction.id for target in fact_matches),
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
                fuzzy_index.add(
                    item.merchant,
                    item.description,
                    batch_id=batch.id,
                    evidence=item.evidence,
                )

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
    ocr_source_locator: dict[str, Any] | None = None,
    ocr_artifact_metadata: dict[str, Any] | None = None,
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
            persist_ocr_text_artifact(
                db,
                batch=batch,
                ocr_text=ocr_text,
                source_locator=ocr_source_locator,
                artifact_metadata=ocr_artifact_metadata,
            )
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
    ocr_source_locator: dict[str, Any] | None = None,
    ocr_artifact_metadata: dict[str, Any] | None = None,
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
            ocr_source_locator=ocr_source_locator,
            ocr_artifact_metadata=ocr_artifact_metadata,
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
            persist_ocr_text_artifact(
                db,
                batch=batch,
                ocr_text=ocr_text,
                source_locator=ocr_source_locator,
                artifact_metadata=ocr_artifact_metadata,
            )
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
                    ocr_source_locator=ocr_source_locator,
                    ocr_artifact_metadata=ocr_artifact_metadata,
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


def _find_possible_duplicate_fact_targets_for_candidate(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
) -> tuple[list[_FormalFactDuplicateTarget], _DuplicateBucketWatermark | None]:
    if candidate.direction is None or candidate.amount is None or candidate.transaction_date is None:
        return [], None
    key = _coarse_duplicate_key(
        candidate.direction,
        Decimal(candidate.amount),
        candidate.transaction_date,
    )
    if key is None:
        return [], None
    buckets, overflow = _load_formal_fact_duplicate_buckets(
        db,
        user_id=candidate.user_id,
        coarse_keys=[key],
    )
    if key in overflow:
        return [], overflow[key]
    return [
        target
        for target in buckets.get(key, [])
        if _fact_target_text_is_similar(
            merchant=candidate.merchant,
            description=candidate.description,
            target=target,
        )
    ], None


def _active_sibling_fingerprint_matches(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
) -> list[FinancialTransactionCandidate]:
    if not candidate.fingerprint:
        return []
    siblings = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == candidate.user_id,
        FinancialTransactionCandidate.id != candidate.id,
        FinancialTransactionCandidate.direction == candidate.direction,
        FinancialTransactionCandidate.amount == candidate.amount,
        FinancialTransactionCandidate.transaction_date == candidate.transaction_date,
        FinancialTransactionCandidate.status.in_({"ready", "needs_review", "possible_duplicate"}),
    ).all()
    return [
        sibling
        for sibling in siblings
        if
        duplicate_text_is_similar(
            candidate.merchant,
            candidate.description,
            sibling.merchant,
            sibling.description,
        )
        and not _same_batch_distinct_source_ocr_rows(
            left_batch_id=candidate.batch_id,
            left_evidence=candidate.evidence,
            right_batch_id=sibling.batch_id,
            right_evidence=sibling.evidence,
        )
    ]


def _has_active_sibling_fingerprint(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
) -> bool:
    return bool(_active_sibling_fingerprint_matches(db, candidate=candidate))


def _candidate_source_slice_entries(
    candidate: FinancialTransactionCandidate,
) -> list[dict[str, object]]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    raw_sources = evidence.get("source_slices")
    sources = [
        dict(source)
        for source in (raw_sources if isinstance(raw_sources, list) else [])
        if isinstance(source, dict) and isinstance(source.get("slice_sequence"), int)
    ]
    if not sources and isinstance(evidence.get("slice_sequence"), int):
        sources.append({
            "slice_sequence": evidence["slice_sequence"],
            "source_locator": evidence.get("source_locator") or {},
            "candidate_region": evidence.get("candidate_region"),
            "ocr_line_index": evidence.get("ocr_line_index"),
        })
    unique: dict[str, dict[str, object]] = {}
    for source in sources:
        key = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str)
        unique.setdefault(key, source)
    return list(unique.values())


def _manual_candidate_merge_eligibility(
    primary: FinancialTransactionCandidate,
    duplicate: FinancialTransactionCandidate,
) -> tuple[bool, str | None]:
    if primary.id == duplicate.id:
        return False, "不能将候选与自身合并"
    if primary.user_id != duplicate.user_id or primary.batch_id != duplicate.batch_id:
        return False, "只能合并同一识别批次里的相邻切片候选"
    if primary.status not in DUPLICATE_CLAIM_CANDIDATE_STATUSES or duplicate.status not in DUPLICATE_CLAIM_CANDIDATE_STATUSES:
        return False, "只能合并尚未入账且正在核对的候选"
    primary_evidence = primary.evidence if isinstance(primary.evidence, dict) else {}
    duplicate_evidence = duplicate.evidence if isinstance(duplicate.evidence, dict) else {}
    if isinstance(primary_evidence.get("manual_candidate_merge_target"), dict):
        return False, "当前候选已并入其他主候选"
    if isinstance(duplicate_evidence.get("manual_candidate_merge_target"), dict):
        return False, "对照候选已并入其他主候选"
    if duplicate_evidence.get("manual_candidate_merges"):
        return False, "对照候选已承载其他重叠证据，请先撤销后再合并"
    if (
        primary.direction != duplicate.direction
        or primary.amount != duplicate.amount
        or primary.transaction_date != duplicate.transaction_date
    ):
        return False, "日期、金额和方向必须一致才能合并"
    if not duplicate_text_is_similar(
        primary.merchant,
        primary.description,
        duplicate.merchant,
        duplicate.description,
    ):
        return False, "交易对方或摘要差异过大，不能作为切片重复合并"
    primary_sequences = {
        int(source["slice_sequence"])
        for source in _candidate_source_slice_entries(primary)
    }
    duplicate_sequences = {
        int(source["slice_sequence"])
        for source in _candidate_source_slice_entries(duplicate)
    }
    if not primary_sequences or not duplicate_sequences:
        return False, "两条候选缺少可对照的切片证据"
    if not any(abs(left - right) == 1 for left in primary_sequences for right in duplicate_sequences):
        return False, "只能合并来自相邻重叠切片的候选"
    visible_on_either_side = (
        duplicate.id in _candidate_duplicate_candidate_ids(primary)
        or primary.id in _candidate_duplicate_candidate_ids(duplicate)
    )
    if not visible_on_either_side:
        return False, "候选重复对照已变化，请刷新后重新核对"
    return True, None


_CANDIDATE_DUPLICATE_EVIDENCE_KEYS = (
    "economic_fact_merge",
    "review_accepted_at",
    "duplicate_review_fingerprint",
    "duplicate_review_transaction_ids",
    "duplicate_review_bucket_watermark",
    "duplicate_review_sibling",
    "possible_duplicate_transaction_ids",
    "possible_duplicate_fact_targets",
    "possible_duplicate_candidate_ids",
    "possible_duplicate_bucket_watermark",
    "formal_duplicate_ai_review",
    "candidate_duplicate_ai_review",
)


def _recheck_candidate_duplicate_state(
    db: Session,
    *,
    candidate: FinancialTransactionCandidate,
    user_id: int,
) -> None:
    evidence = dict(candidate.evidence or {})
    for key in _CANDIDATE_DUPLICATE_EVIDENCE_KEYS:
        evidence.pop(key, None)
    candidate.evidence = evidence
    errors, category = _candidate_validation(
        db,
        candidate=candidate,
        user_id=user_id,
        resolved_fields=set(evidence.get("user_modified_fields") or []),
    )
    candidate.validation_errors = errors
    if category is not None:
        candidate.category_name = category.name
    formal_matches, overflow = _find_possible_duplicates_for_candidate(db, candidate=candidate)
    fact_matches, fact_overflow = _find_possible_duplicate_fact_targets_for_candidate(db, candidate=candidate)
    sibling_matches = _active_sibling_fingerprint_matches(db, candidate=candidate)
    fact_target_ids = sorted({
        (target.transaction.id, target.fact.id)
        for target in fact_matches
    })
    transaction_ids = sorted({
        *(row.id for row in formal_matches),
        *(transaction_id for transaction_id, _ in fact_target_ids),
    })
    evidence = dict(candidate.evidence or {})
    if transaction_ids:
        evidence["possible_duplicate_transaction_ids"] = transaction_ids
    if fact_target_ids:
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in fact_target_ids
        ]
    if sibling_matches:
        evidence["possible_duplicate_candidate_ids"] = sorted(row.id for row in sibling_matches)
    current_overflow = overflow or fact_overflow
    if current_overflow is not None:
        evidence["possible_duplicate_bucket_watermark"] = current_overflow.as_evidence()
    candidate.evidence = evidence
    candidate.duplicate_transaction_id = min(transaction_ids) if transaction_ids else None
    warnings = [
        dict(issue)
        for issue in (candidate.warnings or [])
        if issue.get("code") not in {"POSSIBLE_DUPLICATE", "CROSS_IMAGE_DUPLICATE_AI_REVIEW"}
    ]
    duplicate_found = bool(transaction_ids or sibling_matches or current_overflow is not None)
    if duplicate_found:
        _append_issue(
            warnings,
            field="fingerprint",
            code="POSSIBLE_DUPLICATE",
            message=(
                "发现其他待处理候选或已有账本记录与这笔同日同额且文本相近，请再次核对"
            ),
        )
    candidate.warnings = warnings
    if errors:
        candidate.status = "invalid"
    elif duplicate_found:
        candidate.status = "possible_duplicate"
    elif warnings:
        candidate.status = "needs_review"
    else:
        candidate.status = "ready"


def merge_duplicate_candidates(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportCandidateMergeRequest,
) -> dict[str, object]:
    """Collapse two adjacent-slice candidates while retaining both proofs."""
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_candidate_merge_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能合并候选")
    if batch.version != data.expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    requested_ids = {data.primary_candidate_id, data.duplicate_candidate_id}
    rows = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.id.in_(requested_ids),
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    if len(rows) != 2:
        raise import_error(404, "cashflow_import_candidate_not_found", "待合并候选不存在")
    by_id = {row.id: row for row in rows}
    primary = by_id[data.primary_candidate_id]
    duplicate = by_id[data.duplicate_candidate_id]
    if primary.version != data.primary_expected_version or duplicate.version != data.duplicate_expected_version:
        raise import_error(409, "cashflow_import_stale_candidate", "候选已更新，请刷新后重新合并")
    allowed, block_reason = _manual_candidate_merge_eligibility(primary, duplicate)
    if not allowed:
        raise import_error(409, "cashflow_import_candidate_merge_blocked", block_reason or "这两条候选不能合并")

    merged_at = datetime.utcnow()
    primary_evidence = dict(primary.evidence or {})
    primary_sources = _candidate_source_slice_entries(primary)
    merge_rows = [
        dict(row)
        for row in (primary_evidence.get("manual_candidate_merges") or [])
        if isinstance(row, dict)
    ]
    base_sources = [
        dict(source)
        for source in (primary_evidence.get("manual_candidate_merge_base_sources") or [])
        if isinstance(source, dict)
    ] if merge_rows else primary_sources
    if not merge_rows:
        primary_evidence["manual_candidate_merge_base_sources"] = base_sources
    duplicate_sources = _candidate_source_slice_entries(duplicate)
    merge_rows.append({
        "merged_candidate_id": duplicate.id,
        "merged_row_number": duplicate.row_number,
        "merged_candidate_fingerprint": duplicate.fingerprint,
        "reason": data.reason,
        "merged_at": merged_at.isoformat(),
        "sources": duplicate_sources,
    })
    primary_evidence["manual_candidate_merges"] = merge_rows
    combined_sources = base_sources + [
        source
        for row in merge_rows
        for source in (row.get("sources") if isinstance(row.get("sources"), list) else [])
        if isinstance(source, dict)
    ]
    primary_evidence["source_slices"] = list({
        json.dumps(source, ensure_ascii=False, sort_keys=True, default=str): source
        for source in combined_sources
    }.values())
    primary.evidence = primary_evidence

    duplicate_evidence = dict(duplicate.evidence or {})
    for key in _CANDIDATE_DUPLICATE_EVIDENCE_KEYS:
        duplicate_evidence.pop(key, None)
    duplicate_evidence["manual_candidate_merge_target"] = {
        "primary_candidate_id": primary.id,
        "primary_row_number": primary.row_number,
        "reason": data.reason,
        "merged_at": merged_at.isoformat(),
    }
    duplicate.evidence = duplicate_evidence
    duplicate.status = "excluded"
    duplicate.duplicate_transaction_id = None
    duplicate.warnings = [
        dict(issue)
        for issue in (duplicate.warnings or [])
        if issue.get("code") not in {"POSSIBLE_DUPLICATE", "CROSS_IMAGE_DUPLICATE_AI_REVIEW"}
    ]
    db.flush()
    _recheck_candidate_duplicate_state(db, candidate=primary, user_id=user_id)
    batch.updated_at = merged_at
    db.flush()
    refresh_batch_counts(db, batch)
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_candidate_merge_conflict", "候选或批次已变化，请刷新后重试") from exc
    db.refresh(batch)
    refreshed = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.id.in_(requested_ids),
    ).order_by(FinancialTransactionCandidate.id.asc()).all()
    return {
        "batch": batch_payload(batch),
        "candidates": candidate_payloads(db, batch=batch, candidates=refreshed),
        "primary_candidate_id": primary.id,
        "merged_candidate_id": duplicate.id,
    }


def undo_duplicate_candidate_merge(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    merged_candidate_id: int,
    data: FinancialImportCandidateMergeUndoRequest,
) -> dict[str, object]:
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_candidate_merge_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能撤销候选合并")
    if batch.version != data.expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    merged = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.id == merged_candidate_id,
    ).first()
    if merged is None:
        raise import_error(404, "cashflow_import_candidate_not_found", "已合并候选不存在")
    marker = (merged.evidence or {}).get("manual_candidate_merge_target")
    if not isinstance(marker, dict) or not isinstance(marker.get("primary_candidate_id"), int):
        raise import_error(409, "cashflow_import_candidate_merge_missing", "该候选没有可撤销的切片合并")
    primary_id = int(marker["primary_candidate_id"])
    requested_ids = {primary_id, merged_candidate_id}
    rows = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.id.in_(requested_ids),
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    if len(rows) != 2:
        raise import_error(404, "cashflow_import_candidate_not_found", "合并主候选已不存在")
    by_id = {row.id: row for row in rows}
    primary = by_id[primary_id]
    merged = by_id[merged_candidate_id]
    if merged.version != data.merged_candidate_expected_version:
        raise import_error(409, "cashflow_import_stale_candidate", "已合并候选已更新，请刷新后继续")
    primary_evidence = dict(primary.evidence or {})
    merge_rows = [
        dict(row)
        for row in (primary_evidence.get("manual_candidate_merges") or [])
        if isinstance(row, dict)
    ]
    if not any(row.get("merged_candidate_id") == merged_candidate_id for row in merge_rows):
        raise import_error(409, "cashflow_import_candidate_merge_changed", "合并关系已变化，请刷新后继续")
    remaining = [row for row in merge_rows if row.get("merged_candidate_id") != merged_candidate_id]
    base_sources = [
        dict(source)
        for source in (primary_evidence.get("manual_candidate_merge_base_sources") or [])
        if isinstance(source, dict)
    ]
    if remaining:
        primary_evidence["manual_candidate_merges"] = remaining
        primary_evidence["source_slices"] = base_sources + [
            source
            for row in remaining
            for source in (row.get("sources") if isinstance(row.get("sources"), list) else [])
            if isinstance(source, dict)
        ]
    else:
        primary_evidence.pop("manual_candidate_merges", None)
        primary_evidence.pop("manual_candidate_merge_base_sources", None)
        if base_sources:
            primary_evidence["source_slices"] = base_sources
        else:
            primary_evidence.pop("source_slices", None)
    primary.evidence = primary_evidence
    merged_evidence = dict(merged.evidence or {})
    merged_evidence.pop("manual_candidate_merge_target", None)
    merged.evidence = merged_evidence
    primary.status = "needs_review"
    merged.status = "needs_review"
    db.flush()
    _recheck_candidate_duplicate_state(db, candidate=primary, user_id=user_id)
    _recheck_candidate_duplicate_state(db, candidate=merged, user_id=user_id)
    batch.updated_at = datetime.utcnow()
    db.flush()
    refresh_batch_counts(db, batch)
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_candidate_merge_conflict", "候选或批次已变化，请刷新后重试") from exc
    db.refresh(batch)
    refreshed = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.id.in_(requested_ids),
    ).order_by(FinancialTransactionCandidate.id.asc()).all()
    return {
        "batch": batch_payload(batch),
        "candidates": candidate_payloads(db, batch=batch, candidates=refreshed),
        "primary_candidate_id": primary.id,
        "merged_candidate_id": merged.id,
    }


def _merge_target_snapshot(
    *,
    transaction: FinancialTransaction,
    fact: EconomicFact,
) -> dict[str, object]:
    return {
        "transaction_id": transaction.id,
        "direction": transaction.direction,
        "amount": format(Decimal(transaction.amount), "f"),
        "currency": transaction.currency,
        "transaction_date": transaction.transaction_date.isoformat(),
        "source_type": transaction.source_type,
        "fact_id": fact.id,
        "fact_amount": format(Decimal(fact.amount), "f"),
        "fact_status": fact.status,
    }


def _load_candidate_merge_target(
    db: Session,
    *,
    batch: FinancialImportBatch,
    candidate: FinancialTransactionCandidate,
    target_transaction_id: int,
    target_fact_id: int | None,
    allocated_amount: Decimal,
    require_presented_match: bool = True,
    validate_allocation: bool = True,
) -> tuple[FinancialTransaction, EconomicFact]:
    presented_ids = _candidate_duplicate_transaction_ids(candidate)
    if require_presented_match and target_transaction_id not in presented_ids:
        raise import_error(
            409,
            "cashflow_import_merge_target_changed",
            "目标流水不在本次已展示的疑似重复记录中，请刷新后重新核对",
        )
    target = db.query(FinancialTransaction).filter(
        FinancialTransaction.id == target_transaction_id,
        FinancialTransaction.user_id == candidate.user_id,
    ).first()
    if target is None:
        raise import_error(404, "cashflow_import_merge_target_not_found", "要并入的已有流水不存在")
    presented_fact_targets = _candidate_duplicate_fact_target_ids(candidate)
    transaction_fact_ids = [
        fact_id
        for transaction_id, fact_id in presented_fact_targets
        if transaction_id == target.id
    ]
    if target_fact_id is None and len(transaction_fact_ids) == 1:
        target_fact_id = transaction_fact_ids[0]
    if target_fact_id is None and len(transaction_fact_ids) > 1:
        raise import_error(
            409,
            "cashflow_import_merge_fact_required",
            "该流水对应多个经济事实，请明确选择要归入的拆分项",
        )
    fact_query = (
        db.query(EconomicFact)
        .join(EconomicFactAllocation, EconomicFactAllocation.fact_id == EconomicFact.id)
        .filter(
            EconomicFact.user_id == candidate.user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id == target.id,
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role.in_({"primary", "split_component"}),
        )
    )
    if target_fact_id is not None:
        fact_query = fact_query.filter(EconomicFact.id == target_fact_id)
    fact_rows = fact_query.order_by(EconomicFact.id.asc()).all()
    if target_fact_id is None and len(fact_rows) > 1:
        raise import_error(
            409,
            "cashflow_import_merge_fact_required",
            "该流水已拆分为多个经济事实，请刷新后选择具体拆分项",
        )
    fact = fact_rows[0] if fact_rows else None
    if fact is None:
        raise import_error(409, "cashflow_import_merge_target_changed", "目标经济事实不存在或已变化")
    if require_presented_match and presented_fact_targets and (target.id, fact.id) not in presented_fact_targets:
        raise import_error(
            409,
            "cashflow_import_merge_target_changed",
            "目标经济事实不在本次已展示的疑似重复项中，请刷新后重新核对",
        )
    block_reason = _merge_target_block_reason(
        candidate=candidate,
        candidate_source_type=_formal_source_type(batch.source_type),
        transaction=target,
        fact=fact,
    )
    if block_reason is not None:
        raise import_error(409, "cashflow_import_merge_not_allowed", block_reason)
    if validate_allocation:
        if candidate.amount is None or allocated_amount > Decimal(candidate.amount):
            raise import_error(409, "cashflow_import_merge_amount_invalid", "证据分配金额不能超过当前候选金额")
        if allocated_amount > Decimal(fact.amount):
            raise import_error(409, "cashflow_import_merge_amount_invalid", "证据分配金额不能超过目标经济事实的可分配金额")
    return target, fact


def _validated_candidate_merge_intent(
    db: Session,
    *,
    batch: FinancialImportBatch,
    candidate: FinancialTransactionCandidate,
) -> tuple[dict, FinancialTransaction, EconomicFact] | None:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    intent = evidence.get("economic_fact_merge")
    if not isinstance(intent, dict):
        return None
    try:
        target_transaction_id = int(intent["target_transaction_id"])
        allocated_amount = Decimal(str(intent["allocated_amount"]))
    except (KeyError, TypeError, ValueError):
        raise import_error(
            409,
            "cashflow_import_merge_target_changed",
            "同一经济事实的合并意图不完整，请重新核对",
        )
    if allocated_amount <= Decimal("0.00"):
        raise import_error(409, "cashflow_import_merge_amount_invalid", "证据分配金额必须大于 0")
    if intent.get("candidate_fingerprint") != candidate.fingerprint:
        raise import_error(
            409,
            "cashflow_import_merge_target_changed",
            "候选内容已变化，请重新核对要并入的经济事实",
        )
    target, fact = _load_candidate_merge_target(
        db,
        batch=batch,
        candidate=candidate,
        target_transaction_id=target_transaction_id,
        target_fact_id=int(intent["target_fact_id"]) if intent.get("target_fact_id") is not None else None,
        allocated_amount=allocated_amount,
        validate_allocation=False,
    )
    if intent.get("target_fact_id") != fact.id:
        raise import_error(409, "cashflow_import_merge_target_changed", "目标经济事实已变化，请刷新后重新核对")
    if intent.get("target_snapshot") != _merge_target_snapshot(transaction=target, fact=fact):
        raise import_error(409, "cashflow_import_merge_target_changed", "目标流水或经济事实已变化，请刷新后重新核对")
    if candidate.amount is None or allocated_amount > Decimal(candidate.amount):
        raise import_error(409, "cashflow_import_merge_amount_invalid", "证据分配金额不能超过当前候选金额")
    if allocated_amount > Decimal(fact.amount):
        raise import_error(409, "cashflow_import_merge_amount_invalid", "证据分配金额不能超过目标经济事实的可分配金额")
    reviewed_ids = sorted(
        int(value)
        for value in intent.get("duplicate_transaction_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    )
    if reviewed_ids != _candidate_duplicate_transaction_ids(candidate):
        raise import_error(409, "cashflow_import_merge_target_changed", "疑似重复记录集合已变化，请刷新后重新核对")
    return intent, target, fact


def merge_candidate_group_into_fact(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportCandidateGroupMergeRequest,
) -> dict[str, object]:
    """Atomically save several reviewed candidates against one existing fact."""
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_group_merge_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能组合归入")
    if batch.version != data.expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")

    requested_versions = {
        item.candidate_id: item.expected_version
        for item in data.candidates
    }
    allocation_by_candidate_id = {
        item.candidate_id: Decimal(item.allocated_amount)
        for item in data.candidates
    }
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.id.in_(requested_versions),
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    if len(candidates) != len(requested_versions):
        raise import_error(404, "cashflow_import_candidate_not_found", "部分导入候选不存在")

    member_rows: list[dict[str, object]] = []
    target_transaction: FinancialTransaction | None = None
    target_fact: EconomicFact | None = None
    reviewed_contexts: dict[int, tuple[list[int], list[tuple[int, int]]]] = {}
    reviewed_sibling_ids: dict[int, list[int]] = {}
    requested_candidate_ids = set(requested_versions)
    for candidate in candidates:
        if candidate.version != requested_versions[candidate.id]:
            raise import_error(409, "cashflow_import_stale_candidate", "组合中的候选已更新，请刷新后重新选择")
        if candidate.status not in {"ready", "needs_review", "possible_duplicate"}:
            raise import_error(409, "cashflow_import_candidate_locked", "只能组合尚未入账且可核对的候选")
        errors, category = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            resolved_fields=set((candidate.evidence or {}).get("user_modified_fields") or []),
        )
        if errors:
            raise import_error(409, "cashflow_import_candidate_not_ready", f"第 {candidate.row_number} 行信息不完整，请先单独核对")
        if category is not None:
            candidate.category_name = category.name

        current_matches, overflow_watermark = _find_possible_duplicates_for_candidate(
            db,
            candidate=candidate,
        )
        current_fact_targets, fact_overflow_watermark = _find_possible_duplicate_fact_targets_for_candidate(
            db,
            candidate=candidate,
        )
        if overflow_watermark is not None or fact_overflow_watermark is not None:
            raise import_error(409, "cashflow_import_group_merge_conflict", "疑似重复范围过大，不能用局部结果批量归入")
        current_fact_target_ids = sorted({
            (row.transaction.id, row.fact.id)
            for row in current_fact_targets
        })
        current_transaction_ids = sorted({
            *(row.id for row in current_matches),
            *(transaction_id for transaction_id, _ in current_fact_target_ids),
        })
        if (
            int(data.target_transaction_id),
            int(data.target_fact_id),
        ) not in current_fact_target_ids:
            raise import_error(409, "cashflow_import_group_merge_conflict", f"第 {candidate.row_number} 行不再匹配所选经济事实，请刷新后重新核对")
        if (
            current_transaction_ids != _candidate_duplicate_transaction_ids(candidate)
            or current_fact_target_ids != _candidate_duplicate_fact_target_ids(candidate)
        ):
            raise import_error(409, "cashflow_import_group_merge_conflict", "候选的疑似重复集合已变化，请刷新后重新选择")
        sibling_ids = sorted(
            row.id
            for row in _active_sibling_fingerprint_matches(db, candidate=candidate)
        )
        if not set(sibling_ids).issubset(requested_candidate_ids):
            raise import_error(
                409,
                "cashflow_import_group_selection_incomplete",
                "所选候选还有同日同额的待核对对应，请一并选择或先单独排除",
            )

        allocation = allocation_by_candidate_id[candidate.id]
        if candidate.amount is None or allocation > Decimal(candidate.amount):
            raise import_error(409, "cashflow_import_merge_amount_invalid", f"第 {candidate.row_number} 行归入金额超过候选金额")
        current_target, current_fact = _load_candidate_merge_target(
            db,
            batch=batch,
            candidate=candidate,
            target_transaction_id=int(data.target_transaction_id),
            target_fact_id=int(data.target_fact_id),
            allocated_amount=allocation,
        )
        if target_transaction is None:
            target_transaction = current_target
            target_fact = current_fact
        elif current_target.id != target_transaction.id or current_fact.id != target_fact.id:
            raise import_error(409, "cashflow_import_group_merge_conflict", "组合候选必须归入同一个经济事实")
        reviewed_contexts[candidate.id] = (
            current_transaction_ids,
            current_fact_target_ids,
        )
        reviewed_sibling_ids[candidate.id] = sibling_ids
        member_rows.append({
            "candidate_id": candidate.id,
            "fingerprint": candidate.fingerprint,
            "allocated_amount": format(allocation, "f"),
        })

    if target_transaction is None or target_fact is None:
        raise import_error(409, "cashflow_import_group_merge_conflict", "未找到可归入的目标经济事实")
    group_id = uuid4().hex
    reviewed_at = datetime.utcnow()
    group_payload = {
        "group_id": group_id,
        "target_transaction_id": target_transaction.id,
        "target_fact_id": target_fact.id,
        "target_snapshot": _merge_target_snapshot(
            transaction=target_transaction,
            fact=target_fact,
        ),
        "members": member_rows,
        "reviewed_at": reviewed_at.isoformat(),
    }
    for candidate in candidates:
        current_transaction_ids, current_fact_target_ids = reviewed_contexts[candidate.id]
        allocation = allocation_by_candidate_id[candidate.id]
        evidence = dict(candidate.evidence or {})
        evidence["possible_duplicate_transaction_ids"] = current_transaction_ids
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in current_fact_target_ids
        ]
        evidence["economic_fact_merge"] = {
            "target_transaction_id": target_transaction.id,
            "target_fact_id": target_fact.id,
            "allocated_amount": format(allocation, "f"),
            "reason": data.evidence_merge_reason,
            "reviewed_at": reviewed_at.isoformat(),
            "candidate_fingerprint": candidate.fingerprint,
            "duplicate_transaction_ids": current_transaction_ids,
            "duplicate_fact_targets": [
                {"transaction_id": transaction_id, "fact_id": fact_id}
                for transaction_id, fact_id in current_fact_target_ids
            ],
            "target_snapshot": group_payload["target_snapshot"],
            "group_merge": group_payload,
        }
        evidence["review_accepted_at"] = reviewed_at.isoformat()
        evidence["duplicate_review_fingerprint"] = candidate.fingerprint
        evidence["duplicate_review_transaction_ids"] = current_transaction_ids
        evidence.pop("duplicate_review_bucket_watermark", None)
        evidence["possible_duplicate_candidate_ids"] = reviewed_sibling_ids[candidate.id]
        evidence["duplicate_review_sibling"] = bool(reviewed_sibling_ids[candidate.id])
        candidate.evidence = evidence
        candidate.duplicate_transaction_id = target_transaction.id
        candidate.validation_errors = []
        candidate.warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") not in {"CATEGORY_REVIEW_REQUIRED", "POSSIBLE_DUPLICATE"}
        ]
        candidate.status = "ready"

    batch.updated_at = reviewed_at
    db.flush()
    refresh_batch_counts(db, batch)
    try:
        db.commit()
    except (IntegrityError, StaleDataError) as exc:
        db.rollback()
        raise import_error(409, "cashflow_import_group_merge_conflict", "组合归入时候选或账本已变化，请重试") from exc
    db.refresh(batch)
    refreshed = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.id.in_(requested_versions),
    ).order_by(FinancialTransactionCandidate.id.asc()).all()
    return {
        "batch": batch_payload(batch),
        "candidates": candidate_payloads(db, batch=batch, candidates=refreshed),
        "group_id": group_id,
        "target_fact_id": target_fact.id,
        "allocated_total": sum(allocation_by_candidate_id.values(), Decimal("0.00")),
    }


def _validate_selected_candidate_merge_groups(
    candidates: Sequence[FinancialTransactionCandidate],
) -> None:
    selected_by_id = {candidate.id: candidate for candidate in candidates}
    checked_group_ids: set[str] = set()
    for candidate in candidates:
        intent = (candidate.evidence or {}).get("economic_fact_merge")
        group = intent.get("group_merge") if isinstance(intent, dict) else None
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "")
        if not group_id or group_id in checked_group_ids:
            continue
        checked_group_ids.add(group_id)
        members = group.get("members")
        if not isinstance(members, list) or len(members) < 2:
            raise import_error(409, "cashflow_import_group_merge_changed", "组合归入证据不完整，请重新选择")
        try:
            expected_members = {
                int(row["candidate_id"]): (
                    str(row["fingerprint"]),
                    format(Decimal(str(row["allocated_amount"])), "f"),
                )
                for row in members
                if isinstance(row, dict)
            }
        except (KeyError, TypeError, ValueError):
            raise import_error(409, "cashflow_import_group_merge_changed", "组合归入证据不完整，请重新选择")
        if len(expected_members) != len(members) or not set(expected_members).issubset(selected_by_id):
            raise import_error(409, "cashflow_import_group_selection_incomplete", "同一组归入候选必须一次全部选中确认")
        canonical_group = json.dumps(group, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for member_id, (fingerprint, allocated_amount) in expected_members.items():
            member = selected_by_id[member_id]
            member_intent = (member.evidence or {}).get("economic_fact_merge")
            member_group = member_intent.get("group_merge") if isinstance(member_intent, dict) else None
            try:
                current_allocated_amount = format(
                    Decimal(str(member_intent.get("allocated_amount"))),
                    "f",
                )
            except (AttributeError, TypeError, ValueError):
                current_allocated_amount = ""
            if (
                not isinstance(member_group, dict)
                or json.dumps(member_group, ensure_ascii=False, sort_keys=True, separators=(",", ":")) != canonical_group
                or member.fingerprint != fingerprint
                or current_allocated_amount != allocated_amount
            ):
                raise import_error(409, "cashflow_import_group_merge_changed", "组合中的候选或分配金额已变化，请重新核对")


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
    existing_merge_intent = evidence_before_update.get("economic_fact_merge")
    if (
        data.action == "accept_review"
        and candidate.status == "ready"
        and isinstance(existing_merge_intent, dict)
    ):
        # Switching a saved merge intent back to "record as a new fact" uses
        # the same exact-match acceptance gate as the ordinary review flow.
        candidate.status = "possible_duplicate"
        status_before_update = "possible_duplicate"
    if data.action != "merge_evidence":
        evidence_before_update.pop("economic_fact_merge", None)
        candidate.evidence = evidence_before_update
    presented_duplicate_ids = {
        int(value)
        for value in evidence_before_update.get("possible_duplicate_transaction_ids", [])
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    }
    presented_bucket_watermark = evidence_before_update.get(
        "possible_duplicate_bucket_watermark"
    )
    editable_fields = {
        "direction",
        "amount",
        "transaction_date",
        "category_id",
        "merchant",
        "description",
        "nature",
    }
    requested_candidate_changes = data.model_dump(
        include=editable_fields,
        exclude_unset=True,
    )

    if data.action == "merge_evidence":
        if candidate.status not in {"possible_duplicate", "ready"}:
            raise import_error(
                409,
                "cashflow_import_state_conflict",
                "只有已展示正式重复对应的候选才能并入已有经济事实",
            )
        if candidate.status == "ready" and not isinstance(existing_merge_intent, dict):
            raise import_error(
                409,
                "cashflow_import_state_conflict",
                "该候选已选择按新事实记录，请刷新重复核对结果",
            )
        resolved_fields = set(evidence_before_update.get("user_modified_fields") or [])
        resolved_fields.update(requested_candidate_changes)
        for field, value in requested_candidate_changes.items():
            setattr(candidate, field, value)
        if (
            "transaction_date" in requested_candidate_changes
            and candidate.transaction_date != transaction_date_before_update
            and candidate.occurred_at is not None
        ):
            candidate.occurred_at = None
        if candidate.direction == "transfer":
            candidate.category_id = None
            candidate.category_name = None
            candidate.nature = None
        # Requested fields must be validated as one proposed candidate state.
        # Suppress autoflush so a nonexistent category id is reported as a
        # review error instead of leaking a database FK exception midway.
        with db.no_autoflush:
            errors, category = _candidate_validation(
                db,
                candidate=candidate,
                user_id=user_id,
                resolved_fields=resolved_fields,
            )
        if errors:
            candidate.validation_errors = errors
            candidate.status = "invalid"
            raise import_error(409, "cashflow_import_candidate_not_ready", "候选数据不完整，请先补齐必填字段")
        if category is not None:
            candidate.category_name = category.name
        current_matches, overflow_watermark = _find_possible_duplicates_for_candidate(
            db,
            candidate=candidate,
        )
        current_fact_targets, fact_overflow_watermark = _find_possible_duplicate_fact_targets_for_candidate(
            db,
            candidate=candidate,
        )
        current_match_ids = sorted(row.id for row in current_matches)
        current_fact_target_ids = sorted({
            (target.transaction.id, target.fact.id)
            for target in current_fact_targets
        })
        combined_transaction_ids = sorted({
            *current_match_ids,
            *(transaction_id for transaction_id, _ in current_fact_target_ids),
        })
        presented_fact_target_ids = _candidate_duplicate_fact_target_ids(candidate)
        if (
            overflow_watermark is not None
            or fact_overflow_watermark is not None
            or combined_transaction_ids != sorted(presented_duplicate_ids)
            or (presented_fact_target_ids and current_fact_target_ids != presented_fact_target_ids)
            or int(data.target_transaction_id) not in combined_transaction_ids
            or (
                data.target_fact_id is not None
                and (int(data.target_transaction_id), int(data.target_fact_id)) not in current_fact_target_ids
                and current_fact_target_ids
            )
        ):
            raise import_error(
                409,
                "cashflow_import_merge_target_changed",
                "候选字段修改后疑似重复对应已变化，请刷新后重新核对",
            )
        target, target_fact = _load_candidate_merge_target(
            db,
            batch=batch,
            candidate=candidate,
            target_transaction_id=int(data.target_transaction_id),
            target_fact_id=int(data.target_fact_id) if data.target_fact_id is not None else None,
            allocated_amount=Decimal(data.allocated_amount),
        )
        presented_ids = _candidate_duplicate_transaction_ids(candidate)
        evidence = dict(evidence_before_update)
        evidence["possible_duplicate_transaction_ids"] = combined_transaction_ids
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in current_fact_target_ids
        ]
        reviewed_at = datetime.utcnow()
        evidence["economic_fact_merge"] = {
            "target_transaction_id": target.id,
            "target_fact_id": target_fact.id,
            "allocated_amount": format(Decimal(data.allocated_amount), "f"),
            "reason": data.evidence_merge_reason,
            "reviewed_at": reviewed_at.isoformat(),
            "candidate_fingerprint": candidate.fingerprint,
            "duplicate_transaction_ids": presented_ids,
            "duplicate_fact_targets": [
                {"transaction_id": transaction_id, "fact_id": fact_id}
                for transaction_id, fact_id in current_fact_target_ids
            ],
            "target_snapshot": _merge_target_snapshot(
                transaction=target,
                fact=target_fact,
            ),
        }
        # Bind confirmation to precisely the duplicate rows and fingerprint the
        # user saw. A new matching row forces review again at final confirm.
        evidence["review_accepted_at"] = reviewed_at.isoformat()
        evidence["duplicate_review_fingerprint"] = candidate.fingerprint
        evidence["duplicate_review_transaction_ids"] = presented_ids
        evidence.pop("duplicate_review_bucket_watermark", None)
        evidence["duplicate_review_sibling"] = False
        candidate.evidence = evidence
        candidate.duplicate_transaction_id = target.id
        candidate.validation_errors = []
        candidate.warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") not in {"CATEGORY_REVIEW_REQUIRED", "POSSIBLE_DUPLICATE"}
        ]
        candidate.status = "ready"
    elif data.action == "record_duplicate":
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
        fact_matches, fact_overflow_watermark = _find_possible_duplicate_fact_targets_for_candidate(
            db,
            candidate=candidate,
        )
        fact_target_ids = sorted({
            (target.transaction.id, target.fact.id)
            for target in fact_matches
        })
        possible_ids = sorted({
            *(row.id for row in possible_matches),
            *(transaction_id for transaction_id, _ in fact_target_ids),
        })
        sibling_matches = _active_sibling_fingerprint_matches(db, candidate=candidate)
        sibling_possible = bool(sibling_matches)
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
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in fact_target_ids
        ]
        evidence["possible_duplicate_candidate_ids"] = sorted(row.id for row in sibling_matches)
        evidence["duplicate_review_sibling"] = bool(sibling_possible)
        effective_overflow = overflow_watermark or fact_overflow_watermark
        if effective_overflow is not None:
            bucket_watermark = effective_overflow.as_evidence()
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
        changes = requested_candidate_changes
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
        fact_matches, fact_overflow_watermark = _find_possible_duplicate_fact_targets_for_candidate(
            db,
            candidate=candidate,
        )
        possible = possible_matches[0] if possible_matches else None
        fact_target_ids = {
            (target.transaction.id, target.fact.id)
            for target in fact_matches
        }
        possible_ids = {
            *(row.id for row in possible_matches),
            *(transaction_id for transaction_id, _ in fact_target_ids),
        }
        current_bucket_watermark = (
            (overflow_watermark or fact_overflow_watermark).as_evidence()
            if (overflow_watermark or fact_overflow_watermark) is not None
            else None
        )
        effective_overflow = overflow_watermark or fact_overflow_watermark
        formal_possible = bool(possible_ids) or current_bucket_watermark is not None
        sibling_matches = _active_sibling_fingerprint_matches(db, candidate=candidate)
        sibling_possible = bool(sibling_matches)
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
                    and (
                        not _candidate_duplicate_fact_target_ids(candidate)
                        or sorted(fact_target_ids) == _candidate_duplicate_fact_target_ids(candidate)
                    )
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
            accepted_fact_targets = sorted(fact_target_ids)
            accepted_sibling = sibling_possible
            retained_warnings = []
            possible_matches = []
            possible = None
            formal_possible = False
            sibling_possible = False
            evidence = dict(candidate.evidence or {})
            if sibling_matches:
                evidence["possible_duplicate_candidate_ids"] = sorted(row.id for row in sibling_matches)
            else:
                evidence.pop("possible_duplicate_candidate_ids", None)
            evidence["review_accepted_at"] = datetime.utcnow().isoformat()
            if accepted_possible_ids and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = accepted_possible_ids
                evidence["possible_duplicate_transaction_ids"] = accepted_possible_ids
                evidence["possible_duplicate_fact_targets"] = [
                    {"transaction_id": transaction_id, "fact_id": fact_id}
                    for transaction_id, fact_id in accepted_fact_targets
                ]
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence["duplicate_review_sibling"] = bool(accepted_sibling)
            elif current_bucket_watermark is not None and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = []
                evidence["possible_duplicate_transaction_ids"] = []
                evidence["possible_duplicate_fact_targets"] = []
                evidence["duplicate_review_bucket_watermark"] = current_bucket_watermark
                evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
                evidence["duplicate_review_sibling"] = bool(accepted_sibling)
            elif accepted_sibling and candidate.fingerprint:
                evidence["duplicate_review_fingerprint"] = candidate.fingerprint
                evidence["duplicate_review_transaction_ids"] = []
                evidence["possible_duplicate_transaction_ids"] = []
                evidence["possible_duplicate_fact_targets"] = []
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence["duplicate_review_sibling"] = True
            else:
                evidence.pop("duplicate_review_fingerprint", None)
                evidence.pop("duplicate_review_transaction_ids", None)
                evidence.pop("possible_duplicate_transaction_ids", None)
                evidence.pop("possible_duplicate_fact_targets", None)
                evidence.pop("duplicate_review_bucket_watermark", None)
                evidence.pop("possible_duplicate_bucket_watermark", None)
                evidence.pop("duplicate_review_sibling", None)
                evidence.pop("possible_duplicate_candidate_ids", None)
            candidate.evidence = evidence
        elif formal_possible or sibling_possible:
            _append_issue(
                retained_warnings,
                field="fingerprint",
                code="POSSIBLE_DUPLICATE",
                message=(
                    (
                        f"同日同金额已有 {effective_overflow.count} 个可能对应，"
                        "已触发有界查重，请人工核对后决定是否入账"
                    )
                    if effective_overflow is not None
                    else
                    f"发现 {len(fact_target_ids)} 个同日同金额且描述相近的已有经济事实，请核对后决定是否入账"
                    if fact_target_ids
                    else f"发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请核对后决定是否入账"
                    if possible_matches
                    else "发现其他待处理批次或同批次中同日同额且描述相近的候选，请核对后决定是否入账"
                ),
            )
            evidence = dict(candidate.evidence or {})
            evidence["possible_duplicate_transaction_ids"] = sorted(possible_ids)
            evidence["possible_duplicate_fact_targets"] = [
                {"transaction_id": transaction_id, "fact_id": fact_id}
                for transaction_id, fact_id in sorted(fact_target_ids)
            ]
            evidence["possible_duplicate_candidate_ids"] = sorted(row.id for row in sibling_matches)
            if current_bucket_watermark is not None:
                evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
            else:
                evidence.pop("possible_duplicate_bucket_watermark", None)
            candidate.evidence = evidence
        evidence = dict(candidate.evidence or {})
        if sibling_matches:
            evidence["possible_duplicate_candidate_ids"] = sorted(row.id for row in sibling_matches)
        else:
            evidence.pop("possible_duplicate_candidate_ids", None)
        candidate.evidence = evidence
        candidate.warnings = retained_warnings
        candidate.duplicate_transaction_id = (
            possible.id
            if possible is not None
            else min(possible_ids) if possible_ids else None
        )
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
    corroborating = [
        item
        for item in confirmed
        if isinstance((item.evidence or {}).get("economic_fact_merge"), dict)
        and (item.evidence or {}).get("economic_fact_merge", {}).get("confirmed_at")
    ]
    corroborating_fact_ids = sorted({
        int((item.evidence or {})["economic_fact_merge"]["target_fact_id"])
        for item in corroborating
    })
    independent = []
    for item in confirmed:
        merge_intent = (item.evidence or {}).get("economic_fact_merge")
        if not isinstance(merge_intent, dict) or not merge_intent.get("confirmed_at"):
            independent.append(item)
            continue
        try:
            allocated_amount = Decimal(str(merge_intent["allocated_amount"]))
        except (KeyError, TypeError, ValueError):
            # A confirmed row should never reach this branch, but treating a
            # malformed historical intent as independent is safer than
            # claiming that its full cashflow disappeared from the ledger.
            independent.append(item)
            continue
        if item.amount is not None and Decimal(item.amount) > allocated_amount:
            independent.append(item)
    return {
        "batch": batch_payload(batch),
        "confirmed_candidate_ids": [item.id for item in confirmed],
        "transaction_ids": [item.transaction_id for item in confirmed],
        "duplicate_candidate_ids": [item.id for item in duplicates],
        "independent_candidate_ids": [item.id for item in independent],
        "corroborating_candidate_ids": [item.id for item in corroborating],
        "corroborating_fact_ids": corroborating_fact_ids,
        "confirmed_count": len(confirmed),
        "duplicate_count": len(duplicates),
        "independent_count": len(independent),
        "corroborating_count": len(corroborating),
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
    dict[str, list[_FormalFactDuplicateTarget]],
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
    fact_possible_by_fingerprint: dict[str, list[_FormalFactDuplicateTarget]] = {}
    fact_overflow_by_fingerprint: dict[str, _DuplicateBucketWatermark] = {}
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
        fact_buckets, fact_overflow = _load_formal_fact_duplicate_buckets(
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
            if key is not None and key in fact_overflow:
                if candidate.fingerprint:
                    fact_overflow_by_fingerprint[candidate.fingerprint] = fact_overflow[key]
                continue
            matches = [
                target
                for target in fact_buckets.get(key, []) if key is not None
                if _fact_target_text_is_similar(
                    merchant=candidate.merchant,
                    description=candidate.description,
                    target=target,
                )
            ]
            if matches and candidate.fingerprint:
                fact_possible_by_fingerprint[candidate.fingerprint] = matches

    return (
        available_categories,
        exact_by_key,
        possible_by_fingerprint,
        overflow_by_fingerprint,
        fact_possible_by_fingerprint,
        fact_overflow_by_fingerprint,
    )


def refresh_duplicate_candidates(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
) -> dict[str, object]:
    """Refresh formal-ledger duplicate evidence for a resumable batch.

    A batch can stay open while the trusted ledger changes.  In particular, a
    transaction may later be split into smaller economic facts that an older
    candidate could not see when it was first parsed.  This refresh only
    promotes newly visible formal matches back to human review; it never
    accepts, merges, excludes, confirms, or writes a cashflow fact for the
    user.
    """
    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能重新查重")
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.status.in_({
            "ready",
            "needs_review",
            "possible_duplicate",
        }),
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    if not candidates:
        return {
            "batch": batch_payload(batch),
            "scanned_candidate_count": 0,
            "refreshed_candidate_count": 0,
            "newly_flagged_candidate_count": 0,
        }

    (
        _available_categories,
        exact_by_key,
        possible_by_fingerprint,
        overflow_by_fingerprint,
        fact_possible_by_fingerprint,
        fact_overflow_by_fingerprint,
    ) = _prefetch_confirmation_context(
        db,
        user_id=user_id,
        formal_source_type=_formal_source_type(batch.source_type),
        candidates=candidates,
    )
    refreshed_count = 0
    newly_flagged_count = 0
    for candidate in candidates:
        exact_existing = exact_by_key.get(candidate.external_key or "")
        if exact_existing is not None:
            evidence = dict(candidate.evidence or {})
            for key in (
                "review_accepted_at",
                "duplicate_review_fingerprint",
                "duplicate_review_transaction_ids",
                "duplicate_review_bucket_watermark",
                "duplicate_review_sibling",
                "economic_fact_merge",
                "possible_duplicate_transaction_ids",
                "possible_duplicate_fact_targets",
                "possible_duplicate_bucket_watermark",
            ):
                evidence.pop(key, None)
            warnings = [
                dict(issue)
                for issue in (candidate.warnings or [])
                if issue.get("code") not in {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"}
            ]
            _append_issue(
                warnings,
                field="external_key",
                code="EXACT_DUPLICATE",
                message="恢复批次时发现该条来源流水已进入可信账本，已默认排除",
            )
            candidate.evidence = evidence
            candidate.warnings = warnings
            candidate.duplicate_transaction_id = exact_existing.id
            candidate.status = "exact_duplicate"
            refreshed_count += 1
            newly_flagged_count += 1
            continue
        possible_matches = possible_by_fingerprint.get(candidate.fingerprint or "", [])
        overflow_watermark = overflow_by_fingerprint.get(candidate.fingerprint or "")
        fact_matches = fact_possible_by_fingerprint.get(candidate.fingerprint or "", [])
        fact_overflow_watermark = fact_overflow_by_fingerprint.get(candidate.fingerprint or "")
        current_bucket_watermark = (
            (overflow_watermark or fact_overflow_watermark).as_evidence()
            if (overflow_watermark or fact_overflow_watermark) is not None
            else None
        )
        fact_target_ids = {
            (target.transaction.id, target.fact.id)
            for target in fact_matches
        }
        formal_transaction_ids = {
            *(row.id for row in possible_matches),
            *(transaction_id for transaction_id, _ in fact_target_ids),
        }
        if not formal_transaction_ids and current_bucket_watermark is None:
            continue

        evidence = dict(candidate.evidence or {})
        replay = evidence.get("same_source_replay_match")
        replay_transaction_ids = {
            int(value)
            for value in (replay.get("transaction_ids") if isinstance(replay, dict) else []) or []
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        }
        visible_transaction_ids = sorted(formal_transaction_ids | replay_transaction_ids)
        visible_fact_targets = sorted(fact_target_ids)
        previously_visible_ids = _candidate_duplicate_transaction_ids(candidate)
        previously_visible_fact_targets = _candidate_duplicate_fact_target_ids(candidate)
        previously_visible_watermark = evidence.get("possible_duplicate_bucket_watermark")
        visible_match_is_unchanged = (
            visible_transaction_ids == previously_visible_ids
            and visible_fact_targets == previously_visible_fact_targets
            and current_bucket_watermark == previously_visible_watermark
        )
        review_is_current = (
            evidence.get("duplicate_review_fingerprint") == candidate.fingerprint
            and (
                (
                    current_bucket_watermark is not None
                    and evidence.get("duplicate_review_bucket_watermark")
                    == current_bucket_watermark
                )
                or (
                    current_bucket_watermark is None
                    and visible_transaction_ids
                    == sorted(
                        int(value)
                        for value in evidence.get("duplicate_review_transaction_ids", [])
                        if isinstance(value, int)
                        or (isinstance(value, str) and value.isdigit())
                    )
                    and visible_fact_targets == previously_visible_fact_targets
                )
            )
        )
        if visible_match_is_unchanged and (
            candidate.status == "possible_duplicate" or review_is_current
        ):
            continue

        previous_status = candidate.status
        for key in (
            "review_accepted_at",
            "duplicate_review_fingerprint",
            "duplicate_review_transaction_ids",
            "duplicate_review_bucket_watermark",
            "duplicate_review_sibling",
            "economic_fact_merge",
        ):
            evidence.pop(key, None)
        evidence["possible_duplicate_transaction_ids"] = visible_transaction_ids
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in visible_fact_targets
        ]
        if current_bucket_watermark is not None:
            evidence["possible_duplicate_bucket_watermark"] = current_bucket_watermark
        else:
            evidence.pop("possible_duplicate_bucket_watermark", None)
        warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") != "POSSIBLE_DUPLICATE"
        ]
        effective_overflow = overflow_watermark or fact_overflow_watermark
        _append_issue(
            warnings,
            field="fingerprint",
            code="POSSIBLE_DUPLICATE",
            message=(
                f"恢复批次时发现同日同金额已有 {effective_overflow.count} 个可能对应，请再次人工核对"
                if effective_overflow is not None
                else f"恢复批次时发现 {len(visible_fact_targets)} 个描述相近的已有经济事实，请选择对应事实或明确作为新账记录"
                if visible_fact_targets
                else f"恢复批次时发现 {len(visible_transaction_ids)} 笔同日同金额且描述相近的已有记录，请再次核对"
            ),
        )
        candidate.evidence = evidence
        candidate.warnings = warnings
        candidate.duplicate_transaction_id = (
            min(visible_transaction_ids) if visible_transaction_ids else None
        )
        candidate.status = "possible_duplicate"
        refreshed_count += 1
        if previous_status != "possible_duplicate":
            newly_flagged_count += 1

    if refreshed_count:
        batch.updated_at = datetime.utcnow()
        db.flush()
        refresh_batch_counts(db, batch)
        try:
            db.commit()
        except (IntegrityError, StaleDataError) as exc:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_refresh_conflict",
                "恢复批次时账本或候选已变化，请重试",
            ) from exc
        db.refresh(batch)

    return {
        "batch": batch_payload(batch),
        "scanned_candidate_count": len(candidates),
        "refreshed_candidate_count": refreshed_count,
        "newly_flagged_candidate_count": newly_flagged_count,
    }


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
    _validate_selected_candidate_merge_groups(candidates)

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
        fact_possible_by_fingerprint,
        fact_overflow_by_fingerprint,
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
        if index.has_match(
            selected.merchant,
            selected.description,
            batch_id=selected.batch_id,
            evidence=selected.evidence,
        ):
            selected_sibling_possible_ids.add(selected.id)
        index.add(
            selected.merchant,
            selected.description,
            batch_id=selected.batch_id,
            evidence=selected.evidence,
        )
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
        fact_matches = fact_possible_by_fingerprint.get(candidate.fingerprint or "", [])
        fact_overflow_watermark = fact_overflow_by_fingerprint.get(candidate.fingerprint or "")
        fact_target_ids = {
            (target.transaction.id, target.fact.id)
            for target in fact_matches
        }
        current_bucket_watermark = (
            (overflow_watermark or fact_overflow_watermark).as_evidence()
            if (overflow_watermark or fact_overflow_watermark) is not None
            else None
        )
        if not possible_matches and not fact_matches and current_bucket_watermark is None and not sibling_possible:
            continue
        possible_ids = {
            *(row.id for row in possible_matches),
            *(transaction_id for transaction_id, _ in fact_target_ids),
        }
        evidence = dict(candidate.evidence or {})
        accepted_ids = {
            int(value)
            for value in evidence.get("duplicate_review_transaction_ids", [])
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        }
        accepted_fact_targets = {
            (int(row["transaction_id"]), int(row["fact_id"]))
            for row in evidence.get("possible_duplicate_fact_targets", [])
            if isinstance(row, dict)
            and str(row.get("transaction_id", "")).isdigit()
            and str(row.get("fact_id", "")).isdigit()
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
                and not fact_matches
                or (
                    evidence.get("duplicate_review_fingerprint") == candidate.fingerprint
                    and possible_ids == accepted_ids
                    and fact_target_ids == accepted_fact_targets
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
                    f"确认前发现同日同金额已有 {(overflow_watermark or fact_overflow_watermark).count} 笔记录，"
                    "已触发有界查重，请再次人工核对"
                )
                if (overflow_watermark or fact_overflow_watermark) is not None
                else
                f"确认前发现 {len(fact_target_ids)} 个同日同金额且描述相近的已有经济事实，请再次核对后决定是否入账"
                if fact_target_ids
                else f"确认前发现 {len(possible_matches)} 笔同日同金额且描述相近的已有记录，请再次核对后决定是否入账"
                if possible_matches
                else "确认前发现待处理批次中有同日同额且描述相近的候选，请再次核对"
            ),
        )
        candidate.warnings = warnings
        candidate.status = "possible_duplicate"
        candidate.duplicate_transaction_id = min(possible_ids) if possible_ids else None
        evidence["possible_duplicate_transaction_ids"] = sorted(possible_ids)
        evidence["possible_duplicate_fact_targets"] = [
            {"transaction_id": transaction_id, "fact_id": fact_id}
            for transaction_id, fact_id in sorted(fact_target_ids)
        ]
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

    merge_contexts: dict[
        int,
        tuple[dict, FinancialTransaction, EconomicFact],
    ] = {}
    try:
        for candidate in ordered_candidates:
            merge_context = _validated_candidate_merge_intent(
                db,
                batch=batch,
                candidate=candidate,
            )
            if merge_context is not None:
                merge_contexts[candidate.id] = merge_context
    except HTTPException:
        # Confirmation never leaves a partially created source observation or
        # allocation behind when the reviewed target changed.
        db.rollback()
        raise

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
        merge_context = merge_contexts.get(candidate.id)
        merge_ledger_revision: int | None = None
        merged_fact: EconomicFact | None = None
        try:
            with db.begin_nested():
                db.add(transaction)
                db.flush()
                source_fact = sync_transaction_fact(
                    db,
                    transaction=transaction,
                    user_id=user_id,
                    assume_missing=True,
                )
                transaction_revision = record_transaction_ledger_revision(
                    db,
                    owner=owner,
                    transaction=transaction,
                    operation="create",
                    before_snapshot=None,
                    reason=(
                        f"用户确认导入候选 #{candidate.id} 并作为已有经济事实的来源证据"
                        if merge_context is not None
                        else f"用户确认导入候选 #{candidate.id}"
                    ),
                )
                if merge_context is not None:
                    intent, primary_transaction, primary_fact = merge_context
                    if source_fact is None:
                        raise import_error(
                            409,
                            "cashflow_import_merge_target_changed",
                            "来源观察未能建立经济事实，本次确认已撤销",
                        )
                    primary_before = economic_fact_snapshot(db, primary_fact)
                    source_before = economic_fact_snapshot(db, source_fact)
                    merged_fact = merge_fact_evidence_locked(
                        db,
                        user_id=user_id,
                        primary_transaction=primary_transaction,
                        evidence_transaction=transaction,
                        allocated_amount=Decimal(str(intent["allocated_amount"])),
                        reasons=[str(intent["reason"])],
                        detection_method="import_candidate_user_confirmed",
                        now=datetime.utcnow(),
                        primary_fact_id=primary_fact.id,
                    )
                    db.flush()
                    merge_ledger_revision = transaction_revision.ledger_revision
                    record_economic_fact_revision(
                        db,
                        owner=owner,
                        fact=primary_fact,
                        ledger_revision=merge_ledger_revision,
                        operation="merge_import_evidence",
                        before_snapshot=primary_before,
                        reason=f"候选 #{candidate.id} 作为同一事实的跨来源证据",
                    )
                    record_economic_fact_revision(
                        db,
                        owner=owner,
                        fact=source_fact,
                        ledger_revision=merge_ledger_revision,
                        operation="merge_import_evidence",
                        before_snapshot=source_before,
                        reason=f"候选 #{candidate.id} 的来源事实已分配至主事实 {primary_fact.id}",
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
        except HTTPException:
            db.rollback()
            raise
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
        if merge_context is not None:
            evidence = dict(candidate.evidence or {})
            merge_intent = dict(evidence.get("economic_fact_merge") or {})
            merge_intent["confirmed_at"] = candidate.confirmed_at.isoformat()
            merge_intent["ledger_revision"] = merge_ledger_revision
            merge_intent["target_fact_id"] = merged_fact.id if merged_fact is not None else merge_intent.get("target_fact_id")
            merge_intent["source_transaction_id"] = transaction.id
            evidence["economic_fact_merge"] = merge_intent
            candidate.evidence = evidence
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
