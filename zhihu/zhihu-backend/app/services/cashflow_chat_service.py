"""Ask questions over confirmed cashflow facts without giving the model write authority."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import re
import time
from typing import Any, Callable, Mapping

import httpx

from app.db.session import SessionLocal
from app.models.cashflow import FinancialTransaction
from app.services.ai_configuration_service import effective_ai_configuration
from app.services.cashflow_ai_intake_service import _audit, _error_code
from app.services.cashflow_privacy import redact_cashflow_text


class CashflowChatStreamCancelled(RuntimeError):
    """Stop a provider stream when the browser has closed the response."""


def _partial_json_string_field(content: str, field: str) -> tuple[str, bool]:
    """Decode the currently available prefix of one JSON string field."""
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"', content)
    if match is None:
        return "", False
    index = match.end()
    decoded: list[str] = []
    escapes = {"\"": "\"", "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
    while index < len(content):
        character = content[index]
        if character == '"':
            return "".join(decoded), True
        if character != "\\":
            decoded.append(character)
            index += 1
            continue
        if index + 1 >= len(content):
            break
        escaped = content[index + 1]
        if escaped == "u":
            if index + 6 > len(content):
                break
            raw_codepoint = content[index + 2:index + 6]
            if re.fullmatch(r"[0-9a-fA-F]{4}", raw_codepoint) is None:
                break
            codepoint = int(raw_codepoint, 16)
            index += 6
            if 0xD800 <= codepoint <= 0xDBFF:
                remaining = content[index:]
                if not remaining or remaining == "\\" or (remaining.startswith("\\u") and len(remaining) < 6):
                    break
                if remaining.startswith("\\u"):
                    raw_low = remaining[2:6]
                    if re.fullmatch(r"[0-9a-fA-F]{4}", raw_low):
                        low = int(raw_low, 16)
                        if 0xDC00 <= low <= 0xDFFF:
                            decoded.append(chr(0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)))
                            index += 6
                            continue
                decoded.append("\ufffd")
                continue
            decoded.append("\ufffd" if 0xDC00 <= codepoint <= 0xDFFF else chr(codepoint))
            continue
        replacement = escapes.get(escaped)
        if replacement is None:
            break
        decoded.append(replacement)
        index += 2
    return "".join(decoded), False


def _normalize_markdown_answer(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"[\ud800-\udfff]", "\ufffd", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", normalized)[:8000]


def _call_cashflow_llm_stream(
    prompt: str,
    *,
    user_id: int,
    expected_data_epoch: int | None,
    on_content_delta: Callable[[str], None],
    cancelled: Callable[[], bool] | None = None,
) -> str | None:
    """Call the configured OpenAI-compatible service and forward real content deltas."""
    try:
        with SessionLocal() as configuration_db:
            configuration = effective_ai_configuration(configuration_db)
    except Exception as exc:
        _audit(None, feature="cashflow_confirmed_ledger_qa", modality="text", user_id=user_id, status="failed", error_code=_error_code(exc), expected_data_epoch=expected_data_epoch)
        return None
    if configuration is None:
        _audit(None, feature="cashflow_confirmed_ledger_qa", modality="text", user_id=user_id, status="failed", error_code="AIConfigurationUnavailable", expected_data_epoch=expected_data_epoch)
        return None
    started = time.monotonic()
    content_parts: list[str] = []
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    try:
        with httpx.stream(
            "POST",
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {configuration.api_key}", "Content-Type": "application/json"},
            json={
                "model": configuration.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 1800,
                "stream": True,
            },
            timeout=httpx.Timeout(connect=10, read=75, write=20, pool=10),
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            if "text/event-stream" not in response.headers.get("content-type", "").lower():
                body = response.read().decode("utf-8")
                payload = json.loads(body)
                choice = payload["choices"][0]
                finish_reason = choice.get("finish_reason")
                content = choice.get("message", {}).get("content")
                if not isinstance(content, str):
                    raise ValueError("ModelResponseInvalidJSON")
                content_parts.append(content)
                on_content_delta(content)
                usage = payload.get("usage") if isinstance(payload, dict) else None
            else:
                for line in response.iter_lines():
                    if cancelled and cancelled():
                        raise CashflowChatStreamCancelled("ClientCancelled")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice.get("finish_reason")
                    delta = choice.get("delta")
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(content, str) and content:
                        content_parts.append(content)
                        on_content_delta(content)
        if finish_reason not in {None, "stop"}:
            raise ValueError(f"ModelFinishReason:{finish_reason}")
        content = "".join(content_parts)
        if not content:
            raise ValueError("ModelResponseInvalidJSON")
        _audit(configuration, feature="cashflow_confirmed_ledger_qa", modality="text", user_id=user_id, status="success", latency_ms=round((time.monotonic() - started) * 1000), usage=usage, expected_data_epoch=expected_data_epoch)
        return content
    except CashflowChatStreamCancelled:
        _audit(configuration, feature="cashflow_confirmed_ledger_qa", modality="text", user_id=user_id, status="failed", latency_ms=round((time.monotonic() - started) * 1000), error_code="ClientCancelled", expected_data_epoch=expected_data_epoch)
        raise
    except Exception as exc:
        _audit(configuration, feature="cashflow_confirmed_ledger_qa", modality="text", user_id=user_id, status="failed", latency_ms=round((time.monotonic() - started) * 1000), error_code=_error_code(exc), expected_data_epoch=expected_data_epoch)
        return None


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
    payslip_guardians: list[dict] | None = None,
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
    bounded_payslips = (payslip_guardians or [])[-12:]
    context = {
        "scope": {
            "data_start": data_start.isoformat(),
            "data_end": data_end.isoformat(),
            "confirmed_transaction_count": len(transactions),
            "transaction_detail_rows_supplied_to_ai": min(len(transactions), 80),
            "relation_detail_rows_supplied_to_ai": min(len(relations), 60),
            "active_payslip_guardians_supplied_to_ai": len(bounded_payslips),
            "rule": "流水只含已确认且未删除的当前经济事实；同一事实的辅助证据已剔除，部分分配只提供剩余有效金额；工资只含当前有效的结构化工资条和用户确认的到账关系；不含原文件或 OCR 原文",
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
        "active_payslip_guardians": bounded_payslips,
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
    knowledge_by_slug: Mapping[str, dict[str, Any]] | None = None,
    on_answer_delta: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    from app.services.payslip_intake_service import _call_payslip_llm

    safe_history = [
        {
            "role": item["role"],
            "content": redact_cashflow_text(re.sub(r"\s+", " ", item["content"]).strip(), max_length=800),
        }
        for item in history[-8:]
    ]
    prompt = """你是收支守护的账本和工资解释助手。程序已经完成所有金额计算、工资条字段比对和退款/报销/转账口径处理；你不能重新算账、不能改账、不能虚构缺失数据。
