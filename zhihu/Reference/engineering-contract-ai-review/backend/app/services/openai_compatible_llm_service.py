from __future__ import annotations

import json
from urllib import error, request

from dataclasses import dataclass

from app.core.config import settings
from app.core.perspectives import DEFAULT_PERSPECTIVE, get_perspective
from app.schemas.review import ContractExtractedFields, ReviewRiskItem


class OpenAICompatibleLlmError(RuntimeError):
    pass


@dataclass
class OpenAICompatibleRuntimeSettings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: int


def _build_prompt(fields: ContractExtractedFields, risks: list[ReviewRiskItem], perspective_code: str = DEFAULT_PERSPECTIVE) -> str:
    perspective = get_perspective(perspective_code)
    field_lines = [
        f"- 合同名称：{fields.contract_name or '-'}",
        f"- 项目名称：{fields.project_name or '-'}",
        f"- 甲方：{fields.party_a or '-'}",
        f"- 乙方：{fields.party_b or '-'}",
        f"- 合同类型：{fields.contract_type or '-'}",
        f"- 合同金额：{fields.contract_amount or '-'}",
        f"- 工期：{fields.construction_period or '-'}",
        f"- 付款条款：{fields.payment_terms or '-'}",
        f"- 违约责任：{fields.breach_liability or '-'}",
    ]
    risk_lines = [
        f"- [{risk.level}] {risk.title}：{risk.description}；建议：{risk.recommendation}"
        for risk in risks
    ] or ["- 当前未识别到明显风险。"]

    perspective_instruction = {
        "enterprise": "输出一段简洁、专业、适合企业业务人员阅读的中文审查摘要。",
        "individual": "输出一段通俗易懂的中文审查摘要，帮助个人理解合同中的风险。",
        "worker": "输出一段通俗易懂的中文审查摘要，帮助劳动者理解合同中的权益风险。",
    }
    instruction = perspective_instruction.get(perspective_code, perspective_instruction["enterprise"])

    return (
        f"你是一名工程合同审查助手。请基于给定的合同结构化信息和风险项，"
        f"{instruction}"
        f"要求：1. 控制在120字以内；2. 先概括整体风险，再提示重点关注项；"
        f"3. 不要编造未提供的信息；4. 直接输出摘要正文，不要加标题。\n\n"
        "合同信息：\n"
        f"{chr(10).join(field_lines)}\n\n"
        "风险项：\n"
        f"{chr(10).join(risk_lines)}"
    )


def build_openai_compatible_summary(
    fields: ContractExtractedFields,
    risks: list[ReviewRiskItem],
) -> str:
    runtime = OpenAICompatibleRuntimeSettings(
        llm_base_url=settings.llm_base_url or "",
        llm_api_key=settings.llm_api_key or "",
        llm_model=settings.llm_model or "",
        llm_timeout_seconds=settings.llm_timeout_seconds,
    )
    return build_openai_compatible_summary_with_settings(runtime, fields, risks)


