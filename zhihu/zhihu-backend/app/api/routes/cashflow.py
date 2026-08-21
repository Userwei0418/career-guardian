from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.models.user import User
from app.schemas.cashflow import (
    CashflowSummaryResponse,
    FinancialCategoryCreate,
    FinancialCategoryResponse,
    FinancialTransactionCreate,
    FinancialTransactionResponse,
    FinancialTransactionUpdate,
)
from app.services.cashflow_service import (
    build_month_summary,
    confirmed_at_for,
    get_available_category,
    get_owned_transaction,
    parse_month,
)


router = APIRouter()


def _transaction_response(
    transaction: FinancialTransaction,
    category_name: str | None = None,
) -> FinancialTransactionResponse:
    return FinancialTransactionResponse.model_validate(transaction).model_copy(
        update={"category_name": category_name}
    )


@router.get("/categories", response_model=list[FinancialCategoryResponse])
def list_categories(
    direction: Optional[Literal["income", "expense"]] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(FinancialCategory).filter(
        FinancialCategory.is_active.is_(True),
        or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
    )
    if direction is not None:
        query = query.filter(FinancialCategory.direction == direction)
    return query.order_by(
        FinancialCategory.direction.asc(),
        FinancialCategory.sort_order.asc(),
        FinancialCategory.id.asc(),
    ).all()


@router.post(
    "/categories",
    response_model=FinancialCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: FinancialCategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(FinancialCategory)
        .filter(
            FinancialCategory.direction == data.direction,
            FinancialCategory.name == data.name,
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
            FinancialCategory.is_active.is_(True),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="这个分类已经存在")
    category = FinancialCategory(
        user_id=user.id,
        direction=data.direction,
        name=data.name,
        is_system=False,
        is_active=True,
        sort_order=1000,
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="这个分类已经存在") from None
    db.refresh(category)
    return category


@router.get("/transactions", response_model=list[FinancialTransactionResponse])
def list_transactions(
    month: Optional[str] = None,
    direction: Optional[Literal["income", "expense", "transfer"]] = None,
    transaction_status: Optional[Literal["pending", "confirmed", "excluded"]] = Query(
        default=None,
        alias="status",
    ),
    category_id: Optional[int] = None,
    keyword: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == user.id,
        FinancialTransaction.deleted_at.is_(None),
    )
    if month is not None:
        _, start, end = parse_month(month)
        query = query.filter(
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
        )
    if direction is not None:
        query = query.filter(FinancialTransaction.direction == direction)
    if transaction_status is not None:
        query = query.filter(FinancialTransaction.status == transaction_status)
    if category_id is not None:
        query = query.filter(FinancialTransaction.category_id == category_id)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                FinancialTransaction.merchant.ilike(pattern),
                FinancialTransaction.description.ilike(pattern),
            )
        )
    rows = query.order_by(
        FinancialTransaction.transaction_date.desc(),
        FinancialTransaction.id.desc(),
    ).offset(offset).limit(limit).all()
    category_ids = {item.category_id for item in rows if item.category_id is not None}
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    return [_transaction_response(transaction, category_names.get(transaction.category_id)) for transaction in rows]


@router.post(
    "/transactions",
    response_model=FinancialTransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    data: FinancialTransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = get_available_category(
        db,
        user_id=user.id,
        category_id=data.category_id,
        direction=data.direction,
    )
    transaction = FinancialTransaction(
        user_id=user.id,
        category_id=category.id if category is not None else None,
        direction=data.direction,
        amount=data.amount,
        transaction_date=data.transaction_date,
        merchant=data.merchant,
        description=data.description,
        nature=data.nature,
        source_type="manual",
        status=data.status,
        confirmed_at=confirmed_at_for(data.status),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


@router.put("/transactions/{transaction_id}", response_model=FinancialTransactionResponse)
def update_transaction(
    transaction_id: int,
    data: FinancialTransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    changes = data.model_dump(exclude_unset=True)
    direction = changes.get("direction", transaction.direction)
    category_id = None if direction == "transfer" else changes.get("category_id", transaction.category_id)
    category = get_available_category(
        db,
        user_id=user.id,
        category_id=category_id,
        direction=direction,
    )
    if direction == "transfer":
        changes["category_id"] = None
    if direction != "expense":
        changes["nature"] = None
    for field, value in changes.items():
        setattr(transaction, field, value)
    if "status" in changes:
        transaction.confirmed_at = confirmed_at_for(changes["status"], transaction.confirmed_at)
        if changes["status"] != "excluded":
            transaction.excluded_reason = None
    db.commit()
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


@router.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    transaction.status = "deleted"
    transaction.deleted_at = datetime.utcnow()
    db.commit()
    return {"deleted": True}


@router.get("/summary", response_model=CashflowSummaryResponse)
def get_summary(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, start, end = parse_month(month)
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
        )
        .all()
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    return build_month_summary(
        month=normalized_month,
        transactions=transactions,
        category_names=category_names,
    )
