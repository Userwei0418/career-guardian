from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Iterable, Mapping

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.cashflow import (
    EconomicFactRelation,
    EconomicFactRelationRevision,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialTransaction,
    FinancialTransactionRevision,
)
from app.models.user import User
from app.cashflow_validation import MAX_FINANCIAL_DATE, MIN_FINANCIAL_DATE


VALID_DIRECTIONS = {"income", "expense", "transfer"}
VALID_STATUSES = {"pending", "confirmed", "excluded"}
EXPENSE_NATURES = ("fixed", "flexible", "one_off", "reimbursable", "other")


def _is_retryable_mysql_conflict(exc: OperationalError) -> bool:
    original = getattr(exc, "orig", None)
    args = getattr(original, "args", ())
    return bool(args and args[0] in {1205, 1213})


def lock_financial_ledger_owner(
    db: Session,
    *,
    user_id: int,
    conflict_code: str | None = None,
) -> User:
    """Serialize every formal-ledger mutation for one user.

    Import confirmation uses fuzzy duplicate detection, which cannot be guarded
    by the external-key unique constraint. Manual create/update/delete and data
    clearing must take this same user-row lock before touching transactions so a
    confirmation always rechecks against the latest committed ledger state.
    """
    try:
        owner = (
            db.query(User)
            .filter(User.id == user_id)
            .with_for_update()
            .one_or_none()
        )
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_mysql_conflict(exc):
            message = "同一账本正在写入，请刷新后重试"
            detail = (
                {"code": conflict_code, "message": message}
                if conflict_code is not None
                else message
            )
            raise HTTPException(status_code=409, detail=detail) from exc
        raise
    if owner is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return owner


def commit_financial_ledger(db: Session) -> None:
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        if _is_retryable_mysql_conflict(exc):
            raise HTTPException(status_code=409, detail="同一账本正在写入，请刷新后重试") from exc
        raise


def financial_transaction_snapshot(transaction: FinancialTransaction) -> dict:
    return {
        "id": transaction.id,
        "direction": transaction.direction,
        "amount": format(Decimal(transaction.amount), "f"),
        "currency": transaction.currency,
        "transaction_date": transaction.transaction_date.isoformat(),
        "occurred_at": transaction.occurred_at.isoformat() if transaction.occurred_at else None,
        "category_id": transaction.category_id,
        "merchant": transaction.merchant,
        "description": transaction.description,
        "nature": transaction.nature,
        "source_type": transaction.source_type,
        "source_ref": transaction.source_ref,
        "external_key": transaction.external_key,
        "status": transaction.status,
        "confirmed_at": transaction.confirmed_at.isoformat() if transaction.confirmed_at else None,
        "excluded_reason": transaction.excluded_reason,
        "deleted_at": transaction.deleted_at.isoformat() if transaction.deleted_at else None,
    }


def record_financial_ledger_event(
    db: Session,
    *,
    owner: User,
    event_type: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
) -> int:
    owner.financial_ledger_revision = int(owner.financial_ledger_revision or 0) + 1
    ledger_revision = owner.financial_ledger_revision
    db.add(FinancialLedgerRevisionEvent(
        user_id=owner.id,
        revision_number=ledger_revision,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        actor_user_id=owner.id,
    ))
    return ledger_revision


def record_transaction_ledger_revision(
    db: Session,
    *,
    owner: User,
    transaction: FinancialTransaction,
    operation: str,
    before_snapshot: dict | None,
    reason: str | None = None,
) -> FinancialTransactionRevision:
    transaction_revision = (
        db.query(func.max(FinancialTransactionRevision.transaction_revision))
        .filter(FinancialTransactionRevision.transaction_id == transaction.id)
        .scalar()
        or 0
    ) + 1
    summary = {
        "create": "创建正式流水",
        "update": "修订正式流水",
        "delete": "撤销正式流水",
        "restore": "恢复正式流水",
    }.get(operation, "更新正式流水")
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type=f"transaction_{operation}",
        entity_type="financial_transaction",
        entity_id=transaction.id,
        summary=summary,
    )
    revision = FinancialTransactionRevision(
        user_id=owner.id,
        transaction_id=transaction.id,
        transaction_revision=transaction_revision,
        ledger_revision=ledger_revision,
        operation=operation,
        before_snapshot=before_snapshot,
        after_snapshot=financial_transaction_snapshot(transaction),
        reason=reason,
        actor_user_id=owner.id,
    )
    db.add(revision)
    return revision


