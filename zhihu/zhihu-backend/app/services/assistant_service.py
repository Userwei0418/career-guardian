from __future__ import annotations

"""AI 助手服务 — LLM 结构化抽取 Offer 字段。

输出约束为固定 JSON schema（Pydantic 校验），每个字段携带 confidence。
参考: engineering-contract-ai-review/backend/app/services/openai_compatible_llm_service.py
"""
import json
import time
import urllib.request
import urllib.error
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schemas.offer import OfferExtractedFields, OfferField
from app.services.ai_configuration_service import (
    effective_ai_configuration,
    record_ai_invocation,
    record_unavailable_ai_invocation,
)

OFFER_EXTRACTION_PROMPT = """你是一个专业的 Offer 信息提取助手。请从以下 Offer 文本中提取关键信息。

要求：
1. 输出必须是严格的 JSON 对象，不要输出 markdown，不要输出解释文字。
2. 每个字段包含 value（提取值，找不到则为 null）、confidence（置信度 0-1）、evidence_text（原文依据片段）。
3. 薪资数值请统一为月税前金额（元），如"年薪30万"则 monthly_salary=25000。
4. 如果文本中明确写了"X薪"，salary_months 填对应数字。
5. 试用期工资如果是"80%"，probation_salary_rate 填 0.80。

JSON 结构：
{
  "company_name": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "job_title": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "city": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "monthly_salary": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "salary_months": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "fixed_salary": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "variable_salary": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "bonus": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "allowance": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "probation_months": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "probation_salary_rate": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "work_location": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "working_hours": {"value": "", "confidence": 0.0, "evidence_text": ""},
  "start_date": {"value": "", "confidence": 0.0, "evidence_text": ""}
}

以下是 Offer 文本：
---
{text}
---"""


def _call_llm(
    prompt: str,
    *,
    feature: str = "assistant",
    timeout: int = 30,
    max_tokens: int | None = None,
    db: Session | None = None,
    user_id: int | None = None,
) -> Optional[str]:
    """调用 OpenAI 兼容 LLM 接口"""
    owned_session = db is None
    session = db or SessionLocal()
    try:
        configuration = effective_ai_configuration(session)
        if configuration is None:
            record_unavailable_ai_invocation(
                session,
                feature=feature,
                error_code="AIConfigurationUnavailable",
                user_id=user_id,
            )
            return None
        url = f"{configuration.base_url.rstrip('/')}/chat/completions"
        request_payload: dict[str, Any] = {
            "model": configuration.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        if max_tokens is not None:
            request_payload["max_tokens"] = max_tokens
        req = urllib.request.Request(
            url,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {configuration.api_key}",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            record_ai_invocation(
                session,
                configuration,
                feature=feature,
                status="success",
                latency_ms=round((time.monotonic() - started) * 1000),
                usage=body.get("usage") if isinstance(body, dict) else None,
                user_id=user_id,
            )
            return content
        except Exception as exc:
            session.rollback()
            record_ai_invocation(
                session,
                configuration,
                feature=feature,
                status="failed",
                latency_ms=round((time.monotonic() - started) * 1000),
                error_code=type(exc).__name__,
                user_id=user_id,
            )
            return None
    except Exception:
        session.rollback()
        return None
    finally:
        if owned_session:
            session.close()


def _parse_extraction_result(llm_output: str) -> OfferExtractedFields:
    """解析 LLM 输出为 OfferExtractedFields，严格校验"""
    try:
        # 尝试从 markdown 代码块中提取 JSON
        text = llm_output.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return OfferExtractedFields()

    fields = {}
    for field_name in OfferExtractedFields.model_fields:
        raw = data.get(field_name)
        if isinstance(raw, dict):
            value = raw.get("value")
            confidence = float(raw.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            evidence = raw.get("evidence_text", "")
            fields[field_name] = OfferField(
                value=str(value) if value is not None else None,
                confidence=confidence,
                evidence_text=str(evidence) if evidence else None,
            )
        else:
            fields[field_name] = OfferField()

    return OfferExtractedFields(**fields)


def extract_offer_fields(text: str, db: Session | None = None, user_id: int | None = None) -> OfferExtractedFields:
    """从 Offer 文本中抽取结构化字段。

    优先使用 LLM，不可用时返回空结果（由前端引导用户手动填写）。
    """
    if not text or len(text.strip()) < 10:
        return OfferExtractedFields()

    prompt = OFFER_EXTRACTION_PROMPT.replace("{text}", text[:5000])
    llm_output = _call_llm(prompt, feature="offer_extraction", db=db, user_id=user_id)

    if llm_output is None:
        # LLM 不可用，返回空结果
        return OfferExtractedFields()

    return _parse_extraction_result(llm_output)


def build_mock_offer() -> dict[str, Any]:
    """生成演示模式的预填充 Offer 数据（小林案例）"""
    return {
        "company_name": "星辰科技有限公司",
        "job_title": "前端开发工程师",
        "city": "杭州",
        "monthly_salary": 15000,
        "salary_months": 14,
        "fixed_salary": 12000,
        "variable_salary": 3000,
        "bonus": "年终奖 2-4 个月",
        "allowance": 500,
        "probation_months": 3,
        "probation_salary_rate": 0.80,
        "work_location": "杭州市西湖区文三路",
        "working_hours": "弹性工作制，核心时间 10:00-17:00",
        "start_date": "2026-08-01",
    }