def build_openai_compatible_summary_with_settings(
    runtime,
    fields: ContractExtractedFields,
    risks: list[ReviewRiskItem],
    perspective_code: str = DEFAULT_PERSPECTIVE,
) -> str:
    if not runtime.llm_base_url or not runtime.llm_api_key or not runtime.llm_model:
        raise OpenAICompatibleLlmError("LLM provider is not fully configured.")

    perspective = get_perspective(perspective_code)
    payload = {
        "model": runtime.llm_model,
        "messages": [
            {
                "role": "system",
                "content": perspective.system_prompt,
            },
            {
                "role": "user",
                "content": _build_prompt(fields, risks, perspective_code=perspective_code),
            },
        ],
        "temperature": 0.2,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = runtime.llm_base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime.llm_api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=runtime.llm_timeout_seconds) as resp:
            response_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise OpenAICompatibleLlmError(f"LLM request failed with status {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc.reason}") from exc
    except Exception as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc}") from exc

    try:
        parsed = json.loads(response_body)
        content = parsed["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise OpenAICompatibleLlmError("LLM response format is invalid.") from exc

    if not content:
        raise OpenAICompatibleLlmError("LLM returned empty content.")
    return content


def build_openai_compatible_risk_supplements(
    raw_text: str,
    fields: ContractExtractedFields,
    existing_risks: list[ReviewRiskItem],
) -> list[dict]:
    runtime = OpenAICompatibleRuntimeSettings(
        llm_base_url=settings.llm_base_url or "",
        llm_api_key=settings.llm_api_key or "",
        llm_model=settings.llm_model or "",
        llm_timeout_seconds=settings.llm_timeout_seconds,
    )
    return build_openai_compatible_risk_supplements_with_settings(runtime, raw_text, fields, existing_risks)


def build_openai_compatible_risk_supplements_with_settings(
    runtime,
    raw_text: str,
    fields: ContractExtractedFields,
    existing_risks: list[ReviewRiskItem],
    perspective_code: str = DEFAULT_PERSPECTIVE,
) -> list[dict]:
    if not runtime.llm_base_url or not runtime.llm_api_key or not runtime.llm_model:
        raise OpenAICompatibleLlmError("LLM provider is not fully configured.")

    perspective = get_perspective(perspective_code)
    existing_risk_lines = [
        f"- {risk.code} | {risk.title} | {risk.level}"
        for risk in existing_risks
    ] or ["- 当前暂无已识别风险"]

    perspective_focus = {
        "enterprise": "从企业视角审查合同，重点关注商业风险、合规性和条款对等性。",
        "individual": "从个人视角审查合同，重点关注报酬保障、责任边界和退出机制。",
        "worker": "从劳动者视角审查合同，重点关注工资支付、劳动安全、社保和工伤赔偿。",
    }
    focus = perspective_focus.get(perspective_code, perspective_focus["enterprise"])

    prompt = (
        f"你是一名工程合同审查助手。请基于合同文本、结构化字段和已识别风险，"
        f"{focus}"
        f"补充最多3条额外风险项。要求：1. 只能补充，不要重复已有风险；"
        f"2. 输出必须是 JSON 数组；3. 每项字段固定为 "
        '{"code":"", "title":"", "level":"high|medium|low", "matched_text":"", "description":"", "recommendation":""}；'
        "4. 不要输出 markdown，不要输出解释文字。若无新增风险，输出 []。\n\n"
        f"结构化字段：{fields.model_dump_json(ensure_ascii=False)}\n"
        f"已识别风险：{chr(10).join(existing_risk_lines)}\n"
        "合同文本（节选）：\n"
        f"{raw_text[:5000]}"
    )
    payload = {
        "model": runtime.llm_model,
        "messages": [
            {
                "role": "system",
                "content": perspective.risk_system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.1,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = runtime.llm_base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime.llm_api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=runtime.llm_timeout_seconds) as resp:
            response_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise OpenAICompatibleLlmError(f"LLM request failed with status {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc.reason}") from exc
    except Exception as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc}") from exc

    try:
        parsed = json.loads(response_body)
        content = parsed["choices"][0]["message"]["content"].strip()
        risk_items = json.loads(content)
    except Exception as exc:
        raise OpenAICompatibleLlmError("LLM risk response format is invalid.") from exc

    if not isinstance(risk_items, list):
        raise OpenAICompatibleLlmError("LLM risk response is not a JSON array.")
    return risk_items


def build_openai_compatible_suggestions_with_settings(
    runtime,
    raw_text: str,
    risks: list[ReviewRiskItem],
    perspective_code: str = DEFAULT_PERSPECTIVE,
) -> dict[str, str]:
    """Generate specific modification suggestions for each risk item."""
    if not runtime.llm_base_url or not runtime.llm_api_key or not runtime.llm_model:
        raise OpenAICompatibleLlmError("LLM provider is not fully configured.")

    if not risks:
        return {}

    risk_lines = [
        f'- [{r.code}] {r.title}({r.level}): {r.description}; matched: "{r.matched_text or "-"}"; direction: {r.recommendation}'
        for r in risks
    ]

    perspective_context = {
        "enterprise": "from enterprise compliance and risk control perspective",
        "individual": "from individual rights protection perspective",
        "worker": "from worker rights protection perspective",
    }
    context = perspective_context.get(perspective_code, perspective_context["enterprise"])

    prompt = (
        f"You are a contract review assistant. {context}, "
        "generate specific modification suggestion text for each identified risk.\n"
        "Requirements:\n"
        "1. Output a JSON object, key=risk code, value=suggestion text\n"
        "2. Suggestions should be specific and directly usable, e.g. 'suggest modifying clause X to: ...' or 'suggest adding: ...'\n"
        "3. Each suggestion under 80 Chinese characters\n"
        "4. Output JSON only, no markdown, no explanation\n"
        "5. If no specific suggestion possible, set value to null\n\n"
        f"Risks:\n{chr(10).join(risk_lines)}\n\n"
        f"Contract text (excerpt):\n{raw_text[:3000]}"
    )

    payload = {
        "model": runtime.llm_model,
        "messages": [
            {"role": "system", "content": "严谨的合同修改建议助手，只输出JSON对象。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = runtime.llm_base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime.llm_api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=runtime.llm_timeout_seconds) as resp:
            response_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise OpenAICompatibleLlmError(f"LLM request failed with status {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc.reason}") from exc
    except Exception as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc}") from exc

    try:
        parsed = json.loads(response_body)
        content = parsed["choices"][0]["message"]["content"].strip()
        suggestions = json.loads(content)
    except Exception as exc:
        raise OpenAICompatibleLlmError("LLM suggestion response invalid.") from exc

    if not isinstance(suggestions, dict):
        raise OpenAICompatibleLlmError("LLM suggestion response is not a JSON object.")
    return {k: v for k, v in suggestions.items() if isinstance(v, str) and v.strip()}


def build_openai_compatible_plain_explanations_with_settings(
    runtime,
    raw_text: str,
    risks: list[ReviewRiskItem],
    perspective_code: str = DEFAULT_PERSPECTIVE,
) -> dict[str, str]:
    """Generate plain-language explanations for each risk item."""
    if not runtime.llm_base_url or not runtime.llm_api_key or not runtime.llm_model:
        raise OpenAICompatibleLlmError("LLM provider is not fully configured.")

    if not risks:
        return {}

    risk_lines = [
        f'- [{r.code}] {r.title}({r.level}): {r.description}; matched: "{r.matched_text or "-"}"; suggestion: {r.recommendation}'
        for r in risks
    ]

    perspective_context = {
        "enterprise": "from an enterprise compliance perspective",
        "individual": "from an individual rights protection perspective, using simple everyday language",
        "worker": "from a worker rights protection perspective, using very simple language that any worker can understand",
    }
    context = perspective_context.get(perspective_code, perspective_context["individual"])

    prompt = (
        f"You are a contract review assistant. {context}, "
        "translate each identified risk into plain, easy-to-understand Chinese.\n"
        "Requirements:\n"
        "1. Output a JSON object, key=risk code, value=plain explanation text\n"
        "2. Each explanation should answer: 'What does this mean for me?' and 'What should I watch out for?'\n"
        "3. Use everyday language, avoid legal jargon\n"
        "4. Each explanation under 60 Chinese characters\n"
        "5. Output JSON only, no markdown, no explanation\n\n"
        f"Risks:\n{chr(10).join(risk_lines)}\n\n"
        f"Contract text (excerpt):\n{raw_text[:3000]}"
    )

    payload = {
        "model": runtime.llm_model,
        "messages": [
            {"role": "system", "content": "你是一个合同解读助手，用大白话解释合同条款，只输出JSON对象。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = runtime.llm_base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime.llm_api_key}",
        },
    )
    try:
        with request.urlopen(req, timeout=runtime.llm_timeout_seconds) as resp:
            response_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise OpenAICompatibleLlmError(f"LLM request failed with status {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc.reason}") from exc
    except Exception as exc:
        raise OpenAICompatibleLlmError(f"LLM request failed: {exc}") from exc

    try:
        parsed = json.loads(response_body)
        content = parsed["choices"][0]["message"]["content"].strip()
        explanations = json.loads(content)
    except Exception as exc:
        raise OpenAICompatibleLlmError("LLM explanation response invalid.") from exc

    if not isinstance(explanations, dict):
        raise OpenAICompatibleLlmError("LLM explanation response is not a JSON object.")
    return {k: v for k, v in explanations.items() if isinstance(v, str) and v.strip()}