def economic_relation_snapshot(relation: EconomicFactRelation) -> dict:
    return {
        "id": relation.id,
        "source_fact_id": relation.source_fact_id,
        "target_fact_id": relation.target_fact_id,
        "relation_type": relation.relation_type,
        "allocated_amount": format(Decimal(relation.allocated_amount), "f"),
        "status": relation.status,
        "detection_method": relation.detection_method,
        "reasons": list(relation.reasons or []),
        "confirmed_at": relation.confirmed_at.isoformat() if relation.confirmed_at else None,
        "reversed_at": relation.reversed_at.isoformat() if relation.reversed_at else None,
    }


def record_economic_relation_revision(
    db: Session,
    *,
    owner: User,
    relation: EconomicFactRelation,
    operation: str,
    before_snapshot: dict | None,
    reason: str | None = None,
) -> EconomicFactRelationRevision:
    relation_revision = (
        db.query(func.max(EconomicFactRelationRevision.relation_revision))
        .filter(EconomicFactRelationRevision.relation_id == relation.id)
        .scalar()
        or 0
    ) + 1
    summary = "确认经济事实关系" if operation == "confirm" else "撤销经济事实关系"
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type=f"relation_{operation}",
        entity_type="economic_fact_relation",
        entity_id=relation.id,
        summary=f"{summary}：{relation.relation_type}",
    )
    revision = EconomicFactRelationRevision(
        user_id=owner.id,
        relation_id=relation.id,
        relation_revision=relation_revision,
        ledger_revision=ledger_revision,
        operation=operation,
        before_snapshot=before_snapshot,
        after_snapshot=economic_relation_snapshot(relation),
        reason=reason,
        actor_user_id=owner.id,
    )
    db.add(revision)
    return revision


def parse_month(value: str | None) -> tuple[str, date, date]:
    if value is None:
        today = date.today()
        value = f"{today.year:04d}-{today.month:02d}"
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        start = date(year, month, 1)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="月份必须使用 YYYY-MM 格式") from None
    if value != f"{year:04d}-{month:02d}":
        raise HTTPException(status_code=400, detail="月份必须使用 YYYY-MM 格式")
    if start < MIN_FINANCIAL_DATE or start > date(MAX_FINANCIAL_DATE.year, 12, 1):
        raise HTTPException(status_code=400, detail="月份超出支持范围")
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return value, start, end


def get_available_category(
    db: Session,
    *,
    user_id: int,
    category_id: int | None,
    direction: str,
) -> FinancialCategory | None:
    if direction == "transfer":
        if category_id is not None:
            raise HTTPException(status_code=400, detail="转账不参与收支分类")
        return None
    if category_id is None:
        raise HTTPException(status_code=400, detail="收入和支出必须选择分类")
    category = (
        db.query(FinancialCategory)
        .filter(
            FinancialCategory.id == category_id,
            FinancialCategory.is_active.is_(True),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user_id),
        )
        .first()
    )
    if category is None:
        raise HTTPException(status_code=404, detail="收支分类不存在")
    if category.direction != direction:
        raise HTTPException(status_code=400, detail="分类方向与流水方向不一致")
    return category


def get_owned_transaction(db: Session, *, user_id: int, transaction_id: int) -> FinancialTransaction:
    transaction = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.deleted_at.is_(None),
        )
        .first()
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="收支记录不存在")
    return transaction


def confirmed_at_for(status: str, current: datetime | None = None) -> datetime | None:
    if status == "confirmed":
        return current or datetime.utcnow()
    return None


def _money(value: Decimal | int | float) -> Decimal:
    # Keep cents exact through the response model. Pydantic serializes Decimal
    # as a JSON string, so JavaScript never receives a rounded IEEE-754 number.
    return Decimal(value).quantize(Decimal("0.01"))


