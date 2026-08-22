from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.cashflow import (
    EconomicFact,
    EconomicFactRelation,
    FinancialCategory,
    FinancialTransaction,
)
from app.models.user import User
from app.models.career_case import CareerCase
from app.models.contract import Contract
from app.models.offer import Offer
from app.models.payslip import Payslip, PayslipArrivalLink, PayslipMaterialLink
from app.schemas.cashflow import (
    CashflowSummaryResponse,
    CashflowAskRequest,
    CashflowAskResponse,
    DeletedFinancialTransactionPage,
    EconomicFactResponse,
    EconomicRelationConfirmRequest,
    EconomicRelationResponse,
    EconomicRelationSuggestionResponse,
    FinancialCategoryCreate,
    FinancialCategoryResponse,
    FinancialTransactionCreate,
    FinancialTransactionPage,
    FinancialTransactionResponse,
    FinancialTransactionUpdate,
    RecurringExpenseResponse,
)
from app.services.cashflow_service import (
    build_month_summary,
    build_recurring_expense_insights,
    commit_financial_ledger,
    confirmed_at_for,
    get_available_category,
    get_owned_transaction,
    lock_financial_ledger_owner,
    parse_month,
)
from app.services.cashflow_chat_service import (
    answer_cashflow_question,
    build_cashflow_chat_context,
)
from app.services.cashflow_export_service import build_cashflow_export_bundle
from app.services.cashflow_privacy import redact_cashflow_text
from app.services.economic_fact_service import (
    build_relation_suggestions,
    enrich_relation_suggestions_with_ai,
    get_transaction_fact,
    refresh_fact_type_from_relations,
    sync_transaction_fact,
)
from app.services.payslip_service import (
    build_material_comparisons,
    build_month_comparison,
    build_payslip_guardian_summary,
)


router = APIRouter()


def _transaction_response(
    transaction: FinancialTransaction,
    category_name: str | None = None,
) -> FinancialTransactionResponse:
    return FinancialTransactionResponse.model_validate(transaction).model_copy(
        update={"category_name": category_name}
    )


def _fact_response(fact: EconomicFact) -> EconomicFactResponse:
    return EconomicFactResponse(
        id=fact.id,
        primary_transaction_id=fact.primary_transaction_id,
        fact_type=fact.fact_type,
        title=fact.title,
        occurred_date=fact.occurred_date,
        amount=fact.amount,
        currency=fact.currency,
        status=fact.status,
    )


def _relation_response(db: Session, relation: EconomicFactRelation) -> EconomicRelationResponse:
    source_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.source_fact_id).one()
    target_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.target_fact_id).one()
    return EconomicRelationResponse(
        id=relation.id,
        source_fact_id=source_fact.id,
        target_fact_id=target_fact.id,
        source_transaction_id=source_fact.primary_transaction_id,
        target_transaction_id=target_fact.primary_transaction_id,
        source_title=source_fact.title,
        target_title=target_fact.title,
        source_amount=source_fact.amount,
        target_amount=target_fact.amount,
        source_date=source_fact.occurred_date,
        target_date=target_fact.occurred_date,
        relation_type=relation.relation_type,
        allocated_amount=relation.allocated_amount,
        status=relation.status,
        detection_method=relation.detection_method,
        reasons=relation.reasons or [],
        confirmed_at=relation.confirmed_at,
        reversed_at=relation.reversed_at,
    )


