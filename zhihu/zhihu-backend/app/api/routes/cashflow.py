from __future__ import annotations

import json
from html import escape
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.cashflow import (
    CashflowConversation,
    CashflowConversationTurn,
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRevision,
    EconomicFactRelation,
    EconomicFactRelationRevision,
    FinancialBudget,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialMonthClose,
    FinancialRecurringDecision,
    FinancialTransaction,
    FinancialTransactionRevision,
)
from app.models.cashflow_import import FinancialTransactionCandidate
from app.models.user import User
from app.models.career_case import CareerCase
from app.models.contract import Contract
from app.models.offer import Offer
from app.models.payslip import Payslip, PayslipArrivalLink, PayslipMaterialLink
from app.schemas.cashflow import (
    CashflowMonthlyReportResponse,
    CashflowSummaryResponse,
    CashflowAskRequest,
    CashflowAskResponse,
    CashflowConversationDetailResponse,
    CashflowConversationSummaryResponse,
    CashflowConversationTurnResponse,
    DeletedFinancialTransactionPage,
    EconomicFactMergeBatchConfirmRequest,
    EconomicFactMergeConfirmRequest,
    EconomicFactMembershipResponse,
    EconomicFactResponse,
    EconomicFactRevisionResponse,
    EconomicFactSplitConfirmRequest,
    EconomicFactSplitResponse,
    EconomicRelationBatchReverseRequest,
    EconomicRelationConfirmRequest,
    EconomicRelationResponse,
    EconomicRelationRevisionResponse,
    EconomicRelationSuggestionResponse,
    FinancialCategoryCreate,
    FinancialCategoryResponse,
    FinancialBudgetResponse,
    FinancialBudgetUpsert,
    FinancialLedgerRevisionEventResponse,
    FinancialMonthCloseCreate,
    FinancialMonthCloseResponse,
    FinancialTransactionCreate,
    FinancialTransactionPage,
    FinancialTransactionResponse,
    FinancialTransactionRevisionResponse,
    FinancialTransactionUpdate,
    RecurringExpenseDecisionResponse,
    RecurringExpenseDecisionUpsert,
    RecurringExpenseResponse,
)
from app.services.cashflow_service import (
    build_month_summary,
    build_recurring_expense_insights,
    commit_financial_ledger,
    confirmed_at_for,
    economic_fact_snapshot,
    economic_relation_snapshot,
    financial_transaction_snapshot,
    get_available_category,
    get_owned_transaction,
    lock_financial_ledger_owner,
    parse_month,
    record_economic_relation_revision,
    record_economic_fact_revision,
    record_financial_ledger_event,
    record_transaction_ledger_revision,
    recurring_merchant_fingerprint,
    expand_transactions_with_split_components,
)
from app.services.cashflow_chat_service import (
    answer_cashflow_question,
    build_cashflow_chat_context,
)
from app.services.cashflow_export_service import (
    build_cashflow_export_bundle,
    build_cashflow_export_workbook,
)
from app.services.cashflow_privacy import redact_cashflow_text
from app.services.knowledge_service import recommend_cashflow_knowledge
from app.services.economic_fact_service import (
    build_fact_merge_suggestions,
    build_relation_suggestions,
    enrich_fact_merge_suggestions_with_ai,
    enrich_relation_suggestions_with_ai,
    get_fact_source_transaction,
    get_fact_members,
    get_transaction_fact,
    get_transaction_facts,
    get_transactions_facts,
    refresh_fact_type_from_relations,
    sync_transaction_fact,
    transaction_fact_title,
    transaction_fact_type,
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
    membership: dict | None = None,
) -> FinancialTransactionResponse:
    return FinancialTransactionResponse.model_validate(transaction).model_copy(update={
        "category_name": category_name,
        "economic_fact_id": membership.get("fact_id") if membership else None,
        "economic_fact_role": membership.get("role") if membership else None,
        "counts_as_cashflow": membership.get("counts_as_cashflow", True) if membership else True,
        "allocated_to_other_facts": membership.get("allocated_to_other_facts", Decimal("0.00")) if membership else Decimal("0.00"),
        "effective_cashflow_amount": membership.get("effective_cashflow_amount", transaction.amount) if membership else transaction.amount,
        "split_component_count": membership.get("split_component_count", 0) if membership else 0,
    })


def _fact_response(fact: EconomicFact) -> EconomicFactResponse:
    return EconomicFactResponse(
        id=fact.id,
        primary_transaction_id=fact.primary_transaction_id,
        fact_type=fact.fact_type,
        title=fact.title,
        occurred_date=fact.occurred_date,
        amount=fact.amount,
        currency=fact.currency,
        category_id=fact.category_id,
        nature=fact.nature,
        description=fact.description,
        status=fact.status,
    )


def _fact_relation_transaction(
    db: Session,
    *,
    fact: EconomicFact,
    user_id: int,
) -> FinancialTransaction:
    transaction = get_fact_source_transaction(db, fact=fact, user_id=user_id)
    if transaction is None:
        raise HTTPException(status_code=409, detail="经济事实缺少有效的来源流水")
    return transaction


def _fact_relation_observation(
    fact: EconomicFact,
    transaction: FinancialTransaction,
) -> FinancialTransaction | SimpleNamespace:
    """Present a split fact to deterministic matching as its own observation."""
    if fact.primary_transaction_id == transaction.id:
        return transaction
    return SimpleNamespace(
        id=transaction.id,
        direction=transaction.direction,
        amount=Decimal(fact.amount),
        currency=fact.currency,
        transaction_date=fact.occurred_date,
        category_id=fact.category_id,
        merchant=fact.title,
        description=fact.description or transaction.description,
        nature=fact.nature,
        source_type=transaction.source_type,
        status=transaction.status,
        deleted_at=transaction.deleted_at,
    )


def _active_relation_facts_for_transaction(
    db: Session,
    *,
    transaction: FinancialTransaction,
    user_id: int,
) -> list[tuple[EconomicFact, FinancialTransaction | SimpleNamespace]]:
    facts = get_transaction_facts(
        db,
        transaction_id=transaction.id,
        user_id=user_id,
    )
    return [
        (fact, _fact_relation_observation(fact, transaction))
        for fact in facts
    ]


def _active_relation_facts_for_transactions(
    db: Session,
    *,
    transactions: list[FinancialTransaction],
    user_id: int,
) -> dict[int, list[tuple[EconomicFact, FinancialTransaction | SimpleNamespace]]]:
    facts_by_transaction = get_transactions_facts(
        db,
        transaction_ids=[transaction.id for transaction in transactions],
        user_id=user_id,
    )
    return {
        transaction.id: [
            (fact, _fact_relation_observation(fact, transaction))
            for fact in facts_by_transaction.get(transaction.id, [])
        ]
        for transaction in transactions
    }


def _fact_membership_response(
    db: Session,
    *,
    fact: EconomicFact,
    user_id: int,
) -> EconomicFactMembershipResponse:
    return EconomicFactMembershipResponse(
        fact=_fact_response(fact),
        members=get_fact_members(db, fact=fact, user_id=user_id),
    )


def _fact_payslip_evidence(
    db: Session,
    *,
    fact: EconomicFact,
    user_id: int,
) -> list[dict]:
    transaction_ids = [
        row.transaction_id
        for row in db.query(EconomicFactAllocation.transaction_id).filter(
            EconomicFactAllocation.fact_id == fact.id,
            EconomicFactAllocation.status == "confirmed",
        ).all()
    ]
    if not transaction_ids:
        return []
    rows = (
        db.query(PayslipArrivalLink, Payslip)
        .join(Payslip, Payslip.id == PayslipArrivalLink.payslip_id)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(
            CareerCase.user_id == user_id,
            Payslip.record_status != "deleted",
            PayslipArrivalLink.status == "confirmed",
            or_(
                PayslipArrivalLink.economic_fact_id == fact.id,
                (
                    PayslipArrivalLink.economic_fact_id.is_(None)
                    & PayslipArrivalLink.transaction_id.in_(transaction_ids)
                ),
            ),
        )
        .order_by(Payslip.pay_month.asc(), Payslip.id.asc(), PayslipArrivalLink.id.asc())
        .all()
    )
    grouped: dict[int, dict] = {}
    for link, payslip in rows:
        item = grouped.setdefault(
            payslip.id,
            {
                "payslip_id": payslip.id,
                "pay_month": payslip.pay_month,
                "employer_name": payslip.employer_name,
                "gross_salary": payslip.gross_salary,
                "net_salary": payslip.net_salary,
                "allocated_amount": Decimal("0.00"),
                "transaction_ids": [],
                "role": "entitlement",
                "counts_as_cashflow": False,
            },
        )
        item["allocated_amount"] += Decimal(link.allocated_amount)
        item["transaction_ids"].append(link.transaction_id)
    return list(grouped.values())


def _transaction_memberships(
    db: Session,
    *,
    user_id: int,
    transaction_ids: list[int],
) -> dict[int, dict]:
    if not transaction_ids:
        return {}
    rows = (
        db.query(EconomicFactAllocation, EconomicFact, FinancialTransaction)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .join(FinancialTransaction, FinancialTransaction.id == EconomicFactAllocation.transaction_id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id.in_(transaction_ids),
            EconomicFactAllocation.status == "confirmed",
        )
        .all()
    )
    grouped: dict[int, dict] = {}
    for allocation, fact, transaction in rows:
        item = grouped.setdefault(
            transaction.id,
            {
                "primary_fact_id": None,
                "corroborating_fact_ids": [],
                "split_fact_ids": [],
                "allocated_to_other_facts": Decimal("0.00"),
                "transaction_amount": Decimal(transaction.amount),
            },
        )
        if allocation.role == "corroborating":
            item["corroborating_fact_ids"].append(fact.id)
            item["allocated_to_other_facts"] += Decimal(allocation.allocated_amount)
        elif allocation.role == "split_component":
            item["split_fact_ids"].append(fact.id)
        elif fact.primary_transaction_id == transaction.id:
            item["primary_fact_id"] = fact.id
    memberships: dict[int, dict] = {}
    for transaction_id, item in grouped.items():
        allocated = min(item["transaction_amount"], item["allocated_to_other_facts"])
        effective = max(Decimal("0.00"), item["transaction_amount"] - allocated)
        if item["split_fact_ids"]:
            role = "decomposed"
            fact_id = item["split_fact_ids"][0]
            effective = item["transaction_amount"]
        elif allocated <= Decimal("0.00"):
            role = "primary"
            fact_id = item["primary_fact_id"]
        elif effective <= Decimal("0.00"):
            role = "corroborating"
            fact_id = item["corroborating_fact_ids"][0] if item["corroborating_fact_ids"] else None
        else:
            role = "split"
            fact_id = item["primary_fact_id"]
        memberships[transaction_id] = {
            "fact_id": fact_id,
            "role": role,
            "counts_as_cashflow": effective > Decimal("0.00"),
            "allocated_to_other_facts": allocated,
            "effective_cashflow_amount": effective,
            "split_component_count": len(item["split_fact_ids"]),
        }
    return memberships


def _split_components_for_transactions(
    db: Session,
    *,
    user_id: int,
    transaction_ids: list[int],
) -> tuple[dict[int, list[dict]], set[int]]:
    if not transaction_ids:
        return {}, set()
    rows = (
        db.query(EconomicFactAllocation, EconomicFact, FinancialCategory)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .join(FinancialCategory, FinancialCategory.id == EconomicFact.category_id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id.in_(transaction_ids),
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "split_component",
        )
        .order_by(EconomicFactAllocation.transaction_id.asc(), EconomicFact.id.asc())
        .all()
    )
    grouped: dict[int, list[dict]] = {}
    category_ids: set[int] = set()
    for allocation, fact, category in rows:
        category_ids.add(category.id)
        grouped.setdefault(allocation.transaction_id, []).append({
            "fact_id": fact.id,
            "source_transaction_id": allocation.transaction_id,
            "amount": Decimal(allocation.allocated_amount),
            "category_id": category.id,
            "category_name": category.name,
            "title": fact.title,
            "description": fact.description,
            "nature": fact.nature,
            "status": "confirmed",
        })
    return grouped, category_ids


def _split_response(
    db: Session,
    *,
    transaction: FinancialTransaction,
    user_id: int,
    ledger_revision: int,
) -> EconomicFactSplitResponse:
    grouped, _ = _split_components_for_transactions(
        db,
        user_id=user_id,
        transaction_ids=[transaction.id],
    )
    components = grouped.get(transaction.id, [])
    allocated = sum((Decimal(item["amount"]) for item in components), Decimal("0.00"))
    return EconomicFactSplitResponse(
        transaction_id=transaction.id,
        original_amount=transaction.amount,
        allocated_amount=allocated,
        remaining_amount=max(Decimal("0.00"), Decimal(transaction.amount) - allocated),
        components=components,
        ledger_revision=ledger_revision,
    )


