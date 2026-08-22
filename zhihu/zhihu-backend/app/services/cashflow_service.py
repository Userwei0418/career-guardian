from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Mapping

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.cashflow import FinancialCategory, FinancialTransaction
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
        "daily": daily,
    }