def build_month_summary(
    *,
    month: str,
    transactions: Iterable[FinancialTransaction],
    category_names: Mapping[int, str],
    relation_effects: Mapping[int, Mapping[str, Decimal | int | str | None]] | None = None,
) -> dict:
    income = Decimal("0")
    expense = Decimal("0")
    transfer_amount = Decimal("0")
    confirmed_count = 0
    pending_count = 0
    excluded_count = 0
    category_totals: dict[str, dict[int | None, dict[str, Decimal | int | str | None]]] = {
        "income": {},
        "expense": {},
    }
    expense_nature_totals = {
        nature: {"amount": Decimal("0"), "count": 0}
        for nature in EXPENSE_NATURES
    }
    expense_merchant_totals: dict[str, dict[str, Decimal | int | str]] = {}
    daily_totals: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: {"income": Decimal("0"), "expense": Decimal("0")}
    )

    for transaction in transactions:
        if transaction.status == "pending":
            pending_count += 1
            continue
        if transaction.status == "excluded":
            excluded_count += 1
            continue
        if transaction.status != "confirmed":
            continue
        confirmed_count += 1
        amount = Decimal(transaction.amount)
        effect = (relation_effects or {}).get(getattr(transaction, "id", None), {})
        income_remove = min(amount, Decimal(effect.get("income_remove") or 0))
        expense_remove = min(amount, Decimal(effect.get("expense_remove") or 0))
        transfer_remove = min(amount, Decimal(effect.get("transfer_remove") or 0))
        transfer_add = Decimal(effect.get("transfer_add") or 0)
        expense_offset = Decimal(effect.get("expense_offset") or 0)
        if transaction.direction == "transfer":
            transfer_amount += amount - transfer_remove + transfer_add
            continue
        if transaction.direction not in {"income", "expense"}:
            continue
        if transaction.direction == "income":
            effective_amount = amount - income_remove
            income += effective_amount
        else:
            effective_amount = amount - expense_remove
            expense += effective_amount
            recorded_nature = getattr(transaction, "nature", None)
            nature = recorded_nature if recorded_nature in EXPENSE_NATURES else "other"
            expense_nature_totals[nature]["amount"] += effective_amount
            if effective_amount > 0:
                expense_nature_totals[nature]["count"] += 1
                merchant_name = (
                    getattr(transaction, "merchant", None)
                    or getattr(transaction, "description", None)
                    or category_names.get(transaction.category_id, "未标记商户")
                )
                merchant_bucket = expense_merchant_totals.setdefault(
                    merchant_name,
                    {"merchant_name": merchant_name, "amount": Decimal("0"), "count": 0},
                )
                merchant_bucket["amount"] = Decimal(merchant_bucket["amount"]) + effective_amount
                merchant_bucket["count"] = int(merchant_bucket["count"]) + 1
        daily_totals[transaction.transaction_date][transaction.direction] += effective_amount
        category_id = transaction.category_id
        if effective_amount > 0:
            bucket = category_totals[transaction.direction].setdefault(
                category_id,
                {
                    "category_id": category_id,
                    "category_name": category_names.get(category_id, "未分类"),
                    "amount": Decimal("0"),
                    "count": 0,
                },
            )
            bucket["amount"] = Decimal(bucket["amount"]) + effective_amount
            bucket["count"] = int(bucket["count"]) + 1
        if expense_offset > 0:
            expense -= expense_offset
            daily_totals[transaction.transaction_date]["expense"] -= expense_offset
            offset_category_id = effect.get("offset_category_id")
            offset_bucket = category_totals["expense"].setdefault(
                int(offset_category_id) if offset_category_id is not None else None,
                {
                    "category_id": int(offset_category_id) if offset_category_id is not None else None,
                    "category_name": str(effect.get("offset_category_name") or "退款/报销冲销"),
                    "amount": Decimal("0"),
                    "count": 0,
                },
            )
            offset_bucket["amount"] = Decimal(offset_bucket["amount"]) - expense_offset
            offset_nature = str(effect.get("offset_nature") or "other")
            if offset_nature not in EXPENSE_NATURES:
                offset_nature = "other"
            expense_nature_totals[offset_nature]["amount"] -= expense_offset
            offset_merchant = str(effect.get("offset_merchant") or "未标记商户")
            merchant_bucket = expense_merchant_totals.setdefault(
                offset_merchant,
                {"merchant_name": offset_merchant, "amount": Decimal("0"), "count": 0},
            )
            merchant_bucket["amount"] = Decimal(merchant_bucket["amount"]) - expense_offset
        if transfer_add > 0:
            transfer_amount += transfer_add

    def category_items(direction: str) -> list[dict]:
        items = []
        for bucket in category_totals[direction].values():
            items.append({**bucket, "amount": _money(Decimal(bucket["amount"]))})
        return sorted(items, key=lambda item: (-item["amount"], item["category_name"]))

    daily = [
        {
            "date": day,
            "income": _money(amounts["income"]),
            "expense": _money(amounts["expense"]),
        }
        for day, amounts in sorted(daily_totals.items())
    ]
    expense_natures = [
        {
            "nature": nature,
            "amount": _money(expense_nature_totals[nature]["amount"]),
            "count": expense_nature_totals[nature]["count"],
        }
        for nature in EXPENSE_NATURES
    ]
    expense_merchants = sorted(
        [
            {**bucket, "amount": _money(Decimal(bucket["amount"]))}
            for bucket in expense_merchant_totals.values()
            if Decimal(bucket["amount"]) > 0
        ],
        key=lambda item: (-item["amount"], item["merchant_name"]),
    )
    state = "not_started"
    if confirmed_count or excluded_count:
        state = "recording"
    if pending_count:
        state = "needs_confirmation"
    return {
        "month": month,
        "state": state,
        "income": _money(income),
        "expense": _money(expense),
        "net": _money(income - expense),
        "transfer_amount": _money(transfer_amount),
        "confirmed_count": confirmed_count,
        "pending_count": pending_count,
        "excluded_count": excluded_count,
        "income_categories": category_items("income"),
        "expense_categories": category_items("expense"),
        "expense_natures": expense_natures,
        "expense_merchants": expense_merchants,
        "daily": daily,
    }