def _relation_response(db: Session, relation: EconomicFactRelation) -> EconomicRelationResponse:
    source_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.source_fact_id).one()
    target_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.target_fact_id).one()
    source_transaction = _fact_relation_transaction(
        db,
        fact=source_fact,
        user_id=relation.user_id,
    )
    target_transaction = _fact_relation_transaction(
        db,
        fact=target_fact,
        user_id=relation.user_id,
    )
    return EconomicRelationResponse(
        id=relation.id,
        source_fact_id=source_fact.id,
        target_fact_id=target_fact.id,
        source_transaction_id=source_transaction.id,
        target_transaction_id=target_transaction.id,
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


def _guard_transaction_change_with_relations(
    db: Session,
    *,
    transaction: FinancialTransaction,
    proposed_direction: str,
    proposed_status: str,
    proposed_amount: Decimal,
) -> None:
    active_split = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.transaction_id == transaction.id,
        EconomicFactAllocation.status == "confirmed",
        EconomicFactAllocation.role == "split_component",
    ).first()
    if active_split is not None:
        raise HTTPException(status_code=409, detail="这条来源流水已经拆成多个经济事实，请先在“核对关系”中撤销拆分再编辑")
    fact = get_transaction_fact(
        db,
        transaction_id=transaction.id,
        user_id=transaction.user_id,
    )
    if fact is None:
        return
    if fact.primary_transaction_id != transaction.id:
        raise HTTPException(status_code=409, detail="这条记录是同一经济事实的辅助证据，请先在“核对关系”中撤销合并")
    outgoing_evidence = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.transaction_id == transaction.id,
        EconomicFactAllocation.status == "confirmed",
        EconomicFactAllocation.role == "corroborating",
    ).first()
    if outgoing_evidence is not None and (
        proposed_status != "confirmed"
        or proposed_direction != transaction.direction
        or proposed_amount != Decimal(transaction.amount)
    ):
        raise HTTPException(status_code=409, detail="这条记录已有部分金额作为其他事实的证据，请先撤销对应分配")
    corroborating_allocations = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == fact.id,
        EconomicFactAllocation.status == "confirmed",
        EconomicFactAllocation.role == "corroborating",
    ).all()
    if corroborating_allocations and (
        proposed_status != "confirmed"
        or proposed_direction != transaction.direction
        or proposed_amount != Decimal(transaction.amount)
    ):
        raise HTTPException(status_code=409, detail="这笔事实还有其他来源证据，请先撤销合并再改变金额、方向或状态")
    payslip_arrivals = db.query(PayslipArrivalLink).filter(
        or_(
            PayslipArrivalLink.economic_fact_id == fact.id,
            (
                PayslipArrivalLink.economic_fact_id.is_(None)
                & (PayslipArrivalLink.transaction_id == transaction.id)
            ),
        ),
        PayslipArrivalLink.status == "confirmed",
    ).all()
    if payslip_arrivals:
        if proposed_status != "confirmed" or proposed_direction != "income":
            raise HTTPException(status_code=409, detail="这笔收入事实已作为工资到账证据，请先撤销工资到账关系")
        arrival_allocated = sum(
            (Decimal(item.allocated_amount) for item in payslip_arrivals),
            Decimal("0.00"),
        )
        if proposed_amount < arrival_allocated:
            raise HTTPException(
                status_code=409,
                detail=f"这笔收入已有 {arrival_allocated:.2f} 元作为工资到账证据，新金额不能低于已分配金额",
            )
    relations = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == transaction.user_id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id == fact.id,
            EconomicFactRelation.target_fact_id == fact.id,
        ),
    ).all()
    if not relations:
        return
    if proposed_status != "confirmed":
        raise HTTPException(status_code=409, detail="这笔流水已有确认的事实关系，请先撤销关系再改变状态或删除")
    if proposed_direction != transaction.direction:
        raise HTTPException(status_code=409, detail="这笔流水已有确认的事实关系，请先撤销关系再修改收支方向")
    allocated = sum((Decimal(item.allocated_amount) for item in relations), Decimal("0"))
    if proposed_amount < allocated:
        raise HTTPException(
            status_code=409,
            detail=f"这笔流水已关联 {allocated:.2f} 元，新金额不能低于已分配金额",
        )


def _reverse_economic_relation_locked(
    db: Session,
    *,
    owner: User,
    relation: EconomicFactRelation,
    reason: str,
) -> None:
    before_snapshot = economic_relation_snapshot(relation)
    source_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.source_fact_id).one()
    target_fact = db.query(EconomicFact).filter(EconomicFact.id == relation.target_fact_id).one()
    source_fact_before = economic_fact_snapshot(db, source_fact)
    target_fact_before = economic_fact_snapshot(db, target_fact)
    relation.status = "reversed"
    relation.reversed_at = datetime.utcnow()
    db.flush()
    refresh_fact_type_from_relations(db, source_fact)
    refresh_fact_type_from_relations(db, target_fact)
    relation_revision = record_economic_relation_revision(
        db,
        owner=owner,
        relation=relation,
        operation="reverse",
        before_snapshot=before_snapshot,
        reason=reason,
    )
    for changed_fact, fact_before in (
        (source_fact, source_fact_before),
        (target_fact, target_fact_before),
    ):
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=changed_fact,
            ledger_revision=relation_revision.ledger_revision,
            operation="relation_reverse",
            before_snapshot=fact_before,
            reason=reason,
        )


def _summary_relation_effects(
    db: Session,
    *,
    user_id: int,
    transactions: list[FinancialTransaction],
) -> tuple[dict[object, dict[str, Decimal | int | str | None]], set[int]]:
    transaction_by_id = {
        item.id: item
        for item in transactions
        if getattr(item, "id", None) is not None
    }
    if not transaction_by_id:
        return {}, set()
    effects: dict[object, dict[str, Decimal | int | str | None]] = {}
    category_ids: set[int] = set()

    def add(effect_key: object, key: str, amount: Decimal):
        if isinstance(effect_key, tuple):
            if effect_key[0] != "fact" or effect_key[1] not in month_component_fact_ids:
                return
        elif effect_key not in transaction_by_id:
            return
        effect = effects.setdefault(effect_key, {})
        effect[key] = Decimal(effect.get(key) or 0) + amount

    evidence_allocations = (
        db.query(EconomicFactAllocation, EconomicFact)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id.in_(transaction_by_id),
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "corroborating",
        )
        .all()
    )
    corroborating_totals: dict[int, Decimal] = {}
    for allocation, fact in evidence_allocations:
        transaction = transaction_by_id.get(allocation.transaction_id)
        if transaction is None or fact.primary_transaction_id == transaction.id:
            continue
        amount = min(Decimal(transaction.amount), Decimal(allocation.allocated_amount))
        corroborating_totals[transaction.id] = corroborating_totals.get(
            transaction.id,
            Decimal("0.00"),
        ) + amount
        if transaction.direction == "income":
            add(transaction.id, "income_remove", amount)
        elif transaction.direction == "expense":
            add(transaction.id, "expense_remove", amount)
        elif transaction.direction == "transfer":
            add(transaction.id, "transfer_remove", amount)
    for transaction_id, allocated in corroborating_totals.items():
        if allocated >= Decimal(transaction_by_id[transaction_id].amount) - Decimal("0.01"):
            effects.setdefault(transaction_id, {})["count_remove"] = 1
    month_fact_rows = (
        db.query(EconomicFact, EconomicFactAllocation)
        .join(EconomicFactAllocation, EconomicFactAllocation.fact_id == EconomicFact.id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.transaction_id.in_(transaction_by_id),
        )
        .all()
    )
    month_fact_ids = {fact.id for fact, _ in month_fact_rows}
    month_component_fact_ids = {
        fact.id
        for fact, allocation in month_fact_rows
        if allocation.role == "split_component"
    }
    if not month_fact_ids:
        return effects, category_ids
    relations = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user_id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id.in_(month_fact_ids),
            EconomicFactRelation.target_fact_id.in_(month_fact_ids),
        ),
    ).all()
    if not relations:
        return effects, category_ids
    related_fact_ids = {
        fact_id
        for relation in relations
        for fact_id in (relation.source_fact_id, relation.target_fact_id)
    }
    facts = {
        fact.id: fact
        for fact in db.query(EconomicFact).filter(EconomicFact.id.in_(related_fact_ids)).all()
    }
    component_allocations = (
        db.query(EconomicFactAllocation)
        .filter(
            EconomicFactAllocation.fact_id.in_(related_fact_ids),
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "split_component",
        )
        .order_by(EconomicFactAllocation.id.asc())
        .all()
    )
    component_transaction_ids = {
        allocation.fact_id: allocation.transaction_id
        for allocation in component_allocations
    }
    fact_transaction_ids = {
        fact.id: fact.primary_transaction_id or component_transaction_ids.get(fact.id)
        for fact in facts.values()
    }
    related_transaction_ids = {
        transaction_id
        for transaction_id in fact_transaction_ids.values()
        if transaction_id is not None
    }
    related_transactions = {
        item.id: item
        for item in db.query(FinancialTransaction).filter(
            FinancialTransaction.id.in_(related_transaction_ids),
            FinancialTransaction.user_id == user_id,
        ).all()
    }
    for relation in relations:
        source_fact = facts.get(relation.source_fact_id)
        target_fact = facts.get(relation.target_fact_id)
        if source_fact is None or target_fact is None:
            continue
        source_id = fact_transaction_ids.get(source_fact.id)
        target_id = fact_transaction_ids.get(target_fact.id)
        if source_id is None or target_id is None:
            continue
        source_key: object = (
            ("fact", source_fact.id)
            if source_fact.id in component_transaction_ids
            else source_id
        )
        target_key: object = (
            ("fact", target_fact.id)
            if target_fact.id in component_transaction_ids
            else target_id
        )
        amount = Decimal(relation.allocated_amount)
        source_transaction = related_transactions.get(source_id)
        target_transaction = related_transactions.get(target_id)
        if source_transaction is None or target_transaction is None:
            continue
        if relation.relation_type in {"refunds", "reimburses"}:
            add(source_key, "income_remove", amount)
            add(source_key, "expense_offset", amount)
            source_is_in_month = (
                source_fact.id in month_component_fact_ids
                if isinstance(source_key, tuple)
                else source_id in transaction_by_id
            )
            if source_is_in_month:
                effect = effects.setdefault(source_key, {})
                effect["offset_category_id"] = target_fact.category_id
                effect["offset_nature"] = target_fact.nature or "other"
                effect["offset_merchant"] = (
                    target_fact.title
                    or target_fact.description
                    or target_transaction.merchant
                    or "未标记商户"
                )
                if target_fact.category_id is not None:
                    category_ids.add(target_fact.category_id)
        elif relation.relation_type == "transfer_pair":
            for effect_key, relation_transaction in (
                (source_key, source_transaction),
                (target_key, target_transaction),
            ):
                if relation_transaction.direction == "income":
                    add(effect_key, "income_remove", amount)
                elif relation_transaction.direction == "expense":
                    add(effect_key, "expense_remove", amount)
                elif relation_transaction.direction == "transfer":
                    add(effect_key, "transfer_remove", amount)
            source_is_in_month = (
                source_fact.id in month_component_fact_ids
                if isinstance(source_key, tuple)
                else source_id in transaction_by_id
            )
            anchor_key = source_key if source_is_in_month else target_key
            add(anchor_key, "transfer_add", amount)
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


@router.get("/ledger-revisions", response_model=list[FinancialLedgerRevisionEventResponse])
def list_financial_ledger_revisions(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(FinancialLedgerRevisionEvent)
        .filter(FinancialLedgerRevisionEvent.user_id == user.id)
        .order_by(FinancialLedgerRevisionEvent.revision_number.desc())
        .limit(limit)
        .all()
    )


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


def _filtered_transaction_query(
    db: Session,
    *,
    user: User,
    transaction_id: Optional[int] = None,
    month: Optional[str] = None,
    direction: Optional[str] = None,
    transaction_status: Optional[str] = "confirmed",
    category_id: Optional[int] = None,
    nature: Optional[str] = None,
    keyword: Optional[str] = None,
    merchant_name: Optional[str] = None,
    source_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=400, detail="导出或下钻的开始日期不能晚于结束日期")
    query = db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == user.id,
        FinancialTransaction.deleted_at.is_(None),
    )
    if transaction_id is not None:
        query = query.filter(FinancialTransaction.id == transaction_id)
    if month is not None:
        _, month_start, month_end = parse_month(month)
        query = query.filter(
            FinancialTransaction.transaction_date >= month_start,
            FinancialTransaction.transaction_date < month_end,
        )
    if start_date is not None:
        query = query.filter(FinancialTransaction.transaction_date >= start_date)
    if end_date is not None:
        query = query.filter(FinancialTransaction.transaction_date <= end_date)
    if direction is not None:
        query = query.filter(FinancialTransaction.direction == direction)
    if transaction_status is not None:
        query = query.filter(FinancialTransaction.status == transaction_status)
    if source_type:
        query = query.filter(FinancialTransaction.source_type == source_type.strip())

    confirmed_split = exists().where(and_(
        EconomicFactAllocation.transaction_id == FinancialTransaction.id,
        EconomicFactAllocation.role == "split_component",
        EconomicFactAllocation.status == "confirmed",
        EconomicFact.id == EconomicFactAllocation.fact_id,
        EconomicFact.user_id == user.id,
        EconomicFact.status == "confirmed",
    ))
    if category_id is not None:
        split_category = exists().where(and_(
            EconomicFactAllocation.transaction_id == FinancialTransaction.id,
            EconomicFactAllocation.role == "split_component",
            EconomicFactAllocation.status == "confirmed",
            EconomicFact.id == EconomicFactAllocation.fact_id,
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            EconomicFact.category_id == category_id,
        ))
        query = query.filter(or_(
            and_(~confirmed_split, FinancialTransaction.category_id == category_id),
            split_category,
        ))
    if nature is not None:
        split_nature = exists().where(and_(
            EconomicFactAllocation.transaction_id == FinancialTransaction.id,
            EconomicFactAllocation.role == "split_component",
            EconomicFactAllocation.status == "confirmed",
            EconomicFact.id == EconomicFactAllocation.fact_id,
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            EconomicFact.nature == nature,
        ))
        query = query.filter(
            FinancialTransaction.direction == "expense",
            or_(
                and_(~confirmed_split, FinancialTransaction.nature == nature),
                split_nature,
            ),
        )
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        split_keyword = exists().where(and_(
            EconomicFactAllocation.transaction_id == FinancialTransaction.id,
            EconomicFactAllocation.role == "split_component",
            EconomicFactAllocation.status == "confirmed",
            EconomicFact.id == EconomicFactAllocation.fact_id,
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            or_(EconomicFact.title.ilike(pattern), EconomicFact.description.ilike(pattern)),
        ))
        query = query.filter(or_(
            FinancialTransaction.merchant.ilike(pattern),
            FinancialTransaction.description.ilike(pattern),
            split_keyword,
        ))
    if merchant_name and merchant_name.strip():
        normalized_merchant = merchant_name.strip()
        fallback_category_ids = [
            item.id
            for item in db.query(FinancialCategory.id).filter(
                FinancialCategory.name == normalized_merchant,
                or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
            ).all()
        ]
        direct_merchant_match = or_(
            FinancialTransaction.merchant == normalized_merchant,
            and_(
                or_(FinancialTransaction.merchant.is_(None), FinancialTransaction.merchant == ""),
                FinancialTransaction.description == normalized_merchant,
            ),
        )
        if fallback_category_ids:
            direct_merchant_match = or_(
                direct_merchant_match,
                and_(
                    or_(FinancialTransaction.merchant.is_(None), FinancialTransaction.merchant == ""),
                    or_(FinancialTransaction.description.is_(None), FinancialTransaction.description == ""),
                    FinancialTransaction.category_id.in_(fallback_category_ids),
                ),
            )
        split_merchant = exists().where(and_(
            EconomicFactAllocation.transaction_id == FinancialTransaction.id,
            EconomicFactAllocation.role == "split_component",
            EconomicFactAllocation.status == "confirmed",
            EconomicFact.id == EconomicFactAllocation.fact_id,
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            EconomicFact.title == normalized_merchant,
        ))
        query = query.filter(or_(and_(~confirmed_split, direct_merchant_match), split_merchant))
    return query


