from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.growth import (
    GrowthAuditEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
    GrowthWorkMaterial,
    GrowthWorkMaterialLink,
    GrowthWorkMaterialRelation,
    GrowthWorkMaterialRequest,
    GrowthWorkMaterialStatement,
    GrowthWorkNode,
    GrowthWorkPlacementEvent,
    GrowthWorkProgressEvent,
    GrowthProjectProfile,
    GrowthProjectProgressEvent,
)
from app.models.user import User
from app.schemas.growth import (
    GrowthConfirmIntakeRequest,
    GrowthWorkBoardResponse,
    GrowthWorkCandidate,
    GrowthWorkMaterialConfirm,
    GrowthWorkMaterialCreate,
    GrowthWorkMaterialDetailResponse,
    GrowthWorkMaterialListResponse,
    GrowthWorkMaterialMetadataUpdate,
    GrowthWorkMaterialReanalyze,
    GrowthWorkMaterialWorkstreamsConfirm,
    GrowthWorkNodeCandidate,
    GrowthWorkPlacementUpdate,
    GrowthWorkProgressEventReview,
    GrowthProjectProfileUpsert,
    GrowthProjectProfileResponse,
    GrowthProjectProgressEventReview,
    GrowthProjectProgressEventResponse,
    GrowthProjectTimelineResponse,
    GrowthWorkTrackingProfileUpdate,
    GrowthWorkTimelineResponse,
    GrowthProgressReviewResponse,
)
from app.services.growth_ai_service import (
    GrowthMaterialAIResult,
    GrowthMaterialStatementCandidate,
    GrowthMaterialTargetAnalysis,
    GrowthMaterialTargetContext,
    GrowthMaterialProjectAnalysis,
    GrowthMaterialProjectContext,
    GrowthMaterialUnmatchedWorkstream,
    analyze_growth_material_with_ai,
)
from app.services.growth_work_service import confirm_growth_intake


MATERIAL_RULE_VERSION = "growth-material-rules-v1"
ROUTING_RULE_VERSION = "growth-material-routing-v1"
AI_ROUTING_RULE_VERSION = "growth-material-ai-routing-v2"
PLACEMENT_RULE_VERSION = "growth-placement-v1"
MANUAL_ROUTE_VERSION = "growth-material-manual-route-v1"
MANUAL_PLACEMENT_RULE_VERSION = "growth-placement-manual-v1"
RECOMPUTED_PLACEMENT_RULE_VERSION = "growth-placement-recomputed-v1"
PROGRESS_RULE_VERSION = "growth-progress-ai-v1"
PROJECT_PROGRESS_RULE_VERSION = "growth-project-progress-ai-v1"
MATERIAL_TARGET_CATALOG_LIMIT = 120
MATERIAL_PROJECT_CATALOG_LIMIT = 20
ACTIVE_STATUSES = ("captured", "planned", "in_progress", "blocked", "deferred")
QUADRANT_LABELS = {
    "focus": "重点破局",
    "breakthrough": "稳步推进",
    "maintain": "例行维持",
    "clarify": "待澄清",
    "unknown": "待判断",
}
QUADRANT_ORDER = ("focus", "breakthrough", "maintain", "clarify", "unknown")


@dataclass(frozen=True)
class _MaterialAnalysis:
    statements: list[GrowthMaterialStatementCandidate]
    project_analyses: list[GrowthMaterialProjectAnalysis]
    target_analyses: list[GrowthMaterialTargetAnalysis]
    unmatched_workstreams: list[GrowthMaterialUnmatchedWorkstream]
    priority_axis: Literal["high", "low", "unknown"]
    progress_health: Literal["healthy", "at_risk", "unknown"]
    placement_reason: str
    placement_evidence_excerpt: str | None
    analysis_mode: Literal["rules", "ai"]
    parser_version: str
    provider_name: str | None = None
    model: str | None = None
    fallback_reason: str | None = None
    external_processing_used: bool = False


@dataclass(frozen=True)
class _TargetCandidate:
    target_type: Literal["work_item", "node"]
    target_id: int
    work_item: GrowthWorkItem
    node: GrowthWorkNode | None
    confidence: float
    reason: str
    evidence_spans: list[dict[str, Any]]
    analysis_mode: Literal["rules", "ai"] = "rules"
    priority_axis: Literal["high", "low", "unknown"] = "unknown"
    progress_health: Literal["healthy", "at_risk", "unknown"] = "unknown"
    placement_reason: str | None = None
    proposed_node_status: str | None = None
    impact_kind: Literal[
        "advanced", "setback", "redirected", "context", "no_change", "unknown"
    ] = "unknown"
    progress_headline: str = "本次变化尚待判断"
    causal_reason: str = "原文证据不足"
    previous_state: str | None = None
    current_state: str | None = None
    next_gap: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalized_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _analysis_revision(base_rule: str, material_version: int) -> str:
    """Give each material analysis run an immutable, reviewable identity."""
    return f"{base_rule}:m{material_version}"


@dataclass(frozen=True)
class _InferredOccurredAt:
    value: datetime
    precision: Literal["date", "datetime"]
    evidence_excerpt: str


_EVENT_DATE_TOKEN = (
    r"(?P<year>20\d{2})\s*(?:[-/.]\s*|\u5e74\s*)"
    r"(?P<month>0?[1-9]|1[0-2])\s*(?:[-/.]\s*|\u6708\s*)"
    r"(?P<day>0?[1-9]|[12]\d|3[01])\s*\u65e5?"
)
_EXPLICIT_EVENT_DATE_PATTERNS = (
    # Structured meeting metadata, including markdown tables.
    re.compile(
        rf"(?:\u4f1a\u8bae\u65f6\u95f4|\u4f1a\u8bae\u65e5\u671f)\s*(?:\||[:\uff1a])?\s*{_EVENT_DATE_TOKEN}"
    ),
    # Source descriptions such as \"based on the 2026-08-05 meeting transcript\".
    re.compile(
        rf"(?:\u57fa\u4e8e|\u4f9d\u636e)\s*{_EVENT_DATE_TOKEN}\s*(?:\u7684\s*)?\u4f1a\u8bae(?:\u9010\u5b57\u8bb0\u5f55|\u5f55\u97f3\u8f6c\u5199|\u5f55\u97f3|\u7eaa\u8981|\u8bb0\u5f55)?"
    ),
)


def _infer_material_occurred_at(content: str) -> _InferredOccurredAt | None:
    """Infer only an explicitly labelled event/meeting date.

    A document version/update date is deliberately not accepted.  This keeps
    long proposals and revised reports on an unknown event timeline instead of
    silently turning their publication date into a meeting date.
    """
    for pattern in _EXPLICIT_EVENT_DATE_PATTERNS:
        match = pattern.search(content)
        if match is None:
            continue
        try:
            value = datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue
        return _InferredOccurredAt(
            value=value,
            precision="date",
            evidence_excerpt=match.group(0)[:500],
        )
    return None


def _effective_material_occurrence(
    data: GrowthWorkMaterialCreate,
) -> tuple[datetime | None, str, _InferredOccurredAt | None]:
    explicit = _normalized_datetime(data.occurred_at)
    if explicit is not None:
        return explicit, data.occurred_at_precision, None
    # Customer/project and event time are user-owned metadata.  The Agent may
    # read dates as evidence, but it never persists a guessed meeting date.
    return None, "unknown", None


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _request_fingerprint(operation: str, payload: dict[str, Any]) -> str:
    message = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _audit(
    db: Session,
    *,
    user_id: int,
    entity_type: str,
    entity_id: int | None,
    action: str,
    request_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(
        GrowthAuditEvent(
            user_id=user_id,
            actor_user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            request_id=request_id,
            before_payload=before,
            after_payload=after,
        )
    )


def _sentence_spans(content: str) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for matched in re.finditer(r"[^\n；;。！？!?]+(?:[\n；;。！？!?]|$)", content):
        raw = matched.group(0)
        leading = len(raw) - len(raw.lstrip())
        excerpt = raw.strip()
        if len(excerpt) < 2:
            continue
        start = matched.start() + leading
        spans.append({"start": start, "end": start + len(excerpt), "excerpt": excerpt})
    return spans[:1000]


def _statement_type(excerpt: str, material_type: str) -> str | None:
    question_markers = ("待确认", "需确认", "请确认", "是否", "尚未明确", "还需要确认")
    vendor_markers = (
        "厂商表示",
        "供应商表示",
        "厂商声称",
        "可达到",
        "精度提升",
        "幻觉",
        "模型规模",
        "我们的能力",
    )
    scope_markers = ("范围调整", "优先级调整", "改为", "转为", "不再", "暂不", "后移", "新增方向")
    conflict_markers = ("与此前不一致", "与之前不一致", "口径冲突", "前后矛盾", "存在冲突", "改口")
    proposal_markers = ("建议", "推荐", "计划", "拟", "预计", "希望", "可以先", "方案是", "考虑")
    decision_markers = ("会议确认", "已确认", "明确决定", "决定", "双方同意", "最终确认")
    action_markers = ("下一步", "后续由", "会后", "尽快", "本周启动", "负责", "行动项")
    fact_markers = (
        "已完成",
        "已经完成",
        "已收到",
        "已提供",
        "已分析",
        "已交付",
        "已召开",
        "当前为",
        "实际为",
        "客户反馈",
        "录音显示",
    )
    if any(marker in excerpt for marker in conflict_markers):
        return "conflict"
    if "？" in excerpt or "?" in excerpt or any(marker in excerpt for marker in question_markers):
        return "open_question"
    if any(marker in excerpt for marker in vendor_markers):
        return "vendor_claim"
    if any(marker in excerpt for marker in scope_markers):
        return "scope_change"
    if any(marker in excerpt for marker in proposal_markers):
        return "proposal"
    if any(marker in excerpt for marker in decision_markers):
        return "decision"
    if any(marker in excerpt for marker in fact_markers):
        return "confirmed_fact"
    if any(marker in excerpt for marker in action_markers):
        return "action"
    if material_type == "proposal":
        return "proposal"
    if material_type == "plan":
        return "action"
    return None


def _axis_from_text(
    text: str,
    *,
    material_type: str,
) -> tuple[str, str, str, str | None]:
    spans = _sentence_spans(text)
    high_markers = ("最高优先级", "高优先级", "优先启动", "紧急", "关键交付", "本周必须")
    low_markers = ("低优先级", "暂缓", "后续再做", "非关键", "中长期")
    risk_markers = ("当前卡住", "已延期", "阻塞", "还缺", "缺少", "无法继续", "存在风险", "等待确认")
    healthy_markers = ("进展顺利", "按计划推进", "正在推进", "已启动", "已完成", "已交付", "通过验收")

    high_span = next((span for span in spans if any(marker in span["excerpt"] for marker in high_markers)), None)
    low_span = next((span for span in spans if any(marker in span["excerpt"] for marker in low_markers)), None)
    priority = "high" if high_span and not low_span else "low" if low_span and not high_span else "unknown"

    health = "unknown"
    health_span: dict[str, Any] | None = None
    if material_type not in {"proposal", "plan"}:
        risk_span = next((span for span in spans if any(marker in span["excerpt"] for marker in risk_markers)), None)
        healthy_span = next((span for span in spans if any(marker in span["excerpt"] for marker in healthy_markers)), None)
        if risk_span and not healthy_span:
            health, health_span = "at_risk", risk_span
        elif healthy_span and not risk_span:
            health, health_span = "healthy", healthy_span

    evidence = (high_span or low_span or health_span)
    reason_parts = []
    if priority != "unknown":
        reason_parts.append("材料包含明确的优先级表述")
    if health == "healthy":
        reason_parts.append("材料包含已发生的健康进展证据")
    elif health == "at_risk":
        reason_parts.append("材料包含已出现的阻塞或风险证据")
    if not reason_parts:
        reason_parts.append("材料不足以判定优先级或进展健康度")
    return priority, health, "；".join(reason_parts), evidence["excerpt"] if evidence else None


def analyze_growth_material_with_rules(content: str, material_type: str) -> _MaterialAnalysis:
    statements: list[GrowthMaterialStatementCandidate] = []
    seen: set[tuple[str, str]] = set()
    confidence_by_type = {
        "confirmed_fact": 0.82,
        "decision": 0.86,
        "proposal": 0.8,
        "open_question": 0.9,
        "vendor_claim": 0.78,
        "scope_change": 0.82,
        "action": 0.78,
        "conflict": 0.88,
    }
    for span in _sentence_spans(content):
        statement_type = _statement_type(span["excerpt"], material_type)
        if statement_type is None:
            continue
        key = (statement_type, span["excerpt"])
        if key in seen:
            continue
        seen.add(key)
        statements.append(
            GrowthMaterialStatementCandidate(
                statement_type=statement_type,
                text=span["excerpt"][:2000],
                evidence_excerpt=span["excerpt"][:2000],
                confidence=confidence_by_type[statement_type],
            )
        )
        if len(statements) >= 200:
            break
    priority, health, reason, evidence = _axis_from_text(content, material_type=material_type)
    return _MaterialAnalysis(
        statements=statements,
        project_analyses=[],
        target_analyses=[],
        unmatched_workstreams=[],
        priority_axis=priority,
        progress_health=health,
        placement_reason=reason,
        placement_evidence_excerpt=evidence,
        analysis_mode="rules",
        parser_version=MATERIAL_RULE_VERSION,
    )


def _ai_analysis(result: GrowthMaterialAIResult) -> _MaterialAnalysis:
    return _MaterialAnalysis(
        statements=result.statements,
        project_analyses=result.project_analyses,
        target_analyses=result.target_analyses,
        unmatched_workstreams=result.unmatched_workstreams,
        priority_axis=result.priority_axis,
        progress_health=result.progress_health,
        placement_reason=result.placement_reason,
        placement_evidence_excerpt=result.placement_evidence_excerpt,
        analysis_mode="ai",
        parser_version=result.parser_version,
        provider_name=result.provider_name,
        model=result.model,
        external_processing_used=True,
        fallback_reason="ai_partial" if result.partial else None,
    )


def _analysis_failed(analysis: _MaterialAnalysis) -> bool:
    return bool(analysis.fallback_reason and analysis.fallback_reason != "ai_partial")


def _fallback_reason(exc: HTTPException) -> str:
    if exc.status_code == 503:
        return "ai_unavailable"
    if exc.status_code == 502:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code")
        return {
            "MaterialAIResponseTruncated": "ai_output_truncated",
            "MaterialAIResponseInvalidJSON": "ai_output_json_invalid",
            "MaterialAIResponseSchemaInvalid": "ai_output_schema_invalid",
            "MaterialAIEvidenceInvalid": "ai_evidence_unverified",
            "MaterialAITargetInvalid": "ai_target_unverified",
            "MaterialAITimeout": "ai_timeout",
            "MaterialAINetworkError": "ai_network_error",
        }.get(code, "ai_response_invalid")
    return "ai_failed"


def _failed_ai_analysis(exc: HTTPException) -> _MaterialAnalysis:
    fallback_reason = _fallback_reason(exc)
    return _MaterialAnalysis(
        statements=[],
        project_analyses=[],
        target_analyses=[],
        unmatched_workstreams=[],
        priority_axis="unknown",
        progress_health="unknown",
        placement_reason="AI 分析未通过结构与原文证据校验，未生成占位建议",
        placement_evidence_excerpt=None,
        analysis_mode="rules",
        parser_version=MATERIAL_RULE_VERSION,
        fallback_reason=fallback_reason,
        external_processing_used=fallback_reason != "ai_unavailable",
    )


def _quadrant(priority_axis: str, progress_health: str) -> str:
    return {
        ("high", "at_risk"): "focus",
        ("high", "healthy"): "breakthrough",
        ("low", "healthy"): "maintain",
        ("low", "at_risk"): "clarify",
    }.get((priority_axis, progress_health), "unknown")


def _normalized_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def _title_match(title: str, content_spans: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]]]:
    normalized_title = _normalized_text(title)
    if len(normalized_title) < 2:
        return 0.0, []
    grams = {
        normalized_title[index : index + 2]
        for index in range(max(1, len(normalized_title) - 1))
    }
    matches: list[tuple[float, dict[str, Any]]] = []
    for span in content_spans:
        normalized_excerpt = _normalized_text(span["excerpt"])
        if normalized_title in normalized_excerpt:
            matches.append((0.98, span))
            continue
        if not grams:
            continue
        coverage = sum(1 for gram in grams if gram in normalized_excerpt) / len(grams)
        if coverage >= 0.6:
            matches.append((round(0.45 + coverage * 0.45, 2), span))
    if not matches:
        return 0.0, []
    matches.sort(key=lambda item: (-item[0], item[1]["start"]))
    return matches[0][0], [dict(item[1]) for item in matches[:5]]


def _dominant_link_type(
    statements: list[GrowthWorkMaterialStatement],
    target_spans: list[dict[str, Any]],
) -> str:
    target_text = "\n".join(span["excerpt"] for span in target_spans)
    relevant = [item for item in statements if item.evidence_excerpt in target_text] or statements
    rank = {
        "conflict": 0,
        "scope_change": 1,
        "decision": 2,
        "confirmed_fact": 3,
        "action": 4,
        "open_question": 5,
        "proposal": 6,
        "vendor_claim": 7,
    }
    return min(relevant, key=lambda item: (rank[item.statement_type], item.id)).statement_type if relevant else "context"


def _proposed_node_status(text: str, *, material_type: str) -> str | None:
    if material_type in {"proposal", "plan"}:
        return None
    if any(marker in text for marker in ("已完成", "已经完成", "已交付", "通过验收")):
        return "completed"
    if any(marker in text for marker in ("当前卡住", "已延期", "阻塞", "还缺", "无法继续")):
        return "blocked"
    if any(marker in text for marker in ("正在推进", "已启动", "已开始", "进行中")):
        return "in_progress"
    return None


def _rule_progress_assessment(
    text: str,
    *,
    material_type: str,
) -> tuple[str, str, str, str | None]:
    """Return a conservative impact proposal from explicit wording only.

    This is intentionally weaker than the model comparison.  It gives a
    reviewable fallback without pretending that a plan or a date mention is
    evidence of progress.
    """
    normalized = text.strip()
    if not normalized:
        return "unknown", "本次变化尚待判断", "未找到这条工作线的专属证据", None
    redirected = ("改为", "转为", "不再", "范围调整", "方向调整", "重新定位")
    setback = ("阻塞", "卡住", "延期", "无法继续", "未通过", "失败", "风险上升")
    advanced = (
        "已完成",
        "已经完成",
        "已交付",
        "已验证",
        "验证通过",
        "已跑通",
        "已上线",
        "已解决",
        "通过验收",
        "达成",
    )
    no_change = (
        "无实质变化",
        "没有实质变化",
        "未形成新决定",
        "没有形成新决定",
        "仍维持原结论",
        "重申已知",
    )
    if any(marker in normalized for marker in redirected):
        return "redirected", "项目方向或范围发生变化", "材料出现明确的转向或范围变化表述", normalized[:2000]
    if material_type not in {"proposal", "plan"} and any(
        marker in normalized for marker in setback
    ):
        return "setback", "推进受到阻碍", "材料出现已经发生的阻塞、延期或失败证据", normalized[:2000]
    if material_type not in {"proposal", "plan"} and any(
        marker in normalized for marker in advanced
    ):
        return "advanced", "取得了新的可核验进展", "材料出现已经发生的完成、验证、交付或验收证据", normalized[:2000]
    if any(marker in normalized for marker in no_change):
        return "no_change", "本次没有实质变化", "材料明确未形成新决定或只重复已知信息", normalized[:2000]
    if material_type in {"proposal", "plan"}:
        return "context", "补充了方案或计划背景", "方案和计划不能单独证明结果已经推进", normalized[:2000]
    return "context", "补充了新的项目上下文", "材料与工作线相关，但没有足够证据判断结果变化", normalized[:2000]


def _material_payload(material: GrowthWorkMaterial, *, include_content: bool) -> dict[str, Any]:
    payload = {
        "id": material.id,
        "material_type": material.material_type,
        "title": material.title,
        "account_name": material.account_name,
        "project_id": material.project_id,
        "content_hash": material.content_hash,
        "occurred_at": material.occurred_at,
        "occurred_at_known": material.occurred_at is not None,
        "occurred_at_precision": material.occurred_at_precision,
        "next_follow_up_at": material.next_follow_up_at,
        "source_document_id": material.source_document_id,
        "source_url": material.source_url,
        "analysis_mode": material.analysis_mode,
        "fallback_reason": material.fallback_reason,
        "version": material.version,
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }
    if include_content:
        payload.update(
            {
                "content": material.content,
                "analysis_rule_version": material.analysis_rule_version,
                "ai_requested": material.ai_requested,
                "external_processing_used": material.external_processing_used,
                "provider_name": material.provider_name,
                "model": material.model,
            }
        )
    return payload


def _workstream_candidate(
    material_id: int,
    proposal: GrowthMaterialUnmatchedWorkstream,
    index: int,
    *,
    account_name: str | None,
) -> GrowthWorkCandidate:
    candidate_digest = hashlib.sha256(
        f"{material_id}:{proposal.title}".encode("utf-8")
    ).hexdigest()[:20]
    nodes = [
        GrowthWorkNodeCandidate(
            node_key="material-node-"
            + hashlib.sha256(
                f"{material_id}:{proposal.title}:{node_title}".encode("utf-8")
            ).hexdigest()[:20],
            title=node_title[:300],
            priority_order=(node_index + 1) * 10,
            depends_on_node_keys=[],
            time_hint=None,
        )
        for node_index, node_title in enumerate(proposal.suggested_nodes[:20])
        if node_title.strip()
    ]
    return GrowthWorkCandidate(
        candidate_key=f"material-stream-{candidate_digest}",
        title=proposal.title,
        account_name=account_name,
        objective=proposal.objective,
        success_criteria=list(proposal.success_criteria),
        strategy_summary=proposal.strategy_summary,
        key_constraints=list(proposal.key_constraints),
        description=proposal.summary,
        fact_excerpt=proposal.evidence_excerpt[:500],
        impact_level="high" if proposal.priority_axis == "high" else "unknown",
        energy_level="unknown",
        priority_order=(index + 1) * 10,
        selection_reason="AI 从材料中识别到一条独立交付闭环；建立工作线前需要你确认。",
        confidence=proposal.confidence,
        nodes=nodes,
        resource_links=[],
        open_questions=[],
        tracking_rule="后续会议纪要和进展材料继续归入这条工作线。",
    )


