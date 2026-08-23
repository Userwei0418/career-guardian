"""统一经济事实与正式流水证据的最小同步层。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
import json
import re

from sqlalchemy.orm import Session

from app.models.cashflow import (
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRelation,
    FinancialTransaction,
)
from app.services.cashflow_privacy import redact_cashflow_text


def transaction_fact_type(transaction: FinancialTransaction) -> str:
    if transaction.direction == "transfer":
        return "transfer"
    if transaction.direction == "expense" and transaction.nature == "reimbursable":
        return "reimbursable_expense"
    return transaction.direction


def transaction_fact_title(transaction: FinancialTransaction) -> str:
    return (
        (transaction.merchant or "").strip()
        or (transaction.description or "").strip()
        or {"income": "收入", "expense": "支出", "transfer": "转账"}.get(transaction.direction, "经济事实")
    )[:200]


def sync_transaction_fact(
    db: Session,
    *,
    transaction: FinancialTransaction,
    user_id: int,
    assume_missing: bool = False,
) -> EconomicFact | None:
    """已确认流水必须有事实；排除或删除流水时反转对应事实影响。"""
    if transaction.id is None:
        db.flush()
    fact = None
    if not assume_missing:
        fact = (
            db.query(EconomicFact)
            .filter(
                EconomicFact.primary_transaction_id == transaction.id,
                EconomicFact.user_id == user_id,
            )
            .first()
        )
    is_active = transaction.status == "confirmed" and transaction.deleted_at is None
    now = datetime.utcnow()
    if not is_active:
        if fact is not None:
            fact.status = "reversed"
            for allocation in db.query(EconomicFactAllocation).filter(
                EconomicFactAllocation.fact_id == fact.id,
                EconomicFactAllocation.transaction_id == transaction.id,
                EconomicFactAllocation.status == "confirmed",
            ).all():
                allocation.status = "reversed"
                allocation.reversed_at = now
        return fact

    if fact is None:
        fact = EconomicFact(
            user_id=user_id,
            primary_transaction_id=transaction.id,
            fact_type=transaction_fact_type(transaction),
            title=transaction_fact_title(transaction),
            occurred_date=transaction.transaction_date,
            amount=transaction.amount,
            currency=transaction.currency,
            category_id=transaction.category_id,
            nature=transaction.nature,
            description=transaction.description,
            status="confirmed",
        )
        db.add(fact)
        db.flush()
    else:
        fact.fact_type = transaction_fact_type(transaction)
        fact.title = transaction_fact_title(transaction)
        fact.occurred_date = transaction.transaction_date
        fact.amount = transaction.amount
        fact.currency = transaction.currency
        fact.category_id = transaction.category_id
        fact.nature = transaction.nature
        fact.description = transaction.description
        fact.status = "confirmed"

    allocation = None
    if not assume_missing:
        allocation = (
            db.query(EconomicFactAllocation)
            .filter(
                EconomicFactAllocation.fact_id == fact.id,
                EconomicFactAllocation.transaction_id == transaction.id,
            )
            .first()
        )
    if allocation is None:
        allocation = EconomicFactAllocation(
            fact_id=fact.id,
            transaction_id=transaction.id,
            role="primary",
            allocated_amount=transaction.amount,
            status="confirmed",
            reasons=["用户已确认的正式流水创建基础经济事实"],
            confirmed_by_user_id=user_id,
            confirmed_at=transaction.confirmed_at or now,
        )
        db.add(allocation)
    else:
        allocation.role = "primary"
        allocation.allocated_amount = Decimal(transaction.amount)
        allocation.status = "confirmed"
        allocation.reversed_at = None
    return fact


def get_transaction_fact(
    db: Session,
    *,
    transaction_id: int,
    user_id: int,
) -> EconomicFact | None:
    primary_fact = (
        db.query(EconomicFact)
        .filter(
            EconomicFact.primary_transaction_id == transaction_id,
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
        )
        .first()
    )
    if primary_fact is not None:
        return primary_fact
    return (
        db.query(EconomicFact)
        .join(EconomicFactAllocation, EconomicFactAllocation.fact_id == EconomicFact.id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id == transaction_id,
            EconomicFactAllocation.status == "confirmed",
        )
        .first()
    )


def get_transaction_facts(
    db: Session,
    *,
    transaction_id: int,
    user_id: int,
) -> list[EconomicFact]:
    """Return every active fact this transaction can participate in.

    A normal transaction owns one ``primary`` fact.  A decomposed transaction
    owns two or more ``split_component`` facts whose ``primary_transaction_id``
    is deliberately null.  A fully merged observation may only remain as
    corroborating evidence for another fact.  Relation matching must prefer
    cashflow-bearing primary/component facts and only fall back to a
    corroborated fact when there is no independent remainder.
    """
    return get_transactions_facts(
        db,
        transaction_ids=[transaction_id],
        user_id=user_id,
    ).get(transaction_id, [])


def get_transactions_facts(
    db: Session,
    *,
    transaction_ids: list[int],
    user_id: int,
) -> dict[int, list[EconomicFact]]:
    """Batch form of :func:`get_transaction_facts` for matching workspaces."""
    if not transaction_ids:
        return {}
    rows = (
        db.query(EconomicFactAllocation, EconomicFact)
        .join(EconomicFact, EconomicFact.id == EconomicFactAllocation.fact_id)
        .filter(
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
            EconomicFactAllocation.transaction_id.in_(transaction_ids),
            EconomicFactAllocation.status == "confirmed",
        )
        .all()
    )
    role_order = {"primary": 0, "split_component": 1, "corroborating": 2}
    grouped_rows: dict[int, list[tuple[EconomicFactAllocation, EconomicFact]]] = {}
    for allocation, fact in rows:
        grouped_rows.setdefault(allocation.transaction_id, []).append((allocation, fact))
    result: dict[int, list[EconomicFact]] = {}
    for transaction_id, transaction_rows in grouped_rows.items():
        cashflow_rows = [
            (allocation, fact)
            for allocation, fact in transaction_rows
            if allocation.role in {"primary", "split_component"}
        ]
        selected = cashflow_rows or [
            (allocation, fact)
            for allocation, fact in transaction_rows
            if allocation.role == "corroborating"
        ]
        selected.sort(key=lambda row: (role_order.get(row[0].role, 9), row[1].id))
        facts: list[EconomicFact] = []
        seen: set[int] = set()
        for _, fact in selected:
            if fact.id in seen:
                continue
            seen.add(fact.id)
            facts.append(fact)
        result[transaction_id] = facts
    return result


def get_fact_source_transaction(
    db: Session,
    *,
    fact: EconomicFact,
    user_id: int,
) -> FinancialTransaction | None:
    """Resolve the confirmed source observation behind a fact.

    Split components do not have ``primary_transaction_id``.  Their source is
    carried by the confirmed ``split_component`` allocation instead.
    """
    if fact.primary_transaction_id is not None:
        return (
            db.query(FinancialTransaction)
            .filter(
                FinancialTransaction.id == fact.primary_transaction_id,
                FinancialTransaction.user_id == user_id,
                FinancialTransaction.deleted_at.is_(None),
            )
            .first()
        )
    return (
        db.query(FinancialTransaction)
        .join(
            EconomicFactAllocation,
            EconomicFactAllocation.transaction_id == FinancialTransaction.id,
        )
        .filter(
            EconomicFactAllocation.fact_id == fact.id,
            EconomicFactAllocation.status == "confirmed",
            EconomicFactAllocation.role == "split_component",
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
        )
        .order_by(EconomicFactAllocation.id.asc())
        .first()
    )


def get_fact_members(
    db: Session,
    *,
    fact: EconomicFact,
    user_id: int,
) -> list[dict]:
    rows = (
        db.query(EconomicFactAllocation, FinancialTransaction)
        .join(
            FinancialTransaction,
            FinancialTransaction.id == EconomicFactAllocation.transaction_id,
        )
        .filter(
            EconomicFactAllocation.fact_id == fact.id,
            EconomicFactAllocation.status == "confirmed",
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
        )
        .order_by(
            (EconomicFactAllocation.role == "primary").desc(),
            FinancialTransaction.transaction_date.asc(),
            FinancialTransaction.id.asc(),
        )
        .all()
    )
    return [
        {
            "transaction_id": transaction.id,
            "role": allocation.role,
            "allocated_amount": allocation.allocated_amount,
            "direction": transaction.direction,
            "amount": transaction.amount,
            "transaction_date": transaction.transaction_date,
            "title": transaction_fact_title(transaction),
            "source_type": transaction.source_type,
            "counts_as_cashflow": allocation.role in {"primary", "split_component"},
        }
        for allocation, transaction in rows
    ]


def _normalized_fact_text(transaction: FinancialTransaction) -> str:
    return re.sub(
        r"[^0-9a-z\u4e00-\u9fff]+",
        "",
        f"{transaction.merchant or ''}{transaction.description or ''}".lower(),
    )


def build_fact_merge_suggestions(
    *,
    transaction: FinancialTransaction,
    fact: EconomicFact,
    candidates: list[tuple[FinancialTransaction, EconomicFact]],
) -> list[dict]:
    """Find records that may be corroborating evidence of one economic fact."""
    if fact.primary_transaction_id != transaction.id:
        return []
    source_text = _normalized_fact_text(transaction)
    suggestions: list[dict] = []
    for candidate, candidate_fact in candidates:
        if candidate_fact.id == fact.id or candidate_fact.primary_transaction_id != candidate.id:
            continue
        if transaction.direction != candidate.direction or transaction.currency != candidate.currency:
            continue
        primary_available = Decimal(getattr(fact, "amount", transaction.amount))
        evidence_available = Decimal(getattr(candidate_fact, "amount", candidate.amount))
        amount_diff = abs(primary_available - evidence_available)
        allocated_amount = min(primary_available, evidence_available)
        larger_amount = max(primary_available, evidence_available)
        if allocated_amount <= 0 or allocated_amount / larger_amount < Decimal("0.10"):
            continue
        day_diff = abs((transaction.transaction_date - candidate.transaction_date).days)
        if day_diff > 31:
            continue
        target_text = _normalized_fact_text(candidate)
        text_similarity = (
            SequenceMatcher(None, source_text, target_text).ratio()
            if source_text and target_text
            else 0.0
        )
        source_differs = transaction.source_type != candidate.source_type
        if day_diff > 3 and text_similarity < 0.55:
            continue
        if amount_diff <= Decimal("0.01"):
            reasons = ["两条已确认记录金额完全一致"]
            score = 55
        else:
            reasons = [f"可先核对其中 {allocated_amount:.2f} 元，剩余金额继续作为独立事实"]
            score = 25
        if day_diff == 0:
            score += 25
            reasons.append("发生在同一天")
        elif day_diff == 1:
            score += 20
            reasons.append("日期相差 1 天")
        elif day_diff <= 3:
            score += 15
            reasons.append(f"日期相差 {day_diff} 天")
        else:
            score += 5
            reasons.append(f"日期相差 {day_diff} 天")
        if source_differs:
            score += 10
            reasons.append("来自不同账单来源，可能是同一笔钱的多份证据")
        if text_similarity >= 0.85:
            score += 10
            reasons.append("商户或摘要高度一致")
        elif text_similarity >= 0.55:
            score += 5
            reasons.append("商户或摘要部分相似")
        score = min(100, score)
        tier = "high" if score >= 90 else "medium" if score >= 70 else "low"
        suggestions.append(
            {
                "primary_transaction_id": transaction.id,
                "evidence_transaction_id": candidate.id,
                "primary_fact_id": fact.id,
                "evidence_fact_id": candidate_fact.id,
                "primary_amount": primary_available,
                "evidence_amount": evidence_available,
                "primary_date": transaction.transaction_date,
                "evidence_date": candidate.transaction_date,
                "primary_title": transaction_fact_title(transaction),
                "evidence_title": transaction_fact_title(candidate),
                "primary_source_type": transaction.source_type,
                "evidence_source_type": candidate.source_type,
                "allocated_amount": allocated_amount,
                "score": score,
                "confidence_tier": tier,
                "reasons": reasons,
                "ai_status": "not_needed" if tier == "high" else "unavailable",
                "_ai_context": {
                    "primary_merchant": transaction.merchant,
                    "primary_description": transaction.description,
                    "evidence_merchant": candidate.merchant,
                    "evidence_description": candidate.description,
                },
            }
        )
    high = [item for item in suggestions if item["confidence_tier"] == "high"]
    if len(high) > 1:
        for item in high:
            item["confidence_tier"] = "medium"
            item["ai_status"] = "unavailable"
            item["reasons"].append("存在多条等价记录，程序无法唯一决定")
    return sorted(suggestions, key=lambda item: (-item["score"], item["evidence_transaction_id"]))


def enrich_fact_merge_suggestions_with_ai(
    suggestions: list[dict],
    *,
    transaction: FinancialTransaction,
    user_id: int,
    expected_data_epoch: int | None,
) -> list[dict]:
    ambiguous = [item for item in suggestions if item["confidence_tier"] != "high"][:10]
    if not ambiguous:
        return suggestions
    from app.services.payslip_intake_service import _call_payslip_llm

    safe_suggestions = [
        {
            "primary_transaction_id": item["primary_transaction_id"],
            "evidence_transaction_id": item["evidence_transaction_id"],
            "amount": str(item["primary_amount"]),
            "allocated_amount": str(item["allocated_amount"]),
            "date_gap_days": abs((item["primary_date"] - item["evidence_date"]).days),
            "program_reasons": item["reasons"],
            "primary_source_type": item["primary_source_type"],
            "evidence_source_type": item["evidence_source_type"],
            "primary_merchant": redact_cashflow_text((item.get("_ai_context") or {}).get("primary_merchant") or "", max_length=120),
            "primary_description": redact_cashflow_text((item.get("_ai_context") or {}).get("primary_description") or "", max_length=200),
            "evidence_merchant": redact_cashflow_text((item.get("_ai_context") or {}).get("evidence_merchant") or "", max_length=120),
            "evidence_description": redact_cashflow_text((item.get("_ai_context") or {}).get("evidence_description") or "", max_length=200),
        }
        for item in ambiguous
    ]
    prompt = """你是收支守护的同一经济事实判断助手。程序已找到金额、日期或摘要相近的两条已确认记录。