@router.get("/transactions/page", response_model=FinancialTransactionPage)
def list_transaction_page(
    transaction_id: Annotated[Optional[int], Query(gt=0)] = None,
    month: Optional[str] = None,
    direction: Optional[Literal["income", "expense", "transfer"]] = None,
    transaction_status: Optional[Literal["pending", "confirmed", "excluded"]] = Query(
        default="confirmed",
        alias="status",
    ),
    category_id: Optional[int] = None,
    nature: Optional[Literal["fixed", "flexible", "one_off", "reimbursable", "other"]] = None,
    keyword: Annotated[Optional[str], Query(max_length=100)] = None,
    merchant_name: Annotated[Optional[str], Query(max_length=200)] = None,
    source_type: Annotated[Optional[str], Query(max_length=50)] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort: Literal["date_desc", "amount_desc", "amount_asc"] = "date_desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _filtered_transaction_query(
        db,
        user=user,
        transaction_id=transaction_id,
        month=month,
        direction=direction,
        transaction_status=transaction_status,
        category_id=category_id,
        nature=nature,
        keyword=keyword,
        merchant_name=merchant_name,
        source_type=source_type,
        start_date=start_date,
        end_date=end_date,
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
    memberships = _transaction_memberships(
        db,
        user_id=user.id,
        transaction_ids=[item.id for item in rows],
    )
    return {
        "items": [
            _transaction_response(
                transaction,
                category_names.get(transaction.category_id),
                memberships.get(transaction.id),
            )
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
    relation_fact_contexts = _active_relation_facts_for_transaction(
        db,
        transaction=transaction,
        user_id=user.id,
    )
    if not relation_fact_contexts:
        raise HTTPException(status_code=409, detail="这笔流水尚未建立经济事实，请完成数据迁移后重试")
    fact = relation_fact_contexts[0][0]
    start = transaction.transaction_date - timedelta(days=365)
    end = transaction.transaction_date + timedelta(days=366)
    existing_evidence_fact_ids = {
        row.fact_id
        for row in db.query(EconomicFactAllocation.fact_id).filter(
            EconomicFactAllocation.transaction_id == transaction.id,
            EconomicFactAllocation.role == "corroborating",
            EconomicFactAllocation.status == "confirmed",
        ).all()
    }
    candidate_transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.id != transaction.id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
        )
        .order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
        .limit(500)
        .all()
    )
    relation_candidates: list[tuple[FinancialTransaction | SimpleNamespace, EconomicFact]] = []
    merge_candidates: list[tuple[FinancialTransaction, EconomicFact]] = []
    candidate_contexts = _active_relation_facts_for_transactions(
        db,
        transactions=candidate_transactions,
        user_id=user.id,
    )
    for candidate_transaction in candidate_transactions:
        for candidate_fact, candidate_observation in candidate_contexts.get(candidate_transaction.id, []):
            if candidate_fact.id in existing_evidence_fact_ids:
                continue
            relation_candidates.append((candidate_observation, candidate_fact))
            if candidate_fact.primary_transaction_id == candidate_transaction.id:
                merge_candidates.append((candidate_transaction, candidate_fact))
    existing_pairs = {
        (row.source_fact_id, row.target_fact_id, row.relation_type)
        for row in db.query(EconomicFactRelation).filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
        ).all()
    }
    split_components, _ = _split_components_for_transactions(
        db,
        user_id=user.id,
        transaction_ids=[transaction.id],
    )
    suggestions: list[dict] = []
    for current_fact, current_observation in relation_fact_contexts:
        suggestions.extend(build_relation_suggestions(
            transaction=current_observation,
            fact=current_fact,
            candidates=relation_candidates,
            existing_pairs=existing_pairs,
        ))
    suggestion_keys: set[tuple[int, int, str]] = set()
    unique_suggestions = []
    for suggestion in sorted(
        suggestions,
        key=lambda item: (-item["score"], item["source_fact_id"], item["target_fact_id"]),
    ):
        key = (
            suggestion["source_fact_id"],
            suggestion["target_fact_id"],
            suggestion["relation_type"],
        )
        if key in suggestion_keys:
            continue
        suggestion_keys.add(key)
        unique_suggestions.append(suggestion)
    suggestion_fact_ids = {
        fact_id
        for suggestion in unique_suggestions
        for fact_id in (suggestion["source_fact_id"], suggestion["target_fact_id"])
    }
    allocated_by_fact: dict[int, Decimal] = {fact_id: Decimal("0.00") for fact_id in suggestion_fact_ids}
    if suggestion_fact_ids:
        for relation in db.query(EconomicFactRelation).filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
            or_(
                EconomicFactRelation.source_fact_id.in_(suggestion_fact_ids),
                EconomicFactRelation.target_fact_id.in_(suggestion_fact_ids),
            ),
        ).all():
            amount = Decimal(relation.allocated_amount)
            if relation.source_fact_id in allocated_by_fact:
                allocated_by_fact[relation.source_fact_id] += amount
            if relation.target_fact_id in allocated_by_fact:
                allocated_by_fact[relation.target_fact_id] += amount
        for link in db.query(PayslipArrivalLink).filter(
            PayslipArrivalLink.economic_fact_id.in_(suggestion_fact_ids),
            PayslipArrivalLink.status == "confirmed",
        ).all():
            allocated_by_fact[link.economic_fact_id] += Decimal(link.allocated_amount)
        transaction_fact_ids: dict[int, set[int]] = {}
        for suggestion in unique_suggestions:
            transaction_fact_ids.setdefault(suggestion["source_transaction_id"], set()).add(
                suggestion["source_fact_id"]
            )
            transaction_fact_ids.setdefault(suggestion["target_transaction_id"], set()).add(
                suggestion["target_fact_id"]
            )
        legacy_transaction_ids = set(transaction_fact_ids)
        if legacy_transaction_ids:
            for link in db.query(PayslipArrivalLink).filter(
                PayslipArrivalLink.economic_fact_id.is_(None),
                PayslipArrivalLink.transaction_id.in_(legacy_transaction_ids),
                PayslipArrivalLink.status == "confirmed",
            ).all():
                for fact_id in transaction_fact_ids.get(link.transaction_id, set()):
                    allocated_by_fact[fact_id] += Decimal(link.allocated_amount)
    fact_amounts = {
        fact.id: Decimal(fact.amount)
        for fact in db.query(EconomicFact).filter(EconomicFact.id.in_(suggestion_fact_ids)).all()
    } if suggestion_fact_ids else {}
    available_suggestions = []
    for suggestion in unique_suggestions:
        source_remaining = max(
            Decimal("0.00"),
            fact_amounts[suggestion["source_fact_id"]] - allocated_by_fact[suggestion["source_fact_id"]],
        )
        target_remaining = max(
            Decimal("0.00"),
            fact_amounts[suggestion["target_fact_id"]] - allocated_by_fact[suggestion["target_fact_id"]],
        )
        available = min(
            Decimal(suggestion["allocated_amount"]),
            source_remaining,
            target_remaining,
        )
        if available <= 0:
            continue
        if available != Decimal(suggestion["allocated_amount"]):
            suggestion["allocated_amount"] = available
            suggestion["confidence_tier"] = "medium"
            suggestion["ai_status"] = "unavailable"
            suggestion["reasons"].append(f"扣除已确认关系后，本次最多可分配 {available:.2f} 元")
        available_suggestions.append(suggestion)
    high_source_counts: dict[int, int] = {}
    high_target_counts: dict[int, int] = {}
    for suggestion in available_suggestions:
        if suggestion["confidence_tier"] != "high":
            continue
        high_source_counts[suggestion["source_fact_id"]] = high_source_counts.get(suggestion["source_fact_id"], 0) + 1
        high_target_counts[suggestion["target_fact_id"]] = high_target_counts.get(suggestion["target_fact_id"], 0) + 1
    for suggestion in available_suggestions:
        if suggestion["confidence_tier"] != "high":
            continue
        if (
            high_source_counts.get(suggestion["source_fact_id"], 0) > 1
            or high_target_counts.get(suggestion["target_fact_id"], 0) > 1
        ):
            suggestion["confidence_tier"] = "medium"
            suggestion["ai_status"] = "unavailable"
            suggestion["reasons"].append("同一经济事实存在多个高匹配对象，必须由用户选择")
    suggestions = enrich_relation_suggestions_with_ai(
        available_suggestions[:20],
        transaction=transaction,
        user_id=user.id,
        expected_data_epoch=user.business_data_epoch,
    )
    merge_suggestions = []
    if not split_components.get(transaction.id):
        merge_suggestions = build_fact_merge_suggestions(
            transaction=transaction,
            fact=fact,
            candidates=merge_candidates,
        )[:20]
        merge_suggestions = enrich_fact_merge_suggestions_with_ai(
            merge_suggestions,
            transaction=transaction,
            user_id=user.id,
            expected_data_epoch=user.business_data_epoch,
        )
    return EconomicRelationSuggestionResponse(
        transaction=_transaction_response(transaction),
        fact=_fact_response(fact),
        fact_members=get_fact_members(db, fact=fact, user_id=user.id),
        payslip_evidence=_fact_payslip_evidence(db, fact=fact, user_id=user.id),
        split_components=split_components.get(transaction.id, []),
        merge_suggestions=merge_suggestions,
        suggestions=suggestions,
    )


@router.post(
    "/transactions/{transaction_id}/split",
    response_model=EconomicFactSplitResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_transaction_fact_split(
    transaction_id: int,
    data: EconomicFactSplitConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    if transaction.status != "confirmed" or transaction.deleted_at is not None:
        raise HTTPException(status_code=409, detail="只能拆分有效的已确认流水")
    if transaction.direction not in {"income", "expense"}:
        raise HTTPException(status_code=400, detail="转账记录不能在这里拆分为普通收支")
    allocated_total = sum((Decimal(item.amount) for item in data.components), Decimal("0.00"))
    if allocated_total != Decimal(transaction.amount):
        raise HTTPException(
            status_code=409,
            detail=f"拆分金额合计必须等于原流水 {Decimal(transaction.amount):.2f} 元，当前为 {allocated_total:.2f} 元",
        )
    normalized_components = []
    for item in data.components:
        category = get_available_category(
            db,
            user_id=user.id,
            category_id=item.category_id,
            direction=transaction.direction,
        )
        normalized_components.append((
            item,
            category,
            item.nature if transaction.direction == "expense" else None,
        ))

    original_fact = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.primary_transaction_id == transaction.id,
    ).first()
    if original_fact is None:
        raise HTTPException(status_code=409, detail="来源流水缺少原始经济事实，请完成数据迁移后重试")
    active_split_rows = (
        db.query(EconomicFactAllocation, EconomicFact)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .filter(
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id == transaction.id,
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "split_component",
        )
        .all()
    )
    outgoing_evidence = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.transaction_id == transaction.id,
        EconomicFactAllocation.status == "confirmed",
        EconomicFactAllocation.role == "corroborating",
    ).first()
    incoming_evidence = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == original_fact.id,
        EconomicFactAllocation.status == "confirmed",
        EconomicFactAllocation.role == "corroborating",
    ).first()
    if outgoing_evidence is not None or incoming_evidence is not None:
        raise HTTPException(status_code=409, detail="这条流水已有同一事实证据分配，请先撤销证据合并再拆分")
    affected_fact_ids = {original_fact.id, *(fact.id for _, fact in active_split_rows)}
    active_relation = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id.in_(affected_fact_ids),
            EconomicFactRelation.target_fact_id.in_(affected_fact_ids),
        ),
    ).first()
    if active_relation is not None:
        raise HTTPException(status_code=409, detail="拆分涉及的经济事实已有退款、报销或转账关系，请先撤销关系")
    active_arrival = db.query(PayslipArrivalLink).filter(
        or_(
            PayslipArrivalLink.economic_fact_id.in_(affected_fact_ids),
            (
                PayslipArrivalLink.economic_fact_id.is_(None)
                & (PayslipArrivalLink.transaction_id == transaction.id)
            ),
        ),
        PayslipArrivalLink.status == "confirmed",
    ).first()
    if active_arrival is not None:
        raise HTTPException(status_code=409, detail="拆分涉及的经济事实已作为工资到账证据，请先撤销工资到账关系")

    revision_targets: dict[int, tuple[EconomicFact, dict | None]] = {
        original_fact.id: (original_fact, economic_fact_snapshot(db, original_fact)),
    }
    now = datetime.utcnow()
    for allocation, fact in active_split_rows:
        revision_targets[fact.id] = (fact, economic_fact_snapshot(db, fact))
        allocation.status = "reversed"
        allocation.reversed_at = now
        fact.status = "superseded"
    original_allocation = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == original_fact.id,
        EconomicFactAllocation.transaction_id == transaction.id,
    ).first()
    if original_allocation is None:
        raise HTTPException(status_code=409, detail="原始经济事实分配缺失，无法拆分")
    original_allocation.status = "reversed"
    original_allocation.reversed_at = now
    original_fact.status = "superseded"

    for item, category, nature in normalized_components:
        component_fact = EconomicFact(
            user_id=user.id,
            primary_transaction_id=None,
            fact_type=(
                "reimbursable_expense"
                if transaction.direction == "expense" and nature == "reimbursable"
                else transaction.direction
            ),
            title=item.title,
            occurred_date=transaction.transaction_date,
            amount=item.amount,
            currency=transaction.currency,
            category_id=category.id,
            nature=nature,
            description=item.description,
            status="confirmed",
        )
        db.add(component_fact)
        db.flush()
        db.add(EconomicFactAllocation(
            fact_id=component_fact.id,
            transaction_id=transaction.id,
            role="split_component",
            allocated_amount=item.amount,
            status="confirmed",
            reasons=[data.reason or "用户确认混合流水拆分"],
            confirmed_by_user_id=user.id,
            confirmed_at=now,
        ))
        revision_targets[component_fact.id] = (component_fact, None)
    db.flush()
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="fact_split_confirm",
        entity_type="financial_transaction",
        entity_id=transaction.id,
        summary=f"将流水 {transaction.id} 拆分为 {len(data.components)} 个经济事实",
    )
    for fact, before_snapshot in revision_targets.values():
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=fact,
            ledger_revision=ledger_revision,
            operation="split_confirm",
            before_snapshot=before_snapshot,
            reason=data.reason or "用户确认混合流水拆分",
        )
    commit_financial_ledger(db)
    return _split_response(
        db,
        transaction=transaction,
        user_id=user.id,
        ledger_revision=ledger_revision,
    )