def _normalized_workstream_title(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _workstream_titles_conflict(left: str, right: str) -> bool:
    """Conservative near-duplicate guard for user-confirmed work lines."""
    normalized_left = _normalized_workstream_title(left)
    normalized_right = _normalized_workstream_title(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True
    shorter, longer = sorted((normalized_left, normalized_right), key=len)
    if len(shorter) >= 6 and shorter in longer and len(longer) - len(shorter) <= 4:
        return True
    return (
        min(len(normalized_left), len(normalized_right)) >= 6
        and SequenceMatcher(None, normalized_left, normalized_right).ratio() >= 0.86
    )


def _candidate_title_map(intake: GrowthWorkIntake) -> dict[str, str]:
    payload = intake.candidate_payload if isinstance(intake.candidate_payload, dict) else {}
    return {
        str(item.get("candidate_key")): str(item.get("title") or "").strip()
        for item in payload.get("candidates", [])
        if isinstance(item, dict) and item.get("candidate_key") and item.get("title")
    }


def _guard_workstream_title_conflicts(
    db: Session,
    *,
    user_id: int,
    intake: GrowthWorkIntake,
    selected: list[Any],
) -> None:
    source_titles = _candidate_title_map(intake)
    selected_titles = [
        (
            item.candidate_key,
            ((item.title or "").strip() or source_titles.get(item.candidate_key, "")),
        )
        for item in selected
    ]
    for index, (candidate_key, candidate_title) in enumerate(selected_titles):
        if not candidate_title:
            continue
        for other_key, other_title in selected_titles[index + 1 :]:
            if _workstream_titles_conflict(candidate_title, other_title):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "workstream_title_conflict",
                        "message": "本批候选中存在近义工作线，请只保留一条后再确认",
                        "candidate_key": candidate_key,
                        "candidate_title": candidate_title,
                        "conflicting_candidate_key": other_key,
                        "conflicting_title": other_title,
                    },
                )

    existing_items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status != "cancelled",
            GrowthWorkItem.intake_id != intake.id,
        )
        .all()
    )
    for candidate_key, candidate_title in selected_titles:
        if not candidate_title:
            continue
        conflict = next(
            (
                item
                for item in existing_items
                if _workstream_titles_conflict(candidate_title, item.title)
            ),
            None,
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "workstream_title_conflict",
                    "message": "已有近义工作线；请把材料关联到已有工作线，不要重复创建",
                    "candidate_key": candidate_key,
                    "candidate_title": candidate_title,
                    "existing_work_item_id": conflict.id,
                    "existing_title": conflict.title,
                },
            )


def _persist_workstream_proposals(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    analysis: _MaterialAnalysis,
) -> GrowthWorkIntake | None:
    request_id = f"material-streams:{material.id}"
    intake = (
        db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == request_id,
        )
        .first()
    )
    if analysis.analysis_mode != "ai" or not analysis.unmatched_workstreams:
        if intake is not None and intake.status == "draft":
            intake.status = "cancelled"
            intake.cancelled_at = _now()
        return intake
    candidates = [
        _workstream_candidate(
            material.id,
            proposal,
            index,
            account_name=material.account_name,
        )
        for index, proposal in enumerate(analysis.unmatched_workstreams[:30])
    ]
    proposal_metadata = {
        candidate.candidate_key: {
            "evidence_excerpt": proposal.evidence_excerpt,
            "priority_axis": proposal.priority_axis,
            "progress_health": proposal.progress_health,
            "placement_reason": proposal.placement_reason,
            "confidence": proposal.confidence,
            "objective": proposal.objective,
            "success_criteria": list(proposal.success_criteria),
            "strategy_summary": proposal.strategy_summary,
            "key_constraints": list(proposal.key_constraints),
        }
        for candidate, proposal in zip(candidates, analysis.unmatched_workstreams)
    }
    candidate_payload = {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "emotion": {"detected": False, "summary": None, "deidentified_fact": None},
        "source_material_id": material.id,
        "proposal_metadata": proposal_metadata,
    }
    fingerprint = _request_fingerprint(
        "material_workstream_proposals",
        {"material_id": material.id, "candidates": candidate_payload["candidates"]},
    )
    if intake is None:
        intake = GrowthWorkIntake(
            user_id=user_id,
            request_id=request_id,
            input_fingerprint=fingerprint,
            candidate_payload=candidate_payload,
            parser_version=analysis.parser_version,
            analysis_mode="ai",
            provider_name=analysis.provider_name,
            model=analysis.model,
            status="draft",
        )
        db.add(intake)
        db.flush()
    elif intake.status == "draft":
        intake.input_fingerprint = fingerprint
        intake.candidate_payload = candidate_payload
        intake.parser_version = analysis.parser_version
        intake.provider_name = analysis.provider_name
        intake.model = analysis.model
        db.flush()
    return intake


def _workstream_proposal_batches(
    db: Session,
    *,
    user_id: int,
    material_id: int,
) -> list[dict[str, Any]]:
    intake = (
        db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == f"material-streams:{material_id}",
        )
        .first()
    )
    if intake is None or not isinstance(intake.candidate_payload, dict):
        return []
    payload = intake.candidate_payload
    if payload.get("source_material_id") != material_id:
        return []
    metadata = payload.get("proposal_metadata") or {}
    resolution = payload.get("proposal_resolution") or {}
    confirmed_keys = set(resolution.get("confirmed_candidate_keys") or [])
    dismissed_keys = set(resolution.get("dismissed_candidate_keys") or [])
    if intake.status == "confirmed" and not confirmed_keys and not dismissed_keys:
        # Backward-compatible inference for confirmations written before the
        # explicit resolution metadata existed.
        confirmed_keys = {
            row[0]
            for row in db.query(GrowthWorkItem.candidate_key)
            .filter(
                GrowthWorkItem.user_id == user_id,
                GrowthWorkItem.intake_id == intake.id,
                GrowthWorkItem.deleted_at.is_(None),
            )
            .all()
        }
        dismissed_keys = set(metadata) - confirmed_keys
    candidates = []
    for candidate in payload.get("candidates", []):
        candidate_key = candidate.get("candidate_key")
        candidate_metadata = metadata.get(candidate_key, {})
        priority = candidate_metadata.get("priority_axis") or "unknown"
        health = candidate_metadata.get("progress_health") or "unknown"
        resolution_status = (
            "confirmed"
            if candidate_key in confirmed_keys
            else "dismissed"
            if candidate_key in dismissed_keys or intake.status == "cancelled"
            else "pending"
        )
        candidates.append(
            {
                **candidate,
                "priority_axis": priority,
                "progress_health": health,
                "quadrant": _quadrant(priority, health),
                "placement_reason": candidate_metadata.get("placement_reason")
                or "材料证据不足，保持待判断",
                "evidence_excerpt": candidate_metadata.get("evidence_excerpt") or "",
                "resolution_status": resolution_status,
            }
        )
    return [
        {
            "intake_id": intake.id,
            "source_material_id": material_id,
            "status": intake.status,
            "parser_version": intake.parser_version,
            "selection_policy": "unselected_candidates_dismissed_on_confirm",
            "candidates": candidates,
        }
    ]


def _material_detail(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
) -> GrowthWorkMaterialDetailResponse:
    statements = (
        db.query(GrowthWorkMaterialStatement)
        .filter(
            GrowthWorkMaterialStatement.user_id == user_id,
            GrowthWorkMaterialStatement.material_id == material.id,
        )
        .order_by(GrowthWorkMaterialStatement.id.asc())
        .all()
    )
    links = (
        db.query(GrowthWorkMaterialLink)
        .filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
        )
        .order_by(GrowthWorkMaterialLink.id.asc())
        .all()
    )
    relations = (
        db.query(GrowthWorkMaterialRelation)
        .filter(
            GrowthWorkMaterialRelation.user_id == user_id,
            GrowthWorkMaterialRelation.material_id == material.id,
        )
        .order_by(GrowthWorkMaterialRelation.id.asc())
        .all()
    )
    placements = (
        db.query(GrowthWorkPlacementEvent)
        .filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.material_id == material.id,
        )
        .order_by(GrowthWorkPlacementEvent.id.asc())
        .all()
    )
    progress_events = (
        db.query(GrowthWorkProgressEvent)
        .filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.material_id == material.id,
        )
        .order_by(GrowthWorkProgressEvent.id.asc())
        .all()
    )
    project_progress_events = (
        db.query(GrowthProjectProgressEvent)
        .filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.material_id == material.id,
        )
        .order_by(GrowthProjectProgressEvent.id.asc())
        .all()
    )
    item_ids = (
        {item.work_item_id for item in links}
        | {item.work_item_id for item in placements}
        | {item.work_item_id for item in progress_events}
    )
    item_titles = dict(
        db.query(GrowthWorkItem.id, GrowthWorkItem.title)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.id.in_(item_ids or [-1]),
        )
        .all()
    )
    node_ids = {item.node_id for item in links if item.node_id is not None}
    node_titles = dict(
        db.query(GrowthWorkNode.id, GrowthWorkNode.title)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.id.in_(node_ids or [-1]),
        )
        .all()
    )
    return GrowthWorkMaterialDetailResponse(
        material=_material_payload(material, include_content=True),
        statements=statements,
        links=[
            {
                **{column.name: getattr(link, column.name) for column in link.__table__.columns},
                "work_item_title": item_titles.get(link.work_item_id, "已删除事项"),
                "node_title": node_titles.get(link.node_id) if link.node_id is not None else None,
            }
            for link in links
        ],
        relations=relations,
        placement_events=[
            {
                **{column.name: getattr(item, column.name) for column in item.__table__.columns},
                "work_item_title": item_titles.get(item.work_item_id, "已删除事项"),
            }
            for item in placements
        ],
        progress_events=[
            _progress_event_payload(item, material, include_evidence=True)
            for item in progress_events
        ],
        project_progress_events=[
            _project_progress_event_payload(item, material, include_evidence=True)
            for item in project_progress_events
        ],
        workstream_proposals=_workstream_proposal_batches(
            db,
            user_id=user_id,
            material_id=material.id,
        ),
    )


def get_work_material(
    db: Session,
    *,
    user_id: int,
    material_id: int,
) -> GrowthWorkMaterialDetailResponse:
    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .first()
    )
    if material is None:
        raise HTTPException(status_code=404, detail="工作材料不存在")
    return _material_detail(db, user_id=user_id, material=material)


def list_work_materials(
    db: Session,
    *,
    user_id: int,
    status: str | None = None,
    unassigned_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> GrowthWorkMaterialListResponse:
    allowed_statuses = {"unassigned", "suggested", "confirmed", "dismissed", "mixed"}
    if status is not None and status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="不支持的材料归属状态")
    rows = (
        db.query(
            GrowthWorkMaterial.id,
            GrowthWorkMaterial.material_type,
            GrowthWorkMaterial.title,
            GrowthWorkMaterial.account_name,
            GrowthWorkMaterial.project_id,
            GrowthWorkMaterial.content_hash,
            GrowthWorkMaterial.occurred_at,
            GrowthWorkMaterial.occurred_at_precision,
            GrowthWorkMaterial.next_follow_up_at,
            GrowthWorkMaterial.source_document_id,
            GrowthWorkMaterial.source_url,
            GrowthWorkMaterial.analysis_mode,
            GrowthWorkMaterial.fallback_reason,
            GrowthWorkMaterial.version,
            GrowthWorkMaterial.created_at,
            GrowthWorkMaterial.updated_at,
        )
        .filter(GrowthWorkMaterial.user_id == user_id)
        .order_by(GrowthWorkMaterial.created_at.desc(), GrowthWorkMaterial.id.desc())
        .all()
    )
    counts: dict[int, dict[str, int]] = {}
    for material_id, link_status in (
        db.query(GrowthWorkMaterialLink.material_id, GrowthWorkMaterialLink.status)
        .filter(GrowthWorkMaterialLink.user_id == user_id)
        .all()
    ):
        counts.setdefault(material_id, {"suggested": 0, "confirmed": 0, "dismissed": 0})
        counts[material_id][link_status] += 1

    filtered: list[dict[str, Any]] = []
    for row in rows:
        link_counts = counts.get(row.id, {"suggested": 0, "confirmed": 0, "dismissed": 0})
        project_assigned = row.project_id is not None
        unassigned = not project_assigned and link_counts["confirmed"] == 0
        if not any(link_counts.values()):
            review_status = "confirmed" if project_assigned else "unassigned"
        elif project_assigned and not link_counts["confirmed"]:
            review_status = "mixed"
        elif link_counts["confirmed"] and (
            link_counts["suggested"] or link_counts["dismissed"]
        ):
            review_status = "mixed"
        elif link_counts["confirmed"]:
            review_status = "confirmed"
        elif link_counts["suggested"]:
            review_status = "suggested"
        else:
            review_status = "dismissed"
        if unassigned_only and not unassigned:
            continue
        if status is not None and review_status != status:
            continue
        filtered.append(
            {
                "id": row.id,
                "material_type": row.material_type,
                "title": row.title,
                "account_name": row.account_name,
                "project_id": row.project_id,
                "content_hash": row.content_hash,
                "occurred_at": row.occurred_at,
                "occurred_at_known": row.occurred_at is not None,
                "occurred_at_precision": row.occurred_at_precision,
                "next_follow_up_at": row.next_follow_up_at,
                "source_document_id": row.source_document_id,
                "source_url": row.source_url,
                "analysis_mode": row.analysis_mode,
                "fallback_reason": row.fallback_reason,
                "version": row.version,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "status": review_status,
                "unassigned": unassigned,
                "suggested_link_count": link_counts["suggested"],
                "confirmed_link_count": link_counts["confirmed"],
                "dismissed_link_count": link_counts["dismissed"],
            }
        )
    total = len(filtered)
    return GrowthWorkMaterialListResponse(
        items=filtered[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


def cleanup_unassigned_work_materials(
    db: Session,
    *,
    user_id: int,
    request_id: str,
) -> dict[str, Any]:
    """Remove review-only materials that have never entered confirmed history."""
    materials = (
        db.query(GrowthWorkMaterial)
        .filter(GrowthWorkMaterial.user_id == user_id)
        .order_by(GrowthWorkMaterial.id.asc())
        .all()
    )
    deleted_count = 0
    skipped: list[dict[str, Any]] = []
    for material in materials:
        title = material.title or "未命名材料"
        # A user-selected project is already a confirmed placement, even when
        # the project goal or work-line routing is still pending.  The bulk
        # action is strictly for the unassigned inbox and must never delete it.
        if material.project_id is not None:
            continue
        confirmed_link = db.query(GrowthWorkMaterialLink.id).filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
            GrowthWorkMaterialLink.status == "confirmed",
        ).first()
        if confirmed_link is not None:
            continue
        protected_reason = None
        if db.query(GrowthWorkMaterialStatement.id).filter(
            GrowthWorkMaterialStatement.user_id == user_id,
            GrowthWorkMaterialStatement.material_id == material.id,
            GrowthWorkMaterialStatement.status == "confirmed",
        ).first() is not None:
            protected_reason = "已确认过事实或结论"
        elif db.query(GrowthProjectProgressEvent.id).filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.material_id == material.id,
            GrowthProjectProgressEvent.status == "confirmed",
        ).first() is not None:
            protected_reason = "已确认过对项目总目标的影响"
        elif db.query(GrowthWorkPlacementEvent.id).filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.material_id == material.id,
            GrowthWorkPlacementEvent.status == "confirmed",
        ).first() is not None:
            protected_reason = "已确认过象限或进展变化"
        elif db.query(GrowthWorkProgressEvent.id).filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.material_id == material.id,
            GrowthWorkProgressEvent.status == "confirmed",
        ).first() is not None:
            protected_reason = "已确认过对项目结果的影响"
        elif db.query(GrowthWorkMaterialRelation.id).filter(
            GrowthWorkMaterialRelation.user_id == user_id,
            or_(
                GrowthWorkMaterialRelation.material_id == material.id,
                GrowthWorkMaterialRelation.related_material_id == material.id,
            ),
        ).first() is not None:
            protected_reason = "已建立材料版本或引用关系"

        proposal_intake = db.query(GrowthWorkIntake).filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == f"material-streams:{material.id}",
        ).first()
        if proposal_intake is not None and db.query(GrowthWorkItem.id).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.intake_id == proposal_intake.id,
        ).first() is not None:
            protected_reason = "已经由这份材料建立工作线"
        if protected_reason:
            skipped.append({"id": material.id, "title": title, "reason": protected_reason})
            continue

        db.query(GrowthProjectProgressEvent).filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.material_id == material.id,
        ).delete(synchronize_session=False)
        db.query(GrowthWorkProgressEvent).filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.material_id == material.id,
        ).delete(synchronize_session=False)
        db.query(GrowthWorkPlacementEvent).filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.material_id == material.id,
        ).delete(synchronize_session=False)
        db.query(GrowthWorkMaterialLink).filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
        ).delete(synchronize_session=False)
        db.query(GrowthWorkMaterialStatement).filter(
            GrowthWorkMaterialStatement.user_id == user_id,
            GrowthWorkMaterialStatement.material_id == material.id,
        ).delete(synchronize_session=False)
        db.query(GrowthWorkMaterialRequest).filter(
            GrowthWorkMaterialRequest.user_id == user_id,
            GrowthWorkMaterialRequest.material_id == material.id,
        ).delete(synchronize_session=False)
        if proposal_intake is not None:
            db.delete(proposal_intake)
        _audit(
            db,
            user_id=user_id,
            entity_type="growth_work_material",
            entity_id=material.id,
            action="deleted_unassigned",
            request_id=request_id,
            before={"title": title, "version": material.version},
            after={"deleted": True, "confirmed_history": False},
        )
        db.delete(material)
        owner = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
        if owner is not None:
            owner.business_data_epoch += 1
        db.commit()
        deleted_count += 1

    return {
        "ok": True,
        "deleted_count": deleted_count,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def _existing_request(
    db: Session,
    *,
    user_id: int,
    request_id: str,
    operation: str,
    fingerprint: str,
) -> GrowthWorkMaterial | None:
    request = (
        db.query(GrowthWorkMaterialRequest)
        .filter(
            GrowthWorkMaterialRequest.user_id == user_id,
            GrowthWorkMaterialRequest.request_id == request_id,
        )
        .first()
    )
    if request is None:
        return None
    if request.operation != operation or not hmac.compare_digest(
        request.input_fingerprint,
        fingerprint,
    ):
        raise HTTPException(status_code=409, detail="request_id 已用于不同的材料操作")
    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == request.material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .first()
    )
    if material is None:
        raise HTTPException(status_code=409, detail="幂等请求的材料已不存在")
    return material


def _metadata_matches(material: GrowthWorkMaterial, data: GrowthWorkMaterialCreate) -> bool:
    effective_occurred_at, effective_precision, _ = _effective_material_occurrence(data)
    return (
        material.material_type == data.material_type
        and (material.title or None) == ((data.title or "").strip() or None)
        and (material.account_name or None) == ((data.account_name or "").strip() or None)
        and material.project_id == data.project_id
        and material.occurred_at == effective_occurred_at
        and material.occurred_at_precision == effective_precision
        and material.next_follow_up_at == _normalized_datetime(data.next_follow_up_at)
        and (material.source_document_id or None) == ((data.source_document_id or "").strip() or None)
        and (material.source_url or None) == ((data.source_url or "").strip() or None)
    )


def _persist_relations(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    relation_inputs: list[Any],
) -> list[GrowthWorkMaterialRelation]:
    if not relation_inputs:
        return []
    related_ids = {item.material_id for item in relation_inputs}
    if material.id in related_ids:
        raise HTTPException(status_code=422, detail="材料不能与自身建立版本关系")
    found = {
        item.id: item
        for item in db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.id.in_(related_ids),
        )
        .all()
    }
    if set(found) != related_ids:
        raise HTTPException(status_code=404, detail="关联材料不存在")
    persisted: list[GrowthWorkMaterialRelation] = []
    for relation_input in relation_inputs:
        existing = (
            db.query(GrowthWorkMaterialRelation)
            .filter(
                GrowthWorkMaterialRelation.user_id == user_id,
                GrowthWorkMaterialRelation.material_id == material.id,
                GrowthWorkMaterialRelation.related_material_id == relation_input.material_id,
                GrowthWorkMaterialRelation.relation_type == relation_input.relation_type,
            )
            .first()
        )
        reason = (relation_input.reason or "").strip() or None
        if existing is not None:
            if existing.reason != reason:
                raise HTTPException(status_code=409, detail="相同材料关系已存在但理由不同")
            persisted.append(existing)
            continue
        relation = GrowthWorkMaterialRelation(
            user_id=user_id,
            material_id=material.id,
            related_material_id=relation_input.material_id,
            relation_type=relation_input.relation_type,
            reason=reason,
        )
        db.add(relation)
        persisted.append(relation)
    return persisted


