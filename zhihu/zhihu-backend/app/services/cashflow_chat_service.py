"""Ask questions over confirmed cashflow facts without giving the model write authority."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any, Mapping

from app.models.cashflow import FinancialTransaction
from app.services.cashflow_privacy import redact_cashflow_text


def _json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def build_cashflow_chat_context(
    *,
    data_start: date,
    data_end: date,
    transactions: list[FinancialTransaction],
    category_names: Mapping[int, str],
    fact_types: Mapping[int, str],
    monthly_summaries: list[dict],
    relations: list[dict],
) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    """Create a bounded, redacted context from confirmed records only."""
    category_totals: dict[str, Decimal] = {}
    merchant_totals: dict[str, Decimal] = {}
    for summary in monthly_summaries:
        for direction, field in (("income", "income_categories"), ("expense", "expense_categories")):
            for item in summary.get(field, []):
                key = f"{direction}:{item['category_name']}"
                category_totals[key] = category_totals.get(key, Decimal("0")) + Decimal(item["amount"])
        for item in summary.get("expense_merchants", []):
            merchant = str(item["merchant_name"])
            merchant_totals[merchant] = merchant_totals.get(merchant, Decimal("0")) + Decimal(item["amount"])
    reference_by_id: dict[int, dict[str, Any]] = {}
    transaction_rows: list[dict[str, Any]] = []
    for transaction in sorted(
        transactions,
        key=lambda item: (item.transaction_date, item.id),
        reverse=True,
    ):
        category_name = category_names.get(transaction.category_id, "未分类") if transaction.category_id else None
        title = (
            redact_cashflow_text(transaction.merchant or "", max_length=80)
            or redact_cashflow_text(transaction.description or "", max_length=100)
            or category_name
            or {"income": "收入", "expense": "支出", "transfer": "转账"}.get(transaction.direction, "流水")
        )
        row = {
            "transaction_id": transaction.id,
            "date": transaction.transaction_date.isoformat(),
            "direction": transaction.direction,
            "amount": str(Decimal(transaction.amount)),
            "category": category_name,
            "merchant": redact_cashflow_text(transaction.merchant or "", max_length=80) or None,
            "description": redact_cashflow_text(transaction.description or "", max_length=140) or None,
            "nature": transaction.nature,
            "fact_type": fact_types.get(transaction.id, transaction.direction),
        }
        transaction_rows.append(row)
        reference_by_id[transaction.id] = {
            "transaction_id": transaction.id,
            "transaction_date": transaction.transaction_date,
            "direction": transaction.direction,
            "amount": Decimal(transaction.amount),
            "title": title,
            "category_name": category_name,
            "fact_type": fact_types.get(transaction.id, transaction.direction),
        }
    context = {
        "scope": {
            "data_start": data_start.isoformat(),
            "data_end": data_end.isoformat(),
            "confirmed_transaction_count": len(transactions),
            "transaction_detail_rows_supplied_to_ai": min(len(transactions), 80),
            "relation_detail_rows_supplied_to_ai": min(len(relations), 60),
            "rule": "只含已确认且未删除流水；退款、报销和内部转账使用用户已确认关系后的统计口径",
        },
        "monthly_summaries": [
            {
                "month": summary["month"],
                "income": str(summary["income"]),
                "expense": str(summary["expense"]),
                "net": str(summary["net"]),
                "transfer_amount": str(summary["transfer_amount"]),
                "income_categories": summary["income_categories"],
                "expense_categories": summary["expense_categories"],
                "expense_merchants": summary.get("expense_merchants", []),
            }
            for summary in monthly_summaries
        ],
        "category_totals_confirmed_accounting": [
            {"key": key, "amount": str(amount)}
            for key, amount in sorted(category_totals.items(), key=lambda item: (-item[1], item[0]))[:30]
        ],
        "top_expense_merchants_confirmed_accounting": [
            {"merchant": merchant, "amount": str(amount)}
            for merchant, amount in sorted(merchant_totals.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "confirmed_relations": relations[:60],
        "recent_confirmed_transactions": transaction_rows[:80],
    }
    return context, reference_by_id


def answer_cashflow_question(
    *,
    question: str,
    history: list[dict[str, str]],
    context: dict[str, Any],
    reference_by_id: Mapping[int, dict[str, Any]],
    user_id: int,
    expected_data_epoch: int | None,
) -> dict[str, Any]:
    from app.services.payslip_intake_service import _call_payslip_llm

    safe_history = [
        {
            "role": item["role"],
            "content": redact_cashflow_text(re.sub(r"\s+", " ", item["content"]).strip(), max_length=800),
        }
        for item in history[-8:]
    ]
    prompt = """你是收支守护的账本解释助手。程序已经完成所有金额计算和退款、报销、内部转账口径处理；你不能重新算账、不能改账、不能虚构缺失数据。
只能使用给出的已确认账本上下文回答。问题超出数据范围时明确说明缺少什么；不要把消费趋势写成投资、税务或法律结论。
输出严格 JSON：{{"answer":"简洁但具体的中文回答","referenced_transaction_ids":[1,2],"follow_up_questions":["最多3个可继续问的问题"]}}
引用 ID 只能来自上下文中的 transaction_id。回答中要区分已确认事实、程序计算和推测。
对话历史：{history}
用户问题：{question}
已确认账本上下文：{context}
""".format(
        history=json.dumps(safe_history, ensure_ascii=False),
        question=redact_cashflow_text(question, max_length=500),
        context=json.dumps(context, ensure_ascii=False, default=str),
    )
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_confirmed_ledger_qa",
        max_tokens=1800,
    )
    payload = _json_object(output) if output else None
    if payload is None or not isinstance(payload.get("answer"), str):
        latest = context["monthly_summaries"][-1] if context["monthly_summaries"] else None
        if latest is None:
            answer = "当前数据范围内没有已确认收支，因此还不能回答这个问题。请先确认至少一笔流水。"
        else:
            answer = (
                "AI 服务当前不可用。按程序已确认口径，"
                f"{latest['month']} 收入为 ¥{latest['income']}、支出为 ¥{latest['expense']}、"
                f"净结余为 ¥{latest['net']}。你可以稍后重试以获得针对问题的解释。"
            )
        return {
            "answer": answer,
            "mode": "program",
            "references": [],
            "follow_up_questions": ["本月支出最多的分类是什么？", "与上月相比支出有什么变化？"],
        }

    ids = payload.get("referenced_transaction_ids")
    references = []
    seen: set[int] = set()
    if isinstance(ids, list):
        for raw_id in ids[:20]:
            if not isinstance(raw_id, int) or raw_id in seen or raw_id not in reference_by_id:
                continue
            seen.add(raw_id)
            references.append(reference_by_id[raw_id])
            if len(references) >= 12:
                break
    follow_ups = payload.get("follow_up_questions")
    normalized_follow_ups = []
    if isinstance(follow_ups, list):
        normalized_follow_ups = [
            re.sub(r"\s+", " ", str(item)).strip()[:120]
            for item in follow_ups[:3]
            if str(item).strip()
        ]
    answer = re.sub(r"\s+", " ", payload["answer"]).strip()[:4000]
    if not answer:
        answer = "AI 没有生成可用回答，请换一种问法重试。"
    return {
        "answer": answer,
        "mode": "ai",
        "references": references,
        "follow_up_questions": normalized_follow_ups,
    }