@router.delete(
    "/transactions/{transaction_id}/split",
    response_model=EconomicFactSplitResponse,
)
def reverse_transaction_fact_split(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    original_fact = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.primary_transaction_id == transaction.id,
    ).first()
    split_rows = (
        db.query(EconomicFactAllocation, EconomicFact)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .filter(
            EconomicFact.user_id == user.id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id == transaction.id,
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "split_component",
        )
        .all()
    )
    if original_fact is None or not split_rows:
        raise HTTPException(status_code=404, detail="这条流水没有有效的事实拆分")
    split_fact_ids = {fact.id for _, fact in split_rows}
    active_relation = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id.in_(split_fact_ids),
            EconomicFactRelation.target_fact_id.in_(split_fact_ids),
        ),
    ).first()
    if active_relation is not None:
        raise HTTPException(status_code=409, detail="拆分后的事实已有退款、报销或转账关系，请先撤销关系")
    active_arrival = db.query(PayslipArrivalLink).filter(
        or_(
            PayslipArrivalLink.economic_fact_id.in_(split_fact_ids),
            (
                PayslipArrivalLink.economic_fact_id.is_(None)
                & (PayslipArrivalLink.transaction_id == transaction.id)
            ),
        ),
        PayslipArrivalLink.status == "confirmed",
    ).first()
    if active_arrival is not None:
        raise HTTPException(status_code=409, detail="拆分后的事实已作为工资到账证据，请先撤销工资到账关系")
    revision_targets: dict[int, tuple[EconomicFact, dict | None]] = {
        original_fact.id: (original_fact, economic_fact_snapshot(db, original_fact)),
    }
    now = datetime.utcnow()
    for allocation, fact in split_rows:
        revision_targets[fact.id] = (fact, economic_fact_snapshot(db, fact))
        allocation.status = "reversed"
        allocation.reversed_at = now
        fact.status = "superseded"
    sync_transaction_fact(db, transaction=transaction, user_id=user.id)
    db.flush()
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="fact_split_reverse",
        entity_type="financial_transaction",
        entity_id=transaction.id,
        summary=f"撤销流水 {transaction.id} 的经济事实拆分",
    )
    for fact, before_snapshot in revision_targets.values():
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=fact,
            ledger_revision=ledger_revision,
            operation="split_reverse",
            before_snapshot=before_snapshot,
            reason="用户撤销混合流水拆分",
        )
    commit_financial_ledger(db)
    return _split_response(
        db,
        transaction=transaction,
        user_id=user.id,
        ledger_revision=ledger_revision,
    )


def _merge_fact_evidence_locked(
    db: Session,
    *,
    user: User,
    primary_transaction: FinancialTransaction,
    evidence_transaction: FinancialTransaction,
    allocated_amount: Decimal,
    reasons: list[str],
    detection_method: str,
    now: datetime,
) -> EconomicFact:
    """Apply one evidence allocation inside the caller's locked ledger transaction."""
    if primary_transaction.id == evidence_transaction.id:
        raise HTTPException(status_code=400, detail="不能把同一条记录重复合并")
    if (
        primary_transaction.status != "confirmed"
        or evidence_transaction.status != "confirmed"
        or primary_transaction.deleted_at is not None
        or evidence_transaction.deleted_at is not None
    ):
        raise HTTPException(status_code=409, detail="只能合并两条有效的已确认记录")
    if primary_transaction.direction != evidence_transaction.direction:
        raise HTTPException(status_code=400, detail="同一经济事实的两份证据必须具有相同资金方向")
    if primary_transaction.currency != evidence_transaction.currency:
        raise HTTPException(status_code=400, detail="不同币种暂不能合并为同一经济事实")

    primary_fact = get_transaction_fact(
        db,
        transaction_id=primary_transaction.id,
        user_id=user.id,
    )
    evidence_fact = get_transaction_fact(
        db,
        transaction_id=evidence_transaction.id,
        user_id=user.id,
    )
    if primary_fact is None or evidence_fact is None:
        raise HTTPException(status_code=409, detail="记录缺少经济事实，请完成数据迁移后重试")
    if primary_fact.id == evidence_fact.id:
        raise HTTPException(status_code=409, detail="这两条记录已经属于同一经济事实")
    if primary_fact.primary_transaction_id != primary_transaction.id:
        raise HTTPException(status_code=409, detail="主记录本身是其他事实的辅助证据，请先撤销原合并")
    if evidence_fact.primary_transaction_id != evidence_transaction.id:
        raise HTTPException(status_code=409, detail="证据记录已经并入其他经济事实，请先撤销原合并")
    existing_target_allocation = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == primary_fact.id,
        EconomicFactAllocation.transaction_id == evidence_transaction.id,
    ).first()
    if existing_target_allocation is not None and existing_target_allocation.status == "confirmed":
        raise HTTPException(status_code=409, detail="这条记录已经分配到目标经济事实")
    already_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactAllocation).filter(
                EconomicFactAllocation.transaction_id == evidence_transaction.id,
                EconomicFactAllocation.role == "corroborating",
                EconomicFactAllocation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    available_amount = max(Decimal("0.00"), Decimal(evidence_transaction.amount) - already_allocated)
    if allocated_amount > min(Decimal(primary_fact.amount), available_amount) + Decimal("0.01"):
        raise HTTPException(status_code=409, detail="分配金额超过目标事实金额或这条记录的剩余可分配金额")
    evidence_members = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == evidence_fact.id,
        EconomicFactAllocation.status == "confirmed",
    ).all()
    if any(member.transaction_id != evidence_transaction.id for member in evidence_members):
        raise HTTPException(status_code=409, detail="证据记录代表的事实还包含其他来源，请先逐项核对")
    evidence_relation = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
        or_(
            EconomicFactRelation.source_fact_id == evidence_fact.id,
            EconomicFactRelation.target_fact_id == evidence_fact.id,
        ),
    ).first()
    if evidence_relation is not None:
        raise HTTPException(status_code=409, detail="证据记录已有退款、报销或转账关系，请先撤销该关系")

    remaining_amount = available_amount - allocated_amount
    for allocation in evidence_members:
        if remaining_amount > Decimal("0.00"):
            allocation.allocated_amount = remaining_amount
            allocation.status = "confirmed"
            allocation.reversed_at = None
        else:
            allocation.status = "reversed"
            allocation.reversed_at = now
    evidence_fact.amount = max(Decimal("0.00"), remaining_amount)
    evidence_fact.status = "confirmed" if remaining_amount > Decimal("0.00") else "superseded"
    target_allocation = existing_target_allocation
    allocation_reasons = [f"判断来源：{detection_method}", *reasons][:12]
    if target_allocation is None:
        target_allocation = EconomicFactAllocation(
            fact_id=primary_fact.id,
            transaction_id=evidence_transaction.id,
            role="corroborating",
            allocated_amount=allocated_amount,
            status="confirmed",
            reasons=allocation_reasons,
            confirmed_by_user_id=user.id,
            confirmed_at=now,
        )
        db.add(target_allocation)
    else:
        target_allocation.role = "corroborating"
        target_allocation.allocated_amount = allocated_amount
        target_allocation.status = "confirmed"
        target_allocation.reasons = allocation_reasons
        target_allocation.confirmed_by_user_id = user.id
        target_allocation.confirmed_at = now
        target_allocation.reversed_at = None
    return primary_fact


@router.post(
    "/facts/merge-evidence",
    response_model=EconomicFactMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_fact_evidence_merge(
    data: EconomicFactMergeConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    primary_transaction = get_owned_transaction(
        db,
        user_id=user.id,
        transaction_id=data.primary_transaction_id,
    )
    evidence_transaction = get_owned_transaction(
        db,
        user_id=user.id,
        transaction_id=data.evidence_transaction_id,
    )
    revision_targets = {}
    for transaction in (primary_transaction, evidence_transaction):
        target_fact = get_transaction_fact(db, transaction_id=transaction.id, user_id=user.id)
        if target_fact is not None:
            revision_targets[target_fact.id] = (target_fact, economic_fact_snapshot(db, target_fact))
    primary_fact = _merge_fact_evidence_locked(
        db,
        user=user,
        primary_transaction=primary_transaction,
        evidence_transaction=evidence_transaction,
        allocated_amount=Decimal(data.allocated_amount),
        reasons=data.reasons,
        detection_method=data.detection_method,
        now=datetime.utcnow(),
    )
    db.flush()
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="fact_evidence_merge",
        entity_type="economic_fact",
        entity_id=primary_fact.id,
        summary=f"确认同一经济事实证据：流水 {evidence_transaction.id} 的 {Decimal(data.allocated_amount):.2f} 元并入事实 {primary_fact.id}",
    )
    for target_fact, before_snapshot in revision_targets.values():
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=target_fact,
            ledger_revision=ledger_revision,
            operation="merge_evidence",
            before_snapshot=before_snapshot,
            reason=f"流水 {evidence_transaction.id} 的 {Decimal(data.allocated_amount):.2f} 元作为同一事实证据",
        )
    commit_financial_ledger(db)
    return _fact_membership_response(db, fact=primary_fact, user_id=user.id)


@router.post(
    "/facts/merge-evidence/batch",
    response_model=EconomicFactMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_fact_evidence_batch_merge(
    data: EconomicFactMergeBatchConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if any(item.evidence_transaction_id == data.primary_transaction_id for item in data.allocations):
        raise HTTPException(status_code=400, detail="不能把主记录作为自己的辅助证据")
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    primary_transaction = get_owned_transaction(
        db,
        user_id=user.id,
        transaction_id=data.primary_transaction_id,
    )
    primary_fact: EconomicFact | None = None
    revision_targets: dict[int, tuple[EconomicFact, dict]] = {}
    now = datetime.utcnow()
    try:
        target_fact = get_transaction_fact(db, transaction_id=primary_transaction.id, user_id=user.id)
        if target_fact is not None:
            revision_targets[target_fact.id] = (target_fact, economic_fact_snapshot(db, target_fact))
        for item in data.allocations:
            evidence_transaction = get_owned_transaction(
                db,
                user_id=user.id,
                transaction_id=item.evidence_transaction_id,
            )
            evidence_fact = get_transaction_fact(db, transaction_id=evidence_transaction.id, user_id=user.id)
            if evidence_fact is not None and evidence_fact.id not in revision_targets:
                revision_targets[evidence_fact.id] = (evidence_fact, economic_fact_snapshot(db, evidence_fact))
            primary_fact = _merge_fact_evidence_locked(
                db,
                user=user,
                primary_transaction=primary_transaction,
                evidence_transaction=evidence_transaction,
                allocated_amount=Decimal(item.allocated_amount),
                reasons=item.reasons,
                detection_method=item.detection_method,
                now=now,
            )
        db.flush()
    except Exception:
        db.rollback()
        raise
    if primary_fact is None:
        raise HTTPException(status_code=400, detail="至少选择一条证据记录")
    allocated_total = sum((Decimal(item.allocated_amount) for item in data.allocations), Decimal("0.00"))
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="fact_evidence_batch_merge",
        entity_type="economic_fact",
        entity_id=primary_fact.id,
        summary=f"批量确认同一经济事实：{len(data.allocations)} 条证据，共分配 {allocated_total:.2f} 元",
    )
    for target_fact, before_snapshot in revision_targets.values():
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=target_fact,
            ledger_revision=ledger_revision,
            operation="batch_merge_evidence",
            before_snapshot=before_snapshot,
            reason=f"一次确认 {len(data.allocations)} 条同一事实证据",
        )
    commit_financial_ledger(db)
    return _fact_membership_response(db, fact=primary_fact, user_id=user.id)


@router.delete(
    "/facts/{fact_id}/evidence/{transaction_id}",
    response_model=EconomicFactMembershipResponse,
)
def reverse_fact_evidence_merge(
    fact_id: int,
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    fact = db.query(EconomicFact).filter(
        EconomicFact.id == fact_id,
        EconomicFact.user_id == user.id,
        EconomicFact.status == "confirmed",
    ).first()
    if fact is None:
        raise HTTPException(status_code=404, detail="经济事实不存在")
    if fact.primary_transaction_id == transaction_id:
        raise HTTPException(status_code=400, detail="主记录不能作为辅助证据移除")
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    allocation = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == fact.id,
        EconomicFactAllocation.transaction_id == transaction.id,
        EconomicFactAllocation.role == "corroborating",
        EconomicFactAllocation.status == "confirmed",
    ).first()
    if allocation is None:
        raise HTTPException(status_code=404, detail="这条记录不是该经济事实的有效辅助证据")
    fact_before = economic_fact_snapshot(db, fact)
    now = datetime.utcnow()
    allocation.status = "reversed"
    allocation.reversed_at = now
    original_fact = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.primary_transaction_id == transaction.id,
    ).first()
    if original_fact is None:
        raise HTTPException(status_code=409, detail="原经济事实缺失，无法撤销合并")
    original_fact_before = economic_fact_snapshot(db, original_fact)
    other_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactAllocation).filter(
                EconomicFactAllocation.transaction_id == transaction.id,
                EconomicFactAllocation.id != allocation.id,
                EconomicFactAllocation.role == "corroborating",
                EconomicFactAllocation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    restored_amount = max(Decimal("0.00"), Decimal(transaction.amount) - other_allocated)
    original_fact.fact_type = transaction_fact_type(transaction)
    original_fact.title = transaction_fact_title(transaction)
    original_fact.occurred_date = transaction.transaction_date
    original_fact.amount = restored_amount
    original_fact.currency = transaction.currency
    original_fact.status = "confirmed" if restored_amount > Decimal("0.00") else "superseded"
    original_allocation = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id == original_fact.id,
        EconomicFactAllocation.transaction_id == transaction.id,
    ).first()
    if original_allocation is None:
        raise HTTPException(status_code=409, detail="原经济事实分配缺失，无法撤销合并")
    original_allocation.allocated_amount = restored_amount
    original_allocation.status = "confirmed" if restored_amount > Decimal("0.00") else "reversed"
    original_allocation.reversed_at = None if restored_amount > Decimal("0.00") else now
    db.flush()
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="fact_evidence_unmerge",
        entity_type="economic_fact",
        entity_id=fact.id,
        summary=f"撤销同一经济事实证据：流水 {transaction.id} 恢复为独立事实",
    )
    record_economic_fact_revision(
        db,
        owner=owner,
        fact=fact,
        ledger_revision=ledger_revision,
        operation="unmerge_evidence",
        before_snapshot=fact_before,
        reason=f"移除流水 {transaction.id} 的辅助证据分配",
    )
    record_economic_fact_revision(
        db,
        owner=owner,
        fact=original_fact,
        ledger_revision=ledger_revision,
        operation="restore_evidence_remainder",
        before_snapshot=original_fact_before,
        reason=f"恢复流水 {transaction.id} 的独立事实金额",
    )
    commit_financial_ledger(db)
    return _fact_membership_response(db, fact=fact, user_id=user.id)