def _summary_relation_effects(
    db: Session,
    *,
    user_id: int,
    transactions: list[FinancialTransaction],
) -> tuple[dict[int, dict[str, Decimal | int | str | None]], set[int]]:
    transaction_by_id = {
        item.id: item
        for item in transactions
        if getattr(item, "id", None) is not None
    }
    if not transaction_by_id:
        return {}, set()
    month_facts = db.query(EconomicFact).filter(
        EconomicFact.user_id == user_id,
        EconomicFact.primary_transaction_id.in_(transaction_by_id),
    ).all()
    month_fact_ids = {fact.id for fact in month_facts}
    if not month_fact_ids:
        return {}, set()
    relations = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user_id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id.in_(month_fact_ids),
            EconomicFactRelation.target_fact_id.in_(month_fact_ids),
        ),
    ).all()
    if not relations:
        return {}, set()
    related_fact_ids = {
        fact_id
        for relation in relations
        for fact_id in (relation.source_fact_id, relation.target_fact_id)
    }
    facts = {
        fact.id: fact
        for fact in db.query(EconomicFact).filter(EconomicFact.id.in_(related_fact_ids)).all()
    }
    related_transaction_ids = {
        fact.primary_transaction_id
        for fact in facts.values()
        if fact.primary_transaction_id is not None
    }
    related_transactions = {
        item.id: item
        for item in db.query(FinancialTransaction).filter(
            FinancialTransaction.id.in_(related_transaction_ids),
            FinancialTransaction.user_id == user_id,
        ).all()
    }
    effects: dict[int, dict[str, Decimal | int | str | None]] = {}
    category_ids: set[int] = set()

    def add(transaction_id: int, key: str, amount: Decimal):
        if transaction_id not in transaction_by_id:
            return
        effect = effects.setdefault(transaction_id, {})
        effect[key] = Decimal(effect.get(key) or 0) + amount

    for relation in relations:
        source_fact = facts.get(relation.source_fact_id)
        target_fact = facts.get(relation.target_fact_id)
        if source_fact is None or target_fact is None:
            continue
        source_id = source_fact.primary_transaction_id
        target_id = target_fact.primary_transaction_id
        if source_id is None or target_id is None:
            continue
        amount = Decimal(relation.allocated_amount)
        source_transaction = related_transactions.get(source_id)
        target_transaction = related_transactions.get(target_id)
        if source_transaction is None or target_transaction is None:
            continue
        if relation.relation_type in {"refunds", "reimburses"}:
            add(source_id, "income_remove", amount)
            add(source_id, "expense_offset", amount)
            if source_id in transaction_by_id:
                effect = effects.setdefault(source_id, {})
                effect["offset_category_id"] = target_transaction.category_id
                effect["offset_nature"] = target_transaction.nature or "other"
                effect["offset_merchant"] = (
                    target_transaction.merchant
                    or target_transaction.description
                    or "未标记商户"
                )
                if target_transaction.category_id is not None:
                    category_ids.add(target_transaction.category_id)
        elif relation.relation_type == "transfer_pair":
            for transaction_id, relation_transaction in (
                (source_id, source_transaction),
                (target_id, target_transaction),
            ):
                if relation_transaction.direction == "income":
                    add(transaction_id, "income_remove", amount)
                elif relation_transaction.direction == "expense":
                    add(transaction_id, "expense_remove", amount)
                elif relation_transaction.direction == "transfer":
                    add(transaction_id, "transfer_remove", amount)
            anchor_id = source_id if source_id in transaction_by_id else target_id
            add(anchor_id, "transfer_add", amount)
    return effects, category_ids


def _shift_month_start(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


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
    user_id = user.id
    data_epoch = user.business_data_epoch
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if owner.business_data_epoch != data_epoch:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "cashflow_data_cleared",
                "message": "请求期间账户数据已被清空，请重新创建分类",
            },
        )
    existing = (
        db.query(FinancialCategory)
        .filter(
            FinancialCategory.direction == data.direction,
            FinancialCategory.name == data.name,
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user_id),
            FinancialCategory.is_active.is_(True),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="这个分类已经存在")
    category = FinancialCategory(
        user_id=user_id,
        direction=data.direction,
        name=data.name,
        is_system=False,
        is_active=True,
        sort_order=1000,
    )
    db.add(category)
    try:
        commit_financial_ledger(db)
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