你只判断它们是否较可能是同一笔钱在银行卡、微信、支付宝或其他账单中的多份证据；不能修改金额、不能自动合并、不能写账。
只输出严格 JSON：{{"assessments":[{{"primary_transaction_id":1,"evidence_transaction_id":2,"assessment":"likely|unlikely|uncertain","reason":"一句可核对理由"}}]}}
当前记录 ID：{transaction_id}
候选：{suggestions}
""".format(
        transaction_id=transaction.id,
        suggestions=json.dumps(safe_suggestions, ensure_ascii=False),
    )
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_same_fact_reasoning",
        max_tokens=1400,
    )
    if not output:
        return suggestions
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return suggestions
    assessments = payload.get("assessments") if isinstance(payload, dict) else None
    if not isinstance(assessments, list):
        return suggestions
    by_key = {
        (item["primary_transaction_id"], item["evidence_transaction_id"]): item
        for item in suggestions
    }
    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue
        target = by_key.get(
            (assessment.get("primary_transaction_id"), assessment.get("evidence_transaction_id"))
        )
        verdict = assessment.get("assessment")
        if target is None or verdict not in {"likely", "unlikely", "uncertain"}:
            continue
        target["ai_status"] = "completed"
        target["ai_assessment"] = verdict
        reason = re.sub(r"\s+", " ", str(assessment.get("reason") or "")).strip()
        target["ai_reason"] = reason[:300] or "AI 未提供可核对理由"
    return suggestions


def refresh_fact_type_from_relations(db: Session, fact: EconomicFact) -> None:
    as_source = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.source_fact_id == fact.id,
            EconomicFactRelation.status == "confirmed",
        )
        .order_by(EconomicFactRelation.id.desc())
        .first()
    )
    as_target = (
        db.query(EconomicFactRelation)
        .filter(
            EconomicFactRelation.target_fact_id == fact.id,
            EconomicFactRelation.status == "confirmed",
        )
        .order_by(EconomicFactRelation.id.desc())
        .first()
    )
    if as_source is not None:
        fact.fact_type = {
            "refunds": "refund",
            "reimburses": "reimbursement",
            "transfer_pair": "transfer",
        }.get(as_source.relation_type, fact.fact_type)
        return
    if as_target is not None and as_target.relation_type == "reimburses":
        fact.fact_type = "reimbursable_expense"
        return
    if as_target is not None and as_target.relation_type == "transfer_pair":
        fact.fact_type = "transfer"
        return
    transaction = get_fact_source_transaction(db, fact=fact, user_id=fact.user_id)
    if transaction is not None:
        if fact.primary_transaction_id is None:
            fact.fact_type = (
                "reimbursable_expense"
                if transaction.direction == "expense" and fact.nature == "reimbursable"
                else transaction.direction
            )
        else:
            fact.fact_type = transaction_fact_type(transaction)


def build_relation_suggestions(
    *,
    transaction: FinancialTransaction,
    fact: EconomicFact,
    candidates: list[tuple[FinancialTransaction, EconomicFact]],
    existing_pairs: set[tuple[int, int, str]],
) -> list[dict]:
    """按金额、日期、方向和语义先生成退款/报销/转账关系候选。"""
    source_text = f"{transaction.merchant or ''} {transaction.description or ''}".lower()
    refund_hit = any(word in source_text for word in ("退款", "退货", "冲正", "退回", "refund"))
    reimburse_hit = any(word in source_text for word in ("报销", "费用返还", "reimburse"))
    transfer_hit = any(
        word in source_text
        for word in ("转账", "转入", "转出", "账户互转", "余额充值", "零钱充值", "银行卡充值", "transfer")
    )
    suggestions: list[dict] = []
    for candidate, candidate_fact in candidates:
        day_diff = abs((transaction.transaction_date - candidate.transaction_date).days)
        if day_diff > 365:
            continue
        relation_type: str | None = None
        relation_source_fact = fact
        relation_target_fact = candidate_fact
        relation_source_transaction = transaction
        relation_target_transaction = candidate
        semantic_score = 0
        reasons: list[str] = []

        candidate_text = f"{candidate.merchant or ''} {candidate.description or ''}".lower()
        candidate_refund = any(word in candidate_text for word in ("退款", "退货", "冲正", "退回", "refund"))
        candidate_reimburse = any(word in candidate_text for word in ("报销", "费用返还", "reimburse"))
        candidate_transfer = any(
            word in candidate_text
            for word in ("转账", "转入", "转出", "账户互转", "余额充值", "零钱充值", "银行卡充值", "transfer")
        )
        same_merchant = bool(
            transaction.merchant
            and candidate.merchant
            and transaction.merchant.strip().lower() == candidate.merchant.strip().lower()
        )

        if (
            {transaction.direction, candidate.direction} == {"income", "expense"}
            and day_diff <= 7
            and transfer_hit
            and candidate_transfer
        ):
            relation_type = "transfer_pair"
            if transaction.direction == "expense":
                relation_source_fact, relation_target_fact = candidate_fact, fact
                relation_source_transaction, relation_target_transaction = candidate, transaction
            semantic_score += 30
            reasons.append("流水摘要包含转入、转出或账户互转语义")
        elif transaction.direction == "income" and candidate.direction == "expense" and candidate.transaction_date <= transaction.transaction_date:
            if reimburse_hit or candidate.nature == "reimbursable":
                relation_type = "reimburses"
            elif refund_hit or same_merchant:
                relation_type = "refunds"
            else:
                continue
            if reimburse_hit:
                semantic_score += 30
                reasons.append("收入摘要包含报销语义")
            elif candidate.nature == "reimbursable":
                semantic_score += 25
                reasons.append("原支出已标记为可报销")
            elif refund_hit:
                semantic_score += 30
                reasons.append("收入摘要包含退款或冲正语义")
            elif same_merchant:
                semantic_score += 15
                reasons.append("收入与原支出的商家名称一致")
        elif transaction.direction == "expense" and candidate.direction == "income" and transaction.transaction_date <= candidate.transaction_date:
            if candidate_reimburse or transaction.nature == "reimbursable":
                relation_type = "reimburses"
            elif candidate_refund or same_merchant:
                relation_type = "refunds"
            else:
                continue
            relation_source_fact, relation_target_fact = candidate_fact, fact
            relation_source_transaction, relation_target_transaction = candidate, transaction
            if candidate_reimburse:
                semantic_score += 30
                reasons.append("后续收入摘要包含报销语义")
            elif transaction.nature == "reimbursable":
                semantic_score += 25
                reasons.append("当前支出已标记为可报销")
            elif candidate_refund:
                semantic_score += 30
                reasons.append("后续收入摘要包含退款或冲正语义")
            elif same_merchant:
                semantic_score += 15
                reasons.append("后续收入与当前支出的商家名称一致")
        elif transaction.direction == "transfer" and candidate.direction == "transfer" and day_diff <= 7:
            relation_type = "transfer_pair"
            semantic_score += 30
            reasons.append("两笔都已标记为转账")
        if relation_type is None:
            continue
        pair = (relation_source_fact.id, relation_target_fact.id, relation_type)
        if pair in existing_pairs:
            continue
        amount_diff = abs(Decimal(relation_source_transaction.amount) - Decimal(relation_target_transaction.amount))
        allocated = min(Decimal(relation_source_transaction.amount), Decimal(relation_target_transaction.amount))
        if amount_diff <= Decimal("0.01"):
            amount_score = 50
            reasons.insert(0, "两笔金额完全一致")
        elif allocated > 0 and allocated < max(Decimal(relation_source_transaction.amount), Decimal(relation_target_transaction.amount)):
            amount_score = 25
            reasons.insert(0, "金额可能表达部分退款、部分报销或拆分转账")
        else:
            continue
        date_score = max(0, 20 - min(day_diff, 20))
        reasons.append(f"两笔日期相差 {day_diff} 天")
        score = min(100, amount_score + semantic_score + date_score)
        tier = "high" if score >= 85 else "medium" if score >= 45 else "low"
        suggestions.append(
            {
                "source_transaction_id": relation_source_transaction.id,
                "target_transaction_id": relation_target_transaction.id,
                "source_fact_id": relation_source_fact.id,
                "target_fact_id": relation_target_fact.id,
                "source_direction": relation_source_transaction.direction,
                "target_direction": relation_target_transaction.direction,
                "source_amount": Decimal(relation_source_transaction.amount),
                "target_amount": Decimal(relation_target_transaction.amount),
                "source_date": relation_source_transaction.transaction_date,
                "target_date": relation_target_transaction.transaction_date,
                "source_title": transaction_fact_title(relation_source_transaction),
                "target_title": transaction_fact_title(relation_target_transaction),
                "relation_type": relation_type,
                "allocated_amount": allocated,
                "score": score,
                "confidence_tier": tier,
                "reasons": reasons,
                "ai_status": "not_needed" if tier == "high" else "unavailable",
                "_ai_context": {
                    "source_merchant": relation_source_transaction.merchant,
                    "source_description": relation_source_transaction.description,
                    "target_merchant": relation_target_transaction.merchant,
                    "target_description": relation_target_transaction.description,
                },
            }
        )
    high = [item for item in suggestions if item["confidence_tier"] == "high"]
    if len(high) > 1:
        for item in high:
            item["confidence_tier"] = "medium"
            item["ai_status"] = "unavailable"
            item["reasons"].append("同时存在多个高匹配对象，程序无法唯一决定")
    return sorted(suggestions, key=lambda item: (-item["score"], item["target_transaction_id"]))


def enrich_relation_suggestions_with_ai(
    suggestions: list[dict],
    *,
    transaction: FinancialTransaction,
    user_id: int,
    expected_data_epoch: int | None,
) -> list[dict]:
    ambiguous = [item for item in suggestions if item["confidence_tier"] != "high"][:10]
    if not ambiguous:
        return suggestions
    from app.services.payslip_intake_service import _call_payslip_llm

    safe_transaction = {
        "id": transaction.id,
        "direction": transaction.direction,
        "amount": str(transaction.amount),
        "date": transaction.transaction_date.isoformat(),
        "merchant": redact_cashflow_text(transaction.merchant or "", max_length=120),
        "description": redact_cashflow_text(transaction.description or "", max_length=200),
        "nature": transaction.nature,
    }
    safe_suggestions = [
        {
            "source_transaction_id": item["source_transaction_id"],
            "target_transaction_id": item["target_transaction_id"],
            "source_fact_id": item["source_fact_id"],
            "target_fact_id": item["target_fact_id"],
            "relation_type": item["relation_type"],
            "allocated_amount": str(item["allocated_amount"]),
            "program_reasons": item["reasons"],
            "source_merchant": redact_cashflow_text((item.get("_ai_context") or {}).get("source_merchant") or "", max_length=120),
            "source_description": redact_cashflow_text((item.get("_ai_context") or {}).get("source_description") or "", max_length=200),
            "target_merchant": redact_cashflow_text((item.get("_ai_context") or {}).get("target_merchant") or "", max_length=120),
            "target_description": redact_cashflow_text((item.get("_ai_context") or {}).get("target_description") or "", max_length=200),
        }
        for item in ambiguous
    ]
    prompt = """你是收支守护的经济事实关系判断助手。程序已经先按金额、日期、方向和关键词生成退款、报销或转账候选。