@router.get(
    "/facts/{fact_id}/revisions",
    response_model=list[EconomicFactRevisionResponse],
)
def list_economic_fact_revisions(
    fact_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fact = db.query(EconomicFact).filter(
        EconomicFact.id == fact_id,
        EconomicFact.user_id == user.id,
    ).first()
    if fact is None:
        raise HTTPException(status_code=404, detail="经济事实不存在")
    return (
        db.query(EconomicFactRevision)
        .filter(
            EconomicFactRevision.fact_id == fact.id,
            EconomicFactRevision.user_id == user.id,
        )
        .order_by(EconomicFactRevision.fact_revision.desc())
        .all()
    )


@router.get(
    "/transactions/{transaction_id}/revisions",
    response_model=list[FinancialTransactionRevisionResponse],
)
def list_transaction_revisions(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = get_owned_transaction(db, user_id=user.id, transaction_id=transaction_id)
    return (
        db.query(FinancialTransactionRevision)
        .filter(
            FinancialTransactionRevision.transaction_id == transaction.id,
            FinancialTransactionRevision.user_id == user.id,
        )
        .order_by(FinancialTransactionRevision.transaction_revision.desc())
        .all()
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
    facts = get_transaction_facts(db, transaction_id=transaction.id, user_id=user.id)
    fact_ids = [fact.id for fact in facts]
    if not fact_ids:
        return []
    relations = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
            or_(
                EconomicFactRelation.source_fact_id.in_(fact_ids),
                EconomicFactRelation.target_fact_id.in_(fact_ids),
            ),
        )
        .order_by(EconomicFactRelation.confirmed_at.desc(), EconomicFactRelation.id.desc())
        .all()
    )
    return [_relation_response(db, relation) for relation in relations]


@router.get(
    "/relations/{relation_id}/revisions",
    response_model=list[EconomicRelationRevisionResponse],
)
def list_economic_relation_revisions(
    relation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    relation = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.id == relation_id,
        EconomicFactRelation.user_id == user.id,
    ).one_or_none()
    if relation is None:
        raise HTTPException(status_code=404, detail="经济事实关系不存在")
    return (
        db.query(EconomicFactRelationRevision)
        .filter(
            EconomicFactRelationRevision.relation_id == relation.id,
            EconomicFactRelationRevision.user_id == user.id,
        )
        .order_by(EconomicFactRelationRevision.relation_revision.desc())
        .all()
    )


def _resolve_relation_endpoint(
    db: Session,
    *,
    user_id: int,
    transaction_id: int | None,
    fact_id: int | None,
    side_label: str,
) -> tuple[FinancialTransaction, EconomicFact]:
    transaction = (
        get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
        if transaction_id is not None
        else None
    )
    fact = None
    if fact_id is not None:
        fact = db.query(EconomicFact).filter(
            EconomicFact.id == fact_id,
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
        ).one_or_none()
        if fact is None:
            raise HTTPException(status_code=404, detail=f"{side_label}经济事实不存在或已失效")
        if transaction is not None:
            active_fact_ids = {
                item.id
                for item in get_transaction_facts(
                    db,
                    transaction_id=transaction.id,
                    user_id=user_id,
                )
            }
            if fact.id not in active_fact_ids:
                raise HTTPException(status_code=409, detail=f"{side_label}经济事实不属于指定流水")
    elif transaction is not None:
        facts = get_transaction_facts(
            db,
            transaction_id=transaction.id,
            user_id=user_id,
        )
        if not facts:
            raise HTTPException(status_code=409, detail=f"{side_label}流水缺少经济事实")
        if len(facts) > 1:
            raise HTTPException(
                status_code=409,
                detail=f"{side_label}流水已拆成 {len(facts)} 个经济事实，请明确选择其中一项",
            )
        fact = facts[0]
    if fact is None:
        raise HTTPException(status_code=400, detail=f"{side_label}缺少经济事实")
    if transaction is None:
        transaction = _fact_relation_transaction(db, fact=fact, user_id=user_id)
    return transaction, fact


@router.post("/relations", response_model=EconomicRelationResponse, status_code=status.HTTP_201_CREATED)
def confirm_economic_relation(
    data: EconomicRelationConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    source_transaction, source_fact = _resolve_relation_endpoint(
        db,
        user_id=user.id,
        transaction_id=data.source_transaction_id,
        fact_id=data.source_fact_id,
        side_label="来源端",
    )
    target_transaction, target_fact = _resolve_relation_endpoint(
        db,
        user_id=user.id,
        transaction_id=data.target_transaction_id,
        fact_id=data.target_fact_id,
        side_label="目标端",
    )
    if source_fact.id == target_fact.id:
        raise HTTPException(status_code=400, detail="不能把同一个经济事实关联给自己")
    if source_transaction.status != "confirmed" or target_transaction.status != "confirmed":
        raise HTTPException(status_code=409, detail="只能关联已确认流水")
    if data.relation_type in {"refunds", "reimburses"}:
        if source_transaction.direction != "income" or target_transaction.direction != "expense":
            raise HTTPException(status_code=400, detail="退款或报销必须由一笔收入关联到原支出")
    elif data.relation_type == "transfer_pair":
        direction_pair = {source_transaction.direction, target_transaction.direction}
        if direction_pair not in ({"income", "expense"}, {"transfer"}):
            raise HTTPException(status_code=400, detail="内部转账必须是一进一出或两笔均已标记转账")
    if data.allocated_amount > min(Decimal(source_fact.amount), Decimal(target_fact.amount)):
        raise HTTPException(status_code=409, detail="关联金额不能超过任一笔经济事实的金额")
    source_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactRelation).filter(
                or_(
                    EconomicFactRelation.source_fact_id == source_fact.id,
                    EconomicFactRelation.target_fact_id == source_fact.id,
                ),
                EconomicFactRelation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    source_allocated += sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(PayslipArrivalLink).filter(
                or_(
                    PayslipArrivalLink.economic_fact_id == source_fact.id,
                    (
                        PayslipArrivalLink.economic_fact_id.is_(None)
                        & (PayslipArrivalLink.transaction_id == source_transaction.id)
                    ),
                ),
                PayslipArrivalLink.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    target_allocated = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactRelation).filter(
                or_(
                    EconomicFactRelation.source_fact_id == target_fact.id,
                    EconomicFactRelation.target_fact_id == target_fact.id,
                ),
                EconomicFactRelation.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    target_allocated += sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(PayslipArrivalLink).filter(
                or_(
                    PayslipArrivalLink.economic_fact_id == target_fact.id,
                    (
                        PayslipArrivalLink.economic_fact_id.is_(None)
                        & (PayslipArrivalLink.transaction_id == target_transaction.id)
                    ),
                ),
                PayslipArrivalLink.status == "confirmed",
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
    before_snapshot = economic_relation_snapshot(relation) if relation is not None else None
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
    source_fact_before = economic_fact_snapshot(db, source_fact)
    target_fact_before = economic_fact_snapshot(db, target_fact)
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
    relation_revision = record_economic_relation_revision(
        db,
        owner=owner,
        relation=relation,
        operation="confirm",
        before_snapshot=before_snapshot,
        reason="用户确认经济事实关系",
    )
    for changed_fact, before_snapshot in (
        (source_fact, source_fact_before),
        (target_fact, target_fact_before),
    ):
        record_economic_fact_revision(
            db,
            owner=owner,
            fact=changed_fact,
            ledger_revision=relation_revision.ledger_revision,
            operation="relation_confirm",
            before_snapshot=before_snapshot,
            reason=f"用户确认 {data.relation_type} 关系",
        )
    commit_financial_ledger(db)
    return _relation_response(db, relation)


@router.post(
    "/relations/batch-reverse",
    response_model=list[EconomicRelationResponse],
)
def batch_reverse_economic_relations(
    payload: EconomicRelationBatchReverseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    relations = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.id.in_(payload.relation_ids),
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
        )
        .with_for_update()
        .all()
    )
    relation_by_id = {relation.id: relation for relation in relations}
    unavailable_ids = [relation_id for relation_id in payload.relation_ids if relation_id not in relation_by_id]
    if unavailable_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "relations_not_reversible",
                "message": "选中关系已变更，本次未撤销任何关系",
                "relation_ids": unavailable_ids,
            },
        )
    ordered_relations = [relation_by_id[relation_id] for relation_id in payload.relation_ids]
    for relation in ordered_relations:
        _reverse_economic_relation_locked(
            db,
            owner=owner,
            relation=relation,
            reason=payload.reason or "用户批量撤销经济事实关系",
        )
    commit_financial_ledger(db)
    return [_relation_response(db, relation) for relation in ordered_relations]


@router.delete("/relations/{relation_id}", response_model=EconomicRelationResponse)
def reverse_economic_relation(
    relation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
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
    _reverse_economic_relation_locked(
        db,
        owner=owner,
        relation=relation,
        reason="用户撤销经济事实关系",
    )
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
    record_transaction_ledger_revision(
        db,
        owner=owner,
        transaction=transaction,
        operation="create",
        before_snapshot=None,
        reason="用户手工创建",
    )
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
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    transaction = get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
    changes = data.model_dump(exclude_unset=True)
    revision_reason = changes.pop("revision_reason", None)
    before_snapshot = financial_transaction_snapshot(transaction)
    direction = changes.get("direction", transaction.direction)
    proposed_status = changes.get("status", transaction.status)
    proposed_amount = Decimal(changes.get("amount", transaction.amount))
    _guard_transaction_change_with_relations(
        db,
        transaction=transaction,
        proposed_direction=direction,
        proposed_status=proposed_status,
        proposed_amount=proposed_amount,
    )
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
    if before_snapshot == financial_transaction_snapshot(transaction):
        raise HTTPException(status_code=400, detail="没有需要保存的流水变更")
    sync_transaction_fact(db, transaction=transaction, user_id=user_id)
    record_transaction_ledger_revision(
        db,
        owner=owner,
        transaction=transaction,
        operation="update",
        before_snapshot=before_snapshot,
        reason=revision_reason or "用户修改流水",
    )
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
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    transaction = get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
    _guard_transaction_change_with_relations(
        db,
        transaction=transaction,
        proposed_direction=transaction.direction,
        proposed_status="deleted",
        proposed_amount=Decimal(transaction.amount),
    )
    before_snapshot = financial_transaction_snapshot(transaction)
    transaction.status = "deleted"
    transaction.deleted_at = datetime.utcnow()
    sync_transaction_fact(db, transaction=transaction, user_id=user_id)
    record_transaction_ledger_revision(
        db,
        owner=owner,
        transaction=transaction,
        operation="delete",
        before_snapshot=before_snapshot,
        reason="用户删除流水",
    )
    commit_financial_ledger(db)
    return {"deleted": True, "transaction_id": transaction.id}


@router.post("/transactions/{transaction_id}/restore", response_model=FinancialTransactionResponse)
def restore_transaction(
    transaction_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
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
    before_snapshot = financial_transaction_snapshot(transaction)
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
    record_transaction_ledger_revision(
        db,
        owner=owner,
        transaction=transaction,
        operation="restore",
        before_snapshot=before_snapshot,
        reason="用户恢复已删除流水",
    )
    commit_financial_ledger(db)
    db.refresh(transaction)
    return _transaction_response(transaction, category.name if category is not None else None)


def _build_user_month_summary(db: Session, *, user_id: int, month: str | None) -> dict:
    normalized_month, start, end = parse_month(month)
    return _build_user_period_summary(
        db,
        user_id=user_id,
        start=start,
        end=end,
        label=normalized_month,
    )


def _build_user_period_summary(
    db: Session,
    *,
    user_id: int,
    start: date,
    end: date,
    label: str,
) -> dict:
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
        )
        .all()
    )
    relation_effects, relation_category_ids = _summary_relation_effects(
        db,
        user_id=user_id,
        transactions=transactions,
    )
    split_components, split_category_ids = _split_components_for_transactions(
        db,
        user_id=user_id,
        transaction_ids=[item.id for item in transactions if getattr(item, "id", None) is not None],
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_ids.update(split_category_ids)
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user_id),
        ).all()
    } if category_ids else {}
    for effect in relation_effects.values():
        offset_category_id = effect.get("offset_category_id")
        if offset_category_id is not None:
            effect["offset_category_name"] = category_names.get(int(offset_category_id), "退款/报销冲销")
    return build_month_summary(
        month=label,
        transactions=transactions,
        category_names=category_names,
        relation_effects=relation_effects,
        split_components=split_components,
    )


@router.get("/summary", response_model=CashflowSummaryResponse)
def get_summary(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_user_month_summary(db, user_id=user.id, month=month)


def _budget_response(
    budget: FinancialBudget,
    *,
    summary: dict,
    category_name: str | None,
) -> FinancialBudgetResponse:
    if budget.category_id is None:
        spent = Decimal(summary["expense"])
        scope = "total"
    else:
        spent = next(
            (
                Decimal(item["amount"])
                for item in summary["expense_categories"]
                if item["category_id"] == budget.category_id
            ),
            Decimal("0"),
        )
        scope = "category"
    amount = Decimal(budget.amount)
    remaining = amount - spent
    utilization = (spent / amount * Decimal("100")) if amount > 0 else Decimal("0")
    if spent > amount:
        execution_state = "over_budget"
    elif utilization >= Decimal("80"):
        execution_state = "near_limit"
    else:
        execution_state = "on_track"
    return FinancialBudgetResponse(
        id=budget.id,
        month=budget.month,
        scope=scope,
        category_id=budget.category_id,
        category_name=category_name,
        amount=amount,
        spent_amount=spent,
        remaining_amount=remaining,
        utilization_percent=float(utilization.quantize(Decimal("0.1"))),
        execution_state=execution_state,
        status=budget.status,
        version=budget.version,
        confirmed_at=budget.confirmed_at,
        reversed_at=budget.reversed_at,
    )


def _list_user_budget_responses(
    db: Session,
    *,
    user_id: int,
    normalized_month: str,
) -> list[FinancialBudgetResponse]:
    budgets = (
        db.query(FinancialBudget)
        .filter(
            FinancialBudget.user_id == user_id,
            FinancialBudget.month == normalized_month,
            FinancialBudget.status == "active",
        )
        .order_by(FinancialBudget.category_id.isnot(None), FinancialBudget.id.asc())
        .all()
    )
    category_ids = {item.category_id for item in budgets if item.category_id is not None}
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user_id),
        ).all()
    } if category_ids else {}
    summary = _build_user_month_summary(db, user_id=user_id, month=normalized_month)
    return [
        _budget_response(
            budget,
            summary=summary,
            category_name=category_names.get(budget.category_id),
        )
        for budget in budgets
    ]


def _change_percent(current: Decimal, previous: Decimal) -> float | None:
    if previous == 0:
        return None
    value = (current - previous) / abs(previous) * Decimal("100")
    return float(value.quantize(Decimal("0.1")))


def _build_year_comparison(
    db: Session,
    *,
    user_id: int,
    month_start: date,
    month_end: date,
) -> dict:
    current_start = date(month_start.year, 1, 1)
    previous_start = date(month_start.year - 1, 1, 1)
    previous_end = date(month_start.year - 1, month_end.month, 1)
    if month_end.month == 1:
        previous_end = date(month_start.year, 1, 1)
    current = _build_user_period_summary(
        db,
        user_id=user_id,
        start=current_start,
        end=month_end,
        label=f"{month_start.year}-YTD",
    )
    previous = _build_user_period_summary(
        db,
        user_id=user_id,
        start=previous_start,
        end=previous_end,
        label=f"{month_start.year - 1}-YTD",
    )
    current_income = Decimal(current["income"])
    current_expense = Decimal(current["expense"])
    current_net = Decimal(current["net"])
    previous_income = Decimal(previous["income"])
    previous_expense = Decimal(previous["expense"])
    previous_net = Decimal(previous["net"])
    return {
        "current_year": month_start.year,
        "previous_year": month_start.year - 1,
        "through_month": month_start.month,
        "current_income": current_income,
        "current_expense": current_expense,
        "current_net": current_net,
        "previous_income": previous_income,
        "previous_expense": previous_expense,
        "previous_net": previous_net,
        "income_change_percent": _change_percent(current_income, previous_income),
        "expense_change_percent": _change_percent(current_expense, previous_expense),
        "net_change_percent": _change_percent(current_net, previous_net),
        "net_change_amount": current_net - previous_net,
    }


