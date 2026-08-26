from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Literal, Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.db.session import SessionLocal
from app.schemas.growth import (
    GrowthEmotionCandidate,
    GrowthResourceLink,
    GrowthWorkCandidate,
    GrowthWorkNodeCandidate,
)
from app.services.ai_configuration_service import (
    EffectiveAIConfiguration,
    effective_ai_configuration,
    record_ai_invocation,
    record_unavailable_ai_invocation,
)


FEATURE = "growth_work_intake"
MATERIAL_FEATURE = "growth_work_material"
PROMPT_VERSION = "growth-work-intake-v1"
RULE_PARSER_VERSION = "growth-work-intake-rules-v2"
MATERIAL_PROMPT_VERSION = "growth-work-material-ai-v5"
MODEL_TIMEOUT = httpx.Timeout(connect=10, read=75, write=20, pool=10)
# 单批安全边界，与确认接口保持一致；这不是“只允许保留几项任务”的产品规则。
MAX_CANDIDATES = 50
MATERIAL_CHUNK_CHARS = 16000
MATERIAL_MAX_STATEMENTS_PER_CHUNK = 6
MATERIAL_MAX_TARGETS_PER_CHUNK = 4
MATERIAL_MAX_UNMATCHED_PER_CHUNK = 3
MATERIAL_MAX_NODES_PER_WORKSTREAM = 3
# DeepSeek Pro 在四份真实材料中出现过 2588 token 的成功响应，
# 2600 会在同等输入上偶发以 2601 token 触发 length。4200 仍是单次
# 有界输出，不通过整份重试放大延迟，同时为供应商输出波动留出余量。
MATERIAL_RESPONSE_MAX_TOKENS = 4200
MATERIAL_REPAIR_MAX_TOKENS = 2000
MATERIAL_MAX_TARGETS = 120
MATERIAL_MAX_PROJECTS = 20
MATERIAL_REPAIR_ATTEMPTS = 1


class _ModelNode(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    time_hint: Optional[str] = Field(default=None, max_length=200)


class _ModelCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: Literal["high", "medium", "low", "unknown"] = "unknown"
    energy_level: Literal["high", "medium", "low", "unknown"] = "unknown"
    selection_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)
    nodes: list[_ModelNode] = Field(default_factory=list, max_length=50)
    resource_links: list[GrowthResourceLink] = Field(default_factory=list, max_length=50)
    open_questions: list[str] = Field(default_factory=list, max_length=50)
    tracking_rule: Optional[str] = Field(default=None, max_length=500)


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


class _ModelMaterialStatement(BaseModel):
    statement_type: Literal[
        "confirmed_fact",
        "decision",
        "proposal",
        "open_question",
        "vendor_claim",
        "scope_change",
        "action",
        "conflict",
    ]
    text: str = Field(min_length=1, max_length=2000)
    evidence_excerpt: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class _ModelMaterialTargetAnalysis(BaseModel):
    target_key: str = Field(min_length=1, max_length=100)
    evidence_excerpts: list[str] = Field(default_factory=list, max_length=20)
    relevance_reason: str = Field(min_length=1, max_length=1000)
    priority_axis: Literal["high", "low", "unknown"] = "unknown"
    progress_health: Literal["healthy", "at_risk", "unknown"] = "unknown"
    placement_reason: str = Field(default="证据不足，保持待判断", max_length=1000)
    impact_kind: Literal[
        "advanced", "setback", "redirected", "context", "no_change", "unknown"
    ] = "unknown"
    headline: str = Field(default="本次变化尚待判断", max_length=500)
    causal_reason: str = Field(default="原文证据不足", max_length=2000)
    previous_state: Optional[str] = Field(default=None, max_length=2000)
    current_state: Optional[str] = Field(default=None, max_length=2000)
    next_gap: Optional[str] = Field(default=None, max_length=2000)
    proposed_node_status: Optional[
        Literal["planned", "in_progress", "blocked", "completed", "cancelled"]
    ] = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class _ModelMaterialProjectAnalysis(BaseModel):
    project_key: str = Field(min_length=1, max_length=100)
    evidence_excerpts: list[str] = Field(default_factory=list, max_length=20)
    impact_kind: Literal[
        "advanced", "setback", "redirected", "context", "no_change", "unknown"
    ] = "unknown"
    headline: str = Field(default="本次对项目总目标的作用尚待判断", max_length=500)
    causal_reason: str = Field(default="原文证据不足", max_length=2000)
    previous_state: Optional[str] = Field(default=None, max_length=2000)
    current_state: Optional[str] = Field(default=None, max_length=2000)
    next_gap: Optional[str] = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class _ModelUnmatchedWorkstream(BaseModel):
    kind: Literal["workstream"]
    lifecycle: Literal["active", "selected", "discovery"]
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1000)
    objective: Optional[str] = Field(default=None, max_length=2000)
    success_criteria: list[str] = Field(default_factory=list, max_length=20)
    strategy_summary: Optional[str] = Field(default=None, max_length=2000)
    key_constraints: list[str] = Field(default_factory=list, max_length=20)
    evidence_excerpt: str = Field(min_length=1, max_length=2000)
    suggested_nodes: list[str] = Field(default_factory=list, max_length=20)
    priority_axis: Literal["high", "low", "unknown"] = "unknown"
    progress_health: Literal["healthy", "at_risk", "unknown"] = "unknown"
    placement_reason: str = Field(default="证据不足，保持待判断", max_length=1000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class _ModelMaterialPayload(BaseModel):
    statements: list[_ModelMaterialStatement] = Field(default_factory=list, max_length=200)
    project_analyses: list[_ModelMaterialProjectAnalysis] = Field(
        default_factory=list, max_length=MATERIAL_MAX_PROJECTS
    )
    target_analyses: list[_ModelMaterialTargetAnalysis] = Field(default_factory=list, max_length=120)
    unmatched_workstreams: list[_ModelUnmatchedWorkstream] = Field(default_factory=list, max_length=30)
    priority_axis: Literal["high", "low", "unknown"] = "unknown"
    progress_health: Literal["healthy", "at_risk", "unknown"] = "unknown"
    placement_reason: str = Field(default="材料不足，保持待判断", max_length=1000)
    placement_evidence_excerpt: Optional[str] = Field(default=None, max_length=2000)


@dataclass(frozen=True)
class GrowthMaterialStatementCandidate:
    statement_type: Literal[
        "confirmed_fact",
        "decision",
        "proposal",
        "open_question",
        "vendor_claim",
        "scope_change",
        "action",
        "conflict",
    ]
    text: str
    evidence_excerpt: str
    confidence: float


@dataclass(frozen=True)
class GrowthMaterialTargetContext:
    target_key: str
    target_type: Literal["work_item", "node"]
    target_id: int
    title: str
    parent_title: Optional[str] = None
    current_status: Optional[str] = None
    explicitly_selected: bool = False
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    objective: Optional[str] = None
    success_criteria: tuple[str, ...] = ()
    strategy_summary: Optional[str] = None
    key_constraints: tuple[str, ...] = ()
    recent_progress: tuple[dict[str, Any], ...] = ()
    pending_suggestions: tuple[dict[str, Any], ...] = ()
    last_advancement_at: Optional[str] = None


@dataclass(frozen=True)
class GrowthMaterialProjectContext:
    project_key: str
    project_id: int
    account_name: str
    project_name: str
    objective: str
    version: int = 1
    latest_confirmed_event_id: Optional[int] = None
    success_criteria: tuple[str, ...] = ()
    strategy_summary: Optional[str] = None
    key_constraints: tuple[str, ...] = ()
    recent_progress: tuple[dict[str, Any], ...] = ()
    pending_suggestions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class GrowthMaterialProjectAnalysis:
    project_key: str
    evidence_excerpts: list[str]
    impact_kind: Literal[
        "advanced", "setback", "redirected", "context", "no_change", "unknown"
    ]
    headline: str
    causal_reason: str
    previous_state: Optional[str]
    current_state: Optional[str]
    next_gap: Optional[str]
    confidence: float


@dataclass(frozen=True)
class GrowthMaterialTargetAnalysis:
    target_key: str
    evidence_excerpts: list[str]
    relevance_reason: str
    priority_axis: Literal["high", "low", "unknown"]
    progress_health: Literal["healthy", "at_risk", "unknown"]
    placement_reason: str
    proposed_node_status: Optional[
        Literal["planned", "in_progress", "blocked", "completed", "cancelled"]
    ]
    confidence: float
    impact_kind: Literal[
        "advanced", "setback", "redirected", "context", "no_change", "unknown"
    ] = "unknown"
    headline: str = "本次变化尚待判断"
    causal_reason: str = "原文证据不足"
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    next_gap: Optional[str] = None


@dataclass(frozen=True)
class GrowthMaterialUnmatchedWorkstream:
    title: str
    summary: str
    evidence_excerpt: str
    suggested_nodes: list[str]
    priority_axis: Literal["high", "low", "unknown"]
    progress_health: Literal["healthy", "at_risk", "unknown"]
    placement_reason: str
    confidence: float
    objective: Optional[str] = None
    success_criteria: tuple[str, ...] = ()
    strategy_summary: Optional[str] = None
    key_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrowthMaterialAIResult:
    statements: list[GrowthMaterialStatementCandidate]
    target_analyses: list[GrowthMaterialTargetAnalysis]
    unmatched_workstreams: list[GrowthMaterialUnmatchedWorkstream]
    priority_axis: Literal["high", "low", "unknown"]
    progress_health: Literal["healthy", "at_risk", "unknown"]
    placement_reason: str
    placement_evidence_excerpt: Optional[str]
    provider_name: str
    model: str
    parser_version: str = MATERIAL_PROMPT_VERSION
    repaired: bool = False
    attempt_count: int = 1
    partial: bool = False
    partial_error_codes: tuple[str, ...] = ()
    project_analyses: list[GrowthMaterialProjectAnalysis] = field(default_factory=list)


_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d){8}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ID_CARD = re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)(?:\d[ -]?){14,20}(?!\d)")
_URL = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_NUMBERED_SECTION = re.compile(r"(?m)^\s*(\d{1,2})\s*[\u3001.\uff0e)]\s*")
_TIME_HINT = re.compile(
    r"^(?P<hint>(?:本周|今天|明天|后天|周[一二三四五六日天])(?:上午|中午|下午|晚上)?)"
)
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


def _node_key(candidate_index: int, node_index: int, title: str) -> str:
    digest = hashlib.sha256(f"{candidate_index}:{node_index}:{title}".encode()).hexdigest()[:16]
    return f"node-{node_index + 1}-{digest}"


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
        description=part[:2000] if len(part) > 120 else None,
        fact_excerpt=part[:500],
        impact_level=impact,
        energy_level=energy,
        priority_order=(index + 1) * 10,
        selection_reason="；".join(reason_bits),
        confidence=0.55 if reason_bits == ["从原始输入中提取，仍需你判断优先级"] else 0.7,
        nodes=[
            GrowthWorkNodeCandidate(
                node_key=_node_key(index, 0, title),
                title=title,
                priority_order=10,
                time_hint=_time_hint(title),
            )
        ],
    )


def _time_hint(value: str) -> str | None:
    matched = _TIME_HINT.match(value)
    return matched.group("hint") if matched else None