def _resolve_material_project(
    db: Session,
    *,
    user_id: int,
    project_id: int | None,
    account_name: str | None,
) -> GrowthProjectProfile | None:
    if project_id is not None:
        project = db.query(GrowthProjectProfile).filter(
            GrowthProjectProfile.id == project_id,
            GrowthProjectProfile.user_id == user_id,
        ).first()
        if project is None:
            raise HTTPException(status_code=404, detail="项目档案不存在")
        normalized_account = (account_name or "").strip()
        if normalized_account and normalized_account != project.account_name:
            raise HTTPException(status_code=422, detail="材料客户与所选项目档案不一致")
        return project
    normalized_account = (account_name or "").strip()
    if not normalized_account:
        return None
    matches = db.query(GrowthProjectProfile).filter(
        GrowthProjectProfile.user_id == user_id,
        GrowthProjectProfile.account_name == normalized_account,
    ).order_by(GrowthProjectProfile.id.asc()).limit(2).all()
    # Legacy clients only send account_name.  Resolve it automatically when
    # exactly one stable project exists; once a customer has multiple projects,
    # an explicit project_id is required to avoid cross-project contamination.
    return matches[0] if len(matches) == 1 else None


def _history_temporal_relation(
    *,
    event_occurred_at: datetime | None,
    event_precision: str,
    material_occurred_at: datetime | None,
    material_precision: str,
) -> str:
    """Classify history relative to the user-owned event time.

    Date-only values deliberately compare by calendar date.  Two records on
    the same date cannot be ordered and must never become a previous-state
    baseline merely because one row was inserted first.
    """
    if event_occurred_at is None or material_occurred_at is None:
        return "same_time_or_undated"
    if event_precision == "date" or material_precision == "date":
        event_value = event_occurred_at.date()
        material_value = material_occurred_at.date()
    else:
        event_value = event_occurred_at
        material_value = material_occurred_at
    if event_value < material_value:
        return "before_material"
    if event_value > material_value:
        return "after_material"
    return "same_time_or_undated"


def _material_is_current_project_head(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    material: GrowthWorkMaterial,
) -> bool:
    """Whether this material is not older than the project's confirmed head."""
    if material.occurred_at is None:
        return False
    latest_confirmed_material = (
        db.query(
            GrowthWorkMaterial.occurred_at,
            GrowthWorkMaterial.occurred_at_precision,
        )
        .join(
            GrowthProjectProgressEvent,
            GrowthProjectProgressEvent.material_id == GrowthWorkMaterial.id,
        )
        .filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.project_id == project_id,
            GrowthProjectProgressEvent.status == "confirmed",
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.id != material.id,
            GrowthWorkMaterial.occurred_at.is_not(None),
        )
        .order_by(
            GrowthWorkMaterial.occurred_at.desc(),
            GrowthProjectProgressEvent.id.desc(),
        )
        .first()
    )
    if latest_confirmed_material is None:
        return True
    return _history_temporal_relation(
        event_occurred_at=latest_confirmed_material[0],
        event_precision=latest_confirmed_material[1],
        material_occurred_at=material.occurred_at,
        material_precision=material.occurred_at_precision,
    ) != "after_material"


