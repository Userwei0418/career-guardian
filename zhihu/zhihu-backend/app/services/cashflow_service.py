from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Mapping

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cashflow import FinancialCategory, FinancialTransaction


VALID_DIRECTIONS = {"income", "expense", "transfer"}
VALID_STATUSES = {"pending", "confirmed", "excluded"}
EXPENSE_NATURES = ("fixed", "flexible", "one_off", "reimbursable", "other")


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


def _money(value: Decimal | int | float) -> float:
    return float(Decimal(value).quantize(Decimal("0.01")))


def build_month_summary(
    *,
    month: str,
    transactions: Iterable[FinancialTransaction],
    category_names: Mapping[int, str],
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
        if transaction.direction == "transfer":
            transfer_amount += amount
            continue
        if transaction.direction not in {"income", "expense"}:
            continue
        if transaction.direction == "income":
            income += amount
        else:
            expense += amount
            recorded_nature = getattr(transaction, "nature", None)
            nature = recorded_nature if recorded_nature in EXPENSE_NATURES else "other"
            expense_nature_totals[nature]["amount"] += amount
            expense_nature_totals[nature]["count"] += 1
        daily_totals[transaction.transaction_date][transaction.direction] += amount
        category_id = transaction.category_id
        bucket = category_totals[transaction.direction].setdefault(
            category_id,
            {
                "category_id": category_id,
                "category_name": category_names.get(category_id, "未分类"),
                "amount": Decimal("0"),
                "count": 0,
            },
        )
        bucket["amount"] = Decimal(bucket["amount"]) + amount
        bucket["count"] = int(bucket["count"]) + 1

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