只能使用给出的已确认账本和当前有效工资守护上下文回答。工资守护中的 unverified 只表示证据不足，不能写成少发、多扣、迟发或漏发事实。linked_materials 中 preferred 表示用户选择的当前优先参照，reference 只是普通对照，unresolved 表示适用性尚未确认；这个状态是用户的核对口径，不等于材料法律效力，也不能让普通对照或待确认材料覆盖优先参照。若多份 preferred 或材料之间冲突，必须逐份说明，不能自行选定哪份正确。问题超出数据范围时明确说明缺少什么；不要把消费趋势写成投资、税务或法律结论。
输出严格 JSON：{{"answer":"使用 Markdown 排版的简洁但具体中文回答","referenced_transaction_ids":[1,2],"referenced_payslip_ids":[3],"referenced_knowledge_slugs":["slug"],"follow_up_questions":["最多3个可继续问的问题"]}}
流水和工资引用 ID 只能来自上下文中的 transaction_id 或 payslip_id；知识 slug 只能来自 relevant_knowledge。回答中要区分已确认事实、程序计算、通用知识和推测；通用知识不能直接证明用户存在少发、多扣或违法情形。
answer 必须是安全 Markdown：优先使用短标题、短段落、有序或无序列表和加粗，不要输出 HTML，不要把整段内容挤成一行；金额和比例保持程序上下文中的原值。
对话历史：{history}
用户问题：{question}
已确认账本上下文：{context}
""".format(
        history=json.dumps(safe_history, ensure_ascii=False),
        question=redact_cashflow_text(question, max_length=500),
        context=json.dumps(context, ensure_ascii=False, default=str),
    )
    if on_answer_delta is None:
        output = _call_payslip_llm(
            prompt,
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
            feature="cashflow_confirmed_ledger_qa",
            max_tokens=1800,
        )
    else:
        streamed_content = ""
        emitted_answer = ""
        pending_answer_delta = ""

        def flush_answer_delta() -> None:
            nonlocal pending_answer_delta
            if not pending_answer_delta:
                return
            on_answer_delta(pending_answer_delta)
            pending_answer_delta = ""

        def receive_content_delta(delta: str) -> None:
            nonlocal streamed_content, emitted_answer, pending_answer_delta
            streamed_content += delta
            partial_answer, _ = _partial_json_string_field(streamed_content, "answer")
            if partial_answer.startswith(emitted_answer) and len(partial_answer) > len(emitted_answer):
                next_delta = partial_answer[len(emitted_answer):]
                emitted_answer = partial_answer
                pending_answer_delta += next_delta
                if len(pending_answer_delta) >= 24 or "\n" in pending_answer_delta:
                    flush_answer_delta()

        output = _call_cashflow_llm_stream(
            prompt,
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
            on_content_delta=receive_content_delta,
            cancelled=cancelled,
        )
        flush_answer_delta()
    if cancelled and cancelled():
        raise CashflowChatStreamCancelled("ClientCancelled")
    payload = _json_object(output) if output else None
    if payload is None or not isinstance(payload.get("answer"), str):
        latest = context["monthly_summaries"][-1] if context["monthly_summaries"] else None
        payslips = context.get("active_payslip_guardians") or []
        latest_payslip = payslips[-1] if payslips else None
        if latest is None and latest_payslip is None:
            answer = "当前数据范围内没有已确认收支，因此还不能回答这个问题。请先确认至少一笔流水。"
        elif latest is None:
            answer = (
                "AI 服务当前不可用。按程序守护结果，"
                f"{latest_payslip.get('pay_month') or '该月'}工资条实发为 ¥{latest_payslip.get('net_salary') or '未知'}，"
                f"有 {latest_payslip.get('attention_count', 0)} 项需处理、{latest_payslip.get('unverified_count', 0)} 项尚未核清。"
            )
        else:
            answer = (
                "AI 服务当前不可用。按程序已确认口径，"
                f"{latest['month']} 收入为 ¥{latest['income']}、支出为 ¥{latest['expense']}、"
                f"净结余为 ¥{latest['net']}。"
            )
            if latest_payslip:
                answer += (
                    f"{latest_payslip.get('pay_month') or '该月'}工资守护还有 "
                    f"{latest_payslip.get('attention_count', 0)} 项需处理、"
                    f"{latest_payslip.get('unverified_count', 0)} 项尚未核清。"
                )
            answer += "你可以稍后重试以获得针对问题的解释。"
        return {
            "answer": answer,
            "mode": "program",
            "references": [],
            "payslip_references": [],
            "knowledge_references": [],
            "follow_up_questions": (["这份工资还有哪些项没核清？", "我应该问 HR 什么？"] if latest_payslip else ["本月支出最多的分类是什么？", "与上月相比支出有什么变化？"]),
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
    allowed_payslips = {
        item.get("payslip_id"): item
        for item in context.get("active_payslip_guardians", [])
        if isinstance(item, dict) and isinstance(item.get("payslip_id"), int)
    }
    payslip_references = []
    seen_payslips: set[int] = set()
    raw_payslip_ids = payload.get("referenced_payslip_ids")
    if isinstance(raw_payslip_ids, list):
        for raw_id in raw_payslip_ids[:12]:
            if not isinstance(raw_id, int) or raw_id in seen_payslips or raw_id not in allowed_payslips:
                continue
            seen_payslips.add(raw_id)
            payslip_references.append(allowed_payslips[raw_id])
    allowed_knowledge = knowledge_by_slug or {}
    knowledge_references = []
    seen_knowledge: set[str] = set()
    raw_knowledge_slugs = payload.get("referenced_knowledge_slugs")
    if isinstance(raw_knowledge_slugs, list):
        for raw_slug in raw_knowledge_slugs[:12]:
            slug = str(raw_slug).strip()
            if not slug or slug in seen_knowledge or slug not in allowed_knowledge:
                continue
            seen_knowledge.add(slug)
            knowledge_references.append(allowed_knowledge[slug])
            if len(knowledge_references) >= 6:
                break
    follow_ups = payload.get("follow_up_questions")
    normalized_follow_ups = []
    if isinstance(follow_ups, list):
        normalized_follow_ups = [
            re.sub(r"\s+", " ", str(item)).strip()[:120]
            for item in follow_ups[:3]
            if str(item).strip()
        ]
    answer = _normalize_markdown_answer(payload["answer"])
    if not answer:
        answer = "AI 没有生成可用回答，请换一种问法重试。"
    return {
        "answer": answer,
        "mode": "ai",
        "references": references,
        "payslip_references": payslip_references,
        "knowledge_references": knowledge_references,
        "follow_up_questions": normalized_follow_ups,
    }