def _bounded_temporal_history(
    rows: list[dict[str, Any]],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Keep a bounded window on both sides of an out-of-order material.

    A simple newest-first slice can contain only later meetings and hide the
    actual previous baseline.  Reserve room for up to three confirmed records
    before the material and the nearest three after it, then fill any spare
    slots from the remaining recent context.
    """
    if len(rows) <= limit:
        return rows
    before = [row for row in rows if row["temporal_relation"] == "before_material"]
    later = [row for row in rows if row["temporal_relation"] == "after_material"]
    uncertain = [
        row for row in rows if row["temporal_relation"] == "same_time_or_undated"
    ]
    selected = before[: min(3, limit)]
    selected.extend(list(reversed(later))[: min(3, limit - len(selected))])
    selected.extend(uncertain[: max(0, limit - len(selected))])
    selected_ids = {id(row) for row in selected}
    for row in rows:
        if len(selected) >= limit:
            break
        if id(row) not in selected_ids:
            selected.append(row)
            selected_ids.add(id(row))
    source_order = {id(row): index for index, row in enumerate(rows)}
    return sorted(selected, key=lambda row: source_order[id(row)])


def _analysis_project_catalog(
    db: Session,
    *,
    user_id: int,
    project_id: int | None,
    account_name: str | None,
    exclude_material_id: int | None = None,
    material_occurred_at: datetime | None = None,
    material_occurred_at_precision: str = "unknown",
) -> list[GrowthMaterialProjectContext]:
    # Project analysis is keyed by a stable project id.  account_name is a
    # customer label and may own multiple projects; it must never silently turn
    # an explicitly unassigned material into project progress.
    if project_id is None:
        return []
    query = db.query(GrowthProjectProfile).filter(
        GrowthProjectProfile.user_id == user_id,
        GrowthProjectProfile.confirmed_at.is_not(None),
        GrowthProjectProfile.objective.is_not(None),
    )
    query = query.filter(GrowthProjectProfile.id == project_id)
    projects = query.order_by(GrowthProjectProfile.id.asc()).limit(MATERIAL_PROJECT_CATALOG_LIMIT).all()
    if not projects:
        return []
    project_ids = [project.id for project in projects]
    event_query = (
        db.query(
            GrowthProjectProgressEvent,
            GrowthWorkMaterial.occurred_at,
            GrowthWorkMaterial.occurred_at_precision,
        )
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id)
        .filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.project_id.in_(project_ids),
            GrowthProjectProgressEvent.status != "dismissed",
        )
    )
    if exclude_material_id is not None:
        event_query = event_query.filter(
            GrowthProjectProgressEvent.material_id != exclude_material_id
        )
    rows = event_query.order_by(
        GrowthProjectProgressEvent.project_id.asc(),
        GrowthWorkMaterial.occurred_at.desc(),
        GrowthProjectProgressEvent.created_at.desc(),
        GrowthProjectProgressEvent.id.desc(),
    ).all()
    confirmed: dict[int, list[dict[str, Any]]] = {}
    pending: dict[int, list[dict[str, Any]]] = {}
    latest_confirmed_event_ids: dict[int, int] = {}
    for event, occurred_at, occurred_at_precision in rows:
        destination = confirmed if event.status == "confirmed" else pending
        destination.setdefault(event.project_id, [])
        if event.status == "confirmed":
            latest_confirmed_event_ids.setdefault(event.project_id, event.id)
        destination[event.project_id].append(
            {
                "event_id": event.id,
                "occurred_at": occurred_at.isoformat() if occurred_at else None,
                "occurred_at_precision": occurred_at_precision,
                "temporal_relation": _history_temporal_relation(
                    event_occurred_at=occurred_at,
                    event_precision=occurred_at_precision,
                    material_occurred_at=material_occurred_at,
                    material_precision=material_occurred_at_precision,
                ),
                "impact_kind": event.impact_kind,
                "headline": event.headline,
                "causal_reason": event.causal_reason,
                "previous_state": event.previous_state,
                "current_state": event.current_state,
                "next_gap": event.next_gap,
                "status": event.status,
            }
        )
    confirmed = {
        project_key: _bounded_temporal_history(history)
        for project_key, history in confirmed.items()
    }
    pending = {
        project_key: _bounded_temporal_history(history)
        for project_key, history in pending.items()
    }
    return [
        GrowthMaterialProjectContext(
            project_key=f"project:{project.id}",
            project_id=project.id,
            account_name=project.account_name,
            project_name=project.project_name,
            objective=project.objective or "",
            version=project.version,
            latest_confirmed_event_id=latest_confirmed_event_ids.get(project.id),
            success_criteria=tuple(project.success_criteria or []),
            strategy_summary=project.strategy_summary,
            key_constraints=tuple(project.key_constraints or []),
            recent_progress=tuple(confirmed.get(project.id, [])),
            pending_suggestions=tuple(pending.get(project.id, [])),
        )
        for project in projects
    ]


def _analysis_target_catalog(
    db: Session,
    *,
    user_id: int,
    explicit_work_item_ids: list[int],
    explicit_node_ids: list[int],
    account_name: str | None = None,
    project_id: int | None = None,
    exclude_material_id: int | None = None,
    material_occurred_at: datetime | None = None,
    material_occurred_at_precision: str = "unknown",
    restrict_to_explicit: bool = False,
) -> list[GrowthMaterialTargetContext]:
    explicit_items = set(explicit_work_item_ids)
    explicit_nodes = set(explicit_node_ids)
    normalized_account = (account_name or "").strip() or None
    item_query = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            or_(
                GrowthWorkItem.status.in_(ACTIVE_STATUSES),
                GrowthWorkItem.id.in_(explicit_items or [-1]),
            ),
        )
    )
    if restrict_to_explicit:
        item_query = item_query.filter(
            GrowthWorkItem.id.in_(explicit_items or [-1])
        )
    if normalized_account is not None:
        # Keep legacy ungrouped work lines visible for manual migration, while
        # preventing one customer's material from being auto-routed to a
        # different named account.
        item_query = item_query.filter(
            or_(
                GrowthWorkItem.account_name == normalized_account,
                GrowthWorkItem.account_name.is_(None),
                GrowthWorkItem.id.in_(explicit_items or [-1]),
            )
        )
    if project_id is not None:
        item_query = item_query.filter(
            or_(
                GrowthWorkItem.project_id == project_id,
                GrowthWorkItem.project_id.is_(None),
                GrowthWorkItem.id.in_(explicit_items or [-1]),
            )
        )
    items = (
        item_query.order_by(
            GrowthWorkItem.priority_order.asc(),
            GrowthWorkItem.id.asc(),
        )
        .limit(MATERIAL_TARGET_CATALOG_LIMIT)
        .all()
    )
    item_by_id = {item.id: item for item in items}
    nodes = (
        db.query(GrowthWorkNode)
        .filter(
            GrowthWorkNode.user_id == user_id,
            or_(
                GrowthWorkNode.work_item_id.in_(list(item_by_id) or [-1]),
                GrowthWorkNode.id.in_(explicit_nodes or [-1]),
            ),
            GrowthWorkNode.status != "cancelled",
        )
        .order_by(GrowthWorkNode.work_item_id.asc(), GrowthWorkNode.priority_order.asc())
        .limit(MATERIAL_TARGET_CATALOG_LIMIT)
        .all()
    )
    missing_parent_ids = {node.work_item_id for node in nodes} - set(item_by_id)
    if missing_parent_ids:
        for item in db.query(GrowthWorkItem).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.id.in_(missing_parent_ids),
        ):
            item_by_id[item.id] = item
    progress_query = (
        db.query(
            GrowthWorkProgressEvent,
            GrowthWorkMaterial.occurred_at,
            GrowthWorkMaterial.occurred_at_precision,
        )
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id)
        .filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.work_item_id.in_(list(item_by_id) or [-1]),
            GrowthWorkProgressEvent.status != "dismissed",
        )
    )
    if exclude_material_id is not None:
        progress_query = progress_query.filter(
            GrowthWorkProgressEvent.material_id != exclude_material_id
        )
    progress_rows = (
        progress_query.order_by(
            GrowthWorkProgressEvent.work_item_id.asc(),
            GrowthWorkMaterial.occurred_at.desc(),
            GrowthWorkProgressEvent.created_at.desc(),
        )
        .all()
    )
    recent_by_item: dict[int, list[dict[str, Any]]] = {}
    pending_by_item: dict[int, list[dict[str, Any]]] = {}
    last_advancement_by_item: dict[int, datetime] = {}
    for event, occurred_at, occurred_at_precision in progress_rows:
        destination = recent_by_item if event.status == "confirmed" else pending_by_item
        destination.setdefault(event.work_item_id, [])
        destination[event.work_item_id].append(
            {
                "occurred_at": occurred_at.isoformat() if occurred_at else None,
                "occurred_at_precision": occurred_at_precision,
                "temporal_relation": _history_temporal_relation(
                    event_occurred_at=occurred_at,
                    event_precision=occurred_at_precision,
                    material_occurred_at=material_occurred_at,
                    material_precision=material_occurred_at_precision,
                ),
                "impact_kind": event.impact_kind,
                "headline": event.headline,
                "causal_reason": event.causal_reason,
                "previous_state": event.previous_state,
                "current_state": event.current_state,
                "next_gap": event.next_gap,
                "status": event.status,
            }
        )
        if (
            event.status == "confirmed"
            and event.impact_kind == "advanced"
            and occurred_at is not None
        ):
            prior = last_advancement_by_item.get(event.work_item_id)
            if prior is None or occurred_at > prior:
                last_advancement_by_item[event.work_item_id] = occurred_at

    recent_by_item = {
        item_id: _bounded_temporal_history(history)
        for item_id, history in recent_by_item.items()
    }
    pending_by_item = {
        item_id: _bounded_temporal_history(history)
        for item_id, history in pending_by_item.items()
    }

    catalog = []
    for item in item_by_id.values():
        last_advancement = last_advancement_by_item.get(item.id)
        catalog.append(
            GrowthMaterialTargetContext(
                target_key=f"work_item:{item.id}",
                target_type="work_item",
                target_id=item.id,
                title=item.title,
                current_status=item.status,
                explicitly_selected=item.id in explicit_items,
                account_name=item.account_name,
                project_id=item.project_id,
                objective=item.objective,
                success_criteria=tuple(item.success_criteria or []),
                strategy_summary=item.strategy_summary,
                key_constraints=tuple(item.key_constraints or []),
                recent_progress=tuple(recent_by_item.get(item.id, [])),
                pending_suggestions=tuple(pending_by_item.get(item.id, [])),
                last_advancement_at=(
                    last_advancement.isoformat() if last_advancement is not None else None
                ),
            )
        )
    catalog.extend(
        GrowthMaterialTargetContext(
            target_key=f"node:{node.id}",
            target_type="node",
            target_id=node.id,
            title=node.title,
            parent_title=item_by_id[node.work_item_id].title,
            current_status=node.status,
            explicitly_selected=node.id in explicit_nodes,
            account_name=item_by_id[node.work_item_id].account_name,
            project_id=item_by_id[node.work_item_id].project_id,
            objective=item_by_id[node.work_item_id].objective,
            success_criteria=tuple(item_by_id[node.work_item_id].success_criteria or []),
            strategy_summary=item_by_id[node.work_item_id].strategy_summary,
            key_constraints=tuple(item_by_id[node.work_item_id].key_constraints or []),
            recent_progress=tuple(recent_by_item.get(node.work_item_id, [])),
            pending_suggestions=tuple(pending_by_item.get(node.work_item_id, [])),
            last_advancement_at=(
                last_advancement_by_item[node.work_item_id].isoformat()
                if node.work_item_id in last_advancement_by_item
                else None
            ),
        )
        for node in nodes
        if node.work_item_id in item_by_id
    )
    return catalog[:MATERIAL_TARGET_CATALOG_LIMIT]


def _source_span(content: str, excerpt: str) -> dict[str, Any] | None:
    start = content.find(excerpt)
    if start < 0:
        return None
    return {"start": start, "end": start + len(excerpt), "excerpt": excerpt}


def _targets_from_ai_analysis(
    db: Session,
    *,
    user_id: int,
    content: str,
    target_analyses: list[GrowthMaterialTargetAnalysis],
) -> list[_TargetCandidate]:
    item_ids = {
        int(item.target_key.split(":", 1)[1])
        for item in target_analyses
        if item.target_key.startswith("work_item:")
        and item.target_key.split(":", 1)[1].isdigit()
    }
    node_ids = {
        int(item.target_key.split(":", 1)[1])
        for item in target_analyses
        if item.target_key.startswith("node:")
        and item.target_key.split(":", 1)[1].isdigit()
    }
    items = {
        item.id: item
        for item in db.query(GrowthWorkItem).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.id.in_(item_ids or [-1]),
        )
    }
    node_rows = (
        db.query(GrowthWorkNode, GrowthWorkItem)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkNode.work_item_id)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkNode.id.in_(node_ids or [-1]),
        )
        .all()
    )
    nodes = {node.id: (node, item) for node, item in node_rows}
    targets: list[_TargetCandidate] = []
    parent_item_ids: set[int] = set()
    for analysis in target_analyses:
        if analysis.confidence < 0.5:
            continue
        evidence_spans = [
            span
            for excerpt in analysis.evidence_excerpts
            if (span := _source_span(content, excerpt)) is not None
        ]
        if analysis.target_key.startswith("work_item:"):
            target_id = int(analysis.target_key.split(":", 1)[1])
            item = items.get(target_id)
            if item is None:
                continue
            targets.append(
                _TargetCandidate(
                    target_type="work_item",
                    target_id=item.id,
                    work_item=item,
                    node=None,
                    confidence=analysis.confidence,
                    reason=analysis.relevance_reason,
                    evidence_spans=evidence_spans,
                    analysis_mode="ai",
                    priority_axis=analysis.priority_axis,
                    progress_health=analysis.progress_health,
                    placement_reason=analysis.placement_reason,
                    impact_kind=analysis.impact_kind,
                    progress_headline=analysis.headline,
                    causal_reason=analysis.causal_reason,
                    previous_state=analysis.previous_state,
                    current_state=analysis.current_state,
                    next_gap=analysis.next_gap,
                )
            )
            parent_item_ids.add(item.id)
        elif analysis.target_key.startswith("node:"):
            target_id = int(analysis.target_key.split(":", 1)[1])
            row = nodes.get(target_id)
            if row is None:
                continue
            node, item = row
            targets.append(
                _TargetCandidate(
                    target_type="node",
                    target_id=node.id,
                    work_item=item,
                    node=node,
                    confidence=analysis.confidence,
                    reason=analysis.relevance_reason,
                    evidence_spans=evidence_spans,
                    analysis_mode="ai",
                    priority_axis=analysis.priority_axis,
                    progress_health=analysis.progress_health,
                    placement_reason=analysis.placement_reason,
                    proposed_node_status=analysis.proposed_node_status,
                    impact_kind=analysis.impact_kind,
                    progress_headline=analysis.headline,
                    causal_reason=analysis.causal_reason,
                    previous_state=analysis.previous_state,
                    current_state=analysis.current_state,
                    next_gap=analysis.next_gap,
                )
            )
            if item.id not in parent_item_ids:
                targets.append(
                    _TargetCandidate(
                        target_type="work_item",
                        target_id=item.id,
                        work_item=item,
                        node=None,
                        confidence=max(0.5, round(analysis.confidence - 0.05, 2)),
                        reason=f"AI 识别到材料属于该事项下的节点「{node.title}」。",
                        evidence_spans=evidence_spans,
                        analysis_mode="ai",
                        priority_axis=analysis.priority_axis,
                        progress_health=analysis.progress_health,
                        placement_reason=analysis.placement_reason,
                        impact_kind=analysis.impact_kind,
                        progress_headline=analysis.headline,
                        causal_reason=analysis.causal_reason,
                        previous_state=analysis.previous_state,
                        current_state=analysis.current_state,
                        next_gap=analysis.next_gap,
                    )
                )
                parent_item_ids.add(item.id)
    unique: dict[tuple[str, int], _TargetCandidate] = {}
    for target in targets:
        key = (target.target_type, target.target_id)
        if key not in unique or target.confidence > unique[key].confidence:
            unique[key] = target
    return list(unique.values())


def _load_explicit_targets(
    db: Session,
    *,
    user_id: int,
    work_item_ids: list[int],
    node_ids: list[int],
    content_spans: list[dict[str, Any]],
) -> list[_TargetCandidate]:
    targets: list[_TargetCandidate] = []
    items = {
        item.id: item
        for item in db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.id.in_(work_item_ids or [-1]),
        )
        .all()
    }
    if set(items) != set(work_item_ids):
        raise HTTPException(status_code=404, detail="候选工作项不存在")
    nodes = (
        db.query(GrowthWorkNode, GrowthWorkItem)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkNode.work_item_id)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkNode.id.in_(node_ids or [-1]),
        )
        .all()
    )
    if {node.id for node, _ in nodes} != set(node_ids):
        raise HTTPException(status_code=404, detail="候选工作节点不存在")
    for item_id in work_item_ids:
        item = items[item_id]
        _, spans = _title_match(item.title, content_spans)
        targets.append(
            _TargetCandidate(
                target_type="work_item",
                target_id=item.id,
                work_item=item,
                node=None,
                confidence=1.0,
                reason="由用户指定为候选工作项，关联仍需确认。",
                evidence_spans=spans,
            )
        )
    for node, item in nodes:
        _, spans = _title_match(node.title, content_spans)
        targets.append(
            _TargetCandidate(
                target_type="node",
                target_id=node.id,
                work_item=item,
                node=node,
                confidence=1.0,
                reason="由用户指定为候选工作节点，关联仍需确认。",
                evidence_spans=spans,
            )
        )
    return targets


def _discover_targets(
    db: Session,
    *,
    user_id: int,
    content_spans: list[dict[str, Any]],
) -> list[_TargetCandidate]:
    items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status.in_(ACTIVE_STATUSES),
        )
        .order_by(GrowthWorkItem.priority_order.asc(), GrowthWorkItem.id.asc())
        .all()
    )
    item_by_id = {item.id: item for item in items}
    nodes = (
        db.query(GrowthWorkNode)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id.in_(list(item_by_id) or [-1]),
            GrowthWorkNode.status != "cancelled",
        )
        .all()
    )
    targets: list[_TargetCandidate] = []
    matched_item_ids: set[int] = set()
    for item in items:
        score, spans = _title_match(item.title, content_spans)
        if score >= 0.72:
            targets.append(
                _TargetCandidate(
                    target_type="work_item",
                    target_id=item.id,
                    work_item=item,
                    node=None,
                    confidence=score,
                    reason=f"材料原文与工作项「{item.title}」的标题特征匹配。",
                    evidence_spans=spans,
                )
            )
            matched_item_ids.add(item.id)
    for node in nodes:
        score, spans = _title_match(node.title, content_spans)
        if score < 0.75:
            continue
        item = item_by_id[node.work_item_id]
        targets.append(
            _TargetCandidate(
                target_type="node",
                target_id=node.id,
                work_item=item,
                node=node,
                confidence=score,
                reason=f"材料原文与节点「{node.title}」的标题特征匹配。",
                evidence_spans=spans,
            )
        )
        if item.id not in matched_item_ids:
            targets.append(
                _TargetCandidate(
                    target_type="work_item",
                    target_id=item.id,
                    work_item=item,
                    node=None,
                    confidence=round(max(0.72, score - 0.08), 2),
                    reason=f"材料命中该事项下的节点「{node.title}」。",
                    evidence_spans=spans,
                )
            )
            matched_item_ids.add(item.id)
    unique: dict[tuple[str, int], _TargetCandidate] = {}
    for target in targets:
        key = (target.target_type, target.target_id)
        if key not in unique or target.confidence > unique[key].confidence:
            unique[key] = target
    return sorted(
        unique.values(),
        key=lambda item: (-item.confidence, item.work_item.priority_order, item.target_type, item.target_id),
    )[:20]


def _persist_statements(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    analysis: _MaterialAnalysis,
) -> list[GrowthWorkMaterialStatement]:
    statements: list[GrowthWorkMaterialStatement] = []
    for candidate in analysis.statements:
        if candidate.evidence_excerpt not in material.content:
            continue
        statement_key = "statement-" + hashlib.sha256(
            (
                f"{candidate.statement_type}\n{candidate.text}\n{candidate.evidence_excerpt}"
            ).encode("utf-8")
        ).hexdigest()[:20]
        existing = (
            db.query(GrowthWorkMaterialStatement)
            .filter(
                GrowthWorkMaterialStatement.material_id == material.id,
                GrowthWorkMaterialStatement.statement_key == statement_key,
            )
            .first()
        )
        if existing is not None:
            statements.append(existing)
            continue
        statement = GrowthWorkMaterialStatement(
            user_id=user_id,
            material_id=material.id,
            statement_key=statement_key,
            statement_type=candidate.statement_type,
            text=candidate.text,
            evidence_excerpt=candidate.evidence_excerpt,
            confidence=candidate.confidence,
            status="suggested",
            analysis_mode=analysis.analysis_mode,
            rule_version=analysis.parser_version,
        )
        db.add(statement)
        db.flush()
        statements.append(statement)
    return statements


def _statement_spans(
    content: str,
    statements: list[GrowthWorkMaterialStatement],
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for statement in statements:
        start = content.find(statement.evidence_excerpt)
        if start < 0:
            continue
        spans.append(
            {
                "start": start,
                "end": start + len(statement.evidence_excerpt),
                "excerpt": statement.evidence_excerpt,
                "statement_id": statement.id,
            }
        )
    return spans


def _decorate_spans_with_statements(
    spans: list[dict[str, Any]],
    statements: list[GrowthWorkMaterialStatement],
) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for span in spans:
        statement = next(
            (
                item
                for item in statements
                if item.evidence_excerpt in span["excerpt"] or span["excerpt"] in item.evidence_excerpt
            ),
            None,
        )
        decorated.append({**span, "statement_id": statement.id if statement else None})
    return decorated


def _persist_links_and_placements(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    material_type: str,
    analysis: _MaterialAnalysis,
    targets: list[_TargetCandidate],
    statements: list[GrowthWorkMaterialStatement],
) -> tuple[
    list[GrowthWorkMaterialLink],
    list[GrowthWorkPlacementEvent],
    list[GrowthWorkProgressEvent],
]:
    fallback_spans = _statement_spans(material.content, statements)[:5]
    links: list[GrowthWorkMaterialLink] = []
    target_spans_by_item: dict[int, list[dict[str, Any]]] = {}
    unique_target_item_ids = {target.work_item.id for target in targets}
    for target in targets:
        target_specific_spans = _decorate_spans_with_statements(
            target.evidence_spans,
            statements,
        )
        evidence_spans = (
            target_specific_spans
            if target_specific_spans
            else fallback_spans if len(unique_target_item_ids) == 1 else []
        )
        link_type = _dominant_link_type(statements, evidence_spans)
        existing = (
            db.query(GrowthWorkMaterialLink)
            .filter(
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.target_type == target.target_type,
                GrowthWorkMaterialLink.target_id == target.target_id,
                GrowthWorkMaterialLink.link_type == link_type,
            )
            .first()
        )
        if existing is None:
            relevant_text = "\n".join(span["excerpt"] for span in evidence_spans)
            existing = GrowthWorkMaterialLink(
                user_id=user_id,
                material_id=material.id,
                target_type=target.target_type,
                target_id=target.target_id,
                work_item_id=target.work_item.id,
                node_id=target.node.id if target.node is not None else None,
                link_type=link_type,
                confidence=target.confidence,
                reason=target.reason,
                evidence_spans=evidence_spans,
                proposed_node_status=(
                    target.proposed_node_status
                    if target.node is not None and target.analysis_mode == "ai"
                    else _proposed_node_status(relevant_text, material_type=material_type)
                    if target.node is not None
                    else None
                ),
                status="suggested",
                analysis_mode=target.analysis_mode,
                rule_version=(
                    AI_ROUTING_RULE_VERSION if target.analysis_mode == "ai" else ROUTING_RULE_VERSION
                ),
            )
            db.add(existing)
            db.flush()
        links.append(existing)
        target_spans_by_item.setdefault(target.work_item.id, [])
        known_spans = {
            (span["start"], span["end"])
            for span in target_spans_by_item[target.work_item.id]
        }
        for span in evidence_spans:
            if (span["start"], span["end"]) not in known_spans:
                target_spans_by_item[target.work_item.id].append(span)

    placements: list[GrowthWorkPlacementEvent] = []
    unique_items = {target.work_item.id: target.work_item for target in targets}
    for item_id, item in unique_items.items():
        ai_target = next(
            (
                target
                for target in targets
                if target.work_item.id == item_id
                and target.analysis_mode == "ai"
                and target.target_type == "work_item"
            ),
            next(
                (
                    target
                    for target in targets
                    if target.work_item.id == item_id and target.analysis_mode == "ai"
                ),
                None,
            ),
        )
        evidence_spans = target_spans_by_item.get(item_id, [])[:8]
        relevant_text = "\n".join(span["excerpt"] for span in evidence_spans)
        use_target_ai = ai_target is not None
        use_global_ai = analysis.analysis_mode == "ai" and len(unique_items) == 1 and not use_target_ai
        if not relevant_text and len(unique_items) == 1:
            relevant_text = material.content
        local_priority, local_health, local_reason, local_evidence = _axis_from_text(
            relevant_text,
            material_type=material_type,
        )
        suggested_priority = (
            ai_target.priority_axis
            if use_target_ai and ai_target.priority_axis != "unknown"
            else analysis.priority_axis
            if use_global_ai and analysis.priority_axis != "unknown"
            else local_priority
        )
        suggested_health = (
            ai_target.progress_health
            if use_target_ai and ai_target.progress_health != "unknown"
            else analysis.progress_health
            if use_global_ai and analysis.progress_health != "unknown"
            else local_health
        )
        priority = suggested_priority if suggested_priority != "unknown" else item.priority_axis
        health = suggested_health if suggested_health != "unknown" else item.progress_health
        quadrant = _quadrant(priority, health)
        reason_parts = [
            ai_target.placement_reason
            if use_target_ai and ai_target.placement_reason
            else analysis.placement_reason
            if use_global_ai
            else local_reason
        ]
        if not evidence_spans and len(unique_items) > 1:
            reason_parts = ["未在这份多工作线材料中定位到该工作线的专属证据"]
        if suggested_priority == "unknown" and item.priority_axis != "unknown":
            reason_parts.append("本次材料未改变优先级轴，沿用当前值")
        if suggested_health == "unknown" and item.progress_health != "unknown":
            reason_parts.append("本次材料未改变进展健康轴，沿用当前值")
        if not evidence_spans:
            source_evidence = analysis.placement_evidence_excerpt if use_global_ai else local_evidence
            if source_evidence and source_evidence in material.content:
                start = material.content.find(source_evidence)
                evidence_spans = [
                    {
                        "start": start,
                        "end": start + len(source_evidence),
                        "excerpt": source_evidence,
                        "statement_id": None,
                    }
                ]
        confidence = 0.82 if suggested_priority != "unknown" and suggested_health != "unknown" else 0.62 if (suggested_priority != "unknown" or suggested_health != "unknown") else 0.35
        used_ai_axis = (
            use_target_ai
            and (ai_target.priority_axis != "unknown" or ai_target.progress_health != "unknown")
        ) or (
            use_global_ai
            and (analysis.priority_axis != "unknown" or analysis.progress_health != "unknown")
        )
        placement_revision = _analysis_revision(PLACEMENT_RULE_VERSION, material.version)
        existing = (
            db.query(GrowthWorkPlacementEvent)
            .filter(
                GrowthWorkPlacementEvent.material_id == material.id,
                GrowthWorkPlacementEvent.work_item_id == item.id,
                GrowthWorkPlacementEvent.rule_version == placement_revision,
            )
            .first()
        )
        if existing is None:
            existing = GrowthWorkPlacementEvent(
                user_id=user_id,
                work_item_id=item.id,
                material_id=material.id,
                priority_axis=priority,
                progress_health=health,
                quadrant=quadrant,
                confidence=confidence,
                reason="；".join(reason_parts),
                evidence_spans=evidence_spans,
                rule_version=placement_revision,
                analysis_mode="ai" if used_ai_axis else "rules",
                base_work_item_version=item.version,
                status="suggested",
            )
            db.add(existing)
            db.flush()
        placements.append(existing)
    progress_events: list[GrowthWorkProgressEvent] = []
    for item_id, item in unique_items.items():
        target = next(
            (
                candidate
                for candidate in targets
                if candidate.work_item.id == item_id
                and candidate.analysis_mode == "ai"
                and candidate.target_type == "work_item"
            ),
            next(
                (
                    candidate
                    for candidate in targets
                    if candidate.work_item.id == item_id
                    and candidate.analysis_mode == "ai"
                ),
                next(
                    (
                        candidate
                        for candidate in targets
                        if candidate.work_item.id == item_id
                    ),
                    None,
                ),
            ),
        )
        if target is None:
            continue
        evidence_spans = target_spans_by_item.get(item_id, [])[:8]
        relevant_text = "\n".join(span["excerpt"] for span in evidence_spans)
        if not relevant_text and len(unique_items) == 1:
            relevant_text = material.content
        if target.analysis_mode == "ai":
            impact_kind = target.impact_kind
            headline = target.progress_headline
            causal_reason = target.causal_reason
            previous_state = target.previous_state
            current_state = target.current_state
            next_gap = target.next_gap
            confidence = target.confidence
            rule_version = _analysis_revision(PROGRESS_RULE_VERSION, material.version)
            analysis_mode = "ai"
        else:
            impact_kind, headline, causal_reason, current_state = _rule_progress_assessment(
                relevant_text,
                material_type=material_type,
            )
            previous_state = None
            next_gap = None
            confidence = 0.72 if impact_kind in {"advanced", "setback", "redirected"} else 0.5
            rule_version = _analysis_revision(MATERIAL_RULE_VERSION, material.version)
            analysis_mode = "rules"
        existing_progress = (
            db.query(GrowthWorkProgressEvent)
            .filter(
                GrowthWorkProgressEvent.material_id == material.id,
                GrowthWorkProgressEvent.work_item_id == item.id,
                GrowthWorkProgressEvent.rule_version == rule_version,
            )
            .first()
        )
        if existing_progress is None:
            existing_progress = GrowthWorkProgressEvent(
                user_id=user_id,
                work_item_id=item.id,
                material_id=material.id,
                impact_kind=impact_kind,
                headline=headline[:500],
                causal_reason=causal_reason,
                previous_state=previous_state,
                current_state=current_state,
                next_gap=next_gap,
                evidence_spans=evidence_spans,
                confidence=confidence,
                status="suggested",
                analysis_mode=analysis_mode,
                rule_version=rule_version,
                base_work_item_version=item.version,
                reportable=False,
            )
            db.add(existing_progress)
            db.flush()
        progress_events.append(existing_progress)
    return links, placements, progress_events


def _persist_project_progress_events(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    analysis: _MaterialAnalysis,
    project_base_versions: dict[int, int],
    project_base_confirmed_event_ids: dict[int, int | None],
) -> list[GrowthProjectProgressEvent]:
    if analysis.analysis_mode != "ai" or not analysis.project_analyses:
        return []
    project_ids = {
        int(item.project_key.split(":", 1)[1])
        for item in analysis.project_analyses
        if item.project_key.startswith("project:")
        and item.project_key.split(":", 1)[1].isdigit()
    }
    projects = {
        project.id: project
        for project in db.query(GrowthProjectProfile).filter(
            GrowthProjectProfile.user_id == user_id,
            GrowthProjectProfile.id.in_(project_ids or [-1]),
            GrowthProjectProfile.confirmed_at.is_not(None),
            GrowthProjectProfile.objective.is_not(None),
        )
    }
    events: list[GrowthProjectProgressEvent] = []
    for proposal in analysis.project_analyses:
        if not proposal.project_key.startswith("project:"):
            continue
        raw_id = proposal.project_key.split(":", 1)[1]
        if not raw_id.isdigit():
            continue
        project = projects.get(int(raw_id))
        if project is None:
            continue
        if material.project_id is not None and material.project_id != project.id:
            continue
        evidence_spans = [
            span
            for excerpt in proposal.evidence_excerpts
            if (span := _source_span(material.content, excerpt)) is not None
        ][:20]
        if not evidence_spans:
            continue
        rule_version = _analysis_revision(PROJECT_PROGRESS_RULE_VERSION, material.version)
        existing = db.query(GrowthProjectProgressEvent).filter(
            GrowthProjectProgressEvent.material_id == material.id,
            GrowthProjectProgressEvent.project_id == project.id,
            GrowthProjectProgressEvent.rule_version == rule_version,
        ).first()
        if existing is None:
            existing = GrowthProjectProgressEvent(
                user_id=user_id,
                project_id=project.id,
                material_id=material.id,
                impact_kind=proposal.impact_kind,
                headline=proposal.headline[:500],
                causal_reason=proposal.causal_reason,
                previous_state=proposal.previous_state,
                current_state=proposal.current_state,
                next_gap=proposal.next_gap,
                evidence_spans=evidence_spans,
                confidence=proposal.confidence,
                status="suggested",
                analysis_mode="ai",
                rule_version=rule_version,
                # This is the profile version that was sent to the model, not
                # the version reloaded after the external call.  Review rejects
                # the suggestion if the user changed the project meanwhile.
                base_project_version=project_base_versions.get(project.id, project.version),
                base_confirmed_event_id=project_base_confirmed_event_ids.get(project.id),
                reportable=False,
            )
            db.add(existing)
            db.flush()
        events.append(existing)
    return events


def create_work_material(
    db: Session,
    *,
    user: User,
    data: GrowthWorkMaterialCreate,
) -> GrowthWorkMaterialDetailResponse:
    user_id = user.id
    explicit_project_selection = "project_id" in data.model_fields_set
    explicitly_unassigned = explicit_project_selection and data.project_id is None
    resolved_project = (
        None
        if explicitly_unassigned
        else _resolve_material_project(
            db,
            user_id=user_id,
            project_id=data.project_id,
            account_name=data.account_name,
        )
    )
    if resolved_project is not None:
        data.project_id = resolved_project.id
        if not (data.account_name or "").strip():
            data.account_name = resolved_project.account_name
    payload = data.model_dump(mode="json", exclude={"request_id"})
    fingerprint = _request_fingerprint("create_analyze", payload)
    replay = _existing_request(
        db,
        user_id=user_id,
        request_id=data.request_id,
        operation="create_analyze",
        fingerprint=fingerprint,
    )
    if replay is not None:
        return _material_detail(db, user_id=user_id, material=replay)

    content = data.content
    effective_occurred_at, effective_precision, inferred_occurrence = (
        _effective_material_occurrence(data)
    )
    content_hash = _content_hash(content)
    existing_material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.content_hash == content_hash,
        )
        .first()
    )
    if existing_material is not None and not _metadata_matches(existing_material, data):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "相同原文已存在，但事件时间或来源元数据不同；请使用已有材料建立版本关系",
                "existing_material_id": existing_material.id,
            },
        )

    expected_data_epoch = user.business_data_epoch
    target_catalog = _analysis_target_catalog(
        db,
        user_id=user_id,
        explicit_work_item_ids=data.candidate_work_item_ids,
        explicit_node_ids=data.candidate_node_ids,
        account_name=data.account_name,
        project_id=data.project_id,
        exclude_material_id=existing_material.id if existing_material is not None else None,
        material_occurred_at=effective_occurred_at,
        material_occurred_at_precision=effective_precision,
        restrict_to_explicit=explicitly_unassigned,
    )
    project_catalog = (
        []
        if explicitly_unassigned
        else _analysis_project_catalog(
            db,
            user_id=user_id,
            project_id=data.project_id,
            account_name=data.account_name,
            exclude_material_id=existing_material.id if existing_material is not None else None,
            material_occurred_at=effective_occurred_at,
            material_occurred_at_precision=effective_precision,
        )
    )
    project_base_versions = {
        project.project_id: project.version for project in project_catalog
    }
    project_base_confirmed_event_ids = {
        project.project_id: project.latest_confirmed_event_id for project in project_catalog
    }
    analysis: _MaterialAnalysis
    if existing_material is None:
        try:
            analysis = _ai_analysis(
                analyze_growth_material_with_ai(
                    user_id=user_id,
                    text=content,
                    material_type=data.material_type,
                    material_title=data.title,
                    occurred_at=effective_occurred_at,
                    occurred_at_precision=effective_precision,
                    target_catalog=target_catalog,
                    project_catalog=project_catalog,
                )
            )
        except HTTPException as exc:
            analysis = _failed_ai_analysis(exc)
    else:
        analysis = analyze_growth_material_with_rules(content, data.material_type)

    db.rollback()
    owner = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None or owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise HTTPException(status_code=409, detail="业务数据已在材料分析期间清空，请重新提交")

    replay = _existing_request(
        db,
        user_id=user_id,
        request_id=data.request_id,
        operation="create_analyze",
        fingerprint=fingerprint,
    )
    if replay is not None:
        db.rollback()
        return _material_detail(db, user_id=user_id, material=replay)

    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.content_hash == content_hash,
        )
        .with_for_update()
        .first()
    )
    created = material is None
    if material is not None:
        if not _metadata_matches(material, data):
            db.rollback()
            raise HTTPException(status_code=409, detail="相同原文已以不同元数据建档")
        analysis = analyze_growth_material_with_rules(material.content, material.material_type)
    else:
        material = GrowthWorkMaterial(
            user_id=user_id,
            material_type=data.material_type,
            title=(data.title or "").strip() or None,
            account_name=(data.account_name or "").strip() or None,
            project_id=data.project_id,
            content=content,
            content_hash=content_hash,
            occurred_at=effective_occurred_at,
            occurred_at_precision=effective_precision,
            next_follow_up_at=_normalized_datetime(data.next_follow_up_at),
            source_document_id=(data.source_document_id or "").strip() or None,
            source_url=(data.source_url or "").strip() or None,
            analysis_mode=analysis.analysis_mode,
            analysis_rule_version=analysis.parser_version,
            ai_requested=True,
            external_processing_used=analysis.external_processing_used,
            provider_name=analysis.provider_name,
            model=analysis.model,
            fallback_reason=analysis.fallback_reason,
        )
        db.add(material)
        db.flush()

    statements = (
        _persist_statements(
            db,
            user_id=user_id,
            material=material,
            analysis=analysis,
        )
        if created
        else db.query(GrowthWorkMaterialStatement)
        .filter(
            GrowthWorkMaterialStatement.user_id == user_id,
            GrowthWorkMaterialStatement.material_id == material.id,
        )
        .order_by(GrowthWorkMaterialStatement.id.asc())
        .all()
    )
    relations = _persist_relations(
        db,
        user_id=user_id,
        material=material,
        relation_inputs=data.related_materials,
    )
    content_spans = _sentence_spans(material.content)
    targets = _load_explicit_targets(
        db,
        user_id=user_id,
        work_item_ids=data.candidate_work_item_ids,
        node_ids=data.candidate_node_ids,
        content_spans=content_spans,
    ) if _analysis_failed(analysis) and (
        data.candidate_work_item_ids or data.candidate_node_ids
    ) else [] if _analysis_failed(analysis) else (
        # Candidate IDs are routing hints for the Agent.  They must not
        # overwrite a validated AI delta with a generic rules target.
        # Otherwise the response can be correctly repaired into advanced /
        # setback analyses and still be persisted as context at confidence 0.5.
        _targets_from_ai_analysis(
            db,
            user_id=user_id,
            content=material.content,
            target_analyses=analysis.target_analyses,
        )
        if analysis.analysis_mode == "ai" and analysis.target_analyses
        else _load_explicit_targets(
            db,
            user_id=user_id,
            work_item_ids=data.candidate_work_item_ids,
            node_ids=data.candidate_node_ids,
            content_spans=content_spans,
        )
        if data.candidate_work_item_ids or data.candidate_node_ids
        else _discover_targets(db, user_id=user_id, content_spans=content_spans)
    )
    links, placements, progress_events = _persist_links_and_placements(
        db,
        user_id=user_id,
        material=material,
        material_type=material.material_type,
        analysis=analysis,
        targets=targets,
        statements=statements,
    )
    project_progress_events = _persist_project_progress_events(
        db,
        user_id=user_id,
        material=material,
        analysis=analysis,
        project_base_versions=project_base_versions,
        project_base_confirmed_event_ids=project_base_confirmed_event_ids,
    )
    workstream_intake = (
        _persist_workstream_proposals(
            db,
            user_id=user_id,
            material=material,
            analysis=analysis,
        )
        if created
        else db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == f"material-streams:{material.id}",
        )
        .first()
    )
    if not created:
        material.version += 1
    db.add(
        GrowthWorkMaterialRequest(
            user_id=user_id,
            material_id=material.id,
            request_id=data.request_id,
            operation="create_analyze",
            input_fingerprint=fingerprint,
        )
    )
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material.id,
        action="created_and_analyzed" if created else "deduplicated_and_rerouted",
        request_id=data.request_id,
        after={
            "content_hash": material.content_hash,
            "material_type": material.material_type,
            "occurred_at_known": material.occurred_at is not None,
            "occurred_at_precision": material.occurred_at_precision,
            "occurred_at_inferred": inferred_occurrence is not None,
            "occurred_at_evidence_excerpt": (
                inferred_occurrence.evidence_excerpt if inferred_occurrence else None
            ),
            "analysis_mode": material.analysis_mode,
            "fallback_reason": material.fallback_reason,
            "statement_ids": [item.id for item in statements],
            "link_ids": [item.id for item in links],
            "placement_event_ids": [item.id for item in placements],
            "progress_event_ids": [item.id for item in progress_events],
            "project_progress_event_ids": [item.id for item in project_progress_events],
            "relation_ids": [item.id for item in relations],
            "workstream_proposal_intake_id": workstream_intake.id if workstream_intake else None,
            "original_content_externalized": False,
            "redacted_material_text_externalized": material.external_processing_used,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = _existing_request(
            db,
            user_id=user_id,
            request_id=data.request_id,
            operation="create_analyze",
            fingerprint=fingerprint,
        )
        if replay is None:
            raise HTTPException(status_code=409, detail="材料并发写入冲突，请重试") from exc
        return _material_detail(db, user_id=user_id, material=replay)
    db.refresh(material)
    return _material_detail(db, user_id=user_id, material=material)


def reanalyze_work_material(
    db: Session,
    *,
    user: User,
    material_id: int,
    data: GrowthWorkMaterialReanalyze,
) -> GrowthWorkMaterialDetailResponse:
    user_id = user.id
    fingerprint = _request_fingerprint(
        "reanalyze",
        {"material_id": material_id, "expected_version": data.expected_version},
    )
    replay = (
        db.query(GrowthAuditEvent)
        .filter(
            GrowthAuditEvent.user_id == user_id,
            GrowthAuditEvent.entity_type == "growth_work_material",
            GrowthAuditEvent.entity_id == material_id,
            GrowthAuditEvent.action == "reanalyzed",
            GrowthAuditEvent.request_id == data.request_id,
        )
        .first()
    )
    if replay is not None:
        prior = replay.after_payload if isinstance(replay.after_payload, dict) else {}
        if not hmac.compare_digest(str(prior.get("fingerprint") or ""), fingerprint):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的重新分析请求")
        material = db.query(GrowthWorkMaterial).filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        ).first()
        if material is None:
            raise HTTPException(status_code=404, detail="工作材料不存在")
        return _material_detail(db, user_id=user_id, material=material)

    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .first()
    )
    if material is None:
        raise HTTPException(status_code=404, detail="工作材料不存在")
    if material.version != data.expected_version:
        raise HTTPException(status_code=409, detail="材料版本已变化，请刷新后重试")
    expected_data_epoch = user.business_data_epoch
    existing_routes = (
        db.query(
            GrowthWorkMaterialLink.work_item_id,
            GrowthWorkMaterialLink.node_id,
        )
        .filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
            GrowthWorkMaterialLink.status != "dismissed",
        )
        .all()
    )
    target_catalog = _analysis_target_catalog(
        db,
        user_id=user_id,
        explicit_work_item_ids=sorted(
            {work_item_id for work_item_id, _ in existing_routes}
        ),
        explicit_node_ids=sorted(
            {node_id for _, node_id in existing_routes if node_id is not None}
        ),
        account_name=material.account_name,
        project_id=material.project_id,
        exclude_material_id=material.id,
        material_occurred_at=material.occurred_at,
        material_occurred_at_precision=material.occurred_at_precision,
        restrict_to_explicit=material.project_id is None,
    )
    project_catalog = (
        _analysis_project_catalog(
            db,
            user_id=user_id,
            project_id=material.project_id,
            account_name=material.account_name,
            exclude_material_id=material.id,
            material_occurred_at=material.occurred_at,
            material_occurred_at_precision=material.occurred_at_precision,
        )
        if material.project_id is not None
        else []
    )
    project_base_versions = {
        project.project_id: project.version for project in project_catalog
    }
    project_base_confirmed_event_ids = {
        project.project_id: project.latest_confirmed_event_id for project in project_catalog
    }
    try:
        analysis = _ai_analysis(
            analyze_growth_material_with_ai(
                user_id=user_id,
                text=material.content,
                material_type=material.material_type,
                material_title=material.title,
                occurred_at=material.occurred_at,
                occurred_at_precision=material.occurred_at_precision,
                target_catalog=target_catalog,
                project_catalog=project_catalog,
            )
        )
    except HTTPException as exc:
        analysis = _failed_ai_analysis(exc)

    db.rollback()
    owner = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None or owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise HTTPException(status_code=409, detail="业务数据已在分析期间清空，请重新提交")
    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if material is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="工作材料不存在")
    if material.version != data.expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="材料已在 AI 分析期间更新，请刷新后重试")

    if _analysis_failed(analysis):
        # A failed retry must not destroy a previously useful AI draft or the
        # user's pending review decisions. Record the latest failure only.
        material.ai_requested = True
        material.external_processing_used = (
            material.external_processing_used or analysis.external_processing_used
        )
        material.fallback_reason = analysis.fallback_reason
        material.version += 1
        _audit(
            db,
            user_id=user_id,
            entity_type="growth_work_material",
            entity_id=material.id,
            action="reanalyzed",
            request_id=data.request_id,
            after={
                "fingerprint": fingerprint,
                "analysis_mode": material.analysis_mode,
                "fallback_reason": material.fallback_reason,
                "previous_suggestions_preserved": True,
                "occurred_at_inferred": False,
            },
        )
        db.commit()
        db.refresh(material)
        return _material_detail(db, user_id=user_id, material=material)

    # Replace only unreviewed suggestions. Confirmed and dismissed decisions
    # remain immutable evidence of the user's prior review.
    db.query(GrowthWorkPlacementEvent).filter(
        GrowthWorkPlacementEvent.user_id == user_id,
        GrowthWorkPlacementEvent.material_id == material.id,
        GrowthWorkPlacementEvent.status == "suggested",
    ).delete(synchronize_session=False)
    db.query(GrowthWorkProgressEvent).filter(
        GrowthWorkProgressEvent.user_id == user_id,
        GrowthWorkProgressEvent.material_id == material.id,
        GrowthWorkProgressEvent.status == "suggested",
    ).delete(synchronize_session=False)
    db.query(GrowthProjectProgressEvent).filter(
        GrowthProjectProgressEvent.user_id == user_id,
        GrowthProjectProgressEvent.material_id == material.id,
        GrowthProjectProgressEvent.status == "suggested",
    ).delete(synchronize_session=False)
    db.query(GrowthWorkMaterialLink).filter(
        GrowthWorkMaterialLink.user_id == user_id,
        GrowthWorkMaterialLink.material_id == material.id,
        GrowthWorkMaterialLink.status == "suggested",
    ).delete(synchronize_session=False)
    db.query(GrowthWorkMaterialStatement).filter(
        GrowthWorkMaterialStatement.user_id == user_id,
        GrowthWorkMaterialStatement.material_id == material.id,
        GrowthWorkMaterialStatement.status == "suggested",
    ).delete(synchronize_session=False)
    db.flush()

    material.analysis_mode = analysis.analysis_mode
    material.analysis_rule_version = analysis.parser_version
    material.ai_requested = True
    material.external_processing_used = analysis.external_processing_used
    material.provider_name = analysis.provider_name
    material.model = analysis.model
    material.fallback_reason = analysis.fallback_reason
    material.version += 1
    statements = _persist_statements(
        db,
        user_id=user_id,
        material=material,
        analysis=analysis,
    )
    content_spans = _sentence_spans(material.content)
    targets = [] if _analysis_failed(analysis) else (
        _targets_from_ai_analysis(
            db,
            user_id=user_id,
            content=material.content,
            target_analyses=analysis.target_analyses,
        )
        if analysis.analysis_mode == "ai" and analysis.target_analyses
        else _discover_targets(db, user_id=user_id, content_spans=content_spans)
    )
    links, placements, progress_events = _persist_links_and_placements(
        db,
        user_id=user_id,
        material=material,
        material_type=material.material_type,
        analysis=analysis,
        targets=targets,
        statements=statements,
    )
    project_progress_events = _persist_project_progress_events(
        db,
        user_id=user_id,
        material=material,
        analysis=analysis,
        project_base_versions=project_base_versions,
        project_base_confirmed_event_ids=project_base_confirmed_event_ids,
    )
    workstream_intake = _persist_workstream_proposals(
        db,
        user_id=user_id,
        material=material,
        analysis=analysis,
    )
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material.id,
        action="reanalyzed",
        request_id=data.request_id,
        after={
            "fingerprint": fingerprint,
            "analysis_mode": material.analysis_mode,
            "fallback_reason": material.fallback_reason,
            "statement_ids": [item.id for item in statements],
            "link_ids": [item.id for item in links],
            "placement_event_ids": [item.id for item in placements],
            "progress_event_ids": [item.id for item in progress_events],
            "project_progress_event_ids": [item.id for item in project_progress_events],
            "workstream_proposal_intake_id": workstream_intake.id if workstream_intake else None,
            "occurred_at_inferred": False,
        },
    )
    db.commit()
    db.refresh(material)
    return _material_detail(db, user_id=user_id, material=material)


def confirm_material_workstreams(
    db: Session,
    *,
    user_id: int,
    material_id: int,
    data: GrowthWorkMaterialWorkstreamsConfirm,
) -> GrowthWorkMaterialDetailResponse:
    fingerprint = _request_fingerprint(
        "confirm_material_workstreams",
        {
            "material_id": material_id,
            "expected_material_version": data.expected_material_version,
            "intake_id": data.intake_id,
            "selected": [item.model_dump(mode="json") for item in data.selected],
        },
    )
    replay = (
        db.query(GrowthAuditEvent)
        .filter(
            GrowthAuditEvent.user_id == user_id,
            GrowthAuditEvent.entity_type == "growth_work_material",
            GrowthAuditEvent.entity_id == material_id,
            GrowthAuditEvent.action == "workstreams_confirmed",
            GrowthAuditEvent.request_id == data.request_id,
        )
        .first()
    )
    if replay is not None:
        prior = replay.after_payload if isinstance(replay.after_payload, dict) else {}
        if not hmac.compare_digest(str(prior.get("fingerprint") or ""), fingerprint):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的工作线确认")
        material = db.query(GrowthWorkMaterial).filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        ).first()
        if material is None:
            raise HTTPException(status_code=404, detail="工作材料不存在")
        return _material_detail(db, user_id=user_id, material=material)

    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .first()
    )
    if material is None:
        raise HTTPException(status_code=404, detail="工作材料不存在")
    if material.version != data.expected_material_version:
        raise HTTPException(status_code=409, detail="材料版本已变化，请刷新后重试")
    intake = (
        db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.id == data.intake_id,
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == f"material-streams:{material_id}",
        )
        .first()
    )
    if intake is None or not isinstance(intake.candidate_payload, dict):
        raise HTTPException(status_code=404, detail="工作线候选不存在")
    if intake.candidate_payload.get("source_material_id") != material_id:
        raise HTTPException(status_code=409, detail="工作线候选与材料不匹配")
    selected_keys = {item.candidate_key for item in data.selected}
    proposal_metadata = intake.candidate_payload.get("proposal_metadata") or {}
    unknown = selected_keys - set(proposal_metadata)
    if unknown:
        raise HTTPException(status_code=422, detail="选中了不属于该材料的工作线候选")
    _guard_workstream_title_conflicts(
        db,
        user_id=user_id,
        intake=intake,
        selected=data.selected,
    )

    # Existing intake confirmation owns work-item/node creation and is itself
    # idempotent. If a process stops after that commit, retrying this endpoint
    # resumes the material-link phase below.
    selected_payloads = []
    for item in data.selected:
        payload = item.model_dump(mode="json")
        evidence = str(proposal_metadata[item.candidate_key].get("evidence_excerpt") or "")
        # The generic intake confirmation persists description as initial
        # context/evidence. For material-derived proposals that value must be a
        # verbatim source excerpt, never the AI summary.
        if evidence:
            payload["description"] = evidence
            payload["fact_excerpt"] = evidence[:500]
        selected_payloads.append(payload)
    confirmation = confirm_growth_intake(
        db,
        user_id=user_id,
        intake_id=intake.id,
        data=GrowthConfirmIntakeRequest.model_validate({
            "selected": selected_payloads,
            "retain_emotion": False,
        }),
    )

    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .with_for_update()
        .one()
    )
    if material.version != data.expected_material_version:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="材料已在工作线确认期间更新；工作线已创建，请刷新后重试以补齐关联",
        )
    replay = (
        db.query(GrowthAuditEvent)
        .filter(
            GrowthAuditEvent.user_id == user_id,
            GrowthAuditEvent.entity_type == "growth_work_material",
            GrowthAuditEvent.entity_id == material_id,
            GrowthAuditEvent.action == "workstreams_confirmed",
            GrowthAuditEvent.request_id == data.request_id,
        )
        .first()
    )
    if replay is not None:
        db.rollback()
        return _material_detail(db, user_id=user_id, material=material)

    item_by_key = {item.candidate_key: item for item in confirmation.work_items}
    dismissed_candidate_keys = sorted(set(proposal_metadata) - selected_keys)
    intake_payload = dict(intake.candidate_payload)
    intake_payload["proposal_resolution"] = {
        "policy": "unselected_candidates_dismissed_on_confirm",
        "confirmed_candidate_keys": sorted(selected_keys),
        "dismissed_candidate_keys": dismissed_candidate_keys,
        "resolved_at": _now().isoformat(),
    }
    intake.candidate_payload = intake_payload
    link_ids: list[int] = []
    placement_ids: list[int] = []
    progress_ids: list[int] = []
    for selected in data.selected:
        item = item_by_key[selected.candidate_key]
        metadata = proposal_metadata[selected.candidate_key]
        excerpt = str(metadata.get("evidence_excerpt") or "")
        span = _source_span(material.content, excerpt)
        evidence_spans = [span] if span is not None else []
        link = (
            db.query(GrowthWorkMaterialLink)
            .filter(
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.target_type == "work_item",
                GrowthWorkMaterialLink.target_id == item.id,
                GrowthWorkMaterialLink.link_type == "context",
            )
            .first()
        )
        if link is None:
            link = GrowthWorkMaterialLink(
                user_id=user_id,
                material_id=material.id,
                target_type="work_item",
                target_id=item.id,
                work_item_id=item.id,
                node_id=None,
                link_type="context",
                confidence=float(metadata.get("confidence") or 0.5),
                reason="你确认了 AI 从该材料提议的新工作线。",
                evidence_spans=evidence_spans,
                proposed_node_status=None,
                status="confirmed",
                analysis_mode="ai",
                rule_version=AI_ROUTING_RULE_VERSION,
                confirmed_at=_now(),
            )
            db.add(link)
            db.flush()
        link_ids.append(link.id)
        placement = (
            db.query(GrowthWorkPlacementEvent)
            .filter(
                GrowthWorkPlacementEvent.material_id == material.id,
                GrowthWorkPlacementEvent.work_item_id == item.id,
                GrowthWorkPlacementEvent.rule_version == PLACEMENT_RULE_VERSION,
            )
            .first()
        )
        if placement is None:
            priority = metadata.get("priority_axis") or "unknown"
            health = metadata.get("progress_health") or "unknown"
            placement = GrowthWorkPlacementEvent(
                user_id=user_id,
                work_item_id=item.id,
                material_id=material.id,
                priority_axis=priority,
                progress_health=health,
                quadrant=_quadrant(priority, health),
                confidence=float(metadata.get("confidence") or 0.5),
                reason=str(metadata.get("placement_reason") or "材料证据不足，保持待判断"),
                evidence_spans=evidence_spans,
                rule_version=PLACEMENT_RULE_VERSION,
                analysis_mode="ai",
                base_work_item_version=item.version,
                status="suggested",
            )
            db.add(placement)
            db.flush()
        placement_ids.append(placement.id)
        progress_revision = _analysis_revision("growth-progress-baseline-v1", material.version)
        progress = (
            db.query(GrowthWorkProgressEvent)
            .filter(
                GrowthWorkProgressEvent.material_id == material.id,
                GrowthWorkProgressEvent.work_item_id == item.id,
                GrowthWorkProgressEvent.rule_version == progress_revision,
            )
            .first()
        )
        if progress is None:
            objective = str(metadata.get("objective") or "").strip()
            strategy = str(metadata.get("strategy_summary") or "").strip()
            criteria = [str(value).strip() for value in (metadata.get("success_criteria") or []) if str(value).strip()]
            progress = GrowthWorkProgressEvent(
                user_id=user_id,
                work_item_id=item.id,
                material_id=material.id,
                impact_kind="context",
                headline=f"建立“{item.title}”的首份项目基线"[:500],
                causal_reason="你已确认这份材料定义了一条可独立跟踪的长期工作线；是否构成实质推进仍需单独审阅。",
                previous_state=None,
                current_state=objective or strategy or excerpt or item.title,
                next_gap=criteria[0] if criteria else None,
                evidence_spans=evidence_spans,
                confidence=float(metadata.get("confidence") or 0.5),
                status="suggested",
                analysis_mode="ai",
                rule_version=progress_revision,
                base_work_item_version=item.version,
                reportable=False,
            )
            db.add(progress)
            db.flush()
        progress_ids.append(progress.id)
    material.version += 1
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material.id,
        action="workstreams_confirmed",
        request_id=data.request_id,
        after={
            "fingerprint": fingerprint,
            "intake_id": intake.id,
            "work_item_ids": [item.id for item in confirmation.work_items],
            "work_node_ids": [node.id for node in confirmation.work_nodes],
            "link_ids": link_ids,
            "placement_event_ids": placement_ids,
            "progress_event_ids": progress_ids,
            "dismissed_candidate_keys": dismissed_candidate_keys,
            "selection_policy": "unselected_candidates_dismissed_on_confirm",
        },
    )
    db.commit()
    db.refresh(material)
    return _material_detail(db, user_id=user_id, material=material)


def _apply_suggestion_status(item: Any, *, status: str, expected_version: int) -> None:
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="材料建议版本已变化，请刷新后重试")
    if item.status == "dismissed":
        raise HTTPException(status_code=409, detail="已驳回的判断不能重复操作；请重新分析材料")
    if status == "confirmed" and item.status != "suggested":
        raise HTTPException(status_code=409, detail="只能确认待处理建议")
    if status == "dismissed" and item.status not in {"suggested", "confirmed"}:
        raise HTTPException(status_code=409, detail="当前判断不可撤销")
    now = _now()
    item.status = status
    item.version += 1
    item.confirmed_at = now if status == "confirmed" else None
    item.dismissed_at = now if status == "dismissed" else None


def _recompute_item_placement_from_confirmed(
    db: Session,
    *,
    user_id: int,
    item: GrowthWorkItem,
) -> None:
    latest = (
        db.query(GrowthWorkPlacementEvent)
        .join(
            GrowthWorkMaterial,
            GrowthWorkMaterial.id == GrowthWorkPlacementEvent.material_id,
        )
        .filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.work_item_id == item.id,
            GrowthWorkPlacementEvent.status == "confirmed",
            GrowthWorkMaterial.user_id == user_id,
        )
        .order_by(
            GrowthWorkMaterial.occurred_at.desc(),
            GrowthWorkPlacementEvent.confirmed_at.desc(),
            GrowthWorkPlacementEvent.id.desc(),
        )
        .first()
    )
    if latest is None:
        item.priority_axis = "unknown"
        item.progress_health = "unknown"
        item.quadrant = "unknown"
        item.placement_rule_version = RECOMPUTED_PLACEMENT_RULE_VERSION
    else:
        item.priority_axis = latest.priority_axis
        item.progress_health = latest.progress_health
        item.quadrant = latest.quadrant
        item.placement_rule_version = latest.rule_version
    item.placement_updated_at = _now()
    item.version += 1


def _recompute_item_progress_from_confirmed(
    db: Session,
    *,
    user_id: int,
    item: GrowthWorkItem,
) -> None:
    latest = (
        db.query(GrowthWorkProgressEvent, GrowthWorkMaterial)
        .join(
            GrowthWorkMaterial,
            GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id,
        )
        .filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.work_item_id == item.id,
            GrowthWorkProgressEvent.status == "confirmed",
            GrowthWorkMaterial.user_id == user_id,
        )
        .order_by(
            GrowthWorkMaterial.occurred_at.desc(),
            GrowthWorkProgressEvent.confirmed_at.desc(),
            GrowthWorkProgressEvent.id.desc(),
        )
        .first()
    )
    if latest is None:
        item.progress_summary = None
        item.blocker_note = None
        item.next_action = None
        item.next_follow_up_at = None
    else:
        event, material = latest
        item.progress_summary = event.current_state or event.headline
        item.blocker_note = (
            event.current_state or event.headline
            if event.impact_kind == "setback"
            else None
        )
        item.next_action = event.next_gap
        item.next_follow_up_at = material.next_follow_up_at
    item.version += 1


def _create_confirmed_manual_links(
    db: Session,
    *,
    user_id: int,
    material: GrowthWorkMaterial,
    manual_links: list[Any],
) -> list[GrowthWorkMaterialLink]:
    persisted: list[GrowthWorkMaterialLink] = []
    for manual in manual_links:
        node: GrowthWorkNode | None = None
        if manual.target_type == "work_item":
            item = (
                db.query(GrowthWorkItem)
                .filter(
                    GrowthWorkItem.id == manual.target_id,
                    GrowthWorkItem.user_id == user_id,
                    GrowthWorkItem.deleted_at.is_(None),
                )
                .first()
            )
        else:
            row = (
                db.query(GrowthWorkNode, GrowthWorkItem)
                .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkNode.work_item_id)
                .filter(
                    GrowthWorkNode.id == manual.target_id,
                    GrowthWorkNode.user_id == user_id,
                    GrowthWorkItem.user_id == user_id,
                    GrowthWorkItem.deleted_at.is_(None),
                )
                .first()
            )
            node, item = row if row is not None else (None, None)
        if item is None:
            raise HTTPException(status_code=404, detail="人工归属的工作项或节点不存在")
        existing = (
            db.query(GrowthWorkMaterialLink)
            .filter(
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.target_type == manual.target_type,
                GrowthWorkMaterialLink.target_id == manual.target_id,
                GrowthWorkMaterialLink.link_type == manual.link_type,
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="该材料归属已存在；请直接确认或驳回原建议")
        evidence_spans: list[dict[str, Any]] = []
        if manual.evidence_excerpt:
            start = material.content.find(manual.evidence_excerpt)
            if start < 0:
                raise HTTPException(status_code=422, detail="人工归属证据必须是材料中的连续原文")
            evidence_spans.append(
                {
                    "start": start,
                    "end": start + len(manual.evidence_excerpt),
                    "excerpt": manual.evidence_excerpt,
                    "statement_id": None,
                }
            )
        link = GrowthWorkMaterialLink(
            user_id=user_id,
            material_id=material.id,
            target_type=manual.target_type,
            target_id=manual.target_id,
            work_item_id=item.id,
            node_id=node.id if node is not None else None,
            link_type=manual.link_type,
            confidence=1.0,
            reason=manual.reason.strip(),
            evidence_spans=evidence_spans,
            proposed_node_status=None,
            status="confirmed",
            analysis_mode="rules",
            rule_version=MANUAL_ROUTE_VERSION,
            confirmed_at=_now(),
        )
        db.add(link)
        db.flush()
        persisted.append(link)
    return persisted


def confirm_work_material(
    db: Session,
    *,
    user: User,
    material_id: int,
    data: GrowthWorkMaterialConfirm,
) -> GrowthWorkMaterialDetailResponse:
    user_id = user.id
    fingerprint = _request_fingerprint(
        "confirm",
        data.model_dump(mode="json", exclude={"request_id"}),
    )
    replay = _existing_request(
        db,
        user_id=user_id,
        request_id=data.request_id,
        operation="confirm",
        fingerprint=fingerprint,
    )
    if replay is not None:
        if replay.id != material_id:
            raise HTTPException(status_code=409, detail="request_id 已用于另一份材料")
        return _material_detail(db, user_id=user_id, material=replay)

    expected_data_epoch = user.business_data_epoch
    db.rollback()
    owner = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None or owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise HTTPException(status_code=409, detail="业务数据已清空，请刷新后重试")
    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if material is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="工作材料不存在")
    if material.version != data.expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="工作材料版本已变化，请刷新后重试")

    statement_ids = {item.statement_id for item in data.statement_decisions}
    statements = {
        item.id: item
        for item in db.query(GrowthWorkMaterialStatement)
        .filter(
            GrowthWorkMaterialStatement.user_id == user_id,
            GrowthWorkMaterialStatement.material_id == material.id,
            GrowthWorkMaterialStatement.id.in_(statement_ids or [-1]),
        )
        .with_for_update()
        .all()
    }
    if set(statements) != statement_ids:
        db.rollback()
        raise HTTPException(status_code=404, detail="材料陈述建议不存在")

    link_ids = {item.link_id for item in data.link_decisions}
    links = {
        item.id: item
        for item in db.query(GrowthWorkMaterialLink)
        .filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
            GrowthWorkMaterialLink.id.in_(link_ids or [-1]),
        )
        .with_for_update()
        .all()
    }
    if set(links) != link_ids:
        db.rollback()
        raise HTTPException(status_code=404, detail="材料归属建议不存在")

    placement_ids = {item.placement_event_id for item in data.placement_decisions}
    placements = {
        item.id: item
        for item in db.query(GrowthWorkPlacementEvent)
        .filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.material_id == material.id,
            GrowthWorkPlacementEvent.id.in_(placement_ids or [-1]),
        )
        .with_for_update()
        .all()
    }
    if set(placements) != placement_ids:
        db.rollback()
        raise HTTPException(status_code=404, detail="象限建议不存在")

    placement_item_ids = {item.work_item_id for item in placements.values()}
    work_items = {
        item.id: item
        for item in db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.id.in_(placement_item_ids or [-1]),
        )
        .with_for_update()
        .all()
    }
    if set(work_items) != placement_item_ids:
        db.rollback()
        raise HTTPException(status_code=404, detail="象限建议对应的工作项不存在")
    if len(placement_item_ids) != len(data.placement_decisions):
        db.rollback()
        raise HTTPException(status_code=422, detail="一次确认不能为同一工作项提交多个象限建议")

    before = {
        "material_version": material.version,
        "statement_statuses": {str(key): item.status for key, item in statements.items()},
        "link_statuses": {str(key): item.status for key, item in links.items()},
        "placement_statuses": {str(key): item.status for key, item in placements.items()},
    }
    placement_dismissals = {
        decision.placement_event_id
        for decision in data.placement_decisions
        if decision.status == "dismissed"
    }
    for decision in data.link_decisions:
        link = links[decision.link_id]
        if link.status != "confirmed" or decision.status != "dismissed":
            continue
        another_confirmed_link = db.query(GrowthWorkMaterialLink.id).filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.material_id == material.id,
            GrowthWorkMaterialLink.work_item_id == link.work_item_id,
            GrowthWorkMaterialLink.status == "confirmed",
            GrowthWorkMaterialLink.id != link.id,
        ).first()
        if another_confirmed_link is not None:
            continue
        confirmed_progress = db.query(GrowthWorkProgressEvent.id).filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.material_id == material.id,
            GrowthWorkProgressEvent.work_item_id == link.work_item_id,
            GrowthWorkProgressEvent.status == "confirmed",
        ).first()
        confirmed_placement = db.query(GrowthWorkPlacementEvent.id).filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.material_id == material.id,
            GrowthWorkPlacementEvent.work_item_id == link.work_item_id,
            GrowthWorkPlacementEvent.status == "confirmed",
            GrowthWorkPlacementEvent.id.notin_(placement_dismissals or [-1]),
        ).first()
        if confirmed_progress is not None or confirmed_placement is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "该归属已被已确认进展或象限引用；"
                    "请先撤销对应判断，再撤销归属"
                ),
            )
    for decision in data.statement_decisions:
        _apply_suggestion_status(
            statements[decision.statement_id],
            status=decision.status,
            expected_version=decision.expected_version,
        )
    for decision in data.link_decisions:
        _apply_suggestion_status(
            links[decision.link_id],
            status=decision.status,
            expected_version=decision.expected_version,
        )
    manual_links = _create_confirmed_manual_links(
        db,
        user_id=user_id,
        material=material,
        manual_links=data.manual_links,
    )
    db.flush()

    for decision in data.placement_decisions:
        placement = placements[decision.placement_event_id]
        item = work_items[placement.work_item_id]
        was_confirmed_placement = placement.status == "confirmed"
        if decision.status == "confirmed":
            confirmed_link_exists = (
                db.query(GrowthWorkMaterialLink.id)
                .filter(
                    GrowthWorkMaterialLink.user_id == user_id,
                    GrowthWorkMaterialLink.material_id == material.id,
                    GrowthWorkMaterialLink.work_item_id == item.id,
                    GrowthWorkMaterialLink.status == "confirmed",
                )
                .first()
                is not None
            )
            if not confirmed_link_exists:
                db.rollback()
                raise HTTPException(status_code=422, detail="确认象限前必须先确认该材料与工作项的归属")
            if item.version != decision.expected_work_item_version:
                db.rollback()
                raise HTTPException(status_code=409, detail="工作项版本已变化，请重新生成象限建议")
            if placement.base_work_item_version != item.version:
                db.rollback()
                raise HTTPException(status_code=409, detail="象限建议基于旧版工作项，请重新分析")
        _apply_suggestion_status(
            placement,
            status=decision.status,
            expected_version=decision.expected_version,
        )
        if decision.status == "confirmed":
            if decision.override_priority_axis is not None:
                original = (
                    placement.priority_axis,
                    placement.progress_health,
                    placement.quadrant,
                    placement.rule_version,
                )
                placement.priority_axis = decision.override_priority_axis
                placement.progress_health = decision.override_progress_health
                placement.quadrant = _quadrant(
                    decision.override_priority_axis,
                    decision.override_progress_health,
                )
                placement.reason = (
                    f"{decision.override_reason.strip()}；人工覆盖原建议 "
                    f"{original[0]}/{original[1]}/{original[2]} ({original[3]})"
                )
                placement.rule_version = MANUAL_PLACEMENT_RULE_VERSION
                placement.analysis_mode = "rules"
                placement.confidence = 1.0
            item.priority_axis = placement.priority_axis
            item.progress_health = placement.progress_health
            item.quadrant = placement.quadrant
            item.placement_rule_version = placement.rule_version
            item.placement_updated_at = _now()
            item.version += 1
        elif was_confirmed_placement:
            _recompute_item_placement_from_confirmed(
                db,
                user_id=user_id,
                item=item,
            )

    material.version += 1
    db.add(
        GrowthWorkMaterialRequest(
            user_id=user_id,
            material_id=material.id,
            request_id=data.request_id,
            operation="confirm",
            input_fingerprint=fingerprint,
        )
    )
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material.id,
        action="suggestions_reviewed",
        request_id=data.request_id,
        before=before,
        after={
            "material_version": material.version,
            "statement_decisions": [item.model_dump(mode="json") for item in data.statement_decisions],
            "link_decisions": [item.model_dump(mode="json") for item in data.link_decisions],
            "manual_link_ids": [item.id for item in manual_links],
            "placement_decisions": [item.model_dump(mode="json") for item in data.placement_decisions],
            "node_statuses_updated": False,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = _existing_request(
            db,
            user_id=user_id,
            request_id=data.request_id,
            operation="confirm",
            fingerprint=fingerprint,
        )
        if replay is None or replay.id != material_id:
            raise HTTPException(status_code=409, detail="材料确认并发冲突，请刷新后重试") from exc
        return _material_detail(db, user_id=user_id, material=replay)
    db.refresh(material)
    return _material_detail(db, user_id=user_id, material=material)


def _audit_request_replay(
    db: Session,
    *,
    user_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    request_id: str,
    fingerprint: str,
) -> GrowthAuditEvent | None:
    audit = (
        db.query(GrowthAuditEvent)
        .filter(
            GrowthAuditEvent.user_id == user_id,
            GrowthAuditEvent.entity_type == entity_type,
            GrowthAuditEvent.action == action,
            GrowthAuditEvent.request_id == request_id,
        )
        .first()
    )
    if audit is None:
        return None
    payload = audit.after_payload if isinstance(audit.after_payload, dict) else {}
    if audit.entity_id != entity_id or not hmac.compare_digest(
        str(payload.get("fingerprint") or ""), fingerprint
    ):
        raise HTTPException(status_code=409, detail="request_id 已用于不同的修改请求")
    return audit


def _progress_event_payload(
    event: GrowthWorkProgressEvent,
    material: GrowthWorkMaterial | None = None,
    *,
    include_evidence: bool = False,
) -> dict[str, Any]:
    """Serialize an impact together with its true, user-owned event time."""
    payload = {
        column.name: getattr(event, column.name)
        for column in event.__table__.columns
    }
    payload.update(
        {
            "occurred_at": material.occurred_at if material is not None else None,
            "occurred_at_precision": (
                material.occurred_at_precision if material is not None else "unknown"
            ),
            "material_title": material.title if material is not None else None,
        }
    )
    if not include_evidence:
        payload["evidence_spans"] = []
    return payload


def _project_progress_event_payload(
    event: GrowthProjectProgressEvent,
    material: GrowthWorkMaterial | None = None,
    *,
    include_evidence: bool = False,
) -> dict[str, Any]:
    payload = {
        column.name: getattr(event, column.name)
        for column in event.__table__.columns
    }
    payload.update(
        {
            "occurred_at": material.occurred_at if material is not None else None,
            "occurred_at_precision": (
                material.occurred_at_precision if material is not None else "unknown"
            ),
            "material_title": material.title if material is not None else None,
        }
    )
    if not include_evidence:
        payload["evidence_spans"] = []
    return payload


def _project_profile_payload(project: GrowthProjectProfile) -> dict[str, Any]:
    return {
        column.name: getattr(project, column.name)
        for column in project.__table__.columns
        if column.name != "user_id"
    }


def upsert_project_profile(
    db: Session,
    *,
    user_id: int,
    data: GrowthProjectProfileUpsert,
    project_id: int | None = None,
) -> GrowthProjectProfileResponse:
    fingerprint = _request_fingerprint(
        "project_profile_upsert",
        {"project_id": project_id, **data.model_dump(mode="json", exclude={"request_id"})},
    )
    replay = db.query(GrowthAuditEvent).filter(
        GrowthAuditEvent.user_id == user_id,
        GrowthAuditEvent.action == "project_profile_upserted",
        GrowthAuditEvent.request_id == data.request_id,
    ).first()
    if replay is not None:
        prior = replay.after_payload if isinstance(replay.after_payload, dict) else {}
        if not hmac.compare_digest(str(prior.get("fingerprint") or ""), fingerprint):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的项目档案修改")
        project = db.query(GrowthProjectProfile).filter(
            GrowthProjectProfile.id == replay.entity_id,
            GrowthProjectProfile.user_id == user_id,
        ).first()
        if project is None:
            raise HTTPException(status_code=404, detail="项目档案不存在")
        return GrowthProjectProfileResponse.model_validate(project)

    if project_id is None:
        if data.expected_version is not None:
            raise HTTPException(status_code=422, detail="新建项目档案不能提供 expected_version")
        duplicate = db.query(GrowthProjectProfile.id).filter(
            GrowthProjectProfile.user_id == user_id,
            GrowthProjectProfile.account_name == data.account_name,
            GrowthProjectProfile.project_name == data.project_name,
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="同一客户下已存在同名项目")
        project = GrowthProjectProfile(
            user_id=user_id,
            account_name=data.account_name,
            project_name=data.project_name,
            objective=data.objective,
            success_criteria=data.success_criteria,
            strategy_summary=data.strategy_summary,
            key_constraints=data.key_constraints,
            next_follow_up_at=_normalized_datetime(data.next_follow_up_at),
            stale_after_days=data.stale_after_days,
            version=1,
            confirmed_at=_now(),
        )
        db.add(project)
        db.flush()
        before = None
    else:
        project = db.query(GrowthProjectProfile).filter(
            GrowthProjectProfile.id == project_id,
            GrowthProjectProfile.user_id == user_id,
        ).with_for_update().first()
        if project is None:
            raise HTTPException(status_code=404, detail="项目档案不存在")
        if data.expected_version is None or project.version != data.expected_version:
            raise HTTPException(status_code=409, detail="项目档案版本已变化，请刷新后重试")
        duplicate = db.query(GrowthProjectProfile.id).filter(
            GrowthProjectProfile.user_id == user_id,
            GrowthProjectProfile.account_name == data.account_name,
            GrowthProjectProfile.project_name == data.project_name,
            GrowthProjectProfile.id != project.id,
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="同一客户下已存在同名项目")
        before = _project_profile_payload(project)
        project.account_name = data.account_name
        project.project_name = data.project_name
        project.objective = data.objective
        project.success_criteria = data.success_criteria
        project.strategy_summary = data.strategy_summary
        project.key_constraints = data.key_constraints
        project.next_follow_up_at = _normalized_datetime(data.next_follow_up_at)
        project.stale_after_days = data.stale_after_days
        project.confirmed_at = _now()
        project.version += 1
        # account_name is a denormalized display/filter field on work lines and
        # materials.  Once a stable project id exists the profile owns that
        # value, so keep all attached rows consistent when the user renames or
        # corrects the customer label.
        db.query(GrowthWorkItem).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.project_id == project.id,
        ).update({GrowthWorkItem.account_name: project.account_name}, synchronize_session=False)
        db.query(GrowthWorkMaterial).filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.project_id == project.id,
        ).update({GrowthWorkMaterial.account_name: project.account_name}, synchronize_session=False)
    after = {**_project_profile_payload(project), "fingerprint": fingerprint, "reason": data.reason}
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_project_profile",
        entity_id=project.id,
        action="project_profile_upserted",
        request_id=data.request_id,
        before=_json_safe(before),
        after=_json_safe(after),
    )
    db.commit()
    db.refresh(project)
    return GrowthProjectProfileResponse.model_validate(project)


def review_project_progress_event(
    db: Session,
    *,
    user_id: int,
    event_id: int,
    data: GrowthProjectProgressEventReview,
) -> GrowthProjectProgressEventResponse:
    fingerprint = _request_fingerprint(
        "project_progress_review",
        {"event_id": event_id, **data.model_dump(mode="json", exclude={"request_id"})},
    )
    replay = _audit_request_replay(
        db,
        user_id=user_id,
        entity_type="growth_project_progress_event",
        entity_id=event_id,
        action="project_progress_reviewed",
        request_id=data.request_id,
        fingerprint=fingerprint,
    )
    event = db.query(GrowthProjectProgressEvent).filter(
        GrowthProjectProgressEvent.id == event_id,
        GrowthProjectProgressEvent.user_id == user_id,
    ).with_for_update().first()
    if event is None:
        raise HTTPException(status_code=404, detail="项目进展建议不存在")
    material = db.query(GrowthWorkMaterial).filter(
        GrowthWorkMaterial.id == event.material_id,
        GrowthWorkMaterial.user_id == user_id,
    ).first()
    if material is None:
        raise HTTPException(status_code=404, detail="项目进展建议对应材料不存在")
    if replay is not None:
        return GrowthProjectProgressEventResponse.model_validate(
            _project_progress_event_payload(event, material)
        )
    if event.version != data.expected_version:
        raise HTTPException(status_code=409, detail="项目进展建议版本已变化，请刷新后重试")
    if event.status == "dismissed" and data.status == "confirmed":
        raise HTTPException(status_code=409, detail="已驳回的项目进展不能重新确认，请重新分析材料")
    project = db.query(GrowthProjectProfile).filter(
        GrowthProjectProfile.id == event.project_id,
        GrowthProjectProfile.user_id == user_id,
    ).with_for_update().first()
    if project is None:
        raise HTTPException(status_code=404, detail="项目档案不存在")
    if event.status == "suggested" and data.status == "confirmed":
        if project.version != event.base_project_version:
            raise HTTPException(
                status_code=409,
                detail="项目总目标已在 Agent 分析后更新，请重新分析材料再确认进展",
            )
        latest_confirmed = (
            db.query(GrowthProjectProgressEvent.id)
            .join(
                GrowthWorkMaterial,
                GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id,
            )
            .filter(
                GrowthProjectProgressEvent.user_id == user_id,
                GrowthProjectProgressEvent.project_id == event.project_id,
                GrowthProjectProgressEvent.status == "confirmed",
                GrowthProjectProgressEvent.id != event.id,
                GrowthWorkMaterial.user_id == user_id,
            )
            .order_by(
                GrowthWorkMaterial.occurred_at.desc(),
                GrowthProjectProgressEvent.created_at.desc(),
                GrowthProjectProgressEvent.id.desc(),
            )
            .with_for_update()
            .first()
        )
        current_baseline_id = latest_confirmed[0] if latest_confirmed is not None else None
        if current_baseline_id != event.base_confirmed_event_id:
            raise HTTPException(
                status_code=409,
                detail="项目已有新的已确认进展，请重新分析材料再确认",
            )
    before = _project_progress_event_payload(event, material)
    was_confirmed = event.status == "confirmed"
    if data.status == "confirmed":
        for field_name in (
            "impact_kind",
            "headline",
            "causal_reason",
            "previous_state",
            "current_state",
            "next_gap",
        ):
            override = getattr(data, f"override_{field_name}")
            if override is not None:
                setattr(event, field_name, override.strip() if isinstance(override, str) else override)
        if any(
            getattr(data, f"override_{field}") is not None
            for field in (
                "impact_kind", "headline", "causal_reason", "previous_state", "current_state", "next_gap"
            )
        ):
            event.analysis_mode = "rules"
            event.confidence = 1.0
        event.status = "confirmed"
        event.confirmed_at = _now()
        event.dismissed_at = None
        event.reportable = data.reportable
        if material.next_follow_up_at is not None:
            # A backfilled older meeting must not overwrite the follow-up date
            # already established by a chronologically later confirmed event.
            if _material_is_current_project_head(
                db,
                user_id=user_id,
                project_id=project.id,
                material=material,
            ):
                project.next_follow_up_at = material.next_follow_up_at
    else:
        event.status = "dismissed"
        event.dismissed_at = _now()
        event.confirmed_at = None
        event.reportable = False
        if was_confirmed:
            # Follow-up on the project card is derived from the chronological
            # head of confirmed project events.  Revoking that head must not
            # leave its obsolete reminder behind.
            latest_remaining = (
                db.query(GrowthWorkMaterial)
                .join(
                    GrowthProjectProgressEvent,
                    GrowthProjectProgressEvent.material_id == GrowthWorkMaterial.id,
                )
                .filter(
                    GrowthProjectProgressEvent.user_id == user_id,
                    GrowthProjectProgressEvent.project_id == project.id,
                    GrowthProjectProgressEvent.status == "confirmed",
                    GrowthProjectProgressEvent.id != event.id,
                    GrowthWorkMaterial.user_id == user_id,
                    GrowthWorkMaterial.occurred_at.is_not(None),
                )
                .order_by(
                    GrowthWorkMaterial.occurred_at.desc(),
                    GrowthProjectProgressEvent.id.desc(),
                )
                .first()
            )
            project.next_follow_up_at = (
                latest_remaining.next_follow_up_at
                if latest_remaining is not None
                else None
            )
    event.version += 1
    # The project version is the optimistic-concurrency revision for both its
    # human-authored goal and its reviewed progress state.  Confirming or
    # dismissing any event invalidates every still-pending Agent suggestion
    # made against the prior project snapshot, regardless of event date.
    project.version += 1
    after = _project_progress_event_payload(event, material)
    after.update({"fingerprint": fingerprint, "reason": data.reason})
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_project_progress_event",
        entity_id=event.id,
        action="project_progress_reviewed",
        request_id=data.request_id,
        before=_json_safe(before),
        after=_json_safe(after),
    )
    db.commit()
    db.refresh(event)
    return GrowthProjectProgressEventResponse.model_validate(
        _project_progress_event_payload(event, material)
    )


def get_project_timeline(
    db: Session,
    *,
    user_id: int,
    project_id: int,
) -> GrowthProjectTimelineResponse:
    project = db.query(GrowthProjectProfile).filter(
        GrowthProjectProfile.id == project_id,
        GrowthProjectProfile.user_id == user_id,
    ).first()
    if project is None:
        raise HTTPException(status_code=404, detail="项目档案不存在")
    rows = (
        db.query(GrowthProjectProgressEvent, GrowthWorkMaterial)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id)
        .filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.project_id == project.id,
            GrowthProjectProgressEvent.status != "dismissed",
            GrowthWorkMaterial.user_id == user_id,
        )
        .order_by(
            GrowthWorkMaterial.occurred_at.desc(),
            GrowthProjectProgressEvent.created_at.desc(),
        )
        .all()
    )
    events = [_project_progress_event_payload(event, material) for event, material in rows]
    return GrowthProjectTimelineResponse(
        project=GrowthProjectProfileResponse.model_validate(project),
        latest_confirmed_event=next(
            (event for event in events if event["status"] == "confirmed"), None
        ),
        latest_suggested_event=next(
            (event for event in events if event["status"] == "suggested"), None
        ),
        events=events,
    )


def _tracking_profile(item: GrowthWorkItem) -> dict[str, Any]:
    return {
        "account_name": item.account_name,
        "project_id": item.project_id,
        "objective": item.objective,
        "success_criteria": list(item.success_criteria or []),
        "strategy_summary": item.strategy_summary,
        "key_constraints": list(item.key_constraints or []),
        "next_follow_up_at": item.next_follow_up_at,
        "stale_after_days": item.stale_after_days or 14,
    }


def _item_progress_snapshot(
    db: Session,
    *,
    user_id: int,
    item: GrowthWorkItem,
) -> dict[str, Any]:
    progress_rows = (
        db.query(GrowthWorkProgressEvent, GrowthWorkMaterial)
        .join(
            GrowthWorkMaterial,
            GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id,
        )
        .filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.work_item_id == item.id,
            GrowthWorkProgressEvent.status != "dismissed",
            GrowthWorkMaterial.user_id == user_id,
        )
        .all()
    )
    linked_material_ids = {
        row[0]
        for row in db.query(GrowthWorkMaterialLink.material_id)
        .filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.work_item_id == item.id,
            GrowthWorkMaterialLink.status != "dismissed",
        )
        .all()
    } | {material.id for _, material in progress_rows}
    dated_materials = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.id.in_(linked_material_ids or [-1]),
            GrowthWorkMaterial.occurred_at.is_not(None),
        )
        .all()
    )
    last_activity_at = max(
        (material.occurred_at for material in dated_materials),
        default=None,
    )
    # A recent meeting is activity, not necessarily progress.  When a line has
    # never had a confirmed advancement, using only the newest material date
    # lets a stream of context/no-change meetings postpone the stale warning
    # forever.  Anchor that warning to when tracking actually began instead.
    tracking_candidates = [
        value
        for value in (
            *(material.occurred_at for material in dated_materials),
            item.confirmed_at,
            item.created_at,
        )
        if value is not None
    ]
    tracking_started_at = min(tracking_candidates, default=None)
    last_advancement_at = max(
        (
            material.occurred_at
            for event, material in progress_rows
            if event.status == "confirmed"
            and event.impact_kind == "advanced"
            and material.occurred_at is not None
        ),
        default=None,
    )
    latest_pair = max(
        progress_rows,
        key=lambda pair: (
            pair[1].occurred_at is not None,
            pair[1].occurred_at or datetime.min,
            pair[0].id,
        ),
        default=None,
    )
    today = _now().date()
    days_since_advancement = (
        max(0, (today - last_advancement_at.date()).days)
        if last_advancement_at is not None
        else None
    )
    follow_up_overdue = bool(
        item.next_follow_up_at is not None
        and item.next_follow_up_at.date() < today
    )
    threshold = item.stale_after_days or 14
    stale = False
    stale_reason: str | None = None
    if follow_up_overdue:
        stale = True
        overdue_days = (today - item.next_follow_up_at.date()).days
        stale_reason = f"已超过下次跟进日期 {overdue_days} 天"
    elif last_advancement_at is not None and days_since_advancement is not None:
        if days_since_advancement > threshold:
            stale = True
            stale_reason = f"距离上次确认推进已 {days_since_advancement} 天"
    elif tracking_started_at is not None:
        days_without_advancement = max(0, (today - tracking_started_at.date()).days)
        if days_without_advancement > threshold:
            stale = True
            stale_reason = f"该事项已跟踪 {days_without_advancement} 天，仍无确认推进"
    return {
        "latest_progress_event": (
            _progress_event_payload(*latest_pair) if latest_pair is not None else None
        ),
        "last_activity_at": last_activity_at,
        "last_advancement_at": last_advancement_at,
        "days_since_advancement": days_since_advancement,
        "stale": stale,
        "stale_reason": stale_reason,
        "follow_up_overdue": follow_up_overdue,
    }


def _board_item_payload(
    db: Session,
    *,
    user_id: int,
    item: GrowthWorkItem,
) -> dict[str, Any]:
    quadrant = item.quadrant if item.quadrant in QUADRANT_ORDER else "unknown"
    return {
        "work_item_id": item.id,
        "title": item.title,
        **_tracking_profile(item),
        "status": item.status,
        "priority_axis": item.priority_axis,
        "progress_health": item.progress_health,
        "quadrant": quadrant,
        "version": item.version,
        "placement_rule_version": item.placement_rule_version,
        "placement_updated_at": item.placement_updated_at,
        **_item_progress_snapshot(db, user_id=user_id, item=item),
    }


def _project_progress_snapshot(
    db: Session,
    *,
    user_id: int,
    project: GrowthProjectProfile,
) -> dict[str, Any]:
    rows = (
        db.query(GrowthProjectProgressEvent, GrowthWorkMaterial)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id)
        .filter(
            GrowthProjectProgressEvent.user_id == user_id,
            GrowthProjectProgressEvent.project_id == project.id,
            GrowthProjectProgressEvent.status != "dismissed",
            GrowthWorkMaterial.user_id == user_id,
        )
        .all()
    )
    materials = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.project_id == project.id,
        )
        .all()
    )
    latest_pair = max(
        rows,
        key=lambda pair: (
            pair[1].occurred_at is not None,
            pair[1].occurred_at or pair[0].created_at or datetime.min,
            pair[0].id,
        ),
        default=None,
    )
    last_advancement_at = max(
        (
            material.occurred_at
            for event, material in rows
            if event.status == "confirmed"
            and event.impact_kind == "advanced"
            and material.occurred_at is not None
        ),
        default=None,
    )
    tracking_started_at = min(
        (
            value
            for value in (
                *(material.occurred_at for material in materials),
                project.confirmed_at,
                project.created_at,
            )
            if value is not None
        ),
        default=None,
    )
    today = _now().date()
    follow_up_overdue = bool(
        project.next_follow_up_at is not None
        and project.next_follow_up_at.date() < today
    )
    stale = False
    stale_reason: str | None = None
    threshold = project.stale_after_days or 14
    if follow_up_overdue:
        overdue_days = (today - project.next_follow_up_at.date()).days
        stale = True
        stale_reason = f"项目跟进日期已逾期 {overdue_days} 天"
    elif last_advancement_at is not None:
        days = max(0, (today - last_advancement_at.date()).days)
        if days > threshold:
            stale = True
            stale_reason = f"距项目上次确认推进已 {days} 天"
    elif tracking_started_at is not None:
        days = max(0, (today - tracking_started_at.date()).days)
        if days > threshold:
            stale = True
            stale_reason = f"项目已跟踪 {days} 天，仍无确认推进"
    return {
        "latest_project_progress_event": (
            _project_progress_event_payload(*latest_pair) if latest_pair is not None else None
        ),
        "last_project_advancement_at": last_advancement_at,
        "project_stale": stale,
        "project_stale_reason": stale_reason,
        "project_follow_up_overdue": follow_up_overdue,
    }


def update_work_material_metadata(
    db: Session,
    *,
    user_id: int,
    material_id: int,
    data: GrowthWorkMaterialMetadataUpdate,
) -> GrowthWorkMaterialDetailResponse:
    changes = data.model_dump(mode="json", exclude={"request_id"}, exclude_unset=True)
    fingerprint = _request_fingerprint("update_material_metadata", changes)
    if _audit_request_replay(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material_id,
        action="metadata_updated",
        request_id=data.request_id,
        fingerprint=fingerprint,
    ) is not None:
        material = db.query(GrowthWorkMaterial).filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        ).first()
        if material is None:
            raise HTTPException(status_code=404, detail="工作材料不存在")
        return _material_detail(db, user_id=user_id, material=material)

    material = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.id == material_id,
            GrowthWorkMaterial.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if material is None:
        raise HTTPException(status_code=404, detail="工作材料不存在")
    if material.version != data.expected_version:
        raise HTTPException(status_code=409, detail="材料版本已变化，请刷新后重试")
    fields_set = data.model_fields_set
    before = _material_payload(material, include_content=False)
    if "title" in fields_set:
        material.title = (data.title or "").strip() or None
    requested_account = (
        (data.account_name or "").strip() or None
        if "account_name" in fields_set
        else material.account_name
    )
    if "project_id" in fields_set:
        target_project = (
            _resolve_material_project(
                db,
                user_id=user_id,
                project_id=data.project_id,
                # When the user explicitly corrects the project, the project
                # profile is the source of truth for its customer.  Validate a
                # customer only if the request explicitly supplied one; the
                # material's stale old customer must not block correction.
                account_name=(
                    requested_account if "account_name" in fields_set else None
                ),
            )
            if data.project_id is not None
            else None
        )
        project_changed = material.project_id != data.project_id
        if project_changed:
            incompatible_item = (
                GrowthWorkItem.project_id.is_not(None)
                if data.project_id is None
                else or_(
                    GrowthWorkItem.project_id.is_(None),
                    GrowthWorkItem.project_id != data.project_id,
                )
            )
            confirmed_old_route = (
                db.query(GrowthWorkMaterialLink.id)
                .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkMaterialLink.work_item_id)
                .filter(
                    GrowthWorkMaterialLink.user_id == user_id,
                    GrowthWorkMaterialLink.material_id == material.id,
                    GrowthWorkMaterialLink.status == "confirmed",
                    incompatible_item,
                )
                .first()
            )
            confirmed_old_placement = (
                db.query(GrowthWorkPlacementEvent.id)
                .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkPlacementEvent.work_item_id)
                .filter(
                    GrowthWorkPlacementEvent.user_id == user_id,
                    GrowthWorkPlacementEvent.material_id == material.id,
                    GrowthWorkPlacementEvent.status == "confirmed",
                    incompatible_item,
                )
                .first()
            )
            confirmed_old_progress = (
                db.query(GrowthWorkProgressEvent.id)
                .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkProgressEvent.work_item_id)
                .filter(
                    GrowthWorkProgressEvent.user_id == user_id,
                    GrowthWorkProgressEvent.material_id == material.id,
                    GrowthWorkProgressEvent.status == "confirmed",
                    incompatible_item,
                )
                .first()
            )
            if any((confirmed_old_route, confirmed_old_placement, confirmed_old_progress)):
                raise HTTPException(
                    status_code=409,
                    detail="该材料已确认归入其他工作线，请先撤销旧归线判断再更正项目",
                )
            confirmed_effect = db.query(GrowthProjectProgressEvent.id).filter(
                GrowthProjectProgressEvent.user_id == user_id,
                GrowthProjectProgressEvent.material_id == material.id,
                GrowthProjectProgressEvent.status == "confirmed",
            ).first()
            if confirmed_effect is not None:
                raise HTTPException(
                    status_code=409,
                    detail="该材料已有已确认项目进展，请先撤销该判断再更正项目归属",
                )
            # Unreviewed Agent effects belong to the old routing hypothesis;
            # discard them on an explicit human correction.  Dismissed rows are
            # retained as audit history and never affect the board/review.
            db.query(GrowthProjectProgressEvent).filter(
                GrowthProjectProgressEvent.user_id == user_id,
                GrowthProjectProgressEvent.material_id == material.id,
                GrowthProjectProgressEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkProgressEvent).filter(
                GrowthWorkProgressEvent.user_id == user_id,
                GrowthWorkProgressEvent.material_id == material.id,
                GrowthWorkProgressEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkPlacementEvent).filter(
                GrowthWorkPlacementEvent.user_id == user_id,
                GrowthWorkPlacementEvent.material_id == material.id,
                GrowthWorkPlacementEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkMaterialLink).filter(
                GrowthWorkMaterialLink.user_id == user_id,
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.status == "suggested",
            ).delete(synchronize_session=False)
        if data.project_id is None:
            material.project_id = None
            if "account_name" in fields_set:
                material.account_name = requested_account
        else:
            assert target_project is not None
            material.project_id = target_project.id
            material.account_name = target_project.account_name
    elif "account_name" in fields_set:
        if material.project_id is not None:
            project = _resolve_material_project(
                db,
                user_id=user_id,
                project_id=material.project_id,
                account_name=requested_account,
            )
            assert project is not None
            material.account_name = project.account_name
        else:
            material.account_name = requested_account
    if "occurred_at" in fields_set or "occurred_at_precision" in fields_set:
        next_occurred_at = _normalized_datetime(data.occurred_at)
        occurrence_changed = (
            material.occurred_at != next_occurred_at
            or material.occurred_at_precision != data.occurred_at_precision
        )
        if occurrence_changed:
            confirmed_rows = (
                db.query(GrowthWorkPlacementEvent.id).filter(
                    GrowthWorkPlacementEvent.user_id == user_id,
                    GrowthWorkPlacementEvent.material_id == material.id,
                    GrowthWorkPlacementEvent.status == "confirmed",
                ).first(),
                db.query(GrowthWorkProgressEvent.id).filter(
                    GrowthWorkProgressEvent.user_id == user_id,
                    GrowthWorkProgressEvent.material_id == material.id,
                    GrowthWorkProgressEvent.status == "confirmed",
                ).first(),
                db.query(GrowthProjectProgressEvent.id).filter(
                    GrowthProjectProgressEvent.user_id == user_id,
                    GrowthProjectProgressEvent.material_id == material.id,
                    GrowthProjectProgressEvent.status == "confirmed",
                ).first(),
            )
            if any(confirmed_rows):
                raise HTTPException(
                    status_code=409,
                    detail="该材料已有已确认的历史结论，不能直接更改发生时间",
                )
            # Chronology is an input to previous/current-state analysis.  Once
            # the user corrects it, every unreviewed progress/placement proposal
            # derived from the old position is invalid and must be regenerated.
            # Material links describe ownership, not chronology, and remain.
            db.query(GrowthProjectProgressEvent).filter(
                GrowthProjectProgressEvent.user_id == user_id,
                GrowthProjectProgressEvent.material_id == material.id,
                GrowthProjectProgressEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkProgressEvent).filter(
                GrowthWorkProgressEvent.user_id == user_id,
                GrowthWorkProgressEvent.material_id == material.id,
                GrowthWorkProgressEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkPlacementEvent).filter(
                GrowthWorkPlacementEvent.user_id == user_id,
                GrowthWorkPlacementEvent.material_id == material.id,
                GrowthWorkPlacementEvent.status == "suggested",
            ).delete(synchronize_session=False)
            material.fallback_reason = "material_occurrence_changed_reanalysis_required"
        material.occurred_at = next_occurred_at
        material.occurred_at_precision = data.occurred_at_precision
    if "next_follow_up_at" in fields_set:
        next_follow_up_at = _normalized_datetime(data.next_follow_up_at)
        follow_up_changed = material.next_follow_up_at != next_follow_up_at
        material.next_follow_up_at = next_follow_up_at
        if follow_up_changed and material.occurred_at is not None:
            confirmed_project_ids = [
                row[0]
                for row in db.query(GrowthProjectProgressEvent.project_id)
                .filter(
                    GrowthProjectProgressEvent.user_id == user_id,
                    GrowthProjectProgressEvent.material_id == material.id,
                    GrowthProjectProgressEvent.status == "confirmed",
                )
                .distinct()
                .order_by(GrowthProjectProgressEvent.project_id.asc())
                .all()
            ]
            for confirmed_project_id in confirmed_project_ids:
                if not _material_is_current_project_head(
                    db,
                    user_id=user_id,
                    project_id=confirmed_project_id,
                    material=material,
                ):
                    continue
                project = db.query(GrowthProjectProfile).filter(
                    GrowthProjectProfile.id == confirmed_project_id,
                    GrowthProjectProfile.user_id == user_id,
                ).with_for_update().first()
                if project is None:
                    continue
                project.next_follow_up_at = next_follow_up_at
                # A manual follow-up edit changes the user-owned project state
                # and invalidates pending Agent suggestions based on it.
                project.version += 1
    if "source_document_id" in fields_set:
        material.source_document_id = (data.source_document_id or "").strip() or None
    if "source_url" in fields_set:
        material.source_url = (data.source_url or "").strip() or None
    material.version += 1
    after = _material_payload(material, include_content=False)
    after["fingerprint"] = fingerprint
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_material",
        entity_id=material.id,
        action="metadata_updated",
        request_id=data.request_id,
        before=_json_safe(before),
        after=_json_safe(after),
    )
    db.commit()
    db.refresh(material)
    return _material_detail(db, user_id=user_id, material=material)


def update_work_item_tracking_profile(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: GrowthWorkTrackingProfileUpdate,
) -> dict[str, Any]:
    fingerprint = _request_fingerprint(
        "update_tracking_profile",
        data.model_dump(mode="json", exclude={"request_id"}),
    )
    if _audit_request_replay(
        db,
        user_id=user_id,
        entity_type="growth_work_item",
        entity_id=item_id,
        action="tracking_profile_confirmed",
        request_id=data.request_id,
        fingerprint=fingerprint,
    ) is not None:
        item = db.query(GrowthWorkItem).filter(
            GrowthWorkItem.id == item_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        ).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长工作项不存在")
        return _board_item_payload(db, user_id=user_id, item=item)

    item = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.id == item_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="成长工作项不存在")
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="工作项版本已变化，请刷新后重试")
    before = {**_tracking_profile(item), "version": item.version}
    requested_account = (data.account_name or "").strip() or None
    if "project_id" in data.model_fields_set:
        project = (
            _resolve_material_project(
                db,
                user_id=user_id,
                project_id=data.project_id,
                account_name=requested_account,
            )
            if data.project_id is not None
            else None
        )
        target_project_id = project.id if project is not None else None
        if item.project_id != target_project_id:
            # A work line's project is part of the historical reporting key.
            # Rewriting it in place after a user confirmed any route/placement/
            # progress would silently move old weeks and months to a different
            # project.  That needs a future explicit migration workflow.
            confirmed_link = db.query(GrowthWorkMaterialLink.id).filter(
                GrowthWorkMaterialLink.user_id == user_id,
                GrowthWorkMaterialLink.work_item_id == item.id,
                GrowthWorkMaterialLink.status == "confirmed",
            ).first()
            confirmed_placement = db.query(GrowthWorkPlacementEvent.id).filter(
                GrowthWorkPlacementEvent.user_id == user_id,
                GrowthWorkPlacementEvent.work_item_id == item.id,
                GrowthWorkPlacementEvent.status == "confirmed",
            ).first()
            confirmed_progress = db.query(GrowthWorkProgressEvent.id).filter(
                GrowthWorkProgressEvent.user_id == user_id,
                GrowthWorkProgressEvent.work_item_id == item.id,
                GrowthWorkProgressEvent.status == "confirmed",
            ).first()
            if any((confirmed_link, confirmed_placement, confirmed_progress)):
                raise HTTPException(
                    status_code=409,
                    detail="该工作线已有已确认历史，不能直接修改项目归属；请先使用显式迁移流程",
                )
            # Suggested routing was based on the old project context.  It is
            # safe to discard, while dismissed rows remain as audit history.
            db.query(GrowthWorkProgressEvent).filter(
                GrowthWorkProgressEvent.user_id == user_id,
                GrowthWorkProgressEvent.work_item_id == item.id,
                GrowthWorkProgressEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkPlacementEvent).filter(
                GrowthWorkPlacementEvent.user_id == user_id,
                GrowthWorkPlacementEvent.work_item_id == item.id,
                GrowthWorkPlacementEvent.status == "suggested",
            ).delete(synchronize_session=False)
            db.query(GrowthWorkMaterialLink).filter(
                GrowthWorkMaterialLink.user_id == user_id,
                GrowthWorkMaterialLink.work_item_id == item.id,
                GrowthWorkMaterialLink.status == "suggested",
            ).delete(synchronize_session=False)
        if project is None:
            item.project_id = None
            item.account_name = requested_account
        else:
            item.project_id = project.id
            item.account_name = project.account_name
    elif item.project_id is not None:
        project = _resolve_material_project(
            db,
            user_id=user_id,
            project_id=item.project_id,
            account_name=requested_account,
        )
        assert project is not None
        item.account_name = project.account_name
    else:
        item.account_name = requested_account
    item.objective = (data.objective or "").strip() or None
    item.success_criteria = list(data.success_criteria)
    item.strategy_summary = (data.strategy_summary or "").strip() or None
    item.key_constraints = list(data.key_constraints)
    item.next_follow_up_at = _normalized_datetime(data.next_follow_up_at)
    item.stale_after_days = data.stale_after_days
    item.version += 1
    after = {
        **_tracking_profile(item),
        "version": item.version,
        "reason": data.reason,
        "confirmed": True,
        "fingerprint": fingerprint,
    }
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_item",
        entity_id=item.id,
        action="tracking_profile_confirmed",
        request_id=data.request_id,
        before=_json_safe(before),
        after=_json_safe(after),
    )
    db.commit()
    db.refresh(item)
    return _board_item_payload(db, user_id=user_id, item=item)


def review_work_progress_event(
    db: Session,
    *,
    user_id: int,
    event_id: int,
    data: GrowthWorkProgressEventReview,
) -> dict[str, Any]:
    fingerprint = _request_fingerprint(
        "review_progress_event",
        data.model_dump(mode="json", exclude={"request_id"}),
    )
    if _audit_request_replay(
        db,
        user_id=user_id,
        entity_type="growth_work_progress_event",
        entity_id=event_id,
        action="progress_reviewed",
        request_id=data.request_id,
        fingerprint=fingerprint,
    ) is not None:
        row = (
            db.query(GrowthWorkProgressEvent, GrowthWorkMaterial)
            .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id)
            .filter(
                GrowthWorkProgressEvent.id == event_id,
                GrowthWorkProgressEvent.user_id == user_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="进展影响建议不存在")
        return _progress_event_payload(*row)

    event = (
        db.query(GrowthWorkProgressEvent)
        .filter(
            GrowthWorkProgressEvent.id == event_id,
            GrowthWorkProgressEvent.user_id == user_id,
        )
        .with_for_update()
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="进展影响建议不存在")
    if event.version != data.expected_version:
        raise HTTPException(status_code=409, detail="进展建议版本已变化，请刷新后重试")
    if event.status == "dismissed":
        raise HTTPException(status_code=409, detail="已驳回的进展不能重复操作；请重新分析材料")
    if event.status == "confirmed" and data.status != "dismissed":
        raise HTTPException(status_code=409, detail="已确认进展只能撤销")
    item = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.id == event.work_item_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    material = db.query(GrowthWorkMaterial).filter(
        GrowthWorkMaterial.id == event.material_id,
        GrowthWorkMaterial.user_id == user_id,
    ).first()
    if item is None or material is None:
        raise HTTPException(status_code=404, detail="进展建议对应的工作线或材料不存在")
    before = _progress_event_payload(event, material)
    was_confirmed = event.status == "confirmed"
    if data.status == "confirmed":
        link = (
            db.query(GrowthWorkMaterialLink)
            .filter(
                GrowthWorkMaterialLink.user_id == user_id,
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.work_item_id == item.id,
                GrowthWorkMaterialLink.status != "dismissed",
            )
            .order_by(
                (GrowthWorkMaterialLink.status == "confirmed").desc(),
                GrowthWorkMaterialLink.id.asc(),
            )
            .first()
        )
        if link is None:
            raise HTTPException(status_code=422, detail="确认进展前必须先确定材料归属")
        if link.status == "suggested":
            _apply_suggestion_status(link, status="confirmed", expected_version=link.version)
        for field_name in (
            "impact_kind",
            "headline",
            "causal_reason",
            "previous_state",
            "current_state",
            "next_gap",
        ):
            override = getattr(data, f"override_{field_name}")
            if override is not None:
                setattr(event, field_name, override.strip() if isinstance(override, str) else override)
        if any(
            getattr(data, f"override_{field}") is not None
            for field in (
                "impact_kind",
                "headline",
                "causal_reason",
                "previous_state",
                "current_state",
                "next_gap",
            )
        ):
            event.analysis_mode = "rules"
            event.confidence = 1.0
        event.status = "confirmed"
        event.confirmed_at = _now()
        event.dismissed_at = None
        event.reportable = data.reportable
        if not item.account_name and material.account_name:
            item.account_name = material.account_name
        if material.next_follow_up_at is not None:
            item.next_follow_up_at = material.next_follow_up_at
        item.progress_summary = event.current_state or event.headline
        if event.impact_kind == "setback":
            item.blocker_note = event.current_state or event.headline
        elif event.impact_kind == "advanced":
            item.blocker_note = None
        if event.next_gap:
            item.next_action = event.next_gap
        item.version += 1
    else:
        event.status = "dismissed"
        event.dismissed_at = _now()
        event.confirmed_at = None
        event.reportable = False
        if was_confirmed:
            _recompute_item_progress_from_confirmed(
                db,
                user_id=user_id,
                item=item,
            )
    event.version += 1
    after = _progress_event_payload(event, material)
    after.update({"fingerprint": fingerprint, "reason": data.reason})
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_progress_event",
        entity_id=event.id,
        action="progress_reviewed",
        request_id=data.request_id,
        before=_json_safe(before),
        after=_json_safe(after),
    )
    db.commit()
    db.refresh(event)
    return _progress_event_payload(event, material)


def get_progress_review(
    db: Session,
    *,
    user_id: int,
    period: Literal["week", "month"],
    anchor: date,
    account_name: str | None = None,
) -> GrowthProgressReviewResponse:
    if period == "week":
        period_start = anchor - timedelta(days=anchor.weekday())
        period_end = period_start + timedelta(days=6)
    elif period == "month":
        period_start = anchor.replace(day=1)
        next_month = (
            period_start.replace(year=period_start.year + 1, month=1)
            if period_start.month == 12
            else period_start.replace(month=period_start.month + 1)
        )
        period_end = next_month - timedelta(days=1)
    else:
        raise HTTPException(status_code=422, detail="回顾周期只支持 week 或 month")
    start_at = datetime.combine(period_start, datetime.min.time())
    end_at = datetime.combine(period_end + timedelta(days=1), datetime.min.time())
    normalized_account = (account_name or "").strip() or None
    project_query = db.query(GrowthProjectProfile).filter(
        GrowthProjectProfile.user_id == user_id
    )
    if normalized_account is not None:
        project_query = project_query.filter(
            GrowthProjectProfile.account_name == normalized_account
        )
    projects = project_query.all()
    project_by_id = {project.id: project for project in projects}
    base_filters = [
        GrowthWorkProgressEvent.user_id == user_id,
        # A period review is a working draft: include AI suggestions so the
        # user can see the week/month without first clicking every event.
        # The response keeps status/reportable, so only confirmed+reportable
        # rows can be treated as formal reporting facts.
        GrowthWorkProgressEvent.status != "dismissed",
        GrowthWorkItem.user_id == user_id,
        GrowthWorkItem.deleted_at.is_(None),
        GrowthWorkMaterial.user_id == user_id,
    ]
    if normalized_account is not None:
        base_filters.append(GrowthWorkItem.account_name == normalized_account)
    raw_rows = (
        db.query(GrowthWorkProgressEvent, GrowthWorkMaterial, GrowthWorkItem)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkProgressEvent.work_item_id)
        .filter(
            *base_filters,
            GrowthWorkMaterial.occurred_at.is_not(None),
            GrowthWorkMaterial.occurred_at >= start_at,
            GrowthWorkMaterial.occurred_at < end_at,
        )
        .order_by(
            GrowthWorkItem.account_name.asc(),
            GrowthWorkItem.id.asc(),
            GrowthWorkMaterial.occurred_at.asc(),
            GrowthWorkProgressEvent.id.asc(),
        )
        .all()
    )
    # A reanalysis creates a new immutable suggestion while prior reviewed
    # decisions remain in audit history. Period drafts show only the newest
    # run per material/work-line pair, avoiding duplicate report bullets.
    latest_rows: dict[tuple[int, int], tuple[GrowthWorkProgressEvent, GrowthWorkMaterial, GrowthWorkItem]] = {}
    for row in raw_rows:
        event = row[0]
        key = (event.material_id, event.work_item_id)
        if key not in latest_rows or event.id > latest_rows[key][0].id:
            latest_rows[key] = row
    rows = sorted(
        latest_rows.values(),
        key=lambda row: (
            row[2].account_name or "",
            row[2].id,
            row[1].occurred_at or datetime.min,
            row[0].id,
        ),
    )
    undated_pairs = (
        db.query(GrowthWorkProgressEvent.material_id, GrowthWorkProgressEvent.work_item_id)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthWorkProgressEvent.material_id)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkProgressEvent.work_item_id)
        .filter(*base_filters, GrowthWorkMaterial.occurred_at.is_(None))
        .all()
    )
    undated_count = len({(material_id, work_item_id) for material_id, work_item_id in undated_pairs})

    project_event_filters = [
        GrowthProjectProgressEvent.user_id == user_id,
        GrowthProjectProgressEvent.status != "dismissed",
        GrowthProjectProfile.user_id == user_id,
        GrowthWorkMaterial.user_id == user_id,
    ]
    if normalized_account is not None:
        project_event_filters.append(
            GrowthProjectProfile.account_name == normalized_account
        )
    project_rows_raw = (
        db.query(GrowthProjectProgressEvent, GrowthWorkMaterial, GrowthProjectProfile)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id)
        .join(GrowthProjectProfile, GrowthProjectProfile.id == GrowthProjectProgressEvent.project_id)
        .filter(
            *project_event_filters,
            GrowthWorkMaterial.occurred_at.is_not(None),
            GrowthWorkMaterial.occurred_at >= start_at,
            GrowthWorkMaterial.occurred_at < end_at,
        )
        .all()
    )
    latest_project_rows: dict[
        tuple[int, int],
        tuple[GrowthProjectProgressEvent, GrowthWorkMaterial, GrowthProjectProfile],
    ] = {}
    for row in project_rows_raw:
        event = row[0]
        key = (event.material_id, event.project_id)
        if key not in latest_project_rows or event.id > latest_project_rows[key][0].id:
            latest_project_rows[key] = row
    project_rows = sorted(
        latest_project_rows.values(),
        key=lambda row: (
            row[2].account_name,
            row[2].project_name,
            row[1].occurred_at or datetime.min,
            row[0].id,
        ),
    )
    undated_project_pairs = (
        db.query(GrowthProjectProgressEvent.material_id, GrowthProjectProgressEvent.project_id)
        .join(GrowthWorkMaterial, GrowthWorkMaterial.id == GrowthProjectProgressEvent.material_id)
        .join(GrowthProjectProfile, GrowthProjectProfile.id == GrowthProjectProgressEvent.project_id)
        .filter(*project_event_filters, GrowthWorkMaterial.occurred_at.is_(None))
        .all()
    )
    undated_count += len(
        {(material_id, project_id) for material_id, project_id in undated_project_pairs}
    )

    groups: dict[tuple[int | None, str], dict[str, Any]] = {}
    for event, material, item in rows:
        project = project_by_id.get(item.project_id)
        group_name = project.project_name if project is not None else (item.account_name or "未归类项目")
        key = (project.id if project is not None else None, group_name)
        group = groups.setdefault(
            key,
            {
                "project_id": project.id if project is not None else None,
                "account_name": project.account_name if project is not None else group_name,
                "project_name": group_name,
                "project": _project_profile_payload(project) if project is not None else None,
                "project_events": [],
                "items": {},
            },
        )
        item_group = group["items"]
        item_payload = item_group.setdefault(
            item.id,
            {
                "work_item_id": item.id,
                "title": item.title,
                "account_name": item.account_name,
                "project_id": item.project_id,
                "objective": item.objective,
                "events": [],
            },
        )
        item_payload["events"].append(_progress_event_payload(event, material))
    for event, material, project in project_rows:
        key = (project.id, project.project_name)
        group = groups.setdefault(
            key,
            {
                "project_id": project.id,
                "account_name": project.account_name,
                "project_name": project.project_name,
                "project": _project_profile_payload(project),
                "project_events": [],
                "items": {},
            },
        )
        group["project_events"].append(
            _project_progress_event_payload(event, material)
        )
    return GrowthProgressReviewResponse(
        period=period,
        period_start=period_start,
        period_end=period_end,
        account_name=normalized_account,
        account_groups=[
            {
                **{key: value for key, value in group.items() if key != "items"},
                "items": list(group["items"].values()),
            }
            for group in groups.values()
        ],
        undated_count=undated_count,
    )


def get_work_item_timeline(
    db: Session,
    *,
    user_id: int,
    item_id: int,
) -> GrowthWorkTimelineResponse:
    item = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.id == item_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="成长工作项不存在")
    material_ids = {
        row[0]
        for row in db.query(GrowthWorkMaterialLink.material_id)
        .filter(
            GrowthWorkMaterialLink.user_id == user_id,
            GrowthWorkMaterialLink.work_item_id == item.id,
            GrowthWorkMaterialLink.status != "dismissed",
        )
        .all()
    } | {
        row[0]
        for row in db.query(GrowthWorkPlacementEvent.material_id)
        .filter(
            GrowthWorkPlacementEvent.user_id == user_id,
            GrowthWorkPlacementEvent.work_item_id == item.id,
            GrowthWorkPlacementEvent.status != "dismissed",
        )
        .all()
    } | {
        row[0]
        for row in db.query(GrowthWorkProgressEvent.material_id)
        .filter(
            GrowthWorkProgressEvent.user_id == user_id,
            GrowthWorkProgressEvent.work_item_id == item.id,
            GrowthWorkProgressEvent.status != "dismissed",
        )
        .all()
    }
    materials = (
        db.query(GrowthWorkMaterial)
        .filter(
            GrowthWorkMaterial.user_id == user_id,
            GrowthWorkMaterial.id.in_(material_ids or [-1]),
        )
        .all()
    )
    known = sorted(
        (material for material in materials if material.occurred_at is not None),
        key=lambda material: (material.occurred_at, material.id),
        reverse=True,
    )
    unknown = sorted(
        (material for material in materials if material.occurred_at is None),
        key=lambda material: (material.created_at, material.id),
        reverse=True,
    )
    entries: list[dict[str, Any]] = []
    for material in [*known, *unknown]:
        statements = (
            db.query(GrowthWorkMaterialStatement)
            .filter(
                GrowthWorkMaterialStatement.user_id == user_id,
                GrowthWorkMaterialStatement.material_id == material.id,
            )
            .order_by(GrowthWorkMaterialStatement.id.asc())
            .all()
        )
        links = (
            db.query(GrowthWorkMaterialLink)
            .filter(
                GrowthWorkMaterialLink.user_id == user_id,
                GrowthWorkMaterialLink.material_id == material.id,
                GrowthWorkMaterialLink.work_item_id == item.id,
                GrowthWorkMaterialLink.status != "dismissed",
            )
            .order_by(GrowthWorkMaterialLink.id.asc())
            .all()
        )
        node_ids = {link.node_id for link in links if link.node_id is not None}
        node_titles = dict(
            db.query(GrowthWorkNode.id, GrowthWorkNode.title)
            .filter(
                GrowthWorkNode.user_id == user_id,
                GrowthWorkNode.id.in_(node_ids or [-1]),
            )
            .all()
        )
        relations = (
            db.query(GrowthWorkMaterialRelation)
            .filter(
                GrowthWorkMaterialRelation.user_id == user_id,
                GrowthWorkMaterialRelation.material_id == material.id,
            )
            .order_by(GrowthWorkMaterialRelation.id.asc())
            .all()
        )
        placements = (
            db.query(GrowthWorkPlacementEvent)
            .filter(
                GrowthWorkPlacementEvent.user_id == user_id,
                GrowthWorkPlacementEvent.material_id == material.id,
                GrowthWorkPlacementEvent.work_item_id == item.id,
                GrowthWorkPlacementEvent.status != "dismissed",
            )
            .order_by(GrowthWorkPlacementEvent.id.asc())
            .all()
        )
        progress_events = (
            db.query(GrowthWorkProgressEvent)
            .filter(
                GrowthWorkProgressEvent.user_id == user_id,
                GrowthWorkProgressEvent.material_id == material.id,
                GrowthWorkProgressEvent.work_item_id == item.id,
                GrowthWorkProgressEvent.status != "dismissed",
            )
            # The primary card shows the newest analysis run. Older confirmed
            # decisions remain in progress_events as immutable audit history.
            .order_by(GrowthWorkProgressEvent.id.desc())
            .all()
        )
        entries.append(
            {
                "material": _material_payload(material, include_content=False),
                "statements": [
                    {
                        **{
                            column.name: getattr(statement, column.name)
                            for column in statement.__table__.columns
                        },
                        "evidence_excerpt": None,
                    }
                    for statement in statements
                ],
                "links": [
                    {
                        **{column.name: getattr(link, column.name) for column in link.__table__.columns},
                        "evidence_spans": [],
                        "work_item_title": item.title,
                        "node_title": node_titles.get(link.node_id) if link.node_id is not None else None,
                    }
                    for link in links
                ],
                "relations": relations,
                "placement_events": [
                    {
                        **{column.name: getattr(placement, column.name) for column in placement.__table__.columns},
                        "evidence_spans": [],
                        "work_item_title": item.title,
                    }
                    for placement in placements
                ],
                "progress_events": [
                    _progress_event_payload(progress_event, material)
                    for progress_event in progress_events
                ],
                "progress_event": (
                    _progress_event_payload(progress_events[0], material)
                    if progress_events
                    else None
                ),
            }
        )
    snapshot = _item_progress_snapshot(db, user_id=user_id, item=item)
    return GrowthWorkTimelineResponse(
        work_item_id=item.id,
        title=item.title,
        profile=_tracking_profile(item),
        current_placement={
            "priority_axis": item.priority_axis,
            "progress_health": item.progress_health,
            "quadrant": item.quadrant,
            "rule_version": item.placement_rule_version,
            "updated_at": item.placement_updated_at,
        },
        last_activity_at=snapshot["last_activity_at"],
        last_advancement_at=snapshot["last_advancement_at"],
        days_since_advancement=snapshot["days_since_advancement"],
        stale=snapshot["stale"],
        stale_reason=snapshot["stale_reason"],
        follow_up_overdue=snapshot["follow_up_overdue"],
        entries=entries,
    )


def get_work_board(db: Session, *, user_id: int) -> GrowthWorkBoardResponse:
    projects = (
        db.query(GrowthProjectProfile)
        .filter(GrowthProjectProfile.user_id == user_id)
        .order_by(GrowthProjectProfile.account_name.asc(), GrowthProjectProfile.project_name.asc())
        .all()
    )
    project_by_id = {project.id: project for project in projects}
    items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status.in_(ACTIVE_STATUSES),
        )
        .order_by(GrowthWorkItem.priority_order.asc(), GrowthWorkItem.updated_at.desc())
        .all()
    )
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in QUADRANT_ORDER}
    board_items: list[dict[str, Any]] = []
    for item in items:
        payload = _board_item_payload(db, user_id=user_id, item=item)
        board_items.append(payload)
        grouped[payload["quadrant"]].append(payload)
    # A customer can have several independent projects.  Stable project ids,
    # not the display label, define the grouping boundary.
    account_groups: dict[tuple[int | None, str], dict[str, Any]] = {}
    for project in projects:
        account_groups[(project.id, project.project_name)] = {
            "project_id": project.id,
            "account_name": project.account_name,
            "project_name": project.project_name,
            "project": _project_profile_payload(project),
            "items": [],
        }
    for payload in board_items:
        project = project_by_id.get(payload["project_id"])
        if project is not None:
            key = (project.id, project.project_name)
            account_groups[key]["items"].append(payload)
            continue
        label = payload["account_name"] or "未归类项目"
        key = (None, label)
        group = account_groups.setdefault(
            key,
            {
                "project_id": None,
                "account_name": label,
                "project_name": label,
                "project": None,
                "items": [],
            },
        )
        group["items"].append(payload)

    for group in account_groups.values():
        project = project_by_id.get(group["project_id"])
        group.update(
            _project_progress_snapshot(db, user_id=user_id, project=project)
            if project is not None
            else {
                "latest_project_progress_event": None,
                "last_project_advancement_at": None,
                "project_stale": False,
                "project_stale_reason": None,
                "project_follow_up_overdue": False,
            }
        )
    return GrowthWorkBoardResponse(
        rule_version=PLACEMENT_RULE_VERSION,
        axes={
            "priority_axis": {"high": "高优先级", "low": "低优先级", "unknown": "待判断"},
            "progress_health": {"healthy": "进展健康", "at_risk": "进展有风险", "unknown": "待判断"},
        },
        mapping={
            "high+at_risk": "focus",
            "high+healthy": "breakthrough",
            "low+healthy": "maintain",
            "low+at_risk": "clarify",
            "unknown": "unknown",
        },
        quadrants=[
            {"key": key, "label": QUADRANT_LABELS[key], "items": grouped[key]}
            for key in QUADRANT_ORDER
        ],
        account_groups=[
            {
                **group,
                "item_count": len(group["items"]),
                "stale_count": sum(1 for item in group["items"] if item["stale"]),
                "overdue_count": sum(
                    1 for item in group["items"] if item["follow_up_overdue"]
                ),
            }
            for group in account_groups.values()
        ],
    )


def update_work_item_placement(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: GrowthWorkPlacementUpdate,
) -> dict[str, Any]:
    """Human-confirmed placement tool; callers never write work-item fields directly."""
    item = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.id == item_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="成长工作项不存在")
    if item.status == "cancelled":
        raise HTTPException(status_code=409, detail="已收起的事项不能调整象限；请先恢复跟进")
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="工作项版本已变化，请刷新后重试")

    quadrant = _quadrant(data.priority_axis, data.progress_health)
    before = {
        "priority_axis": item.priority_axis,
        "progress_health": item.progress_health,
        "quadrant": item.quadrant,
        "placement_rule_version": item.placement_rule_version,
        "version": item.version,
    }
    item.priority_axis = data.priority_axis
    item.progress_health = data.progress_health
    item.quadrant = quadrant
    item.placement_rule_version = MANUAL_PLACEMENT_RULE_VERSION
    item.placement_updated_at = _now()
    item.version += 1
    after = {
        "priority_axis": item.priority_axis,
        "progress_health": item.progress_health,
        "quadrant": item.quadrant,
        "placement_rule_version": item.placement_rule_version,
        "placement_reason": data.reason,
        "version": item.version,
        "confirmed": True,
    }
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_item",
        entity_id=item.id,
        action="placement_manually_confirmed",
        request_id=data.request_id,
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(item)
    return _board_item_payload(db, user_id=user_id, item=item)