@router.get("/transactions/page", response_model=FinancialTransactionPage)
def list_transaction_page(
    month: Optional[str] = None,
    direction: Optional[Literal["income", "expense", "transfer"]] = None,
    transaction_status: Optional[Literal["pending", "confirmed", "excluded"]] = Query(
        default="confirmed",
        alias="status",
    ),
    category_id: Optional[int] = None,
    nature: Optional[Literal["fixed", "flexible", "one_off", "reimbursable", "other"]] = None,
    keyword: Optional[str] = Query(default=None, max_length=100),
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = "date_desc",
    limit: int = Query(default=50, ge=1, le=200),
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
    if nature is not None:
        query = query.filter(
            FinancialTransaction.direction == "expense",
            FinancialTransaction.nature == nature,
        )
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                FinancialTransaction.merchant.ilike(pattern),
                FinancialTransaction.description.ilike(pattern),
            )
        )
    total = query.count()
    if sort == "amount_desc":
        ordering = (FinancialTransaction.amount.desc(), FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
    elif sort == "amount_asc":
        ordering = (FinancialTransaction.amount.asc(), FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
    else:
        ordering = (FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
    rows = query.order_by(*ordering).offset(offset).limit(limit).all()
    category_ids = {item.category_id for item in rows if item.category_id is not None}
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    return {
        "items": [
            _transaction_response(transaction, category_names.get(transaction.category_id))
            for transaction in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/transactions/trash", response_model=DeletedFinancialTransactionPage)
def list_deleted_transactions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == user.id,
        FinancialTransaction.deleted_at.isnot(None),
    )
    total = query.count()
    rows = query.order_by(
        FinancialTransaction.deleted_at.desc(),
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
    return {
        "items": [
            {
                "id": item.id,
                "direction": item.direction,
                "amount": item.amount,
                "currency": item.currency,
                "transaction_date": item.transaction_date,
                "category_id": item.category_id,
                "category_name": category_names.get(item.category_id),
                "merchant": item.merchant,
                "description": item.description,
                "nature": item.nature,
                "source_type": item.source_type,
                "deleted_at": item.deleted_at,
            }
            for item in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get(
    "/transactions/{transaction_id}/relation-suggestions",
    response_model=EconomicRelationSuggestionResponse,
)
def get_relation_suggestions(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    if transaction.status != "confirmed":
        raise HTTPException(status_code=409, detail="只能为已确认流水查找经济事实关系")
    fact = get_transaction_fact(db, transaction_id=transaction.id, user_id=user.id)
    if fact is None:
        raise HTTPException(status_code=409, detail="这笔流水尚未建立经济事实，请完成数据迁移后重试")
    start = transaction.transaction_date - timedelta(days=365)
    end = transaction.transaction_date + timedelta(days=366)
    candidates = (
        db.query(FinancialTransaction, EconomicFact)
        .join(EconomicFact, EconomicFact.primary_transaction_id == FinancialTransaction.id)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.id != transaction.id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
            EconomicFact.status == "confirmed",
        )
        .order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
        .limit(500)
        .all()
    )
    existing_pairs = {
        (row.source_fact_id, row.target_fact_id, row.relation_type)
        for row in db.query(EconomicFactRelation).filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
        ).all()
    }
    suggestions = build_relation_suggestions(
        transaction=transaction,
        fact=fact,
        candidates=candidates,
        existing_pairs=existing_pairs,
    )[:20]
    suggestions = enrich_relation_suggestions_with_ai(
        suggestions,
        transaction=transaction,
        user_id=user.id,
        expected_data_epoch=user.business_data_epoch,
    )
    return EconomicRelationSuggestionResponse(
        transaction=_transaction_response(transaction),
        fact=_fact_response(fact),
        suggestions=suggestions,
    )


@router.get(
    "/transactions/{transaction_id}/relations",
    response_model=list[EconomicRelationResponse],
)
def list_transaction_relations(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    fact = get_transaction_fact(db, transaction_id=transaction.id, user_id=user.id)
    if fact is None:
        return []
    relations = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
            or_(
                EconomicFactRelation.source_fact_id == fact.id,
                EconomicFactRelation.target_fact_id == fact.id,
            ),
        )
        .order_by(EconomicFactRelation.confirmed_at.desc(), EconomicFactRelation.id.desc())
        .all()
    )
    return [_relation_response(db, relation) for relation in relations]


@router.post("/relations", response_model=EconomicRelationResponse, status_code=status.HTTP_201_CREATED)
def confirm_economic_relation(
    data: EconomicRelationConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.source_transaction_id == data.target_transaction_id:
        raise HTTPException(status_code=400, detail="不能把同一笔流水关联给自己")
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user.id)
    source_transaction = get_owned_transaction(db, user_id=user.id, transaction_id=data.source_transaction_id)
    target_transaction = get_owned_transaction(db, user_id=user.id, transaction_id=data.target_transaction_id)
    if source_transaction.status != "confirmed" or target_transaction.status != "confirmed":
        raise HTTPException(status_code=409, detail="只能关联已确认流水")
    if data.relation_type in {"refunds", "reimburses"}:
        if source_transaction.direction != "income" or target_transaction.direction != "expense":
            raise HTTPException(status_code=400, detail="退款或报销必须由一笔收入关联到原支出")
    elif data.relation_type == "transfer_pair":
        direction_pair = {source_transaction.direction, target_transaction.direction}
        if direction_pair not in ({"income", "expense"}, {"transfer"}):
            raise HTTPException(status_code=400, detail="内部转账必须是一进一出或两笔均已标记转账")
    source_fact = get_transaction_fact(db, transaction_id=source_transaction.id, user_id=user.id)
    target_fact = get_transaction_fact(db, transaction_id=target_transaction.id, user_id=user.id)
    if source_fact is None or target_fact is None:
        raise HTTPException(status_code=409, detail="关联流水缺少经济事实，请完成数据迁移后重试")
    if data.allocated_amount > min(Decimal(source_fact.amount), Decimal(target_fact.amount)):
        raise HTTPException(status_code=409, detail="关联金额不能超过任一笔经济事实的金额")
    source_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactRelation).filter(
                EconomicFactRelation.source_fact_id == source_fact.id,
                EconomicFactRelation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    target_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactRelation).filter(
                EconomicFactRelation.target_fact_id == target_fact.id,
                EconomicFactRelation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    if source_allocated + data.allocated_amount > Decimal(source_fact.amount) + Decimal("0.01"):
        raise HTTPException(status_code=409, detail="来源事实的可关联金额不足")
    if target_allocated + data.allocated_amount > Decimal(target_fact.amount) + Decimal("0.01"):
        raise HTTPException(status_code=409, detail="目标事实的可关联金额不足")
    relation = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.source_fact_id == source_fact.id,
            EconomicFactRelation.target_fact_id == target_fact.id,
            EconomicFactRelation.relation_type == data.relation_type,
        )
        .first()
    )
    now = datetime.utcnow()
    if relation is not None and relation.status == "confirmed":
        raise HTTPException(status_code=409, detail="这两笔事实已建立同类关系")
    if relation is None:
        relation = EconomicFactRelation(
            user_id=user.id,
            source_fact_id=source_fact.id,
            target_fact_id=target_fact.id,
            relation_type=data.relation_type,
            allocated_amount=data.allocated_amount,
            status="confirmed",
            detection_method=data.detection_method,
            reasons=data.reasons,
            confirmed_by_user_id=user.id,
            confirmed_at=now,
        )
        db.add(relation)
    else:
        relation.allocated_amount = data.allocated_amount
        relation.status = "confirmed"
        relation.detection_method = data.detection_method
        relation.reasons = data.reasons
        relation.confirmed_by_user_id = user.id
        relation.confirmed_at = now
        relation.reversed_at = None
    source_fact.fact_type = {
        "refunds": "refund",
        "reimburses": "reimbursement",
        "transfer_pair": "transfer",
    }[data.relation_type]
    if data.relation_type == "reimburses":
        target_fact.fact_type = "reimbursable_expense"
    elif data.relation_type == "transfer_pair":
        target_fact.fact_type = "transfer"
    db.flush()
    commit_financial_ledger(db)
    return _relation_response(db, relation)


@router.delete("/relations/{relation_id}", response_model=EconomicRelationResponse)
def reverse_economic_relation(
    relation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user.id)
    relation = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.id == relation_id,
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
        )
        .first()
    )
    if relation is None:
        raise HTTPException(status_code=404, detail="经济事实关系不存在")
    relation.status = "reversed"
    relation.reversed_at = datetime.utcnow()
    db.flush()
    source_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.source_fact_id).one()
    target_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.target_fact_id).one()
    refresh_fact_type_from_relations(db, source_fact)
    refresh_fact_type_from_relations(db, target_fact)
    commit_financial_ledger(db)
    return _relation_response(db, relation)


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
    user_id = user.id
    data_epoch = user.business_data_epoch
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if owner.business_data_epoch != data_epoch:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "cashflow_data_cleared",
                "message": "请求期间账户数据已被清空，请重新记录这笔收支",
            },
        )
    category = get_available_category(
        db,
        user_id=user_id,
        category_id=data.category_id,
        direction=data.direction,
    )
    transaction = FinancialTransaction(
        user_id=user_id,
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
    db.flush()
    sync_transaction_fact(db, transaction=transaction, user_id=user_id)
    commit_financial_ledger(db)
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


@router.put("/transactions/{transaction_id}", response_model=FinancialTransactionResponse)
def update_transaction(
    transaction_id: int,
    data: FinancialTransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user_id)
    transaction = get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
    changes = data.model_dump(exclude_unset=True)
    direction = changes.get("direction", transaction.direction)
    category_id = None if direction == "transfer" else changes.get("category_id", transaction.category_id)
    category = get_available_category(
        db,
        user_id=user_id,
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
    sync_transaction_fact(db, transaction=transaction, user_id=user_id)
    commit_financial_ledger(db)
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


@router.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user_id)
    transaction = get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
    transaction.status = "deleted"
    transaction.deleted_at = datetime.utcnow()
    sync_transaction_fact(db, transaction=transaction, user_id=user_id)
    commit_financial_ledger(db)
    return {"deleted": True, "transaction_id": transaction.id}


@router.post("/transactions/{transaction_id}/restore", response_model=FinancialTransactionResponse)
def restore_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user.id)
    transaction = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.deleted_at.isnot(None),
        )
        .with_for_update()
        .first()
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="已删除的收支记录不存在")
    category = None
    if transaction.category_id is not None:
        category = db.query(FinancialCategory).filter(
            FinancialCategory.id == transaction.category_id,
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).first()
    if transaction.direction in {"income", "expense"} and category is None:
        raise HTTPException(status_code=409, detail="原收支分类已不存在，无法恢复这笔记录")
    transaction.status = "confirmed"
    transaction.deleted_at = None
    transaction.confirmed_at = transaction.confirmed_at or datetime.utcnow()
    sync_transaction_fact(db, transaction=transaction, user_id=user.id)
    commit_financial_ledger(db)
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


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
    relation_effects, relation_category_ids = _summary_relation_effects(
        db,
        user_id=user.id,
        transactions=transactions,
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    for effect in relation_effects.values():
        offset_category_id = effect.get("offset_category_id")
        if offset_category_id is not None:
            effect["offset_category_name"] = category_names.get(int(offset_category_id), "退款/报销冲销")
    return build_month_summary(
        month=normalized_month,
        transactions=transactions,
        category_names=category_names,
        relation_effects=relation_effects,
    )


def _shift_month(month: str, offset: int) -> str:
    year, month_number = (int(value) for value in month.split("-", 1))
    absolute = year * 12 + month_number - 1 + offset
    return f"{absolute // 12:04d}-{absolute % 12 + 1:02d}"


@router.get("/recurring-expenses", response_model=RecurringExpenseResponse)
def get_recurring_expenses(
    end_month: Optional[str] = None,
    months: int = Query(default=6, ge=2, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_end, _, range_end = parse_month(end_month)
    start_month = _shift_month(normalized_end, -(months - 1))
    _, range_start, _ = parse_month(start_month)
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= range_start,
            FinancialTransaction.transaction_date < range_end,
        )
        .all()
    )
    relation_effects, relation_category_ids = _summary_relation_effects(
        db,
        user_id=user.id,
        transactions=transactions,
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    for effect in relation_effects.values():
        offset_category_id = effect.get("offset_category_id")
        if offset_category_id is not None:
            effect["offset_category_name"] = category_names.get(int(offset_category_id), "退款/报销冲销")
    summaries = []
    for offset in range(months):
        current_month = _shift_month(start_month, offset)
        _, month_start, month_end = parse_month(current_month)
        summaries.append(
            build_month_summary(
                month=current_month,
                transactions=[
                    item
                    for item in transactions
                    if month_start <= item.transaction_date < month_end
                ],
                category_names=category_names,
                relation_effects=relation_effects,
            )
        )
    return {
        "start_month": start_month,
        "end_month": normalized_end,
        "months_analyzed": months,
        "items": build_recurring_expense_insights(summaries),
    }


def _payslip_guardians_for_chat(
    db: Session,
    *,
    user_id: int,
    data_start: date,
    data_end: date,
) -> list[dict]:
    """只将当前有效的结构化工资守护结果给 AI，不复制 OCR 或原文件。"""
    start_month = f"{data_start.year:04d}-{data_start.month:02d}"
    last_day = data_end - timedelta(days=1)
    end_month = f"{last_day.year:04d}-{last_day.month:02d}"
    payslips = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(
            CareerCase.user_id == user_id,
            Payslip.record_status == "active",
            Payslip.pay_month.isnot(None),
            Payslip.pay_month >= start_month,
            Payslip.pay_month <= end_month,
        )
        .order_by(Payslip.pay_month.asc(), Payslip.id.asc())
        .limit(12)
        .all()
    )
    contexts: list[dict] = []
    for payslip in payslips:
        offers = (
            db.query(Offer)
            .join(PayslipMaterialLink, PayslipMaterialLink.offer_id == Offer.id)
            .join(CareerCase, CareerCase.id == Offer.case_id)
            .filter(PayslipMaterialLink.payslip_id == payslip.id, CareerCase.user_id == user_id)
            .order_by(PayslipMaterialLink.id.asc())
            .all()
        )
        contracts = (
            db.query(Contract)
            .join(PayslipMaterialLink, PayslipMaterialLink.contract_id == Contract.id)
            .join(CareerCase, CareerCase.id == Contract.case_id)
            .filter(PayslipMaterialLink.payslip_id == payslip.id, CareerCase.user_id == user_id)
            .order_by(PayslipMaterialLink.id.asc())
            .all()
        )
        arrival_rows = (
            db.query(PayslipArrivalLink, FinancialTransaction)
            .join(FinancialTransaction, FinancialTransaction.id == PayslipArrivalLink.transaction_id)
            .filter(
                PayslipArrivalLink.payslip_id == payslip.id,
                PayslipArrivalLink.status == "confirmed",
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.status == "confirmed",
                FinancialTransaction.deleted_at.is_(None),
            )
            .order_by(PayslipArrivalLink.confirmed_at.asc(), PayslipArrivalLink.id.asc())
            .all()
        )
        net_salary = Decimal(payslip.net_salary or 0)
        confirmed_amount = sum((Decimal(link.allocated_amount) for link, _ in arrival_rows), Decimal("0.00"))
        remaining_amount = max(Decimal("0.00"), net_salary - confirmed_amount)
        arrival_summary = SimpleNamespace(
            match_status="matched" if remaining_amount <= Decimal("1.00") and confirmed_amount > 0 else "partial" if confirmed_amount > 0 else "unmatched",
            net_salary=net_salary,
            confirmed_amount=confirmed_amount,
            remaining_amount=remaining_amount,
            links=[SimpleNamespace(transaction_date=transaction.transaction_date) for _, transaction in arrival_rows],
        )
        previous = None
        employer = (payslip.employer_name or "").strip().lower()
        if payslip.pay_month and employer:
            previous = (
                db.query(Payslip)
                .join(CareerCase, CareerCase.id == Payslip.case_id)
                .filter(
                    Payslip.id != payslip.id,
                    CareerCase.user_id == user_id,
                    Payslip.record_status != "deleted",
                    Payslip.pay_month.isnot(None),
                    Payslip.pay_month < payslip.pay_month,
                    func.lower(func.trim(Payslip.employer_name)) == employer,
                )
                .order_by(Payslip.pay_month.desc(), Payslip.created_at.desc(), Payslip.id.desc())
                .first()
            )
        material_comparisons = build_material_comparisons(payslip, offers, contracts)
        guardian = build_payslip_guardian_summary(
            payslip=payslip,
            material_comparisons=material_comparisons,
            arrival_summary=arrival_summary,
            month_comparison=build_month_comparison(payslip, previous),
            offers=offers,
        )
        component_fields = (
            "base_salary", "performance", "bonus", "overtime_pay", "allowance",
            "social_insurance", "housing_fund", "individual_tax",
            "attendance_deductions", "meal_deductions", "other_deductions",
        )
        contexts.append(
            {
                "payslip_id": payslip.id,
                "pay_month": payslip.pay_month,
                "employer_name": redact_cashflow_text(payslip.employer_name or "", max_length=100) or None,
                "gross_salary": str(payslip.gross_salary) if payslip.gross_salary is not None else None,
                "net_salary": str(payslip.net_salary) if payslip.net_salary is not None else None,
                "components": {
                    field: str(getattr(payslip, field))
                    for field in component_fields
                    if getattr(payslip, field) is not None
                },
                "arrival_match_status": arrival_summary.match_status,
                "confirmed_arrival_amount": str(confirmed_amount),
                "attention_count": guardian["attention_count"],
                "unverified_count": guardian["unverified_count"],
                "checks": [
                    {
                        "key": item["key"],
                        "status": item["status"],
                        "title": redact_cashflow_text(item["title"], max_length=220),
                        "explanation": redact_cashflow_text(item["explanation"], max_length=500),
                        "evidence": [redact_cashflow_text(value, max_length=180) for value in item["evidence"][:6]],
                    }
                    for item in guardian["checks"]
                ],
                "hr_questions": [redact_cashflow_text(item, max_length=300) for item in guardian["hr_questions"][:8]],
            }
        )
    return contexts


@router.post("/ask", response_model=CashflowAskResponse)
def ask_confirmed_cashflow(
    data: CashflowAskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, selected_start, selected_end = parse_month(data.month)
    data_start = _shift_month_start(selected_start, -5)
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= data_start,
            FinancialTransaction.transaction_date < selected_end,
        )
        .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        .all()
    )
    relation_effects, relation_category_ids = _summary_relation_effects(
        db,
        user_id=user.id,
        transactions=transactions,
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    for effect in relation_effects.values():
        offset_category_id = effect.get("offset_category_id")
        if offset_category_id is not None:
            effect["offset_category_name"] = category_names.get(int(offset_category_id), "退款/报销冲销")

    monthly_summaries = []
    for offset in range(-5, 1):
        month_start = _shift_month_start(selected_start, offset)
        month_end = _shift_month_start(month_start, 1)
        month_transactions = [
            item
            for item in transactions
            if month_start <= item.transaction_date < month_end
        ]
        monthly_summaries.append(
            build_month_summary(
                month=f"{month_start.year:04d}-{month_start.month:02d}",
                transactions=month_transactions,
                category_names=category_names,
                relation_effects=relation_effects,
            )
        )

    facts = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.primary_transaction_id.in_([item.id for item in transactions]),
        EconomicFact.status == "confirmed",
    ).all() if transactions else []
    fact_types = {
        fact.primary_transaction_id: fact.fact_type
        for fact in facts
        if fact.primary_transaction_id is not None
    }
    fact_by_id = {fact.id: fact for fact in facts}
    fact_ids = set(fact_by_id)
    relation_rows = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id.in_(fact_ids),
            EconomicFactRelation.target_fact_id.in_(fact_ids),
        ),
    ).order_by(EconomicFactRelation.confirmed_at.desc()).all() if fact_ids else []
    related_fact_ids = {
        fact_id
        for relation in relation_rows
        for fact_id in (relation.source_fact_id, relation.target_fact_id)
        if fact_id not in fact_by_id
    }
    if related_fact_ids:
        for fact in db.query(EconomicFact).filter(
            EconomicFact.user_id == user.id,
            EconomicFact.id.in_(related_fact_ids),
        ).all():
            fact_by_id[fact.id] = fact
    relation_context = []
    for relation in relation_rows:
        source_fact = fact_by_id.get(relation.source_fact_id)
        target_fact = fact_by_id.get(relation.target_fact_id)
        if source_fact is None or target_fact is None:
            continue
        relation_context.append(
            {
                "relation_type": relation.relation_type,
                "allocated_amount": str(relation.allocated_amount),
                "source_transaction_id": source_fact.primary_transaction_id,
                "target_transaction_id": target_fact.primary_transaction_id,
            }
        )

    payslip_guardians = _payslip_guardians_for_chat(
        db,
        user_id=user.id,
        data_start=data_start,
        data_end=selected_end,
    )
    context, reference_by_id = build_cashflow_chat_context(
        data_start=data_start,
        data_end=selected_end - timedelta(days=1),
        transactions=transactions,
        category_names=category_names,
        fact_types=fact_types,
        monthly_summaries=monthly_summaries,
        relations=relation_context,
        payslip_guardians=payslip_guardians,
    )
    user_id = user.id
    expected_data_epoch = user.business_data_epoch
    db.rollback()
    answer = answer_cashflow_question(
        question=data.question,
        history=[item.model_dump() for item in data.history],
        context=context,
        reference_by_id=reference_by_id,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
    )
    return CashflowAskResponse(
        **answer,
        data_start=data_start,
        data_end=selected_end - timedelta(days=1),
        transaction_count=len(transactions),
        generated_at=datetime.utcnow(),
    )


@router.get("/export")
def export_confirmed_cashflow(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
        )
        .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
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
    facts = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.status == "confirmed",
    ).order_by(EconomicFact.occurred_date.asc(), EconomicFact.id.asc()).all()
    relations = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
    ).order_by(EconomicFactRelation.confirmed_at.asc(), EconomicFactRelation.id.asc()).all()
    payslips = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(CareerCase.user_id == user.id, Payslip.record_status != "deleted")
        .order_by(Payslip.pay_month.asc(), Payslip.id.asc())
        .all()
    )
    payslip_ids = [item.id for item in payslips]
    material_links = db.query(PayslipMaterialLink).filter(
        PayslipMaterialLink.payslip_id.in_(payslip_ids)
    ).all() if payslip_ids else []
    arrival_links = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id.in_(payslip_ids),
        PayslipArrivalLink.status == "confirmed",
    ).all() if payslip_ids else []
    payload = build_cashflow_export_bundle(
        generated_at=datetime.utcnow(),
        business_data_epoch=user.business_data_epoch,
        transactions=transactions,
        category_names=category_names,
        facts=facts,
        relations=relations,
        payslips=payslips,
        material_links=material_links,
        arrival_links=arrival_links,
    )
    filename = f"cashflow-guardian-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
