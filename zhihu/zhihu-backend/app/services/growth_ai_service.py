from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.db.session import SessionLocal
from app.schemas.growth import GrowthEmotionCandidate, GrowthWorkCandidate
from app.services.ai_configuration_service import (
    EffectiveAIConfiguration,
    effective_ai_configuration,
    record_ai_invocation,
    record_unavailable_ai_invocation,
)


FEATURE = "growth_work_intake"
PROMPT_VERSION = "growth-work-intake-v1"
MODEL_TIMEOUT = httpx.Timeout(connect=10, read=75, write=20, pool=10)
MAX_CANDIDATES = 8


class _ModelCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: Literal["high", "medium", "low", "unknown"] = "unknown"
    energy_level: Literal["high", "medium", "low", "unknown"] = "unknown"
    selection_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class _ModelEmotion(BaseModel):
    detected: bool = False
    summary: Optional[str] = Field(default=None, max_length=500)
    deidentified_fact: Optional[str] = Field(default=None, max_length=1000)


class _ModelPayload(BaseModel):
    candidates: list[_ModelCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)
    emotion: _ModelEmotion = Field(default_factory=_ModelEmotion)


@dataclass(frozen=True)
class GrowthAnalysisResult:
    candidates: list[GrowthWorkCandidate]
    emotion: GrowthEmotionCandidate
    analysis_mode: Literal["rules", "ai"]
    parser_version: str
    provider_name: Optional[str] = None
    model: Optional[str] = None


_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_CARD = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)(?:\d[ -]?){14,20}(?!\d)")
_EMOTION_WORDS = (
    "烦", "焦虑", "委屈", "生气", "愤怒", "难受", "崩溃", "压力", "内耗", "害怕", "失望", "累",
)
_URGENT_WORDS = ("今天", "马上", "尽快", "截止", "紧急", "立刻", "老板要", "客户等")
_HIGH_IMPACT_WORDS = ("客户", "上线", "交付", "汇报", "评审", "故障", "合同", "老板", "跨部门")
_LOW_ENERGY_WORDS = ("整理", "归档", "补充", "同步", "更新文档", "填表")
_WORK_WORDS = (
    "客户", "项目", "需求", "方案", "文档", "会议", "汇报", "评审", "上线", "交付", "故障",
    "合同", "数据", "代码", "测试", "排期", "沟通", "同步", "整理", "准备", "完成", "推进",
    "处理", "修改", "确认", "跟进", "分析", "设计", "开发", "复盘", "学习", "老板", "同事",
)


def redact_growth_text(text: str) -> str:
    redacted = _PHONE.sub("[手机号已隐藏]", text)
    redacted = _EMAIL.sub("[邮箱已隐藏]", redacted)
    redacted = _ID_CARD.sub("[证件号已隐藏]", redacted)
    redacted = _ACCOUNT.sub("[账号已隐藏]", redacted)
    return redacted


def _candidate_key(index: int, title: str) -> str:
    digest = hashlib.sha256(f"{index}:{title}".encode()).hexdigest()[:16]
    return f"candidate-{index + 1}-{digest}"


def _clean_part(value: str) -> str:
    return re.sub(r"^[\s\-—•●*\d.、()（）]+|\s+$", "", value)


def _rule_parts(text: str) -> list[str]:
    parts = []
    for value in re.split(r"[\n；;]+|(?<=[。！？!?])", text):
        cleaned = _clean_part(value).strip("。！？!?，,")
        # Emotion is detected separately and must not become a work title. For
        # mixed sentences, keep only clauses that still describe work or action.
        clauses = [clause.strip() for clause in re.split(r"[，,]", cleaned) if clause.strip()]
        work_clauses = [
            clause
            for clause in clauses
            if not any(word in clause for word in _EMOTION_WORDS)
            or any(word in clause for word in _WORK_WORDS)
        ]
        cleaned = "，".join(work_clauses)
        if len(cleaned) < 3:
            continue
        if any(word in cleaned for word in _EMOTION_WORDS) and not any(
            word in cleaned for word in _WORK_WORDS
        ):
            continue
        if cleaned not in parts:
            parts.append(cleaned)
    return parts[:MAX_CANDIDATES]


def _rule_candidate(index: int, part: str) -> GrowthWorkCandidate:
    urgent = any(word in part for word in _URGENT_WORDS)
    high_impact = any(word in part for word in _HIGH_IMPACT_WORDS)
    impact = "high" if high_impact else "medium" if urgent else "unknown"
    energy = "low" if any(word in part for word in _LOW_ENERGY_WORDS) else "unknown"
    reason_bits = []
    if urgent:
        reason_bits.append("包含明确时效信号")
    if high_impact:
        reason_bits.append("涉及客户、交付或关键沟通")
    if not reason_bits:
        reason_bits.append("从原始输入中提取，仍需你判断优先级")
    title = part[:120]
    return GrowthWorkCandidate(
        candidate_key=_candidate_key(index, title),
        title=title,
        description=part if len(part) > 120 else None,
        fact_excerpt=part[:500],
        impact_level=impact,
        energy_level=energy,
        priority_order=(index + 1) * 10,
        selection_reason="；".join(reason_bits),
        confidence=0.55 if reason_bits == ["从原始输入中提取，仍需你判断优先级"] else 0.7,
    )