def build_recurring_expense_insights(month_summaries: Iterable[Mapping]) -> list[dict]:
    """Find repeat expense patterns without mutating ledger classifications.

    Input summaries must already use the confirmed-ledger relation-adjusted
    accounting basis. The result is deliberately a candidate signal: a stable
    monthly amount can be rent, insurance or a subscription, so this function
    never assigns a business category by itself.
    """
    grouped: dict[str, dict] = {}
    for summary in month_summaries:
        month = str(summary.get("month") or "")
        if not month:
            continue
        for item in summary.get("expense_merchants") or []:
            merchant_name = " ".join(str(item.get("merchant_name") or "").split())
            amount = Decimal(item.get("amount") or 0)
            count = int(item.get("count") or 0)
            if not merchant_name or amount <= 0 or count <= 0:
                continue
            normalized = merchant_name.casefold()
            bucket = grouped.setdefault(
                normalized,
                {"merchant_name": merchant_name, "monthly": {}},
            )
            month_bucket = bucket["monthly"].setdefault(
                month,
                {"amount": Decimal("0"), "count": 0},
            )
            month_bucket["amount"] += amount
            month_bucket["count"] += count

    insights = []
    for bucket in grouped.values():
        monthly = [
            {"month": month, "amount": values["amount"], "count": values["count"]}
            for month, values in sorted(bucket["monthly"].items())
        ]
        months_seen = len(monthly)
        if months_seen < 2:
            continue
        amounts = [Decimal(item["amount"]) for item in monthly]
        total = sum(amounts, Decimal("0"))
        average = total / Decimal(months_seen)
        minimum = min(amounts)
        maximum = max(amounts)
        variation = ((maximum - minimum) / average * Decimal("100")) if average > 0 else Decimal("0")
        occurrence_count = sum(int(item["count"]) for item in monthly)
        average_occurrences = Decimal(occurrence_count) / Decimal(months_seen)
        stable_monthly = variation <= Decimal("15") and average_occurrences <= Decimal("1.5")
        if months_seen >= 3 and variation <= Decimal("15"):
            confidence_tier = "high"
        elif variation <= Decimal("35") or months_seen >= 3:
            confidence_tier = "medium"
        else:
            confidence_tier = "low"
        reasons = [f"近期 {months_seen} 个月都有已确认支出"]
        if stable_monthly:
            reasons.append(f"每月金额波动约 {variation.quantize(Decimal('0.1'))}%")
            reasons.append("平均每月不超过 1.5 笔，像稳定月付")
        else:
            reasons.append(f"金额波动约 {variation.quantize(Decimal('0.1'))}%，只能确认为周期性消费线索")
        insights.append(
            {
                "merchant_fingerprint": recurring_merchant_fingerprint(bucket["merchant_name"]),
                "merchant_name": bucket["merchant_name"],
                "pattern_type": "stable_monthly" if stable_monthly else "recurring_variable",
                "confidence_tier": confidence_tier,
                "months_seen": months_seen,
                "occurrence_count": occurrence_count,
                "average_amount": _money(average),
                "minimum_amount": _money(minimum),
                "maximum_amount": _money(maximum),
                "variation_percent": float(variation.quantize(Decimal("0.1"))),
                "reasons": reasons,
                "monthly": [
                    {**item, "amount": _money(Decimal(item["amount"]))}
                    for item in monthly
                ],
            }
        )
    return sorted(
        insights,
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}[item["confidence_tier"]],
            -item["months_seen"],
            -item["average_amount"],
            item["merchant_name"],
        ),
    )


def recurring_merchant_fingerprint(merchant_name: str) -> str:
    normalized = " ".join(merchant_name.split()).casefold()
    return sha256(normalized.encode("utf-8")).hexdigest()