def _build_settlement_outlook(
    db: Session,
    *,
    user_id: int,
    month_start: date,
    month_end: date,
) -> dict:
    today = date.today()
    as_of = min(today, month_end - timedelta(days=1))
    facts = db.query(EconomicFact).filter(
        EconomicFact.user_id == user_id,
        EconomicFact.status == "confirmed",
        EconomicFact.occurred_date <= as_of,
    ).all()
    fact_ids = [fact.id for fact in facts]
    relations = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user_id,
        EconomicFactRelation.status == "confirmed",
        EconomicFactRelation.relation_type.in_(["refunds", "reimburses"]),
        or_(
            EconomicFactRelation.source_fact_id.in_(fact_ids),
            EconomicFactRelation.target_fact_id.in_(fact_ids),
        ),
    ).all() if fact_ids else []
    settled_by_source: dict[int, Decimal] = {}
    reimbursed_by_target: dict[int, Decimal] = {}
    for relation in relations:
        amount = Decimal(relation.allocated_amount)
        settled_by_source[relation.source_fact_id] = (
            settled_by_source.get(relation.source_fact_id, Decimal("0.00")) + amount
        )
        if relation.relation_type == "reimburses":
            reimbursed_by_target[relation.target_fact_id] = (
                reimbursed_by_target.get(relation.target_fact_id, Decimal("0.00")) + amount
            )
    allocations = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id.in_(fact_ids),
        EconomicFactAllocation.status == "confirmed",
    ).order_by(EconomicFactAllocation.id.asc()).all() if fact_ids else []
    allocation_transaction_ids: dict[int, int] = {}
    for allocation in allocations:
        allocation_transaction_ids.setdefault(allocation.fact_id, allocation.transaction_id)

    items: list[dict] = []
    open_reimbursement_amount = Decimal("0.00")
    possible_refund_amount = Decimal("0.00")
    refund_words = ("退款", "退货", "冲正", "退回", "返还", "报销", "refund", "reimburse")
    for fact in facts:
        amount = Decimal(fact.amount)
        transaction_id = fact.primary_transaction_id or allocation_transaction_ids.get(fact.id)
        common = {
            "fact_id": fact.id,
            "source_transaction_id": transaction_id,
            "title": fact.title,
            "occurred_date": fact.occurred_date,
            "original_amount": amount,
            "age_days": max(0, (as_of - fact.occurred_date).days),
            "cross_month": fact.occurred_date < month_start,
        }
        if fact.nature == "reimbursable" or fact.fact_type == "reimbursable_expense":
            settled = min(amount, reimbursed_by_target.get(fact.id, Decimal("0.00")))
            remaining = max(Decimal("0.00"), amount - settled)
            if remaining > 0:
                open_reimbursement_amount += remaining
                items.append({
                    **common,
                    "kind": "reimbursement_due",
                    "settled_amount": settled,
                    "remaining_amount": remaining,
                })
            continue
        text = f"{fact.title} {fact.description or ''}".lower()
        is_possible_refund = fact.fact_type in {"refund", "reimbursement"} or (
            fact.fact_type == "income" and any(word in text for word in refund_words)
        )
        if is_possible_refund:
            settled = min(amount, settled_by_source.get(fact.id, Decimal("0.00")))
            remaining = max(Decimal("0.00"), amount - settled)
            if remaining > 0:
                possible_refund_amount += remaining
                items.append({
                    **common,
                    "kind": "possible_refund_inflow",
                    "settled_amount": settled,
                    "remaining_amount": remaining,
                })
    items.sort(key=lambda item: (-item["age_days"], item["fact_id"]))
    return {
        "as_of": as_of,
        "open_reimbursement_count": sum(item["kind"] == "reimbursement_due" for item in items),
        "open_reimbursement_amount": open_reimbursement_amount,
        "possible_refund_count": sum(item["kind"] == "possible_refund_inflow" for item in items),
        "possible_refund_amount": possible_refund_amount,
        "items": items[:20],
    }


def _build_month_end_forecast(
    *,
    month_start: date,
    month_end: date,
    summary: dict,
    budgets: list[FinancialBudgetResponse],
) -> dict:
    today = date.today()
    days_in_month = (month_end - month_start).days
    total_budget = next((Decimal(item.amount) for item in budgets if item.category_id is None), None)
    income = Decimal(summary["income"])
    expense = Decimal(summary["expense"])
    if month_end <= today:
        utilization = (
            float((expense / total_budget * Decimal("100")).quantize(Decimal("0.1")))
            if total_budget and total_budget > 0 else None
        )
        return {
            "state": "actual",
            "as_of": month_end - timedelta(days=1),
            "elapsed_days": days_in_month,
            "days_in_month": days_in_month,
            "projected_income": income,
            "projected_expense": expense,
            "projected_net": income - expense,
            "projected_budget_utilization_percent": utilization,
            "basis": "该月份已结束，展示已确认经济事实的实际结果，不再外推。",
        }
    if today < month_start:
        return {
            "state": "unavailable",
            "as_of": today,
            "elapsed_days": 0,
            "days_in_month": days_in_month,
            "basis": "该月份尚未开始，暂不生成预测。",
        }
    elapsed_days = (today - month_start).days + 1
    if elapsed_days < 3 or summary["confirmed_count"] == 0:
        return {
            "state": "unavailable",
            "as_of": today,
            "elapsed_days": elapsed_days,
            "days_in_month": days_in_month,
            "basis": "已确认数据不足 3 天或尚无正式流水，暂不外推。",
        }
    projected_expense = (expense / Decimal(elapsed_days) * Decimal(days_in_month)).quantize(Decimal("0.01"))
    utilization = (
        float((projected_expense / total_budget * Decimal("100")).quantize(Decimal("0.1")))
        if total_budget and total_budget > 0 else None
    )
    return {
        "state": "in_progress",
        "as_of": today,
        "elapsed_days": elapsed_days,
        "days_in_month": days_in_month,
        "projected_income": income,
        "projected_expense": projected_expense,
        "projected_net": income - projected_expense,
        "projected_budget_utilization_percent": utilization,
        "basis": "收入按当前已确认值保守保留；支出按本月至今的日均速度外推，未确认候选不参与。",
    }