def analyze_with_rules(text: str) -> GrowthAnalysisResult:
    sanitized = redact_growth_text(text.strip())
    parts = _rule_parts(sanitized)
    if not parts:
        raise HTTPException(status_code=422, detail="没有识别到可整理的工作内容")
    candidates = [_rule_candidate(index, part) for index, part in enumerate(parts)]
    emotion_detected = any(word in sanitized for word in _EMOTION_WORDS)
    emotion = GrowthEmotionCandidate(
        detected=emotion_detected,
        summary="检测到情绪表达；默认不会保存原文，也不会进入周报或职业资产。" if emotion_detected else None,
        deidentified_fact=None,
    )
    return GrowthAnalysisResult(
        candidates=candidates,
        emotion=emotion,
        analysis_mode="rules",
        parser_version=f"{PROMPT_VERSION}-rules",
    )


def _json_payload(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("ModelResponseContentMissing")
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("ModelResponseInvalidJSON")
    return payload


def _audit(
    configuration: EffectiveAIConfiguration | None,
    *,
    user_id: int,
    status: str,
    latency_ms: int = 0,
    usage: dict | None = None,
    error_code: str | None = None,
) -> None:
    with SessionLocal() as audit_db:
        if configuration is None:
            record_unavailable_ai_invocation(
                audit_db,
                feature=FEATURE,
                error_code=error_code or "AIConfigurationUnavailable",
                user_id=user_id,
            )
        else:
            record_ai_invocation(
                audit_db,
                configuration,
                feature=FEATURE,
                status=status,
                latency_ms=latency_ms,
                usage=usage,
                error_code=error_code,
                user_id=user_id,
            )


def analyze_with_ai(*, user_id: int, text: str) -> GrowthAnalysisResult:
    with SessionLocal() as configuration_db:
        configuration = effective_ai_configuration(configuration_db)
    if configuration is None:
        _audit(None, user_id=user_id, status="failed", error_code="AIConfigurationUnavailable")
        raise HTTPException(status_code=503, detail="成长守护 AI 当前未配置，可改用本地整理")

    redacted = redact_growth_text(text.strip())
    started = time.monotonic()
    try:
        response = httpx.post(
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {configuration.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": configuration.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是成长守护的工作整理助手。只从用户提供的文字提取候选，不得补写事实、数字、结果、角色或截止时间。"
                            "输出 1 到 8 个工作候选，给出影响和精力建议及可核对理由；情绪只做中性识别，不评判用户。"
                            "原始情绪不得混入任务标题，不得把候选写成已确认或已完成。"
                            '输出严格 JSON：{"candidates":[{"title":"", "description":null, "fact_excerpt":"输入连续短句",'
                            '"impact_level":"high|medium|low|unknown","energy_level":"high|medium|low|unknown",'
                            '"selection_reason":"", "confidence":0到1}],'
                            '"emotion":{"detected":true或false,"summary":字符串或null,"deidentified_fact":字符串或null}}。'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"text": redacted}, ensure_ascii=False),
                    },
                ],
                "temperature": 0,
                "max_tokens": 1800,
            },
            timeout=MODEL_TIMEOUT,
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"}:
            raise ValueError(f"ModelFinishReason:{choice.get('finish_reason')}")
        payload = _ModelPayload.model_validate(_json_payload(choice["message"]["content"]))
        candidates = []
        for item in payload.candidates:
            # A model response is still only a candidate. Reject an emotion-only
            # title rather than persisting it as a task when the model drifts.
            if any(word in item.title for word in _EMOTION_WORDS) and not any(
                word in item.title for word in _WORK_WORDS
            ):
                continue
            index = len(candidates)
            candidates.append(
                GrowthWorkCandidate(
                    candidate_key=_candidate_key(index, item.title),
                    title=item.title,
                    description=item.description,
                    fact_excerpt=item.fact_excerpt,
                    impact_level=item.impact_level,
                    energy_level=item.energy_level,
                    priority_order=(index + 1) * 10,
                    selection_reason=item.selection_reason,
                    confidence=item.confidence,
                )
            )
        if not candidates:
            raise ValueError("ModelResponseContainsNoWorkCandidate")
        _audit(
            configuration,
            user_id=user_id,
            status="success",
            latency_ms=round((time.monotonic() - started) * 1000),
            usage=body.get("usage") if isinstance(body, dict) else None,
        )
        return GrowthAnalysisResult(
            candidates=candidates,
            emotion=GrowthEmotionCandidate(
                detected=payload.emotion.detected,
                summary=(
                    "检测到情绪表达；默认不会保存原文，也不会进入周报或职业资产。"
                    if payload.emotion.detected
                    else None
                ),
                deidentified_fact=payload.emotion.deidentified_fact,
            ),
            analysis_mode="ai",
            parser_version=PROMPT_VERSION,
            provider_name=configuration.provider_name,
            model=configuration.model,
        )
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        _audit(
            configuration,
            user_id=user_id,
            status="failed",
            latency_ms=round((time.monotonic() - started) * 1000),
            error_code=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="AI 没有返回稳定的工作候选，请重试或改用本地整理") from exc