你只能判断语义是否支持该关系，不能修改金额、不能写账、不能代替用户确认。
只输出严格 JSON：{{"assessments":[{{"source_transaction_id":1,"target_transaction_id":2,"source_fact_id":11,"target_fact_id":22,"relation_type":"refunds|reimburses|transfer_pair","assessment":"likely|unlikely|uncertain","reason":"一句可核对理由"}}]}}
当前流水：{transaction}
关系候选：{suggestions}
""".format(
        transaction=json.dumps(safe_transaction, ensure_ascii=False),
        suggestions=json.dumps(safe_suggestions, ensure_ascii=False),
    )
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_relation_reasoning",
        max_tokens=1400,
    )
    if not output:
        return suggestions
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return suggestions
    assessments = payload.get("assessments") if isinstance(payload, dict) else None
    if not isinstance(assessments, list):
        return suggestions
    by_fact_key = {
        (item["source_fact_id"], item["target_fact_id"], item["relation_type"]): item
        for item in suggestions
    }
    by_transaction_key: dict[tuple[int, int, str], list[dict]] = {}
    for item in suggestions:
        by_transaction_key.setdefault(
            (
                item["source_transaction_id"],
                item["target_transaction_id"],
                item["relation_type"],
            ),
            [],
        ).append(item)
    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue
        fact_key = (
            assessment.get("source_fact_id"),
            assessment.get("target_fact_id"),
            assessment.get("relation_type"),
        )
        target = by_fact_key.get(fact_key)
        if target is None:
            transaction_matches = by_transaction_key.get((
                assessment.get("source_transaction_id"),
                assessment.get("target_transaction_id"),
                assessment.get("relation_type"),
            ), [])
            # Backward compatible with an older model response only when the
            # transaction pair resolves to exactly one fact pair.
            target = transaction_matches[0] if len(transaction_matches) == 1 else None
        verdict = assessment.get("assessment")
        if target is None or verdict not in {"likely", "unlikely", "uncertain"}:
            continue
        target["ai_status"] = "completed"
        target["ai_assessment"] = verdict
        reason = re.sub(r"\s+", " ", str(assessment.get("reason") or "")).strip()
        target["ai_reason"] = reason[:300] or "AI 未提供可核对理由"
    return suggestions
