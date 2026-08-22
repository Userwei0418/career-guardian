"""统一经济事实与正式流水证据的最小同步层。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    return (
        db.query(EconomicFact)
        .filter(
            EconomicFact.primary_transaction_id == transaction_id,
            EconomicFact.user_id == user_id,
            EconomicFact.status == "confirmed",
        )
        .first()
    )


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
    transaction = (
        db.query(FinancialTransaction)
        .filter(FinancialTransaction.id == fact.primary_transaction_id)
        .first()
    )
    if transaction is not None:
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
只输出严格 JSON：{{"assessments":[{{"source_transaction_id":1,"target_transaction_id":2,"relation_type":"refunds|reimburses|transfer_pair","assessment":"likely|unlikely|uncertain","reason":"一句可核对理由"}}]}}
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
    by_key = {
        (item["source_transaction_id"], item["target_transaction_id"], item["relation_type"]): item
        for item in suggestions
    }
    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue
        key = (
            assessment.get("source_transaction_id"),
            assessment.get("target_transaction_id"),
            assessment.get("relation_type"),
        )
        target = by_key.get(key)
        verdict = assessment.get("assessment")
        if target is None or verdict not in {"likely", "unlikely", "uncertain"}:
            continue
        target["ai_status"] = "completed"
        target["ai_assessment"] = verdict
        reason = re.sub(r"\s+", " ", str(assessment.get("reason") or "")).strip()
        target["ai_reason"] = reason[:300] or "AI 未提供可核对理由"
    return suggestions