def _split_section_chunks(value: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    depth = 0
    for character in value:
        if character in "（(":
            depth += 1
        elif character in "）)" and depth:
            depth -= 1
        if depth == 0 and (character.isspace() or character in "；;。！？!?"):
            cleaned = "".join(current).strip(" ，,。！？!?；;")
            if cleaned:
                chunks.append(cleaned)
            current = []
        else:
            current.append(character)
    cleaned = "".join(current).strip(" ，,。！？!?；;")
    if cleaned:
        chunks.append(cleaned)
    return chunks


def _looks_like_action(value: str) -> bool:
    return bool(_TIME_HINT.match(value)) or value.startswith(
        ("整理", "完成", "推进", "确认", "跟进", "处理", "修改", "准备", "开始", "开发", "设计", "支持", "分析", "学习")
    )


def _is_tracking_rule(value: str) -> bool:
    return any(marker in value for marker in ("持续盯", "持续跟进", "持续跟踪", "定期跟进", "长期跟踪"))


def _is_open_question(value: str) -> bool:
    cleaned = value.strip("（）() ")
    return cleaned.startswith(("等", "等待", "待确认")) or (
        cleaned.startswith("需要") and any(marker in cleaned for marker in ("支持", "确认", "资源"))
    )


def _inferred_node_dependencies(
    node_titles: list[str],
    node_keys: list[str],
    index: int,
) -> list[str]:
    title = node_titles[index]
    if index == 0:
        return []
    if any(marker in title for marker in ("发给", "发送", "提交", "交付")):
        shared_objects = [object_name for object_name in ("问卷", "方案", "文档", "报告", "材料") if object_name in title]
        for prior_index in range(index - 1, -1, -1):
            if any(object_name in node_titles[prior_index] for object_name in shared_objects):
                return [node_keys[prior_index]]
    if any(marker in title for marker in ("整理到", "汇总到", "形成问卷", "形成方案")):
        return node_keys[:index]
    if any(marker in title for marker in ("开始", "启动", "跑初版")):
        for prior_index in range(index - 1, -1, -1):
            if any(marker in node_titles[prior_index] for marker in ("确认", "方案", "设计", "评审")):
                return [node_keys[prior_index]]
    return []


def _numbered_sections(text: str) -> list[str]:
    matches = list(_NUMBERED_SECTION.finditer(text))
    if not matches:
        return []
    return [
        text[matched.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()
        for index, matched in enumerate(matches)
        if text[matched.end() : matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip()
    ][:MAX_CANDIDATES]


def _numbered_candidate(index: int, section: str) -> GrowthWorkCandidate:
    raw_urls = [url.rstrip("，,。；;）)") for url in _URL.findall(section)]
    without_urls = _URL.sub(" ", section)
    chunks = _split_section_chunks(without_urls)
    if not chunks:
        raise ValueError("NumberedSectionContainsOnlyLinks")

    first = chunks[0]
    dependency_match = re.match(r"^(.{2,24}?)(等.+)$", first)
    if dependency_match:
        title = dependency_match.group(1).strip()
        details = [dependency_match.group(2), *chunks[1:]]
    elif len(chunks) > 1 and not _looks_like_action(first):
        title = first
        details = chunks[1:]
    elif len(chunks) > 1:
        title = " / ".join(chunks[:2])[:120]
        details = chunks
    else:
        title = first[:120]
        details = []

    node_titles: list[str] = []
    open_questions: list[str] = []
    tracking_rule: str | None = None
    for detail in details:
        cleaned = detail.strip("（）() ")
        if not cleaned:
            continue
        if _is_tracking_rule(cleaned):
            tracking_rule = cleaned
        elif _is_open_question(detail):
            open_questions.append(cleaned)
        else:
            normalized = re.sub(r"^(这边|并|然后|再)", "", cleaned).strip()
            if normalized and normalized not in node_titles:
                node_titles.append(normalized)
    if not node_titles:
        node_titles.append(title)

    source_text = re.sub(r"\s+", " ", without_urls).strip()
    urgent = any(word in source_text for word in _URGENT_WORDS)
    high_impact = any(word in source_text for word in _HIGH_IMPACT_WORDS)
    node_keys = [
        _node_key(index, node_index, node_title)
        for node_index, node_title in enumerate(node_titles)
    ]
    return GrowthWorkCandidate(
        candidate_key=_candidate_key(index, title),
        title=title,
        description=section.strip()[:20000] if section.strip() != title else None,
        fact_excerpt=source_text[:500],
        impact_level="high" if high_impact else "medium" if urgent else "unknown",
        energy_level="low" if any(word in source_text for word in _LOW_ENERGY_WORDS) else "unknown",
        priority_order=(index + 1) * 10,
        selection_reason="按你的显式编号保留为一个长期事项；段内动作仅作为待确认节点",
        confidence=0.85,
        nodes=[
            GrowthWorkNodeCandidate(
                node_key=node_keys[node_index],
                title=node_title,
                priority_order=(node_index + 1) * 10,
                depends_on_node_keys=_inferred_node_dependencies(
                    node_titles,
                    node_keys,
                    node_index,
                ),
                time_hint=_time_hint(node_title),
            )
            for node_index, node_title in enumerate(node_titles)
        ],
        resource_links=[GrowthResourceLink(url=url) for url in dict.fromkeys(raw_urls)],
        open_questions=list(dict.fromkeys(open_questions)),
        tracking_rule=tracking_rule,
    )


def analyze_with_rules(text: str) -> GrowthAnalysisResult:
    sanitized = redact_growth_text(text.strip())
    numbered = _numbered_sections(sanitized)
    if numbered:
        try:
            candidates = [_numbered_candidate(index, section) for index, section in enumerate(numbered)]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="没有识别到可整理的工作内容") from exc
    else:
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
        parser_version=RULE_PARSER_VERSION,
    )


def _json_payload(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError("ModelResponseContentMissing")
    stripped = content.strip().lstrip("\ufeff")
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # A few OpenAI-compatible providers prepend a short explanation even
        # when the prompt asks for JSON. Recover only a complete, balanced JSON
        # object; never attempt to invent or auto-complete missing fields.
        start = stripped.find("{")
        if start < 0:
            raise ValueError("ModelResponseInvalidJSON")
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index, char in enumerate(stripped[start:], start=start):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise ValueError("ModelResponseInvalidJSON")
        try:
            payload = json.loads(stripped[start:end])
        except json.JSONDecodeError as exc:
            raise ValueError("ModelResponseInvalidJSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("ModelResponseInvalidJSON")
    return payload


def _audit(
    configuration: EffectiveAIConfiguration | None,
    *,
    user_id: int,
    status: str,
    feature: str = FEATURE,
    latency_ms: int = 0,
    usage: dict | None = None,
    error_code: str | None = None,
) -> None:
    with SessionLocal() as audit_db:
        if configuration is None:
            record_unavailable_ai_invocation(
                audit_db,
                feature=feature,
                error_code=error_code or "AIConfigurationUnavailable",
                user_id=user_id,
            )
        else:
            record_ai_invocation(
                audit_db,
                configuration,
                feature=feature,
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
                            f"输出 1 到 {MAX_CANDIDATES} 个工作候选，完整保留可区分的事项，"
                            "用户有显式编号时优先把每个编号作为父事项，段内动作放入 nodes；"
                            "依赖或待确认信息放入 open_questions，持续跟踪要求放入 tracking_rule，链接放入 resource_links。"
                            "给出影响和精力建议及可核对理由；情绪只做中性识别，不评判用户。"
                            "原始情绪不得混入任务标题，不得把候选写成已确认或已完成。"
                            '输出严格 JSON：{"candidates":[{"title":"", "description":null, "fact_excerpt":"输入连续短句",'
                            '"impact_level":"high|medium|low|unknown","energy_level":"high|medium|low|unknown",'
                            '"selection_reason":"", "confidence":0到1,'
                            '"nodes":[{"title":"","time_hint":null}],'
                            '"resource_links":[{"url":"https://...","label":null}],'
                            '"open_questions":[],"tracking_rule":null}],'
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
            model_nodes = item.nodes or [_ModelNode(title=item.title)]
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
                    nodes=[
                        GrowthWorkNodeCandidate(
                            node_key=_node_key(index, node_index, node.title),
                            title=node.title,
                            priority_order=(node_index + 1) * 10,
                            depends_on_node_keys=[],
                            time_hint=node.time_hint,
                        )
                        for node_index, node in enumerate(model_nodes)
                    ],
                    resource_links=item.resource_links,
                    open_questions=item.open_questions,
                    tracking_rule=item.tracking_rule,
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


def _evidence_key(value: str) -> str:
    """Normalize formatting only; semantic paraphrases must still fail."""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def _base_evidence_units(original: str) -> list[str]:
    return [
        matched.group(0).strip()
        for matched in re.finditer(r"[^\n；;。！？!?]+(?:[\n；;。！？!?]|$)", original)
        if matched.group(0).strip()
    ]


def _evidence_units(original: str) -> list[str]:
    units = _base_evidence_units(original)
    # The model occasionally quotes two adjacent source sentences. Build small
    # continuous windows while keeping the returned evidence verbatim-local.
    windows: list[str] = []
    for start in range(len(units)):
        combined = ""
        for end in range(start, min(start + 4, len(units))):
            combined += units[end]
            if len(combined) <= 2000:
                windows.append(combined)
    return windows


def _material_evidence_catalog(
    original_chunk: str,
) -> tuple[list[dict[str, str]], dict[str, tuple[str, str]]]:
    """Assign compact local IDs to source units sent to the model.

    The model returns IDs instead of copying long evidence paragraphs.  The
    server still maps every ID back to a verbatim local excerpt before storing
    it, so titles and model summaries can never become evidence.
    """
    payload: list[dict[str, str]] = []
    lookup: dict[str, tuple[str, str]] = {}
    for index, original in enumerate(_base_evidence_units(original_chunk), start=1):
        evidence_id = f"E{index}"
        redacted = redact_growth_text(original)
        payload.append({"evidence_id": evidence_id, "text": redacted})
        lookup[evidence_id] = (original, redacted)
    return payload, lookup


def _restore_local_material_excerpt(original: str, redacted: str, evidence: str) -> str:
    """Map a redacted model quote back to a locally stored verbatim span.

    Exact quotes remain the primary path. The normalized fallback tolerates
    markdown bullets, whitespace and punctuation only; it deliberately does
    not accept a semantic paraphrase as evidence.
    """
    evidence = evidence.strip()
    if not evidence:
        raise ValueError("MaterialEvidenceMissing")
    if evidence in redacted:
        exact_candidates = [
            source
            for source in _evidence_units(original)
            if evidence in redact_growth_text(source)
        ]
        if exact_candidates:
            # Evidence IDs name one local source unit. Prefer that tight unit
            # over an earlier multi-sentence window that merely contains it.
            return min(exact_candidates, key=lambda source: len(_evidence_key(source)))[:2000]
    normalized_evidence = _evidence_key(evidence)
    if len(normalized_evidence) < 6:
        raise ValueError("MaterialEvidenceTooShort")
    candidates: list[tuple[int, float, str]] = []
    for source in _evidence_units(original):
        normalized_source = _evidence_key(redact_growth_text(source))
        if not normalized_source:
            continue
        if normalized_evidence in normalized_source:
            candidates.append((len(normalized_source) - len(normalized_evidence), 1.0, source))
            continue
        # Only accept a near-identical formatting variation. This is not used
        # to rescue general paraphrases.
        ratio = SequenceMatcher(None, normalized_evidence, normalized_source).ratio()
        length_ratio = min(len(normalized_evidence), len(normalized_source)) / max(
            len(normalized_evidence), len(normalized_source)
        )
        if ratio >= 0.96 and length_ratio >= 0.9:
            candidates.append((abs(len(normalized_source) - len(normalized_evidence)), ratio, source))
    if candidates:
        candidates.sort(key=lambda item: (item[0], -item[1], len(item[2])))
        return candidates[0][2][:2000]
    raise ValueError("MaterialEvidenceNotInRedactedSource")


def _material_chunks(text: str, *, max_chars: int = MATERIAL_CHUNK_CHARS) -> list[str]:
    """Split long minutes on headings/paragraphs without dropping source text."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("MaterialInputEmpty")
    paragraphs = re.split(r"(?=\n\s*(?:#{1,6}\s+|[一-鿿]、|\d{1,2}[.、]、?))|\n{2,}", stripped)
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _target_catalog_payload(
    target_catalog: list[GrowthMaterialTargetContext],
) -> list[dict[str, Any]]:
    return [
        {
            "target_key": target.target_key,
            "target_type": target.target_type,
            "title": target.title,
            "parent_title": target.parent_title,
            "current_status": target.current_status,
            "explicitly_selected": target.explicitly_selected,
            "account_name": target.account_name,
            "project_id": target.project_id,
            "objective": target.objective,
            "success_criteria": list(target.success_criteria),
            "strategy_summary": target.strategy_summary,
            "key_constraints": list(target.key_constraints),
            "recent_progress": list(target.recent_progress),
            "pending_suggestions": list(target.pending_suggestions),
            "last_advancement_at": target.last_advancement_at,
        }
        for target in target_catalog[:MATERIAL_MAX_TARGETS]
    ]


def _partition_confirmed_history(
    history: tuple[dict[str, Any], ...],
) -> dict[str, list[dict[str, Any]]]:
    """Expose chronology without letting a later record become `previous`.

    Catalog queries already cap each confirmed history at six rows.  Keeping
    every row in the prompt matters for backfilled meeting notes: the newest
    database record can have happened after the material currently being
    analysed and is therefore context, never the previous-state baseline.
    """
    rows = list(history[:6])
    return {
        "all": rows,
        "before": [
            row for row in rows if row.get("temporal_relation") == "before_material"
        ],
        "later": [
            row for row in rows if row.get("temporal_relation") == "after_material"
        ],
        "uncertain": [
            row
            for row in rows
            if row.get("temporal_relation")
            not in {"before_material", "after_material"}
        ],
    }


def _project_context_payload(
    project_catalog: list[GrowthMaterialProjectContext],
    target_catalog: list[GrowthMaterialTargetContext],
) -> list[dict[str, Any]]:
    """Build the project view from a human-confirmed project profile.

    Workstream goals remain subordinate context.  They must never be composed
    into a replacement for the independently authored project goal.
    """
    grouped_workstreams: dict[int, list[GrowthMaterialTargetContext]] = defaultdict(list)
    for target in target_catalog[:MATERIAL_MAX_TARGETS]:
        if target.target_type != "work_item":
            continue
        if target.project_id is not None:
            grouped_workstreams[target.project_id].append(target)

    contexts: list[dict[str, Any]] = []
    for project in project_catalog[:MATERIAL_MAX_PROJECTS]:
        workstreams = grouped_workstreams.get(project.project_id, [])
        project_history = _partition_confirmed_history(project.recent_progress)
        contexts.append(
            {
                "project_key": project.project_key,
                "account_name": project.account_name,
                "project_name": project.project_name,
                "base_project_version": project.version,
                "base_confirmed_event_id": project.latest_confirmed_event_id,
                "project_objective": {
                    "source": "human_confirmed_project_profile",
                    "objective": project.objective,
                    "success_criteria": list(project.success_criteria),
                    "strategy_summary": project.strategy_summary,
                    "key_constraints": list(project.key_constraints),
                },
                "confirmed_project_history": project_history["all"],
                "previous_confirmed_project_history": project_history["before"],
                "later_confirmed_project_context": project_history["later"],
                "same_time_or_undated_project_context": project_history["uncertain"],
                "latest_confirmed_project_progress": (
                    project_history["before"][0] if project_history["before"] else None
                ),
                "pending_project_suggestions": list(project.pending_suggestions[:6]),
                "latest_pending_project_suggestion": (
                    project.pending_suggestions[0] if project.pending_suggestions else None
                ),
                "workstreams": [
                    {
                        "target_key": item.target_key,
                        "title": item.title,
                        "current_status": item.current_status,
                        "confirmed_progress_history": (
                            _partition_confirmed_history(item.recent_progress)["all"]
                        ),
                        "previous_confirmed_history": (
                            _partition_confirmed_history(item.recent_progress)["before"]
                        ),
                        "later_confirmed_context": (
                            _partition_confirmed_history(item.recent_progress)["later"]
                        ),
                        "same_time_or_undated_confirmed_context": (
                            _partition_confirmed_history(item.recent_progress)["uncertain"]
                        ),
                        "latest_confirmed_progress": (
                            _partition_confirmed_history(item.recent_progress)["before"][0]
                            if _partition_confirmed_history(item.recent_progress)["before"]
                            else None
                        ),
                        "pending_suggestions": list(item.pending_suggestions[:6]),
                        "latest_pending_suggestion": (
                            item.pending_suggestions[0] if item.pending_suggestions else None
                        ),
                        "success_criteria": list(item.success_criteria),
                        "remaining_gap": {
                            "completion_state": (
                                "已标记完成；仍需由材料证据判断成功标准是否全部满足"
                                if item.current_status == "completed"
                                else "尚未标记完成；成功标准仍待满足或核验"
                            ),
                            "success_criteria_pending_verification": (
                                [] if item.current_status == "completed" else list(item.success_criteria)
                            ),
                            "known_constraints": list(item.key_constraints),
                            "pending_suggestions": list(item.pending_suggestions),
                        },
                    }
                    for item in workstreams
                ],
            }
        )
    return contexts


_GENERIC_TARGET_BIGRAMS = {
    "项目",
    "目标",
    "当前",
    "本次",
    "工作",
    "进行",
    "推进",
    "确认",
    "完成",
    "需要",
    "继续",
    "方案",
    "实现",
    "结果",
    "下一",
    "一步",
}


def _target_descriptor_text(target: GrowthMaterialTargetContext) -> str:
    values: list[str] = [
        target.title,
        target.parent_title or "",
        target.objective or "",
        target.strategy_summary or "",
        *target.success_criteria,
        *target.key_constraints,
    ]
    for row in (*target.recent_progress, *target.pending_suggestions):
        if not isinstance(row, dict):
            continue
        values.extend(
            str(row.get(key) or "")
            for key in (
                "summary",
                "headline",
                "causal_reason",
                "previous_state",
                "current_state",
                "next_gap",
            )
        )
    return "\n".join(value for value in values if value)


def _target_has_strong_evidence_overlap(
    target: GrowthMaterialTargetContext,
    evidence_text: str,
) -> bool:
    """Detect an omitted likely target only to request model reconsideration.

    This never assigns a target or impact in code.  It gates one repair turn
    when the model produced project-level evidence but silently omitted an
    existing work line whose human-authored profile shares multiple concrete
    signals with that evidence.
    """
    descriptor = _target_descriptor_text(target)
    descriptor_key = _evidence_key(descriptor)
    evidence_key = _evidence_key(evidence_text)
    title_key = _material_business_title_key(target.title)
    if len(title_key) >= 4 and title_key in evidence_key:
        return True
    descriptor_ascii = set(re.findall(r"[a-z0-9]{2,}", descriptor.lower()))
    evidence_ascii = set(re.findall(r"[a-z0-9]{2,}", evidence_text.lower()))
    if descriptor_ascii & evidence_ascii:
        return True
    descriptor_bigrams = {
        descriptor_key[index : index + 2]
        for index in range(max(0, len(descriptor_key) - 1))
        if descriptor_key[index : index + 2] not in _GENERIC_TARGET_BIGRAMS
    }
    evidence_bigrams = {
        evidence_key[index : index + 2]
        for index in range(max(0, len(evidence_key) - 1))
    }
    return len(descriptor_bigrams & evidence_bigrams) >= 2


def _likely_omitted_target_keys(
    *,
    target_catalog: list[GrowthMaterialTargetContext],
    projects: list[GrowthMaterialProjectAnalysis],
    statements: list[GrowthMaterialStatementCandidate],
) -> list[str]:
    project_ids = {
        int(item.project_key.split(":", 1)[1])
        for item in projects
        if item.project_key.startswith("project:")
        and item.project_key.split(":", 1)[1].isdigit()
    }
    evidence_text = "\n".join(
        [
            excerpt
            for project in projects
            for excerpt in project.evidence_excerpts
        ]
        + [statement.evidence_excerpt for statement in statements]
    )
    if not evidence_text:
        return []
    return [
        target.target_key
        for target in target_catalog
        if target.target_type == "work_item"
        and (not project_ids or target.project_id in project_ids)
        and _target_has_strong_evidence_overlap(target, evidence_text)
    ]


def _likely_omitted_project_keys(
    *,
    project_catalog: list[GrowthMaterialProjectContext],
    projects: list[GrowthMaterialProjectAnalysis],
    targets: list[GrowthMaterialTargetAnalysis],
    statements: list[GrowthMaterialStatementCandidate],
    unmatched: list[GrowthMaterialUnmatchedWorkstream],
    target_catalog: list[GrowthMaterialTargetContext],
) -> list[str]:
    """Request one model repair when an explicitly selected project is omitted.

    ``project_catalog`` is populated only for a material carrying a stable,
    confirmed ``project_id``.  With exactly one such project, a validated
    work-line delta or factual statement means the Agent has enough evidence to
    state how the material affects the overall objective, including the valid
    outcomes ``context`` or ``no_change``.  This gate never chooses the impact
    in code; it only prevents the project-level record from disappearing.
    """
    if projects or len(project_catalog) != 1:
        return []
    project = project_catalog[0]
    target_by_key = {item.target_key: item for item in target_catalog}
    project_target_exists = any(
        target_by_key.get(item.target_key) is not None
        and target_by_key[item.target_key].project_id == project.project_id
        for item in targets
    )
    if not project_target_exists and not statements and not unmatched:
        return []
    return [project.project_key]


def _material_system_prompt() -> str:
    return (
        "你是长期项目跟进 Agent，不是泛化的内容摘要器。只能使用输入原文，不得猜测日期、承诺、结果或负责人。"
        "material_title 是用户填写的整份材料归属线索，可用于理解总体项目和稳定命名，"
        "但不是客观事实，不得把它填入任何 evidence 字段。"
        "先识别材料中正在推进的项目/线索，再分别归入 target_catalog 中最合适的工作项或节点。"
        "工作线要以可交付目标和业务闭环命名，不得把技术标签、会议名、供应商名、功能清单或一次外呼直接建成项目。"
        "只有原文支持独立交付目标、当前动作或验收边界时才能新建工作线。"
        "原文明说‘待客户确认’、‘未找到讨论记录’、‘缺少明确优先级/负责人/验收’或‘不与主线捆绑承诺’的能力模块，不得拆成新工作线。"
        "共享同一技术但交付闭环不同的线必须拆开，例如‘在线语音客服试点’与‘办公热线数字化接入’不能合并为‘语音中台’。"
        "前者是网页/小程序上的在线语音试点，后者是模拟电话、总机、转接、录音和工单的数字化闭环。"
        "project_contexts 来自用户已确认的项目档案；project_objective 是独立的项目总目标和验收标准，"
        "不是工作线目标的派生组合。workstreams 只是达成总目标的分线，列出当前状态、最新已确认进展、"
        "最新待确认建议、成功标准和剩余缺口。"
        "先对每个受影响项目输出 project_analyses，明确材料让项目总目标更近、更远、转向、只补充背景还是无变化；"
        "再分别输出受影响工作线的 target_analyses 增量。没有用户已确认项目档案时，不得伪造 project_analyses；"
        "不得把项目层结论无分析地复制给每条线，也不得为了凑全项目而输出未受材料影响的工作线；"
        "但同一份证据可以同时让项目总目标和某条工作线推进，不得因为已输出 project_analyses 就遗漏直接受影响的 target_analyses。"
        "一份材料可同时命中多条工作线；每条线必须独立给出证据、优先级和进展判断。"
        "target_catalog 还包含该工作线的目标、成功标准、当前策略、关键约束和最近进展。"
        "recent_progress 只是用户已确认的事实基线；pending_suggestions 是以前材料的未确认 Agent 判断，"
        "只能用来定位可能的时间线索，不得当作 previous_state 或已知事实。"
        "material_occurrence 是用户手动提供的本次材料发生时间及精度；不得用正文推测值覆盖它。"
        "历史中 temporal_relation=before_material 的已确认事件才可作为 previous_state 基线；"
        "after_material 是后续上下文，same_time_or_undated 无法确定先后，两者都不得冒充 previous_state。"
        "项目与工作线中已给出最近最多 6 条已确认历史，需结合而不是只读最新一条。"
        "必须把本次材料与这些既有状态比较，判断本次增量影响，而不是重新摘要整份材料。"
        "impact_kind 只能 advanced/setback/redirected/context/no_change/unknown。"
        "advanced 仅表示已确认决定、已验证、已交付或明确缩小成功标准差距；开会、提出方案、列下一步本身不算推进。"
        "只要某个可核对的子交付物已完成，即使最终验收仍在未来，该工作线也是 advanced；"
        "current_state 只写已完成的部分，未发生的验收日期写入 next_gap，不得写成已验收。"
        "setback 表示新增关键阻塞、撤回、未达承诺、暂停原实施路径或可行性下降；"
        "redirected 表示已明确采用新目标、范围或实现路线。若只是因条件未明而停下，用 setback；"
        "若已明确从‘直接实施’改为‘先勘察再决策’的新路线，用 redirected，同时 progress_health 应为 at_risk。"
        "context 仅表示补充了不改变可执行状态、交付物、时序或路线的背景，不是保守默认选项；"
        "no_change 表示只重复目录中的已知信息；无法判断才用 unknown。"
        "判定示例：‘FAQ 样本已准备，8月30日安排转人工验收’为 advanced，已完成的是 FAQ 样本，转人工验收仍是 next_gap；"
        "‘电话型号和接口未确认，暂不实施’为 setback；若同时明确‘改为先现场勘察再决定实施’，为 redirected。"
        "headline 必须一句话说明本次对该工作线的结果影响；causal_reason 解释因果；next_gap 只写仍缺什么。"
        "previous_state/current_state 仅在原文和目录状态能支持前后变化时填写，不能猜。"
        "如果 material_title 或正文所述业务闭环与已有目录项等价，必须优先 target_analyses，不得另起近义名称。"
        "若原文描述了新项目但目录中确实无对应项，才放入 unmatched_workstreams，不要硬匹配。"
        "严格区分 confirmed_fact（已发生且可由原文支持的事实）、decision（明确决定）、"
        "proposal（建议/方案/计划）、open_question（待确认）、vendor_claim（厂商未验证陈述）、"
        "scope_change（范围或优先级变化）、action（行动项）和 conflict（原文显式的口径冲突）。"
        "计划中的‘完成’不得标为已完成事实。"
        "证据只能引用 chunk.evidence_units 中的 evidence_id；不要复制原文，不得伪造 ID。"
        "priority_axis 只能 high/low/unknown；progress_health 只能 healthy/at_risk/unknown；"
        "priority_axis=high 仅限原文明示当前优先、本周/截止时间或关键阻塞；否则必须 unknown 或 low。"
        "progress_health=healthy 仅限原文有已完成、已验证、已跑通或按计划推进的正向证据。"
        "出现待确认、尚未、未解决、外部依赖、现场勘察、待验证等信息时不得 healthy，应为 at_risk 或 unknown。"
        "证据不足必须 unknown。不要输出象限，象限由程序规则计算。"
        f"每个分块最多输出 {MATERIAL_MAX_STATEMENTS_PER_CHUNK} 条高价值 statements、"
        f"{MATERIAL_MAX_TARGETS_PER_CHUNK} 条 target_analyses、{MATERIAL_MAX_UNMATCHED_PER_CHUNK} 条 unmatched_workstreams；"
        f"每条新工作线最多 {MATERIAL_MAX_NODES_PER_WORKSTREAM} 个里程碑。合并重复句，只保留改变进展判断的信息。"
        "text/summary/placement_reason 每项不超过 60 个汉字，不得输出解释性前后缀。"
        "输出要紧凑：不要输出 relevance_reason、顶层 priority_axis/progress_health/placement_reason/"
        "placement_evidence_id，这些由程序根据每条工作线汇总；不要重复同一证据的原文。"
        "unmatched_workstreams.kind 只能是 workstream；lifecycle 只能 active/selected/discovery。"
        "能力模块、远期想法、尚未获得选择的备选方向不能输出到 unmatched_workstreams。"
        '只输出下列紧凑结构的合法 JSON：'
        '{"statements":[{"statement_type":"decision","text":"中性摘要","evidence_id":"E12","confidence":0.8}],'
        '"project_analyses":[{"project_key":"project:1","evidence_ids":["E12"],'
        '"impact_kind":"advanced","headline":"项目总体缩小了接入方案差距",'
        '"causal_reason":"已验证关键接口","previous_state":"接入可行性待验证",'
        '"current_state":"关键接口已验证","next_gap":"业务验收","confidence":0.9}],'
        '"target_analyses":[{"target_key":"work_item:1","evidence_ids":["E12"],'
        '"priority_axis":"unknown","progress_health":"unknown",'
        '"placement_reason":"FAQ 子交付物已完成","impact_kind":"advanced",'
        '"headline":"FAQ 样本已准备，进入转人工验收前",'
        '"causal_reason":"已完成可核对的 FAQ 样本，缩小了试点验收差距",'
        '"previous_state":"FAQ 样本待准备","current_state":"FAQ 样本已准备","next_gap":"按预定日期执行转人工验收",'
        '"proposed_node_status":null,"confidence":0.8}],'
        '"unmatched_workstreams":[{"kind":"workstream","lifecycle":"discovery",'
        '"title":"稳定项目名","summary":"独立交付闭环","objective":"目标状态",'
        '"success_criteria":["验收标准"],"strategy_summary":"当前路径",'
        '"key_constraints":["关键约束"],"evidence_id":"E20",'
        '"suggested_nodes":["里程碑"],"priority_axis":"unknown","progress_health":"unknown",'
        '"confidence":0.8}]}。'
    )


def _material_error_code(exc: Exception) -> str:
    message = str(exc)
    if "ModelFinishReason:length" in message:
        return "MaterialAIResponseTruncated"
    if "ModelResponseInvalidJSON" in message or isinstance(exc, json.JSONDecodeError):
        return "MaterialAIResponseInvalidJSON"
    if "MaterialEvidence" in message:
        return "MaterialAIEvidenceInvalid"
    if "MaterialProject" in message:
        return "MaterialAIProjectInvalid"
    if "MaterialTarget" in message:
        return "MaterialAITargetInvalid"
    if "MaterialResponseSchemaInvalid" in message:
        return "MaterialAIResponseSchemaInvalid"
    if isinstance(exc, ValidationError):
        return "MaterialAIResponseSchemaInvalid"
    if isinstance(exc, httpx.TimeoutException):
        return "MaterialAITimeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"MaterialAIHTTP{exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return "MaterialAINetworkError"
    return type(exc).__name__


def _material_error_is_repairable(exc: Exception) -> bool:
    """Only retry output errors that a short correction turn can fix.

    A second full generation roughly doubles latency. Length truncation,
    provider/network errors and Pydantic schema failures are therefore terminal;
    schema drift is handled locally item by item instead.
    """
    if isinstance(exc, (httpx.HTTPError, ValidationError, KeyError)):
        return False
    message = str(exc)
    if "ModelFinishReason:length" in message:
        return False
    return any(
        marker in message
        for marker in (
            "ModelResponseInvalidJSON",
            "MaterialEvidence",
            "MaterialTarget",
            "MaterialProject",
            "MaterialWorkstreamBoundary",
        )
    )


def _merge_usage(total: dict[str, int], usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value


def _post_material_model(
    configuration: EffectiveAIConfiguration,
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> dict[str, Any]:
    request_json: dict[str, Any] = {
        "model": configuration.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    response = httpx.post(
        f"{configuration.base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {configuration.api_key}",
            "Content-Type": "application/json",
        },
        json=request_json,
        timeout=MODEL_TIMEOUT,
        follow_redirects=False,
    )
    # Some compatible providers do not implement response_format. A 400 here
    # is a protocol capability mismatch, so retry the same request without it.
    if response.status_code == 400:
        request_json.pop("response_format", None)
        response = httpx.post(
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {configuration.api_key}",
                "Content-Type": "application/json",
            },
            json=request_json,
            timeout=MODEL_TIMEOUT,
            follow_redirects=False,
        )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("ModelResponseInvalidJSON")
    return body


_MATERIAL_STATEMENT_TYPE_ALIASES = {
    "confirmed_fact": "confirmed_fact",
    "fact": "confirmed_fact",
    "已确认事实": "confirmed_fact",
    "确认事实": "confirmed_fact",
    "事实": "confirmed_fact",
    "decision": "decision",
    "决策": "decision",
    "决定": "decision",
    "proposal": "proposal",
    "建议": "proposal",
    "方案": "proposal",
    "open_question": "open_question",
    "question": "open_question",
    "待确认": "open_question",
    "开放问题": "open_question",
    "vendor_claim": "vendor_claim",
    "厂商陈述": "vendor_claim",
    "厂商说法": "vendor_claim",
    "scope_change": "scope_change",
    "范围变化": "scope_change",
    "口径变化": "scope_change",
    "action": "action",
    "action_item": "action",
    "行动项": "action",
    "下一步": "action",
    "conflict": "conflict",
    "冲突": "conflict",
    "口径冲突": "conflict",
}
_MATERIAL_PRIORITY_ALIASES = {
    "high": "high",
    "高": "high",
    "高优先级": "high",
    "low": "low",
    "低": "low",
    "低优先级": "low",
    "unknown": "unknown",
    "未知": "unknown",
    "待判断": "unknown",
    "": "unknown",
}
_MATERIAL_PROGRESS_ALIASES = {
    "healthy": "healthy",
    "正常": "healthy",
    "健康": "healthy",
    "at_risk": "at_risk",
    "at-risk": "at_risk",
    "有风险": "at_risk",
    "风险": "at_risk",
    "阻塞": "at_risk",
    "unknown": "unknown",
    "未知": "unknown",
    "待判断": "unknown",
    "": "unknown",
}
_MATERIAL_IMPACT_ALIASES = {
    "advanced": "advanced",
    "推进": "advanced",
    "进展": "advanced",
    "setback": "setback",
    "受阻": "setback",
    "倒退": "setback",
    "离目标更远": "setback",
    "redirected": "redirected",
    "转向": "redirected",
    "方向变化": "redirected",
    "context": "context",
    "补充信息": "context",
    "上下文": "context",
    "no_change": "no_change",
    "no-change": "no_change",
    "无变化": "no_change",
    "无实质变化": "no_change",
    "unknown": "unknown",
    "未知": "unknown",
    "待判断": "unknown",
    "": "unknown",
}
_MATERIAL_NODE_STATUS_ALIASES = {
    "planned": "planned",
    "计划中": "planned",
    "待开始": "planned",
    "in_progress": "in_progress",
    "in-progress": "in_progress",
    "进行中": "in_progress",
    "推进中": "in_progress",
    "blocked": "blocked",
    "阻塞": "blocked",
    "卡点": "blocked",
    "completed": "completed",
    "已完成": "completed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "已取消": "cancelled",
}


def _material_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _material_text(value: Any, *, limit: int, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return default
    text = str(value).strip()
    return text[:limit] if text else default


def _material_confidence(value: Any) -> float:
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.5
    if result > 1 and result <= 100:
        result /= 100
    return min(1.0, max(0.0, result))


def _material_enum(value: Any, aliases: dict[str, str], *, default: str) -> str:
    key = _material_text(value, limit=100).casefold()
    return aliases.get(key, default)


def _normalized_material_model_payload(
    content: Any,
    *,
    evidence_lookup: Optional[dict[str, tuple[str, str]]] = None,
) -> tuple[dict[str, Any], int, int, list[str]]:
    """Normalize harmless provider schema drift before strict evidence checks.

    Models commonly emit a single object instead of a list, localized enum
    labels, percentages, or omit explanatory fields.  Those variations should
    not invalidate an otherwise verifiable material.  Evidence and target keys
    remain strict and are validated after normalization.
    """
    raw = _json_payload(content)
    raw_candidate_count = sum(
        len(_material_list(raw.get(key)))
        for key in (
            "statements",
            "project_analyses",
            "target_analyses",
            "unmatched_workstreams",
        )
    )
    missing_required_workstream_metadata = 0
    target_contract_errors: list[str] = []
    evidence_lookup = evidence_lookup or {}

    def evidence_from_id(value: Any) -> str:
        evidence_id = _material_text(value, limit=100).upper()
        matched = evidence_lookup.get(evidence_id)
        return matched[1] if matched is not None else ""

    statements: list[dict[str, Any]] = []
    for item in _material_list(raw.get("statements"))[:MATERIAL_MAX_STATEMENTS_PER_CHUNK]:
        if not isinstance(item, dict):
            continue
        statement_type = _material_enum(
            item.get("statement_type") or item.get("type"),
            _MATERIAL_STATEMENT_TYPE_ALIASES,
            default="",
        )
        text = _material_text(item.get("text") or item.get("summary"), limit=2000)
        evidence = evidence_from_id(item.get("evidence_id")) or _material_text(
            item.get("evidence_excerpt") or item.get("evidence"), limit=2000
        )
        if not statement_type or not text or not evidence:
            continue
        statements.append(
            {
                "statement_type": statement_type,
                "text": text,
                "evidence_excerpt": evidence,
                "confidence": _material_confidence(item.get("confidence")),
            }
        )

    projects: list[dict[str, Any]] = []
    raw_projects = _material_list(raw.get("project_analyses"))
    if len(raw_projects) > MATERIAL_MAX_PROJECTS:
        target_contract_errors.append("project_count_exceeds_global_limit")
    for project_index, item in enumerate(raw_projects[:MATERIAL_MAX_PROJECTS], start=1):
        if not isinstance(item, dict):
            target_contract_errors.append(f"project_{project_index}_not_object")
            continue
        project_key = _material_text(item.get("project_key"), limit=100)
        evidence_ids = item.get("evidence_ids")
        evidence_id_values = (
            [evidence_ids]
            if isinstance(evidence_ids, str)
            else _material_list(evidence_ids)
        )
        evidence = []
        for candidate in evidence_id_values[:20]:
            evidence_id = _material_text(candidate, limit=100).upper()
            matched = evidence_lookup.get(evidence_id)
            if not evidence_id or matched is None:
                target_contract_errors.append(
                    f"project_{project_index}_evidence_id_invalid"
                )
                continue
            evidence.append(matched[1])
        evidence = list(dict.fromkeys(evidence))
        if not project_key:
            target_contract_errors.append(f"project_{project_index}_key_missing")
        if not evidence:
            target_contract_errors.append(f"project_{project_index}_evidence_missing")
        if not project_key or not evidence:
            continue
        projects.append(
            {
                "project_key": project_key,
                "evidence_excerpts": evidence,
                "impact_kind": _material_enum(
                    item.get("impact_kind"), _MATERIAL_IMPACT_ALIASES, default="unknown"
                ),
                "headline": _material_text(
                    item.get("headline"),
                    limit=500,
                    default="本次对项目总目标的作用尚待判断",
                ),
                "causal_reason": _material_text(
                    item.get("causal_reason"), limit=2000, default="原文证据不足"
                ),
                "previous_state": _material_text(item.get("previous_state"), limit=2000) or None,
                "current_state": _material_text(item.get("current_state"), limit=2000) or None,
                "next_gap": _material_text(item.get("next_gap"), limit=2000) or None,
                "confidence": _material_confidence(item.get("confidence")),
            }
        )

    targets: list[dict[str, Any]] = []
    raw_targets = _material_list(raw.get("target_analyses"))
    if len(raw_targets) > MATERIAL_MAX_TARGETS:
        target_contract_errors.append("target_count_exceeds_global_limit")
    # The prompt asks for at most four high-value targets to keep the response
    # compact, but a provider returning a fifth valid target must not make it
    # disappear silently. Preserve every bounded target and validate it.
    for target_index, item in enumerate(raw_targets[:MATERIAL_MAX_TARGETS], start=1):
        if not isinstance(item, dict):
            target_contract_errors.append(f"target_{target_index}_not_object")
            continue
        target_key = _material_text(item.get("target_key"), limit=100)
        if not target_key:
            target_contract_errors.append(f"target_{target_index}_key_missing")

        # v5 evidence IDs are authoritative whenever the field is present.
        # Falling back to a free-text quote after a bad ID would let an invalid
        # per-target citation pass without the repair turn noticing it.
        if "evidence_ids" in item:
            evidence_ids = item.get("evidence_ids")
            if isinstance(evidence_ids, str):
                evidence_id_values = [evidence_ids]
            else:
                evidence_id_values = _material_list(evidence_ids)
            if not evidence_id_values:
                target_contract_errors.append(f"target_{target_index}_evidence_ids_missing")
            if len(evidence_id_values) > 20:
                target_contract_errors.append(f"target_{target_index}_evidence_ids_exceed_limit")
            evidence = []
            for candidate in evidence_id_values[:20]:
                evidence_id = _material_text(candidate, limit=100).upper()
                matched = evidence_lookup.get(evidence_id)
                if not evidence_id or matched is None:
                    target_contract_errors.append(
                        f"target_{target_index}_evidence_id_invalid"
                    )
                    continue
                evidence.append(matched[1])
        else:
            evidence_value = item.get("evidence_excerpts")
            if evidence_value is None:
                evidence_value = item.get("evidence_excerpt") or item.get("evidence")
            if isinstance(evidence_value, str):
                evidence_values = [evidence_value]
            else:
                evidence_values = _material_list(evidence_value)
            if len(evidence_values) > 20:
                target_contract_errors.append(
                    f"target_{target_index}_evidence_excerpts_exceed_limit"
                )
            evidence = [
                value
                for value in (
                    _material_text(candidate, limit=2000) for candidate in evidence_values[:20]
                )
                if value
            ]
        evidence = list(dict.fromkeys(evidence))
        if not target_key or not evidence:
            if not evidence:
                target_contract_errors.append(f"target_{target_index}_evidence_missing")
            continue
        proposed_status = _material_enum(
            item.get("proposed_node_status"),
            _MATERIAL_NODE_STATUS_ALIASES,
            default="",
        )
        targets.append(
            {
                "target_key": target_key,
                "evidence_excerpts": evidence,
                "relevance_reason": _material_text(
                    item.get("relevance_reason"), limit=1000, default="原文与该工作线直接相关"
                ),
                "priority_axis": _material_enum(
                    item.get("priority_axis"), _MATERIAL_PRIORITY_ALIASES, default="unknown"
                ),
                "progress_health": _material_enum(
                    item.get("progress_health"), _MATERIAL_PROGRESS_ALIASES, default="unknown"
                ),
                "placement_reason": _material_text(
                    item.get("placement_reason"), limit=1000, default="依据原文证据归属"
                ),
                "impact_kind": _material_enum(
                    item.get("impact_kind"), _MATERIAL_IMPACT_ALIASES, default="unknown"
                ),
                "headline": _material_text(
                    item.get("headline"), limit=500, default="本次变化尚待判断"
                ),
                "causal_reason": _material_text(
                    item.get("causal_reason"), limit=2000, default="原文证据不足"
                ),
                "previous_state": _material_text(item.get("previous_state"), limit=2000) or None,
                "current_state": _material_text(item.get("current_state"), limit=2000) or None,
                "next_gap": _material_text(item.get("next_gap"), limit=2000) or None,
                "proposed_node_status": proposed_status or None,
                "confidence": _material_confidence(item.get("confidence")),
            }
        )

    unmatched: list[dict[str, Any]] = []
    for item in _material_list(raw.get("unmatched_workstreams"))[
        :MATERIAL_MAX_UNMATCHED_PER_CHUNK
    ]:
        if not isinstance(item, dict):
            continue
        kind = _material_text(item.get("kind"), limit=100).casefold()
        lifecycle = _material_text(item.get("lifecycle"), limit=100).casefold()
        if not kind or not lifecycle:
            missing_required_workstream_metadata += 1
            continue
        if kind != "workstream" or lifecycle not in {"active", "selected", "discovery"}:
            continue
        title = _material_text(item.get("title"), limit=300)
        evidence = evidence_from_id(item.get("evidence_id")) or _material_text(
            item.get("evidence_excerpt") or item.get("evidence"), limit=2000
        )
        if not title or not evidence:
            continue
        nodes = []
        for node in _material_list(item.get("suggested_nodes"))[:MATERIAL_MAX_NODES_PER_WORKSTREAM]:
            if isinstance(node, dict):
                node = node.get("title") or node.get("name")
            value = _material_text(node, limit=300)
            if value:
                nodes.append(value)
        unmatched.append(
            {
                "kind": "workstream",
                "lifecycle": lifecycle,
                "title": title,
                "summary": _material_text(
                    item.get("summary"), limit=1000, default=f"跟进{title}的交付闭环"
                ),
                "objective": _material_text(item.get("objective"), limit=2000) or None,
                "success_criteria": [
                    value
                    for value in (
                        _material_text(candidate, limit=500)
                        for candidate in _material_list(item.get("success_criteria"))[:20]
                    )
                    if value
                ],
                "strategy_summary": _material_text(item.get("strategy_summary"), limit=2000) or None,
                "key_constraints": [
                    value
                    for value in (
                        _material_text(candidate, limit=500)
                        for candidate in _material_list(item.get("key_constraints"))[:20]
                    )
                    if value
                ],
                "evidence_excerpt": evidence,
                "suggested_nodes": nodes,
                "priority_axis": _material_enum(
                    item.get("priority_axis"), _MATERIAL_PRIORITY_ALIASES, default="unknown"
                ),
                "progress_health": _material_enum(
                    item.get("progress_health"), _MATERIAL_PROGRESS_ALIASES, default="unknown"
                ),
                "placement_reason": _material_text(
                    item.get("placement_reason"), limit=1000, default="原文支持一条独立交付线"
                ),
                "confidence": _material_confidence(item.get("confidence")),
            }
        )

    placement_evidence = evidence_from_id(raw.get("placement_evidence_id")) or _material_text(
        raw.get("placement_evidence_excerpt") or raw.get("placement_evidence"), limit=2000
    )
    return (
        {
            "statements": statements,
            "project_analyses": projects,
            "target_analyses": targets,
            "unmatched_workstreams": unmatched,
            "priority_axis": _material_enum(
                raw.get("priority_axis"), _MATERIAL_PRIORITY_ALIASES, default="unknown"
            ),
            "progress_health": _material_enum(
                raw.get("progress_health"), _MATERIAL_PROGRESS_ALIASES, default="unknown"
            ),
            "placement_reason": _material_text(
                raw.get("placement_reason"), limit=1000, default="材料涉及多条工作线，按各线证据判断"
            ),
            "placement_evidence_excerpt": placement_evidence or None,
        },
        raw_candidate_count,
        missing_required_workstream_metadata,
        target_contract_errors,
    )


_MATERIAL_HIGH_PRIORITY_EVIDENCE = re.compile(
    r"高优先|优先级高|第一优先|当前优先|优先(?:推进|落地)|"
    r"本周|今天|尽快|立即|截止|关键阻塞|必须先|先行|作为突破口"
)
_MATERIAL_LOW_PRIORITY_EVIDENCE = re.compile(
    r"第二优先|优先级低|(?:位于|排在|放在).{0,24}(?:之后|后面)|"
    r"后续(?:再|接入|评估|推进|安排|考虑|开展|做)|第二课题|暂缓"
)
_MATERIAL_HEALTHY_EVIDENCE = re.compile(
    r"已完成|已经完成|已验证|验证通过|已交付|已跑通|已经跑通|已上线|按计划|如期"
)
_MATERIAL_RISK_EVIDENCE = re.compile(
    r"待确认|尚未|未解决|未完成|外部依赖|依赖|现场勘察|待验证|暂不|缺少|不清|风险|阻塞|无法|(?:需要|需).{0,20}确认"
)


def _conservative_material_axes(
    priority_axis: str,
    progress_health: str,
    *,
    evidence: list[str],
) -> tuple[str, str]:
    source = "\n".join(value for value in evidence if value)
    if priority_axis == "high":
        if _MATERIAL_LOW_PRIORITY_EVIDENCE.search(source):
            priority_axis = "low"
        elif not _MATERIAL_HIGH_PRIORITY_EVIDENCE.search(source):
            priority_axis = "unknown"
    if progress_health == "healthy":
        if _MATERIAL_RISK_EVIDENCE.search(source):
            progress_health = "at_risk"
        elif not _MATERIAL_HEALTHY_EVIDENCE.search(source):
            progress_health = "unknown"
    return priority_axis, progress_health


def _validated_material_payload(
    *,
    content: Any,
    original_chunk: str,
    redacted_chunk: str,
    allowed_target_keys: set[str],
    allowed_project_keys: set[str],
    evidence_lookup: Optional[dict[str, tuple[str, str]]] = None,
) -> tuple[
    _ModelMaterialPayload,
    list[GrowthMaterialStatementCandidate],
    list[GrowthMaterialProjectAnalysis],
    list[GrowthMaterialTargetAnalysis],
    list[GrowthMaterialUnmatchedWorkstream],
    str | None,
]:
    (
        normalized_payload,
        raw_candidate_count,
        missing_required_workstream_metadata,
        target_contract_errors,
    ) = _normalized_material_model_payload(
        content,
        evidence_lookup=evidence_lookup,
    )
    if target_contract_errors:
        raise ValueError(
            "MaterialTargetContractInvalid:" + ",".join(dict.fromkeys(target_contract_errors))
        )
    payload = _ModelMaterialPayload.model_validate(normalized_payload)
    statements: list[GrowthMaterialStatementCandidate] = []
    invalid_evidence_count = 0
    for item in payload.statements:
        try:
            evidence = _restore_local_material_excerpt(
                original_chunk,
                redacted_chunk,
                item.evidence_excerpt,
            )
        except ValueError:
            invalid_evidence_count += 1
            continue
        statements.append(
            GrowthMaterialStatementCandidate(
                statement_type=item.statement_type,
                text=item.text.strip(),
                evidence_excerpt=evidence,
                confidence=item.confidence,
            )
        )
    projects: list[GrowthMaterialProjectAnalysis] = []
    for item in payload.project_analyses:
        if item.project_key not in allowed_project_keys:
            raise ValueError("MaterialProjectKeyInvalid")
        evidence = []
        for value in item.evidence_excerpts:
            try:
                evidence.append(
                    _restore_local_material_excerpt(original_chunk, redacted_chunk, value)
                )
            except ValueError as exc:
                raise ValueError("MaterialProjectEvidenceInvalid") from exc
        if not evidence:
            raise ValueError("MaterialProjectEvidenceMissing")
        projects.append(
            GrowthMaterialProjectAnalysis(
                project_key=item.project_key,
                evidence_excerpts=list(dict.fromkeys(evidence)),
                impact_kind=item.impact_kind,
                headline=item.headline.strip(),
                causal_reason=item.causal_reason.strip(),
                previous_state=(item.previous_state or "").strip() or None,
                current_state=(item.current_state or "").strip() or None,
                next_gap=(item.next_gap or "").strip() or None,
                confidence=item.confidence,
            )
        )
    targets: list[GrowthMaterialTargetAnalysis] = []
    for item in payload.target_analyses:
        if item.target_key not in allowed_target_keys:
            raise ValueError("MaterialTargetKeyInvalid")
        evidence = []
        target_evidence_invalid = False
        for value in item.evidence_excerpts:
            try:
                evidence.append(
                    _restore_local_material_excerpt(original_chunk, redacted_chunk, value)
                )
            except ValueError:
                invalid_evidence_count += 1
                target_evidence_invalid = True
        if target_evidence_invalid:
            raise ValueError("MaterialTargetEvidenceInvalid")
        if not evidence:
            # Relevance without a verifiable quote is not actionable routing.
            raise ValueError("MaterialTargetEvidenceMissing")
        priority_axis, progress_health = _conservative_material_axes(
            item.priority_axis,
            item.progress_health,
            evidence=evidence,
        )
        targets.append(
            GrowthMaterialTargetAnalysis(
                target_key=item.target_key,
                evidence_excerpts=list(dict.fromkeys(evidence)),
                relevance_reason=item.relevance_reason.strip(),
                priority_axis=priority_axis,
                progress_health=progress_health,
                placement_reason=item.placement_reason.strip(),
                proposed_node_status=item.proposed_node_status,
                confidence=item.confidence,
                impact_kind=item.impact_kind,
                headline=item.headline.strip(),
                causal_reason=item.causal_reason.strip(),
                previous_state=(item.previous_state or "").strip() or None,
                current_state=(item.current_state or "").strip() or None,
                next_gap=(item.next_gap or "").strip() or None,
            )
        )
    unmatched: list[GrowthMaterialUnmatchedWorkstream] = []
    for item in payload.unmatched_workstreams:
        try:
            evidence = _restore_local_material_excerpt(
                original_chunk,
                redacted_chunk,
                item.evidence_excerpt,
            )
        except ValueError:
            invalid_evidence_count += 1
            continue
        priority_axis, progress_health = _conservative_material_axes(
            item.priority_axis,
            item.progress_health,
            evidence=[evidence],
        )
        unmatched.append(
            GrowthMaterialUnmatchedWorkstream(
                title=item.title.strip(),
                summary=item.summary.strip(),
                evidence_excerpt=evidence,
                suggested_nodes=[value.strip() for value in item.suggested_nodes if value.strip()],
                priority_axis=priority_axis,
                progress_health=progress_health,
                placement_reason=item.placement_reason.strip(),
                confidence=item.confidence,
                objective=(item.objective or "").strip() or None,
                success_criteria=tuple(
                    value.strip() for value in item.success_criteria if value.strip()
                ),
                strategy_summary=(item.strategy_summary or "").strip() or None,
                key_constraints=tuple(
                    value.strip() for value in item.key_constraints if value.strip()
                ),
            )
        )
    placement_excerpt = None
    if payload.placement_evidence_excerpt:
        try:
            placement_excerpt = _restore_local_material_excerpt(
                original_chunk,
                redacted_chunk,
                payload.placement_evidence_excerpt,
            )
        except ValueError:
            invalid_evidence_count += 1
    payload.priority_axis, payload.progress_health = _conservative_material_axes(
        payload.priority_axis,
        payload.progress_health,
        evidence=[placement_excerpt] if placement_excerpt else [],
    )
    valid_count = len(statements) + len(targets) + len(unmatched)
    if raw_candidate_count and not valid_count:
        if missing_required_workstream_metadata:
            raise ValueError("MaterialResponseSchemaInvalid:workstream_metadata")
        raise ValueError("MaterialEvidenceAllCandidatesInvalid")
    return payload, statements, projects, targets, unmatched, placement_excerpt


_MATERIAL_TITLE_SUFFIXES = (
    "交流会需求整理",
    "会议纪要",
    "会议材料",
    "调研报告",
    "澄清材料",
    "需求整理",
    "会议记录",
    "材料",
)
_MATERIAL_DELIVERY_SUFFIXES = (
    "数字化接入",
    "数字化",
    "建设项目",
    "建设",
    "试点",
    "项目",
)
_MATERIAL_UNCONFIRMED_PATTERNS = (
    re.compile(r"缺少明确.{0,40}(?:优先级|负责人|预算|验收)"),
    re.compile(r"(?:没有|未找到|未见).{0,50}(?:讨论记录|客户确认|原话|证据)"),
    re.compile(r"不与.{0,50}捆绑承诺"),
    re.compile(r"不是.{0,40}范围确认.{0,30}并行建设"),
)


def _material_title_hint(value: Optional[str]) -> str:
    title = (value or "").strip().strip("··-_— ")
    changed = True
    while changed and title:
        changed = False
        for suffix in _MATERIAL_TITLE_SUFFIXES:
            if title.endswith(suffix):
                title = title[: -len(suffix)].rstrip("··-_— ")
                changed = True
                break
    return title


def _material_business_title_key(value: str, *, strip_delivery_suffix: bool = False) -> str:
    key = _evidence_key(value)
    for prefix in ("人民日报", "央媒", "报社"):
        normalized_prefix = _evidence_key(prefix)
        if key.startswith(normalized_prefix):
            key = key[len(normalized_prefix) :]
            break
    if strip_delivery_suffix:
        for suffix in _MATERIAL_DELIVERY_SUFFIXES:
            normalized_suffix = _evidence_key(suffix)
            if key.endswith(normalized_suffix):
                key = key[: -len(normalized_suffix)]
                break
    return key


def _material_validation_title_key(value: str) -> str:
    """Normalize equivalent validation-stage labels only for title canonicalization."""
    key = _material_business_title_key(value)
    for marker in ("demo", "poc", "概念验证", "原型验证", "原型", "试点"):
        key = key.replace(_evidence_key(marker), "")
    return key


def _canonicalize_unmatched_title(
    item: GrowthMaterialUnmatchedWorkstream,
    *,
    material_title: Optional[str],
) -> GrowthMaterialUnmatchedWorkstream:
    hint = _material_title_hint(material_title)
    if not hint:
        return item
    hint_key = _material_business_title_key(hint)
    item_key = _material_business_title_key(item.title)
    if not hint_key or not item_key:
        return item
    hint_validation_key = _material_validation_title_key(hint)
    item_validation_key = _material_validation_title_key(item.title)
    equivalent = (
        hint_key == item_key
        or (
            min(len(hint_validation_key), len(item_validation_key)) >= 6
            and hint_validation_key == item_validation_key
        )
        or (
            min(len(hint_key), len(item_key)) >= 7
            and SequenceMatcher(None, hint_key, item_key).ratio() >= 0.9
        )
    )
    if not equivalent or item.title == hint:
        return item
    return GrowthMaterialUnmatchedWorkstream(
        title=hint,
        summary=item.summary,
        evidence_excerpt=item.evidence_excerpt,
        suggested_nodes=item.suggested_nodes,
        priority_axis=item.priority_axis,
        progress_health=item.progress_health,
        placement_reason=item.placement_reason,
        confidence=item.confidence,
        objective=item.objective,
        success_criteria=item.success_criteria,
        strategy_summary=item.strategy_summary,
        key_constraints=item.key_constraints,
    )


_TYPESETTING_TITLE_RE = re.compile(
    r"智能排版|AI自动组版|AI组版|自动组版|排版(?:预演|原型|方案|草稿)|画板",
    re.IGNORECASE,
)
_TYPESETTING_SCOPE_RE = re.compile(
    r"首期|草稿|候选方案|预演|原型|不(?:改造|替代|直接生成)|"
    r"正式(?:组版|排版|印刷)|参考清单",
    re.IGNORECASE,
)


def _canonicalize_typesetting_workstream(
    item: GrowthMaterialUnmatchedWorkstream,
    *,
    original_text: str,
) -> GrowthMaterialUnmatchedWorkstream:
    """Keep a scoped prototype from being named as production auto-typesetting."""
    if not _TYPESETTING_TITLE_RE.search(item.title):
        return item
    if not _TYPESETTING_TITLE_RE.search(original_text) or not _TYPESETTING_SCOPE_RE.search(
        original_text
    ):
        return item
    prefix = "人民日报" if "人民日报" in original_text or "人民日报" in item.title else ""
    canonical_title = f"{prefix}智能排版原型验证"
    if item.title == canonical_title:
        return item
    return GrowthMaterialUnmatchedWorkstream(
        title=canonical_title,
        summary=item.summary,
        evidence_excerpt=item.evidence_excerpt,
        suggested_nodes=item.suggested_nodes,
        priority_axis=item.priority_axis,
        progress_health=item.progress_health,
        placement_reason=item.placement_reason,
        confidence=item.confidence,
        objective=item.objective,
        success_criteria=item.success_criteria,
        strategy_summary=item.strategy_summary,
        key_constraints=item.key_constraints,
    )


_VOICE_EXPLICIT_ONLINE_RE = re.compile(
    r"在线语音|网页(?:内嵌)?(?:客服|入口|语音)?|小程序(?:入口)?|微信公众号"
)
_VOICE_AGENT_RE = re.compile(r"\bAgent\b|智能体|AI", re.IGNORECASE)
_VOICE_KNOWLEDGE_RE = re.compile(r"FAQ|知识库|知识片段|常见问题", re.IGNORECASE)
_VOICE_HANDOFF_RE = re.compile(r"转人工|人工接管|人工坐席")
_VOICE_VALIDATION_RE = re.compile(r"真实问题|真实场景|实测|验证|试点|\bDemo\b", re.IGNORECASE)
_VOICE_PHONE_CHANNEL_RE = re.compile(
    r"固定电话|固话|\bSIP\b|电话(?:线路|总机|系统|接入|呼入|呼出|转接)|"
    r"总机|模拟(?:电话|信号|音频)|程控|语音网关|400(?:热线|电话)?|双声道|"
    r"主叫|被叫|(?:电话|通话|线路|坐席).{0,18}录音|录音.{0,18}(?:电话|通话|线路|坐席)",
    re.IGNORECASE,
)
_VOICE_PHONE_DEPENDENCY_RE = re.compile(
    r"现场勘察|线路测试|设备选型|接口待确认|待验证|待确认|"
    r"固定电话|固话|\bSIP\b|电话线路|电话总机|总机|模拟(?:电话|信号|音频)|"
    r"程控|语音网关|双声道",
    re.IGNORECASE,
)
_VOICE_SEQUENCE_RE = re.compile(
    r"(?:先行?|本周|优先).{0,100}(?:在线语音|网页|小程序).{0,180}"
    r"(?:后续|跑通后|暂不接|再评估|再接入).{0,100}"
    r"(?:固定电话|固话|\bSIP\b|400|电话线路|总机)",
    re.IGNORECASE | re.DOTALL,
)
_VOICE_DELIVERY_TITLE_RE = re.compile(
    r"在线语音|语音客服|智能语音|语音中台|IT服务热线|服务热线|"
    r"办公热线|热线数字化|电话数字化|电话接入|固定电话|固话",
    re.IGNORECASE,
)
_VOICE_TITLE_BOUNDARY_RE = re.compile(
    r"在线语音|语音客服|智能语音|语音中台|(?:IT|技术部)?服务热线|"
    r"办公热线|电话数字化|电话接入|语音与电话",
    re.IGNORECASE,
)


def _voice_delivery_kind(title: str) -> str | None:
    if re.search(r"在线语音|网页|小程序", title):
        return "online"
    if re.search(
        r"办公热线|热线数字化|电话数字化|电话接入|固定电话|固话",
        title,
    ):
        return "hotline"
    return None


@dataclass(frozen=True)
class _VoiceBoundaryEvidence:
    online: str
    hotline: str
    explicitly_sequenced: bool


def _voice_online_unit_score(value: str) -> int:
    return (
        (8 if _VOICE_EXPLICIT_ONLINE_RE.search(value) else 0)
        + (4 if _VOICE_AGENT_RE.search(value) else 0)
        + (3 if _VOICE_KNOWLEDGE_RE.search(value) else 0)
        + (4 if _VOICE_HANDOFF_RE.search(value) else 0)
        + (3 if _VOICE_VALIDATION_RE.search(value) else 0)
        + (2 if _MATERIAL_HIGH_PRIORITY_EVIDENCE.search(value) else 0)
        - (3 if _VOICE_PHONE_CHANNEL_RE.search(value) else 0)
    )


def _voice_hotline_unit_score(value: str) -> int:
    return (
        (7 if _VOICE_PHONE_CHANNEL_RE.search(value) else 0)
        + (5 if _VOICE_PHONE_DEPENDENCY_RE.search(value) else 0)
        + (3 if _MATERIAL_LOW_PRIORITY_EVIDENCE.search(value) else 0)
        + (2 if _MATERIAL_RISK_EVIDENCE.search(value) else 0)
        - (3 if _VOICE_EXPLICIT_ONLINE_RE.search(value) else 0)
    )


def _voice_boundary_evidence(original_text: str) -> _VoiceBoundaryEvidence | None:
    """Find two evidence-backed channel loops without trusting model naming.

    Agent/FAQ/transfer-human features alone never create a split.  They count
    as the online-service loop only when the same material also contains a
    physical telephone channel with a distinct dependency such as SIP, a PBX,
    an analogue line or an on-site survey.
    """
    units = _base_evidence_units(original_text)
    explicit_online = [value for value in units if _VOICE_EXPLICIT_ONLINE_RE.search(value)]
    phone_units = [value for value in units if _VOICE_PHONE_CHANNEL_RE.search(value)]
    if not phone_units:
        return None

    functional_online = (
        bool(_VOICE_AGENT_RE.search(original_text))
        and sum(
            bool(pattern.search(original_text))
            for pattern in (
                _VOICE_KNOWLEDGE_RE,
                _VOICE_HANDOFF_RE,
                _VOICE_VALIDATION_RE,
            )
        )
        >= 2
    )
    if not explicit_online and not functional_online:
        return None

    functional_units = [
        value
        for value in units
        if any(
            pattern.search(value)
            for pattern in (
                _VOICE_AGENT_RE,
                _VOICE_KNOWLEDGE_RE,
                _VOICE_HANDOFF_RE,
                _VOICE_VALIDATION_RE,
            )
        )
    ]
    online_units = explicit_online or functional_units
    if not online_units:
        return None
    online = max(online_units, key=lambda value: (_voice_online_unit_score(value), -len(value)))
    hotline = max(phone_units, key=lambda value: (_voice_hotline_unit_score(value), -len(value)))
    if hotline == online:
        alternatives = [value for value in phone_units if value != online]
        if alternatives:
            hotline = max(
                alternatives,
                key=lambda value: (_voice_hotline_unit_score(value), -len(value)),
            )

    sequenced = bool(_VOICE_SEQUENCE_RE.search(original_text))
    independent_phone_dependency = any(
        _VOICE_PHONE_DEPENDENCY_RE.search(value) for value in phone_units
    )
    # Distinct technical ownership/dependencies are sufficient even when a
    # later clarification document no longer repeats the words "online/web".
    independently_scoped = independent_phone_dependency and (
        bool(explicit_online) or (functional_online and online != hotline)
    )
    if not sequenced and not independently_scoped:
        return None
    return _VoiceBoundaryEvidence(
        online=online[:2000],
        hotline=hotline[:2000],
        explicitly_sequenced=sequenced,
    )


def _voice_business_prefix(
    *,
    material_title: Optional[str],
    unmatched: list[GrowthMaterialUnmatchedWorkstream],
    target_catalog: list[GrowthMaterialTargetContext],
    original_text: str,
) -> str:
    sources = [
        _material_title_hint(material_title),
        *(item.title for item in unmatched),
        *(item.parent_title or item.title for item in target_catalog),
    ]
    for source in sources:
        source = source.strip().strip("·×·-_— ")
        if not source:
            continue
        boundary = _VOICE_TITLE_BOUNDARY_RE.search(source)
        prefix = source[: boundary.start()] if boundary else source
        # Model-generated delivery titles sometimes put a channel word between
        # the organisation and the physical-hotline label (for example,
        # ``人民日报网页办公热线数字化接入``).  A channel is never part of the
        # business owner prefix; keeping it would leak the online channel into
        # the separately tracked telephone workstream.
        prefix = re.sub(r"(?:网页(?:端|内嵌)?|小程序|在线)+$", "", prefix).strip()
        prefix = re.sub(r"(?:IT|技术部|办公|客户服务|服务)$", "", prefix).strip()
        if 2 <= len(_evidence_key(prefix)) <= 24 and not _VOICE_DELIVERY_TITLE_RE.search(prefix):
            return prefix
    if "人民日报" in original_text:
        return "人民日报"
    organization = re.search(
        r"[\u4e00-\u9fffA-Za-z0-9]{2,16}(?:日报|报社|公司|集团)",
        original_text,
    )
    return organization.group(0) if organization else ""


def _voice_priority(evidence: str, *, default_low: bool = False) -> str:
    if _MATERIAL_LOW_PRIORITY_EVIDENCE.search(evidence):
        return "low"
    if _MATERIAL_HIGH_PRIORITY_EVIDENCE.search(evidence):
        return "high"
    return "low" if default_low else "unknown"


def _apply_voice_delivery_boundary(
    targets: list[GrowthMaterialTargetAnalysis],
    unmatched: list[GrowthMaterialUnmatchedWorkstream],
    *,
    original_text: str,
    material_title: Optional[str],
    target_catalog: list[GrowthMaterialTargetContext],
) -> tuple[list[GrowthMaterialTargetAnalysis], list[GrowthMaterialUnmatchedWorkstream]]:
    evidence = _voice_boundary_evidence(original_text)
    if evidence is None:
        return targets, unmatched

    prefix = _voice_business_prefix(
        material_title=material_title,
        unmatched=unmatched,
        target_catalog=target_catalog,
        original_text=original_text,
    )
    target_by_key = {target.target_key: target for target in target_catalog}
    existing_nodes: dict[str, list[str]] = {}
    for item in unmatched:
        kind = _voice_delivery_kind(item.title)
        if kind is None:
            continue
        safe_nodes = [
            node
            for node in item.suggested_nodes
            if not re.search(r"已完成|已经完成|已交付|已上线|已跑通", node)
        ]
        if safe_nodes:
            existing_nodes[kind] = safe_nodes
    voice_target_keys = {
        key
        for key, target in target_by_key.items()
        if _VOICE_DELIVERY_TITLE_RE.search(target.title)
        or _VOICE_DELIVERY_TITLE_RE.search(target.parent_title or "")
    }
    target_kind_by_key = {
        key: _voice_delivery_kind(
            " ".join(
                value
                for value in (target.title, target.parent_title or "")
                if value
            )
        )
        for key, target in target_by_key.items()
        if key in voice_target_keys
    }
    existing_target_kinds = {
        kind
        for item in targets
        if (kind := target_kind_by_key.get(item.target_key)) is not None
    }
    # Preserve model analyses that are already routed to an unambiguous online
    # or hotline work line.  The boundary pass exists to split a merged
    # ``语音中台`` candidate; rebuilding already-separated targets as
    # unmatched workstreams would erase advanced/setback/redirected deltas and
    # later re-route them as generic context.  Node completion remains unset
    # because the channel split alone cannot prove a milestone is complete.
    kept_targets = []
    for item in targets:
        if item.target_key not in voice_target_keys:
            kept_targets.append(item)
            continue
        kind = target_kind_by_key.get(item.target_key)
        if kind is None:
            # A merged generic voice target is intentionally replaced by the
            # two deterministic delivery loops below.
            continue
        boundary_excerpt = evidence.online if kind == "online" else evidence.hotline
        kept_targets.append(
            replace(
                item,
                evidence_excerpts=list(
                    dict.fromkeys([boundary_excerpt, *item.evidence_excerpts])
                )[:20],
                proposed_node_status=None,
            )
        )
    first_voice_index = next(
        (
            index
            for index, item in enumerate(unmatched)
            if _VOICE_DELIVERY_TITLE_RE.search(item.title)
        ),
        0,
    )
    insertion_index = sum(
        not _VOICE_DELIVERY_TITLE_RE.search(item.title)
        for item in unmatched[:first_voice_index]
    )
    kept_unmatched = [
        item for item in unmatched if not _VOICE_DELIVERY_TITLE_RE.search(item.title)
    ]
    online_health = (
        "at_risk"
        if _MATERIAL_RISK_EVIDENCE.search(evidence.online)
        or _VOICE_VALIDATION_RE.search(evidence.online)
        else "unknown"
    )
    hotline_health = (
        "at_risk"
        if _MATERIAL_RISK_EVIDENCE.search(evidence.hotline)
        or _VOICE_PHONE_DEPENDENCY_RE.search(evidence.hotline)
        else "unknown"
    )
    prefix = prefix.strip()
    split_workstreams_by_kind = {
        "online": GrowthMaterialUnmatchedWorkstream(
            title=f"{prefix}在线语音客服试点",
            summary="用网页/小程序入口验证 Agent、FAQ 与转人工闭环",
            evidence_excerpt=evidence.online,
            suggested_nodes=existing_nodes.get("online")
            or ["建议：用真实问题验证 Agent、FAQ 与转人工闭环"],
            priority_axis=_voice_priority(evidence.online),
            progress_health=online_health,
            placement_reason="原文将在线服务验证与真实电话线路接入分开描述",
            confidence=0.94 if evidence.explicitly_sequenced else 0.88,
            objective="验证在线语音 Agent、FAQ 与转人工闭环是否可用",
            success_criteria=("真实问题可正确回答", "无法处理时顺畅转人工"),
            strategy_summary="先用网页或小程序入口验证，再决定电话接入",
            key_constraints=(),
        ),
        "hotline": GrowthMaterialUnmatchedWorkstream(
            title=f"{prefix}办公热线数字化接入",
            summary="完成固定电话/总机/线路、录音和转接的数字化接入闭环",
            evidence_excerpt=evidence.hotline,
            suggested_nodes=existing_nodes.get("hotline")
            or ["建议：完成电话线路现场勘察并确认数字化接入方案"],
            priority_axis=_voice_priority(
                evidence.hotline,
                default_low=evidence.explicitly_sequenced,
            ),
            progress_health=hotline_health,
            placement_reason="原文显示电话数字化依赖线路、总机、录音或现场勘察条件",
            confidence=0.94 if evidence.explicitly_sequenced else 0.88,
            objective="把现有热线建成可分流、可留痕、可追踪的数字链路",
            success_criteria=("呼入转接链路可用", "录音转写与工单使用统一标识"),
            strategy_summary="先完成线路数字化和完整留痕，再引入 AI 前置接听",
            key_constraints=("电话总机与线路条件待现场验证",),
        ),
    }
    split_workstreams = [
        split_workstreams_by_kind[kind]
        for kind in ("online", "hotline")
        if kind not in existing_target_kinds
    ]
    kept_unmatched[insertion_index:insertion_index] = split_workstreams
    return kept_targets, kept_unmatched


def _unmatched_evidence_is_explicitly_unconfirmed(
    item: GrowthMaterialUnmatchedWorkstream,
    *,
    original_text: str,
) -> bool:
    """Reject capability headings whose adjacent source explicitly denies scope.

    The gate is deliberately narrow: ordinary blockers and pending actions are
    valid tracking material.  Only explicit absence-of-scope/commitment language
    disqualifies creation of a new long-running workstream.
    """
    evidence = item.evidence_excerpt
    candidate_key = _material_business_title_key(item.title, strip_delivery_suffix=True)
    if not candidate_key:
        return False
    for pattern in _MATERIAL_UNCONFIRMED_PATTERNS:
        if pattern.search(evidence) and candidate_key in _evidence_key(evidence):
            return True
    # A table often places the short capability name on one row and its
    # qualification on the following rows.  Inspect only title-like evidence;
    # this avoids applying a later caveat about another capability to a genuine
    # project sentence earlier in the document.
    evidence_key = _evidence_key(evidence)
    if len(evidence_key) > 40 or (
        candidate_key not in evidence_key and evidence_key not in candidate_key
    ):
        return False
    position = original_text.find(evidence)
    if position < 0:
        return False
    following = original_text[position : position + len(evidence) + 360]
    return any(pattern.search(following) for pattern in _MATERIAL_UNCONFIRMED_PATTERNS)


def _target_title_match_score(
    workstream_title: str,
    target: GrowthMaterialTargetContext,
) -> float:
    candidate = _material_business_title_key(workstream_title)
    choices = [target.title]
    if target.parent_title:
        choices.append(target.parent_title)
    score = 0.0
    for value in choices:
        existing = _material_business_title_key(value)
        if not candidate or not existing:
            continue
        if _TYPESETTING_TITLE_RE.search(workstream_title) and _TYPESETTING_TITLE_RE.search(value):
            candidate_score = 0.96
        elif candidate == existing:
            candidate_score = 1.0
        elif min(len(candidate), len(existing)) >= 4 and (
            candidate in existing or existing in candidate
        ):
            candidate_score = 0.9
        else:
            candidate_score = SequenceMatcher(None, candidate, existing).ratio()
        score = max(score, candidate_score)
    if target.target_type == "work_item":
        score += 0.01
    return score


def _reroute_existing_workstreams(
    unmatched: list[GrowthMaterialUnmatchedWorkstream],
    *,
    target_catalog: list[GrowthMaterialTargetContext],
) -> tuple[list[GrowthMaterialTargetAnalysis], list[GrowthMaterialUnmatchedWorkstream]]:
    routed: list[GrowthMaterialTargetAnalysis] = []
    remaining: list[GrowthMaterialUnmatchedWorkstream] = []
    for item in unmatched:
        ranked = sorted(
            (
                (_target_title_match_score(item.title, target), target)
                for target in target_catalog
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.86:
            remaining.append(item)
            continue
        score, target = ranked[0]
        routed.append(
            GrowthMaterialTargetAnalysis(
                target_key=target.target_key,
                evidence_excerpts=[item.evidence_excerpt],
                relevance_reason="AI 候选名称与已有工作线等价，已归入已有线索",
                priority_axis=item.priority_axis,
                progress_health=item.progress_health,
                placement_reason=item.placement_reason,
                proposed_node_status=None,
                confidence=max(item.confidence, min(score, 1.0)),
                impact_kind="context",
                headline=item.summary,
                causal_reason="本材料首次建立或补充了该工作线的交付闭环",
                previous_state=None,
                current_state=item.summary,
                next_gap=None,
            )
        )
    return routed, remaining


def _merge_axis(
    values: list[str],
    *,
    risk_first: bool = False,
    prefer_latest: bool = False,
) -> str:
    known = [value for value in values if value != "unknown"]
    if not known:
        return "unknown"
    if prefer_latest:
        return known[-1]
    if risk_first and "at_risk" in known:
        return "at_risk"
    if not risk_first and "high" in known:
        return "high"
    return known[-1] if len(set(known)) == 1 else "unknown"


def _merge_impact(values: list[str]) -> str:
    """Use source order for the latest meaningful project-state change.

    A fixed severity order makes an early setback permanently override a later
    verified advance. Chunks are appended in source order, so the last
    state-changing impact is the best bounded representation of current state.
    Context/no-change remain useful when no chunk reports a state transition.
    """
    known = [value for value in values if value != "unknown"]
    if not known:
        return "unknown"
    for value in reversed(known):
        if value in {"redirected", "setback", "advanced"}:
            return value
    return known[-1]


def analyze_growth_material_with_ai(
    *,
    user_id: int,
    text: str,
    material_type: str,
    material_title: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    occurred_at_precision: Literal["date", "datetime", "unknown"] = "unknown",
    target_catalog: Optional[list[GrowthMaterialTargetContext]] = None,
    project_catalog: Optional[list[GrowthMaterialProjectContext]] = None,
) -> GrowthMaterialAIResult:
    """Analyze long material in bounded chunks with one controlled repair pass."""
    with SessionLocal() as configuration_db:
        configuration = effective_ai_configuration(configuration_db)
    if configuration is None:
        _audit(
            None,
            user_id=user_id,
            status="failed",
            feature=MATERIAL_FEATURE,
            error_code="AIConfigurationUnavailable",
        )
        raise HTTPException(
            status_code=503,
            detail={"message": "AI 分析服务暂时不可用，已保留原文", "code": "AIConfigurationUnavailable"},
        )

    target_catalog = (target_catalog or [])[:MATERIAL_MAX_TARGETS]
    project_catalog = (project_catalog or [])[:MATERIAL_MAX_PROJECTS]
    allowed_target_keys = {item.target_key for item in target_catalog}
    allowed_project_keys = {item.project_key for item in project_catalog}
    chunks = _material_chunks(text)
    started = time.monotonic()
    total_usage: dict[str, int] = {}
    all_statements: list[GrowthMaterialStatementCandidate] = []
    all_projects: list[GrowthMaterialProjectAnalysis] = []
    all_targets: list[GrowthMaterialTargetAnalysis] = []
    all_unmatched: list[GrowthMaterialUnmatchedWorkstream] = []
    chunk_axes: list[tuple[str, str, str, str | None]] = []
    repaired = False
    attempt_count = 0
    successful_chunks = 0
    chunk_errors: list[Exception] = []
    try:
        for chunk_index, original_chunk in enumerate(chunks):
            redacted_chunk = redact_growth_text(original_chunk)
            evidence_units, evidence_lookup = _material_evidence_catalog(original_chunk)
            user_payload = {
                "material_type": material_type,
                "material_title": redact_growth_text((material_title or "").strip()) or None,
                "material_occurrence": {
                    "occurred_at": occurred_at.isoformat() if occurred_at is not None else None,
                    "precision": occurred_at_precision,
                    "source": "human_supplied" if occurred_at is not None else "unknown",
                },
                "chunk": {
                    "index": chunk_index + 1,
                    "total": len(chunks),
                    "evidence_units": evidence_units,
                },
                "target_catalog": _target_catalog_payload(target_catalog),
                "project_contexts": _project_context_payload(project_catalog, target_catalog),
            }
            previous_content: Any = None
            last_exc: Exception | None = None
            for attempt in range(MATERIAL_REPAIR_ATTEMPTS + 1):
                attempt_count += 1
                messages = [
                    {"role": "system", "content": _material_system_prompt()},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ]
                if attempt and previous_content is not None:
                    repair_detail = (
                        "请仅修复 JSON 结构、target_key 和逐字证据引用；"
                    )
                    if last_exc is not None and "MaterialTargetCoverageMissing:" in str(last_exc):
                        omitted_keys = str(last_exc).split(
                            "MaterialTargetCoverageMissing:", 1
                        )[1]
                        repair_detail = (
                            "上一个输出有项目层或事实证据，但遗漏了明确命中的已有工作线。"
                            f"请逐条重新判断这些候选 target_key：{omitted_keys}。"
                            "只输出证据确实改变了该线可执行状态的 target_analyses，"
                            "按 advanced/setback/redirected/context 边界独立判定；"
                            "不得把未发生的验收写成已完成，也不得为了凑数输出无关线。"
                        )
                    elif last_exc is not None and "MaterialProjectCoverageMissing:" in str(last_exc):
                        omitted_keys = str(last_exc).split(
                            "MaterialProjectCoverageMissing:", 1
                        )[1]
                        repair_detail = (
                            "材料已经明确归入一个用户确认的项目，且上一个输出已有有效工作线增量或事实证据，"
                            "但遗漏了项目总目标层判断。"
                            f"请为这些 project_key 补充 project_analyses：{omitted_keys}。"
                            "必须独立判断 advanced/setback/redirected/context/no_change；"
                            "不得强行写成 advanced，不得伪造已完成结果；若只补充背景就用 context，"
                            "若只是重复已知状态就用 no_change。"
                            "请在完整 JSON 中保留上一个输出里仍有效的 statements、target_analyses "
                            "和 unmatched_workstreams。"
                        )
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": previous_content
                                if isinstance(previous_content, str)
                                else json.dumps(previous_content, ensure_ascii=False),
                            },
                            {
                                "role": "user",
                                "content": (
                                    "上一个输出无法通过结构或原文证据校验。"
                                    f"{repair_detail}"
                                    f"错误类型：{_material_error_code(last_exc) if last_exc else 'unknown'}。"
                                    "不得添加输入中没有的事实。只输出精简、完整 JSON。"
                                ),
                            },
                        ]
                    )
                try:
                    body = _post_material_model(
                        configuration,
                        messages=messages,
                        max_tokens=(
                            MATERIAL_REPAIR_MAX_TOKENS
                            if attempt
                            else MATERIAL_RESPONSE_MAX_TOKENS
                        ),
                    )
                    _merge_usage(total_usage, body.get("usage"))
                    choice = body["choices"][0]
                    previous_content = choice.get("message", {}).get("content")
                    finish_reason = choice.get("finish_reason")
                    if finish_reason not in {None, "stop"}:
                        raise ValueError(f"ModelFinishReason:{finish_reason}")
                    payload, statements, projects, targets, unmatched, placement_excerpt = (
                        _validated_material_payload(
                            content=previous_content,
                            original_chunk=original_chunk,
                            redacted_chunk=redacted_chunk,
                            allowed_target_keys=allowed_target_keys,
                            allowed_project_keys=allowed_project_keys,
                            evidence_lookup=evidence_lookup,
                        )
                    )
                    omitted_project_keys = _likely_omitted_project_keys(
                        project_catalog=project_catalog,
                        projects=projects,
                        targets=targets,
                        statements=statements,
                        unmatched=unmatched,
                        target_catalog=target_catalog,
                    )
                    if omitted_project_keys:
                        raise ValueError(
                            "MaterialProjectCoverageMissing:"
                            + ",".join(omitted_project_keys)
                        )
                    if not targets:
                        omitted_target_keys = _likely_omitted_target_keys(
                            target_catalog=target_catalog,
                            projects=projects,
                            statements=statements,
                        )
                        if omitted_target_keys:
                            raise ValueError(
                                "MaterialTargetCoverageMissing:"
                                + ",".join(omitted_target_keys)
                            )
                    all_statements.extend(statements)
                    all_projects.extend(projects)
                    all_targets.extend(targets)
                    all_unmatched.extend(unmatched)
                    chunk_axes.append(
                        (
                            payload.priority_axis,
                            payload.progress_health,
                            payload.placement_reason.strip(),
                            placement_excerpt,
                        )
                    )
                    if attempt:
                        repaired = True
                    successful_chunks += 1
                    last_exc = None
                    break
                except (
                    httpx.HTTPError,
                    KeyError,
                    ValueError,
                    json.JSONDecodeError,
                    ValidationError,
                ) as exc:
                    last_exc = exc
                    repairable = _material_error_is_repairable(exc)
                    if attempt < MATERIAL_REPAIR_ATTEMPTS and repairable:
                        continue
                    break
            if last_exc is not None:
                chunk_errors.append(last_exc)
                continue

        if successful_chunks == 0 and chunk_errors:
            raise chunk_errors[-1]

        statement_seen: set[tuple[str, str, str]] = set()
        statements = []
        for item in all_statements:
            key = (item.statement_type, item.text, item.evidence_excerpt)
            if key not in statement_seen:
                statement_seen.add(key)
                statements.append(item)

        grouped_projects: dict[str, list[GrowthMaterialProjectAnalysis]] = defaultdict(list)
        for item in all_projects:
            grouped_projects[item.project_key].append(item)
        projects = []
        for key, values in grouped_projects.items():
            projects.append(
                GrowthMaterialProjectAnalysis(
                    project_key=key,
                    evidence_excerpts=list(
                        dict.fromkeys(
                            excerpt
                            for value in values
                            for excerpt in value.evidence_excerpts
                        )
                    )[:20],
                    impact_kind=_merge_impact([value.impact_kind for value in values]),
                    headline="；".join(
                        dict.fromkeys(value.headline for value in values if value.headline)
                    )[:500] or "本次对项目总目标的作用尚待判断",
                    causal_reason="；".join(
                        dict.fromkeys(
                            value.causal_reason for value in values if value.causal_reason
                        )
                    )[:2000] or "原文证据不足",
                    previous_state=next(
                        (value.previous_state for value in values if value.previous_state),
                        None,
                    ),
                    current_state=next(
                        (value.current_state for value in reversed(values) if value.current_state),
                        None,
                    ),
                    next_gap=next(
                        (value.next_gap for value in reversed(values) if value.next_gap),
                        None,
                    ),
                    confidence=max(value.confidence for value in values),
                )
            )

        all_targets, all_unmatched = _apply_voice_delivery_boundary(
            all_targets,
            all_unmatched,
            original_text=text,
            material_title=material_title,
            target_catalog=target_catalog,
        )

        qualified_unmatched: list[GrowthMaterialUnmatchedWorkstream] = []
        for item in all_unmatched:
            item = _canonicalize_unmatched_title(item, material_title=material_title)
            item = _canonicalize_typesetting_workstream(item, original_text=text)
            if _unmatched_evidence_is_explicitly_unconfirmed(item, original_text=text):
                continue
            qualified_unmatched.append(item)
        routed_targets, all_unmatched = _reroute_existing_workstreams(
            qualified_unmatched,
            target_catalog=target_catalog,
        )
        all_targets.extend(routed_targets)

        grouped_targets: dict[str, list[GrowthMaterialTargetAnalysis]] = defaultdict(list)
        for item in all_targets:
            grouped_targets[item.target_key].append(item)
        targets = []
        for key, values in grouped_targets.items():
            evidence = list(
                dict.fromkeys(excerpt for value in values for excerpt in value.evidence_excerpts)
            )[:20]
            targets.append(
                GrowthMaterialTargetAnalysis(
                    target_key=key,
                    evidence_excerpts=evidence,
                    relevance_reason="；".join(dict.fromkeys(value.relevance_reason for value in values))[:1000],
                    priority_axis=_merge_axis(
                        [value.priority_axis for value in values], prefer_latest=True
                    ),
                    progress_health=_merge_axis(
                        [value.progress_health for value in values], prefer_latest=True
                    ),
                    placement_reason="；".join(
                        dict.fromkeys(value.placement_reason for value in values)
                    )[:1000],
                    proposed_node_status=next(
                        (
                            value.proposed_node_status
                            for value in reversed(values)
                            if value.proposed_node_status is not None
                        ),
                        None,
                    ),
                    confidence=max(value.confidence for value in values),
                    impact_kind=_merge_impact([value.impact_kind for value in values]),
                    headline="；".join(
                        dict.fromkeys(value.headline for value in values if value.headline)
                    )[:500] or "本次变化尚待判断",
                    causal_reason="；".join(
                        dict.fromkeys(value.causal_reason for value in values if value.causal_reason)
                    )[:2000] or "原文证据不足",
                    previous_state=next(
                        (value.previous_state for value in values if value.previous_state), None
                    ),
                    current_state=next(
                        (value.current_state for value in reversed(values) if value.current_state), None
                    ),
                    next_gap=next(
                        (value.next_gap for value in reversed(values) if value.next_gap), None
                    ),
                )
            )

        unmatched_by_title: dict[str, GrowthMaterialUnmatchedWorkstream] = {}
        for item in all_unmatched:
            key = _evidence_key(item.title)
            previous = unmatched_by_title.get(key)
            if previous is None or item.confidence > previous.confidence:
                unmatched_by_title[key] = item
        unmatched = list(unmatched_by_title.values())

        if len(targets) == 1:
            priority_axis = targets[0].priority_axis
            progress_health = targets[0].progress_health
            placement_reason = targets[0].placement_reason
            placement_excerpt = targets[0].evidence_excerpts[0] if targets[0].evidence_excerpts else None
        elif len(targets) > 1:
            priority_axis = progress_health = "unknown"
            placement_reason = f"材料涉及 {len(targets)} 条工作线，已按工作线分别判断"
            placement_excerpt = None
        else:
            priority_axis = _merge_axis([value[0] for value in chunk_axes])
            progress_health = _merge_axis([value[1] for value in chunk_axes], risk_first=True)
            placement_reason = "；".join(
                dict.fromkeys(value[2] for value in chunk_axes if value[2])
            )[:1000] or "未找到可归属的已有工作线"
            placement_excerpt = next((value[3] for value in chunk_axes if value[3]), None)

        partial_error_codes = tuple(
            dict.fromkeys(_material_error_code(error) for error in chunk_errors)
        )
        _audit(
            configuration,
            user_id=user_id,
            status="partial" if partial_error_codes else "success",
            feature=MATERIAL_FEATURE,
            latency_ms=round((time.monotonic() - started) * 1000),
            usage=total_usage,
            error_code=(
                "MaterialAIPartial:" + ",".join(partial_error_codes)
                if partial_error_codes
                else None
            ),
        )
        return GrowthMaterialAIResult(
            statements=statements,
            target_analyses=targets,
            unmatched_workstreams=unmatched,
            priority_axis=priority_axis,
            progress_health=progress_health,
            placement_reason=placement_reason,
            placement_evidence_excerpt=placement_excerpt,
            provider_name=configuration.provider_name,
            model=configuration.model,
            parser_version=(
                MATERIAL_PROMPT_VERSION
                + (":repaired" if repaired else "")
                + (":partial" if chunk_errors else "")
            ),
            repaired=repaired,
            attempt_count=attempt_count,
            partial=bool(partial_error_codes),
            partial_error_codes=partial_error_codes,
            project_analyses=projects,
        )
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        error_code = _material_error_code(exc)
        _audit(
            configuration,
            user_id=user_id,
            status="failed",
            feature=MATERIAL_FEATURE,
            latency_ms=round((time.monotonic() - started) * 1000),
            usage=total_usage,
            error_code=error_code,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "AI 结果未通过结构或原文证据校验，已保留材料并降级整理",
                "code": error_code,
            },
        ) from exc