@router.get("/budgets", response_model=list[FinancialBudgetResponse])
def list_financial_budgets(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, _, _ = parse_month(month)
    return _list_user_budget_responses(
        db,
        user_id=user.id,
        normalized_month=normalized_month,
    )


@router.post("/budgets", response_model=FinancialBudgetResponse)
def upsert_financial_budget(
    payload: FinancialBudgetUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, _, _ = parse_month(payload.month)
    lock_financial_ledger_owner(db, user_id=user.id)
    category = None
    if payload.category_id is not None:
        category = (
            db.query(FinancialCategory)
            .filter(
                FinancialCategory.id == payload.category_id,
                FinancialCategory.direction == "expense",
                FinancialCategory.is_active.is_(True),
                or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
            )
            .one_or_none()
        )
        if category is None:
            raise HTTPException(status_code=400, detail="支出预算分类不存在或已停用")
    scope_key = "total" if category is None else f"category:{category.id}"
    budget = (
        db.query(FinancialBudget)
        .filter(
            FinancialBudget.user_id == user.id,
            FinancialBudget.month == normalized_month,
            FinancialBudget.scope_key == scope_key,
        )
        .with_for_update()
        .one_or_none()
    )
    now = datetime.utcnow()
    if budget is None:
        if payload.expected_version is not None:
            raise HTTPException(status_code=409, detail="预算已变更，请刷新后重试")
        budget = FinancialBudget(
            user_id=user.id,
            month=normalized_month,
            scope_key=scope_key,
            category_id=category.id if category is not None else None,
            amount=payload.amount,
            status="active",
            version=1,
            confirmed_at=now,
        )
        db.add(budget)
    else:
        if budget.status == "active" and payload.expected_version is None:
            raise HTTPException(status_code=409, detail="预算已存在，请刷新后再修改")
        if payload.expected_version is not None and payload.expected_version != budget.version:
            raise HTTPException(status_code=409, detail="预算已被修改，请刷新后重试")
        budget.amount = payload.amount
        budget.status = "active"
        budget.version += 1
        budget.confirmed_at = now
        budget.reversed_at = None
    commit_financial_ledger(db)
    db.refresh(budget)
    summary = _build_user_month_summary(db, user_id=user.id, month=normalized_month)
    return _budget_response(
        budget,
        summary=summary,
        category_name=category.name if category is not None else None,
    )


@router.delete("/budgets/{budget_id}", response_model=FinancialBudgetResponse)
def reverse_financial_budget(
    budget_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_financial_ledger_owner(db, user_id=user.id)
    budget = (
        db.query(FinancialBudget)
        .filter(FinancialBudget.id == budget_id, FinancialBudget.user_id == user.id)
        .with_for_update()
        .one_or_none()
    )
    if budget is None:
        raise HTTPException(status_code=404, detail="预算不存在")
    category = None
    if budget.category_id is not None:
        category = db.query(FinancialCategory).filter(FinancialCategory.id == budget.category_id).one_or_none()
    if budget.status == "active":
        budget.status = "reversed"
        budget.reversed_at = datetime.utcnow()
        budget.version += 1
        commit_financial_ledger(db)
        db.refresh(budget)
    summary = _build_user_month_summary(db, user_id=user.id, month=budget.month)
    return _budget_response(
        budget,
        summary=summary,
        category_name=category.name if category is not None else None,
    )


@router.get("/monthly-report", response_model=CashflowMonthlyReportResponse)
def get_cashflow_monthly_report(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, month_start, month_end = parse_month(month)
    summary = _build_user_month_summary(db, user_id=user.id, month=normalized_month)
    budgets = _list_user_budget_responses(
        db,
        user_id=user.id,
        normalized_month=normalized_month,
    )
    budget_alerts = [item for item in budgets if item.execution_state != "on_track"]
    decision_counts = {
        decision_type: count
        for decision_type, count in db.query(
            FinancialRecurringDecision.decision_type,
            func.count(FinancialRecurringDecision.id),
        ).filter(
            FinancialRecurringDecision.user_id == user.id,
            FinancialRecurringDecision.status == "active",
            FinancialRecurringDecision.decision_type.in_(["subscription", "fixed_expense"]),
        ).group_by(FinancialRecurringDecision.decision_type).all()
    }
    income = Decimal(summary["income"])
    expense = Decimal(summary["expense"])
    net = Decimal(summary["net"])
    savings_rate = (net / income * Decimal("100")) if income > 0 else None
    if summary["state"] == "not_started":
        readiness = "empty"
    elif summary["pending_count"] > 0:
        readiness = "needs_confirmation"
    elif income <= 0 or expense <= 0:
        readiness = "partial"
    else:
        readiness = "ready"
    top_category = max(
        summary["expense_categories"],
        key=lambda item: Decimal(item["amount"]),
        default=None,
    )
    top_merchant = max(
        summary["expense_merchants"],
        key=lambda item: Decimal(item["amount"]),
        default=None,
    )
    highlights: list[dict] = []
    if readiness == "empty":
        highlights.append({
            "level": "attention",
            "title": "本月尚无可报告数据",
            "detail": "确认至少一笔收入或支出后，程序才会生成月度结论。",
        })
    if summary["pending_count"] > 0:
        highlights.append({
            "level": "attention",
            "title": f"还有 {summary['pending_count']} 笔正式流水待确认",
            "detail": "待确认项未进入本报告的金额、预算或排行。",
        })
    missing_sides = [label for amount, label in ((income, "收入"), (expense, "支出")) if amount <= 0]
    if readiness != "empty" and missing_sides:
        highlights.append({
            "level": "warning",
            "title": f"本月缺少已确认{' / '.join(missing_sides)}",
            "detail": "结余率和整体趋势只能按已有一侧数据解读。",
        })
    if budget_alerts:
        over_count = sum(item.execution_state == "over_budget" for item in budget_alerts)
        near_count = len(budget_alerts) - over_count
        parts = []
        if over_count:
            parts.append(f"{over_count} 项超支")
        if near_count:
            parts.append(f"{near_count} 项接近上限")
        highlights.append({
            "level": "warning" if over_count else "attention",
            "title": "预算执行需要关注",
            "detail": "、".join(parts) + "；只使用已确认且冲销后的支出计算。",
        })
    if income > 0:
        if net < 0:
            highlights.append({
                "level": "warning",
                "title": "本月已确认支出高于收入",
                "detail": f"当前净结余为 {net:.2f} 元，可结合分类支出查看主要变化。",
            })
        else:
            highlights.append({
                "level": "positive",
                "title": "本月保持正结余",
                "detail": f"已确认口径的结余率为 {savings_rate.quantize(Decimal('0.1'))}%。",
            })
    if top_category is not None:
        highlights.append({
            "level": "info",
            "title": f"最大支出分类：{top_category['category_name']}",
            "detail": f"共 {top_category['count']} 笔，金额 {Decimal(top_category['amount']):.2f} 元。",
        })
    recurring_total = decision_counts.get("subscription", 0) + decision_counts.get("fixed_expense", 0)
    if recurring_total:
        highlights.append({
            "level": "info",
            "title": f"已管理 {recurring_total} 项周期支出结论",
            "detail": f"其中订阅 {decision_counts.get('subscription', 0)} 项，固定支出 {decision_counts.get('fixed_expense', 0)} 项。",
        })
    year_comparison = _build_year_comparison(
        db,
        user_id=user.id,
        month_start=month_start,
        month_end=month_end,
    )
    settlement_outlook = _build_settlement_outlook(
        db,
        user_id=user.id,
        month_start=month_start,
        month_end=month_end,
    )
    forecast = _build_month_end_forecast(
        month_start=month_start,
        month_end=month_end,
        summary=summary,
        budgets=budgets,
    )
    return {
        "month": normalized_month,
        "ledger_revision": user.financial_ledger_revision,
        "readiness": readiness,
        "income": income,
        "expense": expense,
        "net": net,
        "savings_rate_percent": (
            float(savings_rate.quantize(Decimal("0.1"))) if savings_rate is not None else None
        ),
        "confirmed_count": summary["confirmed_count"],
        "pending_count": summary["pending_count"],
        "top_expense_category": top_category,
        "top_expense_merchant": top_merchant,
        "subscription_count": decision_counts.get("subscription", 0),
        "fixed_expense_count": decision_counts.get("fixed_expense", 0),
        "budget_alerts": budget_alerts,
        "highlights": highlights,
        "year_comparison": year_comparison,
        "settlement_outlook": settlement_outlook,
        "forecast": forecast,
        "generated_at": datetime.utcnow(),
    }


def _cashflow_report_html(report: CashflowMonthlyReportResponse) -> str:
    year = report.year_comparison
    settlement = report.settlement_outlook
    forecast = report.forecast
    settlement_rows = "".join(
        "<tr>"
        f"<td>{escape('待报销' if item.kind == 'reimbursement_due' else '待关联退款/报销')}</td>"
        f"<td>{escape(item.title)}</td><td>{item.occurred_date.isoformat()}</td>"
        f"<td>¥{item.original_amount:.2f}</td><td>¥{item.remaining_amount:.2f}</td>"
        f"<td>{item.age_days} 天</td></tr>"
        for item in (settlement.items if settlement else [])
    ) or '<tr><td colspan="6">暂无跨月待结事项</td></tr>'
    highlight_items = "".join(
        f"<li><strong>{escape(item.title)}</strong>：{escape(item.detail)}</li>"
        for item in report.highlights
    ) or "<li>暂无额外提示</li>"
    year_block = ""
    if year is not None:
        year_block = f"""
        <section><h2>{year.current_year} 年累计对比（截至 {year.through_month} 月）</h2>
        <div class="metrics"><div><span>本年收入</span><strong>¥{year.current_income:.2f}</strong></div>
        <div><span>本年支出</span><strong>¥{year.current_expense:.2f}</strong></div>
        <div><span>本年净结余</span><strong>¥{year.current_net:.2f}</strong></div>
        <div><span>{year.previous_year} 同期净结余</span><strong>¥{year.previous_net:.2f}</strong></div></div>
        <p class="note">净结余是已确认收支的累计差额，不等于银行卡余额。</p></section>"""
    forecast_block = ""
    if forecast is not None:
        forecast_value = (
            f"预计月末支出 ¥{forecast.projected_expense:.2f}，预计净结余 ¥{forecast.projected_net:.2f}"
            if forecast.projected_expense is not None and forecast.projected_net is not None
            else "当前数据不足，暂不生成金额预测"
        )
        forecast_block = f"<section><h2>月末预测</h2><p><strong>{escape(forecast_value)}</strong></p><p class=\"note\">{escape(forecast.basis)}</p></section>"
    settlement_block = ""
    if settlement is not None:
        settlement_block = f"""
        <section><h2>退款与报销待结</h2><p>待报销 {settlement.open_reimbursement_count} 项 / ¥{settlement.open_reimbursement_amount:.2f}；
        待关联退款或报销进账 {settlement.possible_refund_count} 项 / ¥{settlement.possible_refund_amount:.2f}</p>
        <table><thead><tr><th>类型</th><th>事项</th><th>发生日</th><th>原金额</th><th>未结金额</th><th>账龄</th></tr></thead>
        <tbody>{settlement_rows}</tbody></table></section>"""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>{escape(report.month)} 收支报告</title>
    <style>body{{font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1f2933;max-width:960px;margin:0 auto;padding:40px}}
    h1{{margin-bottom:4px}}h2{{margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:8px}}.meta,.note{{color:#667085}}
    .metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.metrics div{{background:#f6f7f5;border-radius:12px;padding:16px}}
    .metrics span{{display:block;color:#667085;font-size:12px}}.metrics strong{{display:block;margin-top:6px;font-size:20px}}
    table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left}}ul{{padding-left:20px}}
    @media(max-width:680px){{body{{padding:20px}}.metrics{{grid-template-columns:repeat(2,1fr)}}table{{font-size:12px}}}}</style></head><body>
    <h1>{escape(report.month)} 收支守护报告</h1><p class="meta">可信账本 r{report.ledger_revision} · 生成于 {report.generated_at.isoformat()} UTC</p>
    <section><h2>本月已确认结果</h2><div class="metrics"><div><span>收入</span><strong>¥{report.income:.2f}</strong></div>
    <div><span>支出</span><strong>¥{report.expense:.2f}</strong></div><div><span>净结余</span><strong>¥{report.net:.2f}</strong></div>
    <div><span>确认流水</span><strong>{report.confirmed_count} 笔</strong></div></div>
    <p class="note">只使用用户已确认的经济事实；未确认 OCR、文件及 AI 候选均未计入。</p></section>
    {year_block}{forecast_block}{settlement_block}<section><h2>程序提示</h2><ul>{highlight_items}</ul></section>
    <footer><p class="note">本报告由确定性账本规则计算，AI 可解释但不改写金额。退款、报销与转账按已确认关系重算。</p></footer></body></html>"""


@router.get("/monthly-report/export")
def export_cashflow_monthly_report(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = CashflowMonthlyReportResponse.model_validate(
        get_cashflow_monthly_report(month=month, user=user, db=db)
    )
    content = _cashflow_report_html(report).encode("utf-8")
    filename = f"cashflow-report-{report.month}-r{report.ledger_revision}.html"
    return StreamingResponse(
        BytesIO(content),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _month_close_snapshot(report: dict) -> tuple[dict, str]:
    snapshot = CashflowMonthlyReportResponse.model_validate(report).model_dump(mode="json")
    fingerprint_payload = {
        key: value
        for key, value in snapshot.items()
        if key not in {"generated_at", "ledger_revision", "forecast"}
    }
    settlement = fingerprint_payload.get("settlement_outlook")
    if settlement is not None:
        fingerprint_payload["settlement_outlook"] = {
            key: value
            for key, value in settlement.items()
            if key != "as_of"
        }
        fingerprint_payload["settlement_outlook"]["items"] = [
            {key: value for key, value in item.items() if key != "age_days"}
            for item in settlement.get("items", [])
        ]
    fingerprint = sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return snapshot, fingerprint


def _pending_month_candidate_count(
    db: Session,
    *,
    user_id: int,
    month: str,
) -> int:
    _, start, end = parse_month(month)
    return int(
        db.query(func.count(FinancialTransactionCandidate.id)).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.transaction_date >= start,
            FinancialTransactionCandidate.transaction_date < end,
            FinancialTransactionCandidate.status.in_([
                "ready",
                "needs_review",
                "possible_duplicate",
                "invalid",
            ]),
        ).scalar()
        or 0
    )


def _month_close_response(
    month_close: FinancialMonthClose,
    *,
    current_fingerprint: str,
    current_close_id: int | None,
) -> FinancialMonthCloseResponse:
    return FinancialMonthCloseResponse(
        id=month_close.id,
        month=month_close.month,
        version=month_close.version,
        ledger_revision=month_close.ledger_revision,
        report_snapshot=month_close.report_snapshot,
        pending_candidate_count=month_close.pending_candidate_count,
        status=month_close.status,
        is_current=month_close.id == current_close_id,
        is_stale=month_close.report_fingerprint != current_fingerprint,
        closed_at=month_close.closed_at,
        reopened_at=month_close.reopened_at,
    )


@router.get("/monthly-closes", response_model=list[FinancialMonthCloseResponse])
def list_financial_month_closes(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, _, _ = parse_month(month)
    records = (
        db.query(FinancialMonthClose)
        .filter(
            FinancialMonthClose.user_id == user.id,
            FinancialMonthClose.month == normalized_month,
        )
        .order_by(FinancialMonthClose.version.desc())
        .all()
    )
    current_report = get_cashflow_monthly_report(
        month=normalized_month,
        user=user,
        db=db,
    )
    _, current_fingerprint = _month_close_snapshot(current_report)
    current_close_id = records[0].id if records and records[0].status == "closed" else None
    return [
        _month_close_response(
            record,
            current_fingerprint=current_fingerprint,
            current_close_id=current_close_id,
        )
        for record in records
    ]


@router.post(
    "/monthly-closes",
    response_model=FinancialMonthCloseResponse,
    status_code=status.HTTP_201_CREATED,
)
def close_financial_month(
    payload: FinancialMonthCloseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, _, _ = parse_month(payload.month)
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    if owner.financial_ledger_revision != payload.expected_ledger_revision:
        raise HTTPException(status_code=409, detail="账本已变更，请刷新月报后再结账")
    latest = (
        db.query(FinancialMonthClose)
        .filter(
            FinancialMonthClose.user_id == user.id,
            FinancialMonthClose.month == normalized_month,
        )
        .order_by(FinancialMonthClose.version.desc())
        .with_for_update()
        .first()
    )
    if latest is not None and latest.status == "closed":
        raise HTTPException(status_code=409, detail="该月已结账；如需更新，请先重开月结")
    report = get_cashflow_monthly_report(month=normalized_month, user=owner, db=db)
    if report["readiness"] == "empty":
        raise HTTPException(status_code=409, detail="本月尚无已确认收支，不能结账")
    if report["pending_count"] > 0:
        raise HTTPException(
            status_code=409,
            detail=f"本月还有 {report['pending_count']} 笔正式流水待确认，处理后才能结账",
        )
    snapshot, fingerprint = _month_close_snapshot(report)
    month_close = FinancialMonthClose(
        user_id=user.id,
        month=normalized_month,
        version=(latest.version + 1) if latest is not None else 1,
        ledger_revision=owner.financial_ledger_revision,
        report_fingerprint=fingerprint,
        report_snapshot=snapshot,
        pending_candidate_count=_pending_month_candidate_count(
            db,
            user_id=user.id,
            month=normalized_month,
        ),
        status="closed",
        closed_at=datetime.utcnow(),
    )
    db.add(month_close)
    commit_financial_ledger(db)
    db.refresh(month_close)
    return _month_close_response(
        month_close,
        current_fingerprint=fingerprint,
        current_close_id=month_close.id,
    )


@router.post(
    "/monthly-closes/{month_close_id}/reopen",
    response_model=FinancialMonthCloseResponse,
)
def reopen_financial_month(
    month_close_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    requested = (
        db.query(FinancialMonthClose)
        .filter(
            FinancialMonthClose.id == month_close_id,
            FinancialMonthClose.user_id == user.id,
        )
        .with_for_update()
        .one_or_none()
    )
    if requested is None:
        raise HTTPException(status_code=404, detail="当前月结记录不存在")
    latest = (
        db.query(FinancialMonthClose)
        .filter(
            FinancialMonthClose.user_id == user.id,
            FinancialMonthClose.month == requested.month,
        )
        .order_by(FinancialMonthClose.version.desc())
        .with_for_update()
        .first()
    )
    if latest is None or latest.id != requested.id:
        raise HTTPException(status_code=404, detail="当前月结记录不存在")
    if latest.status == "closed":
        latest.status = "reopened"
        latest.reopened_at = datetime.utcnow()
        commit_financial_ledger(db)
        db.refresh(latest)
    current_report = get_cashflow_monthly_report(month=latest.month, user=owner, db=db)
    _, current_fingerprint = _month_close_snapshot(current_report)
    return _month_close_response(
        latest,
        current_fingerprint=current_fingerprint,
        current_close_id=None,
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
    split_components, split_category_ids = _split_components_for_transactions(
        db,
        user_id=user.id,
        transaction_ids=[item.id for item in transactions if getattr(item, "id", None) is not None],
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_ids.update(split_category_ids)
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
                split_components=split_components,
            )
        )
    insights = build_recurring_expense_insights(summaries)
    fingerprints = [item["merchant_fingerprint"] for item in insights]
    decisions = {
        item.merchant_fingerprint: item
        for item in db.query(FinancialRecurringDecision).filter(
            FinancialRecurringDecision.user_id == user.id,
            FinancialRecurringDecision.status == "active",
            FinancialRecurringDecision.merchant_fingerprint.in_(fingerprints),
        ).all()
    } if fingerprints else {}
    for insight in insights:
        insight["user_decision"] = decisions.get(insight["merchant_fingerprint"])
    return {
        "start_month": start_month,
        "end_month": normalized_end,
        "months_analyzed": months,
        "items": insights,
    }


@router.post("/recurring-decisions", response_model=RecurringExpenseDecisionResponse)
def confirm_recurring_expense_decision(
    payload: RecurringExpenseDecisionUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_financial_ledger_owner(db, user_id=user.id)
    fingerprint = recurring_merchant_fingerprint(payload.merchant_name)
    decision = (
        db.query(FinancialRecurringDecision)
        .filter(
            FinancialRecurringDecision.user_id == user.id,
            FinancialRecurringDecision.merchant_fingerprint == fingerprint,
        )
        .with_for_update()
        .one_or_none()
    )
    now = datetime.utcnow()
    if decision is None:
        decision = FinancialRecurringDecision(
            user_id=user.id,
            merchant_fingerprint=fingerprint,
            merchant_name=payload.merchant_name,
            decision_type=payload.decision_type,
            status="active",
            note=payload.note,
            evidence=payload.evidence,
            version=1,
            confirmed_at=now,
        )
        db.add(decision)
    else:
        decision.merchant_name = payload.merchant_name
        decision.decision_type = payload.decision_type
        decision.status = "active"
        decision.note = payload.note
        decision.evidence = payload.evidence
        decision.version += 1
        decision.confirmed_at = now
        decision.reversed_at = None
    commit_financial_ledger(db)
    db.refresh(decision)
    return decision


@router.get("/recurring-decisions", response_model=list[RecurringExpenseDecisionResponse])
def list_recurring_expense_decisions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(FinancialRecurringDecision)
        .filter(
            FinancialRecurringDecision.user_id == user.id,
            FinancialRecurringDecision.status == "active",
        )
        .order_by(
            FinancialRecurringDecision.decision_type.asc(),
            FinancialRecurringDecision.merchant_name.asc(),
            FinancialRecurringDecision.id.asc(),
        )
        .all()
    )


@router.delete("/recurring-decisions/{decision_id}", response_model=RecurringExpenseDecisionResponse)
def reverse_recurring_expense_decision(
    decision_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lock_financial_ledger_owner(db, user_id=user.id)
    decision = (
        db.query(FinancialRecurringDecision)
        .filter(
            FinancialRecurringDecision.id == decision_id,
            FinancialRecurringDecision.user_id == user.id,
        )
        .with_for_update()
        .one_or_none()
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="周期性支出判断不存在")
    if decision.status == "active":
        decision.status = "reversed"
        decision.reversed_at = datetime.utcnow()
        decision.version += 1
        commit_financial_ledger(db)
        db.refresh(decision)
    return decision


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


def _cashflow_conversation_summary(
    conversation: CashflowConversation,
    *,
    turn_count: int,
    latest_ledger_revision: int | None,
) -> CashflowConversationSummaryResponse:
    return CashflowConversationSummaryResponse(
        id=conversation.id,
        month=conversation.month,
        title=conversation.title,
        status=conversation.status,
        turn_count=turn_count,
        latest_ledger_revision=latest_ledger_revision,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _cashflow_conversation_turn(turn: CashflowConversationTurn) -> CashflowConversationTurnResponse:
    return CashflowConversationTurnResponse(
        question=turn.question,
        response=CashflowAskResponse(
            conversation_id=turn.conversation_id,
            turn_id=turn.id,
            answer=turn.answer,
            mode=turn.mode,
            ledger_revision=turn.ledger_revision,
            data_start=turn.data_start,
            data_end=turn.data_end,
            transaction_count=turn.transaction_count,
            references=turn.references or [],
            payslip_references=turn.payslip_references or [],
            knowledge_references=turn.knowledge_references or [],
            follow_up_questions=turn.follow_up_questions or [],
            generated_at=turn.generated_at,
        ),
    )


@router.get(
    "/conversations",
    response_model=list[CashflowConversationSummaryResponse],
)
def list_cashflow_conversations(
    month: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, _, _ = parse_month(month)
    conversations = (
        db.query(CashflowConversation)
        .filter(
            CashflowConversation.user_id == user.id,
            CashflowConversation.month == normalized_month,
            CashflowConversation.status == "active",
        )
        .order_by(CashflowConversation.updated_at.desc(), CashflowConversation.id.desc())
        .limit(limit)
        .all()
    )
    conversation_ids = [conversation.id for conversation in conversations]
    aggregates = {
        conversation_id: (int(turn_count), latest_revision)
        for conversation_id, turn_count, latest_revision in db.query(
            CashflowConversationTurn.conversation_id,
            func.count(CashflowConversationTurn.id),
            func.max(CashflowConversationTurn.ledger_revision),
        ).filter(
            CashflowConversationTurn.user_id == user.id,
            CashflowConversationTurn.conversation_id.in_(conversation_ids),
        ).group_by(CashflowConversationTurn.conversation_id).all()
    } if conversation_ids else {}
    return [
        _cashflow_conversation_summary(
            conversation,
            turn_count=aggregates.get(conversation.id, (0, None))[0],
            latest_ledger_revision=aggregates.get(conversation.id, (0, None))[1],
        )
        for conversation in conversations
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=CashflowConversationDetailResponse,
)
def get_cashflow_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = db.query(CashflowConversation).filter(
        CashflowConversation.id == conversation_id,
        CashflowConversation.user_id == user.id,
        CashflowConversation.status == "active",
    ).one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="收支问询会话不存在")
    turns = db.query(CashflowConversationTurn).filter(
        CashflowConversationTurn.conversation_id == conversation.id,
        CashflowConversationTurn.user_id == user.id,
    ).order_by(CashflowConversationTurn.id.asc()).all()
    latest_revision = turns[-1].ledger_revision if turns else None
    summary = _cashflow_conversation_summary(
        conversation,
        turn_count=len(turns),
        latest_ledger_revision=latest_revision,
    )
    return CashflowConversationDetailResponse(
        **summary.model_dump(),
        turns=[_cashflow_conversation_turn(turn) for turn in turns],
    )


@router.post("/ask", response_model=CashflowAskResponse)
def ask_confirmed_cashflow(
    data: CashflowAskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_month, selected_start, selected_end = parse_month(data.month)
    conversation_id = data.conversation_id
    if conversation_id is not None:
        conversation = db.query(CashflowConversation).filter(
            CashflowConversation.id == conversation_id,
            CashflowConversation.user_id == user.id,
            CashflowConversation.status == "active",
        ).one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="收支问询会话不存在")
        if conversation.month != normalized_month:
            raise HTTPException(status_code=409, detail="会话月份与当前报告月份不一致")
        stored_turns = (
            db.query(CashflowConversationTurn)
            .filter(
                CashflowConversationTurn.conversation_id == conversation.id,
                CashflowConversationTurn.user_id == user.id,
            )
            .order_by(CashflowConversationTurn.id.desc())
            .limit(4)
            .all()
        )
        conversation_history = [
            message
            for turn in reversed(stored_turns)
            for message in (
                {"role": "user", "content": turn.question},
                {"role": "assistant", "content": turn.answer},
            )
        ]
    else:
        conversation_history = [item.model_dump() for item in data.history]
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
    split_components, split_category_ids = _split_components_for_transactions(
        db,
        user_id=user.id,
        transaction_ids=[item.id for item in transactions if getattr(item, "id", None) is not None],
    )
    category_ids = {item.category_id for item in transactions if item.category_id is not None}
    category_ids.update(relation_category_ids)
    category_ids.update(split_category_ids)
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

    analysis_transactions = []
    for item in transactions:
        effect = relation_effects.get(item.id, {})
        if effect.get("count_remove"):
            continue
        removal_key = {
            "income": "income_remove",
            "expense": "expense_remove",
            "transfer": "transfer_remove",
        }.get(item.direction)
        removed = Decimal(effect.get(removal_key) or 0) if removal_key else Decimal("0.00")
        effective_amount = max(Decimal("0.00"), Decimal(item.amount) - removed)
        if effective_amount == Decimal(item.amount):
            analysis_transactions.append(item)
            continue
        analysis_transactions.append(SimpleNamespace(
            id=item.id,
            transaction_date=item.transaction_date,
            direction=item.direction,
            amount=effective_amount,
            category_id=item.category_id,
            merchant=item.merchant,
            description=item.description,
            nature=item.nature,
        ))
    analysis_transactions = expand_transactions_with_split_components(
        analysis_transactions,
        split_components,
    )

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
                split_components=split_components,
            )
        )

    facts = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.primary_transaction_id.in_([item.id for item in analysis_transactions]),
        EconomicFact.status == "confirmed",
    ).all() if analysis_transactions else []
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
        transactions=analysis_transactions,
        category_names=category_names,
        fact_types=fact_types,
        monthly_summaries=monthly_summaries,
        relations=relation_context,
        payslip_guardians=payslip_guardians,
    )
    knowledge_context, knowledge_by_slug = recommend_cashflow_knowledge(
        db,
        question=data.question,
        has_payslip=bool(payslip_guardians),
    )
    context["relevant_knowledge"] = knowledge_context
    user_id = user.id
    expected_data_epoch = user.business_data_epoch
    expected_ledger_revision = user.financial_ledger_revision
    db.rollback()
    answer = answer_cashflow_question(
        question=data.question,
        history=conversation_history,
        context=context,
        reference_by_id=reference_by_id,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        knowledge_by_slug=knowledge_by_slug,
    )
    db.expire_all()
    current_owner = db.get(User, user_id)
    if current_owner is None or current_owner.business_data_epoch != expected_data_epoch:
        raise HTTPException(status_code=409, detail="账户数据已清空，请重新提问")
    if current_owner.financial_ledger_revision != expected_ledger_revision:
        raise HTTPException(status_code=409, detail="问询期间账本已更新，请基于最新数据重新提问")
    generated_at = datetime.utcnow()
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if owner.business_data_epoch != expected_data_epoch:
        raise HTTPException(status_code=409, detail="账户数据已清空，请重新提问")
    if owner.financial_ledger_revision != expected_ledger_revision:
        raise HTTPException(status_code=409, detail="问询期间账本已更新，请基于最新数据重新提问")
    if conversation_id is None:
        conversation = CashflowConversation(
            user_id=user_id,
            month=normalized_month,
            title=data.question[:120],
            status="active",
        )
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
    else:
        conversation = db.query(CashflowConversation).filter(
            CashflowConversation.id == conversation_id,
            CashflowConversation.user_id == user_id,
            CashflowConversation.status == "active",
        ).with_for_update().one_or_none()
        if conversation is None:
            raise HTTPException(status_code=409, detail="收支问询会话已变更，请刷新后重试")
    conversation.updated_at = generated_at
    turn = CashflowConversationTurn(
        user_id=user_id,
        conversation_id=conversation_id,
        question=data.question,
        answer=answer["answer"],
        mode=answer["mode"],
        ledger_revision=expected_ledger_revision,
        data_start=data_start,
        data_end=selected_end - timedelta(days=1),
        transaction_count=len(analysis_transactions),
        references=jsonable_encoder(answer.get("references") or []),
        payslip_references=jsonable_encoder(answer.get("payslip_references") or []),
        knowledge_references=jsonable_encoder(answer.get("knowledge_references") or []),
        follow_up_questions=list(answer.get("follow_up_questions") or []),
        generated_at=generated_at,
    )
    db.add(turn)
    db.flush()
    turn_id = turn.id
    commit_financial_ledger(db)
    return CashflowAskResponse(
        **answer,
        conversation_id=conversation_id,
        turn_id=turn_id,
        ledger_revision=expected_ledger_revision,
        data_start=data_start,
        data_end=selected_end - timedelta(days=1),
        transaction_count=len(analysis_transactions),
        generated_at=generated_at,
    )


@router.get("/export")
def export_confirmed_cashflow(
    export_format: Literal["bundle", "xlsx"] = Query(default="bundle", alias="format"),
    transaction_id: Annotated[Optional[int], Query(gt=0)] = None,
    month: Optional[str] = None,
    direction: Optional[Literal["income", "expense", "transfer"]] = None,
    category_id: Optional[int] = None,
    nature: Optional[Literal["fixed", "flexible", "one_off", "reimbursable", "other"]] = None,
    keyword: Annotated[Optional[str], Query(max_length=100)] = None,
    merchant_name: Annotated[Optional[str], Query(max_length=200)] = None,
    source_type: Annotated[Optional[str], Query(max_length=50)] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    export_filters = {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in {
            "transaction_id": transaction_id,
            "month": month,
            "direction": direction,
            "category_id": category_id,
            "nature": nature,
            "keyword": keyword.strip() if keyword and keyword.strip() else None,
            "merchant_name": merchant_name.strip() if merchant_name and merchant_name.strip() else None,
            "source_type": source_type.strip() if source_type and source_type.strip() else None,
            "start_date": start_date,
            "end_date": end_date,
        }.items()
        if value is not None
    }
    filters_applied = bool(export_filters)
    transactions = (
        _filtered_transaction_query(
            db,
            user=user,
            transaction_id=transaction_id,
            month=month,
            direction=direction,
            transaction_status="confirmed",
            category_id=category_id,
            nature=nature,
            keyword=keyword,
            merchant_name=merchant_name,
            source_type=source_type,
            start_date=start_date,
            end_date=end_date,
        )
        .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        .all()
    )
    transaction_ids = [item.id for item in transactions]
    fact_query = db.query(EconomicFact).filter(
        EconomicFact.user_id == user.id,
        EconomicFact.status == "confirmed",
    )
    if filters_applied:
        allocated_fact_ids = [
            item.fact_id
            for item in db.query(EconomicFactAllocation.fact_id).filter(
                EconomicFactAllocation.transaction_id.in_(transaction_ids),
                EconomicFactAllocation.status == "confirmed",
            ).distinct().all()
        ] if transaction_ids else []
        if transaction_ids or allocated_fact_ids:
            fact_query = fact_query.filter(or_(
                EconomicFact.primary_transaction_id.in_(transaction_ids),
                EconomicFact.id.in_(allocated_fact_ids),
            ))
        else:
            fact_query = fact_query.filter(EconomicFact.id == -1)
    facts = fact_query.order_by(EconomicFact.occurred_date.asc(), EconomicFact.id.asc()).all()
    category_ids = {
        item.category_id
        for item in [*transactions, *facts]
        if item.category_id is not None
    }
    category_names = {
        item.id: item.name
        for item in db.query(FinancialCategory).filter(
            FinancialCategory.id.in_(category_ids),
            or_(FinancialCategory.user_id.is_(None), FinancialCategory.user_id == user.id),
        ).all()
    } if category_ids else {}
    fact_ids = [item.id for item in facts]
    allocations = db.query(EconomicFactAllocation).filter(
        EconomicFactAllocation.fact_id.in_(fact_ids),
        EconomicFactAllocation.status == "confirmed",
    ).all() if fact_ids else []
    relation_query = db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user.id,
        EconomicFactRelation.status == "confirmed",
    )
    if filters_applied:
        relation_query = relation_query.filter(
            EconomicFactRelation.source_fact_id.in_(fact_ids),
            EconomicFactRelation.target_fact_id.in_(fact_ids),
        ) if fact_ids else relation_query.filter(EconomicFactRelation.id == -1)
    relations = relation_query.order_by(
        EconomicFactRelation.confirmed_at.asc(),
        EconomicFactRelation.id.asc(),
    ).all()
    payslip_query = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(CareerCase.user_id == user.id, Payslip.record_status != "deleted")
    )
    if filters_applied:
        linked_payslip_ids = [
            item.payslip_id
            for item in db.query(PayslipArrivalLink.payslip_id).filter(
                PayslipArrivalLink.status == "confirmed",
                or_(
                    PayslipArrivalLink.transaction_id.in_(transaction_ids),
                    PayslipArrivalLink.economic_fact_id.in_(fact_ids),
                ),
            ).distinct().all()
        ] if transaction_ids or fact_ids else []
        fine_grained_filters = any((category_id, nature, keyword, merchant_name, source_type, start_date, end_date))
        payslip_conditions = []
        if linked_payslip_ids:
            payslip_conditions.append(Payslip.id.in_(linked_payslip_ids))
        if not fine_grained_filters and direction in {None, "income"}:
            if month:
                payslip_conditions.append(Payslip.pay_month == month)
            elif direction == "income":
                payslip_conditions.append(Payslip.id > 0)
        if payslip_conditions:
            payslip_query = payslip_query.filter(or_(*payslip_conditions))
        else:
            payslip_query = payslip_query.filter(Payslip.id == -1)
    payslips = payslip_query.order_by(Payslip.pay_month.asc(), Payslip.id.asc()).all()
    payslip_ids = [item.id for item in payslips]
    material_links = db.query(PayslipMaterialLink).filter(
        PayslipMaterialLink.payslip_id.in_(payslip_ids)
    ).all() if payslip_ids else []
    arrival_links = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id.in_(payslip_ids),
        PayslipArrivalLink.status == "confirmed",
    ).all() if payslip_ids else []
    generated_at = datetime.utcnow()
    export_kwargs = dict(
        generated_at=generated_at,
        business_data_epoch=user.business_data_epoch,
        ledger_revision=user.financial_ledger_revision,
        transactions=transactions,
        category_names=category_names,
        facts=facts,
        allocations=allocations,
        relations=relations,
        payslips=payslips,
        material_links=material_links,
        arrival_links=arrival_links,
        scope_description=(
            "当前账户中符合导出筛选条件的已确认、未删除、未撤销结构化数据"
            if filters_applied
            else "当前账户中已确认、未删除、未撤销的结构化数据"
        ),
        filters=export_filters,
    )
    if export_format == "xlsx":
        payload = build_cashflow_export_workbook(**export_kwargs)
        extension = "xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        payload = build_cashflow_export_bundle(**export_kwargs)
        extension = "zip"
        media_type = "application/zip"
    scope_slug = f"-{month}" if month else ""
    filename = f"cashflow-guardian{scope_slug}-{generated_at.strftime('%Y%m%d-%H%M%S')}.{extension}"
    return StreamingResponse(
        BytesIO(payload),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
