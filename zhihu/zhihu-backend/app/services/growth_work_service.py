from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.career_event import CareerEvent
from app.models.growth import (
    GrowthAuditEvent,
    GrowthCommunicationDraft,
    GrowthEmotionNote,
    GrowthInquiry,
    GrowthWeeklyReport,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
    GrowthWorkNode,
    GrowthWorkNodeEvidence,
    GrowthWorkUpdate,
)
from app.models.user import User
from app.schemas.growth import (
    GrowthAnalyzeRequest,
    GrowthAnalyzeResponse,
    GrowthConfirmIntakeRequest,
    GrowthConfirmIntakeResponse,
    GrowthEmotionCandidate,
    GrowthUpdateWorkEventRequest,
    GrowthUpdateWorkItemRequest,
    GrowthUpdateWorkItemResponse,
    GrowthWeeklyReportCreate,
    GrowthWeeklyReportUpdate,
    GrowthWorkCandidate,
    GrowthWorkInboxAnalyzeRequest,
    GrowthWorkInboxAnalyzeResponse,
    GrowthWorkNodeCreate,
    GrowthWorkNodeUpdate,
    GrowthWorkUpdateCreate,
    GrowthWorkspaceResponse,
)
from app.services.growth_ai_service import analyze_with_ai, analyze_with_rules


PRIVACY_NOTICE = (
    "分析草稿不保存整段原文；确认后会把你选中的父事项原文片段保存到该事项，"
    "用于节点追溯，不会外发；只有你另行同意 AI 处理时才会发送脱敏后的最小文本。"
    "情绪原文默认不保存，只有你明确选择时才加密存储，且不进入周报或职业资产。"
)
ACTIVE_STATUSES = ("captured", "planned", "in_progress", "blocked", "deferred")
WORK_TRANSITIONS = {
    "captured": {"captured", "planned", "in_progress", "blocked", "completed", "deferred", "cancelled"},
    "planned": {"planned", "in_progress", "blocked", "completed", "deferred", "cancelled"},
    "in_progress": {"in_progress", "blocked", "completed", "deferred", "cancelled"},
    "blocked": {"blocked", "in_progress", "completed", "deferred", "cancelled"},
    "deferred": {"deferred", "planned", "in_progress", "blocked", "completed", "cancelled"},
    "completed": {"completed"},
    "cancelled": {"cancelled", "captured", "planned"},
}
EVENT_TRANSITIONS = {
    "captured": {"confirmed", "needs_more_evidence", "discarded"},
    "structured": {"confirmed", "needs_more_evidence", "discarded"},
    "needs_more_evidence": {"confirmed", "needs_more_evidence", "discarded"},
    "confirmed": {"confirmed", "archived"},
    "discarded": {"discarded"},
    "archived": {"archived"},
}
NODE_TRANSITIONS = {
    "planned": {"planned", "in_progress", "blocked", "completed", "cancelled"},
    "in_progress": {"in_progress", "blocked", "completed", "cancelled"},
    "blocked": {"blocked", "in_progress", "completed", "cancelled"},
    "completed": {"completed"},
    "cancelled": {"cancelled", "planned"},
}
NODE_ANALYSIS_RULE_VERSION = "growth-node-analysis-rules-v1"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalized_datetime(value: datetime | None) -> datetime | None:
    """Persist datetimes as naive UTC, matching the rest of the growth domain."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _classify_work_update(content: str, requested_kind: str) -> str:
    if requested_kind != "auto":
        return requested_kind
    if any(token in content for token in ("卡住", "卡点", "阻塞", "缺少", "还缺", "无法", "等确认", "风险")):
        return "blocker"
    if any(token in content for token in ("已完成", "已经完成", "搞定", "已交付", "通过评审", "确认完成", "结果是")):
        return "result"
    if any(token in content for token in ("下一步", "接下来", "计划", "准备", "待办", "之后要")):
        return "next_action"
    if any(token in content for token in ("进展", "推进", "正在", "目前", "已经", "收到反馈")):
        return "progress"
    return "context"


def _work_update_coaching(kind: str) -> tuple[str, list[str], list[str]]:
    if kind == "blocker":
        return (
            "已记录这个卡点；它不会自动改变任务状态。",
            ["可以继续补充缺少的是信息、决策还是资源。", "需要沟通时，再明确希望谁给出什么回应。"],
            ["S：这段卡点可以作为情境线索，沉淀前仍需核对事实。"],
        )
    if kind == "result":
        return (
            "已记录这条结果线索；它还不是已确认的 STAR 或周报事实。",
            ["如要沉淀成果，可稍后补充你采取的具体行动和可核对反馈。"],
            ["R：保留可核对的结果或反馈。", "A：只补充你确实采取过的行动。"],
        )
    if kind == "next_action":
        return (
            "已记录下一步线索；它不会替你承诺时间或改变任务状态。",
            ["如有必要，可再补充时间点、协作对象或完成标准。"],
            ["T：这段内容可以作为待完成任务线索，完成后再核对实际行动和结果。"],
        )
    if kind == "progress":
        return (
            "已记录这次进展；后续可以继续追加，不必重写已有内容。",
            ["有新反馈或范围变化时，继续追加一条即可。"],
            ["A：这段进展可以作为行动线索，确认时只保留已发生的事实。"],
        )
    return (
        "已保存这段上下文；它不会自动改变任务状态。",
        ["需要时可以继续补充进展、卡点、下一步或结果。"],
        [],
    )


def _node_key(item_id: int, request_id: str, title: str) -> str:
    digest = hashlib.sha256(f"{item_id}:{request_id}:{title}".encode("utf-8")).hexdigest()[:20]
    return f"manual-{digest}"


def _normalized_node_text(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()
    return re.sub(r"^(确认|完成|推进|开始|整理|支持|验证|跟进)", "", normalized)


def _node_topic_text(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()
    for token in sorted(
        (
            "怎么回事", "还要等", "进行中", "整理到", "通过评审", "已经完成",
            "本周", "今天", "明天", "后天", "必须", "需要", "确认", "了解", "具体", "开始",
            "正在", "完成", "推进", "整理", "发给", "发送", "提交", "交付", "已启动",
            "开了会", "开会", "先把", "写起来", "等待", "还缺", "卡住", "阻塞", "搞定",
            "得", "需", "写", "已", "和",
        ),
        key=len,
        reverse=True,
    ):
        normalized = normalized.replace(token, "")
    return normalized


def _longest_common_text(left: str, right: str) -> int:
    if not left or not right:
        return 0
    right = right[:1000]
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_character in left:
        current = [0]
        for index, right_character in enumerate(right, start=1):
            value = previous[index - 1] + 1 if left_character == right_character else 0
            current.append(value)
            longest = max(longest, value)
        previous = current
    return longest


def _node_action_compatible(title: str, clause: str) -> bool:
    if any(marker in title for marker in ("发给", "发送", "提交", "交付")):
        return any(marker in clause for marker in ("发给", "发送", "提交", "交付", "人民日报"))
    return True


def _node_match_confidence(title: str, content: str) -> float:
    if not _node_action_compatible(title, content):
        return 0.0
    title_text = _normalized_node_text(title)
    content_text = _normalized_node_text(content)
    if not title_text or not content_text:
        return 0.0
    if title_text in content_text:
        return 0.96
    if len(title_text) >= 4 and title_text[: max(4, len(title_text) - 2)] in content_text:
        return 0.84
    common_length = _longest_common_text(_node_topic_text(title), _node_topic_text(content))
    if common_length < 2:
        return 0.0
    confidence = 0.72 + min(common_length, 6) * 0.04
    if any(marker in title for marker in ("整理", "方案", "问卷")) and any(
        marker in content for marker in ("写", "整理", "起草", "先把")
    ):
        confidence += 0.12
    if "硬件" in title and "硬件" in content:
        confidence += 0.1
    return round(min(confidence, 0.95), 2)


def _proposed_node_status(content: str) -> str | None:
    if any(token in content for token in ("已完成", "已经完成", "搞定", "已交付", "已结束", "通过评审")):
        return "completed"
    if any(token in content for token in ("卡住", "卡点", "阻塞", "等待", "还要等", "等供应商", "还缺", "无法", "风险")):
        return "blocked"
    if any(token in content for token in ("推进", "开始", "正在", "进行中", "已启动", "先把", "写起来", "开了会")):
        return "in_progress"
    return None


def _node_relation_kind(kind: str, proposed_status: str | None) -> str:
    if proposed_status == "completed":
        return "completion"
    if proposed_status == "blocked":
        return "blocker"
    if proposed_status == "in_progress":
        return "progress"
    if kind == "result":
        return "completion"
    if kind == "blocker":
        return "blocker"
    if kind in {"progress", "next_action"}:
        return "progress"
    return "context"


def _create_node_suggestion_title(content: str) -> str:
    first = next((part.strip() for part in re.split(r"[\n；;。！？!?]+", content) if part.strip()), content.strip())
    return first[:300]


def _analyze_node_suggestions(
    content: str,
    nodes: list[GrowthWorkNode],
) -> tuple[list[dict[str, Any]], list[tuple[GrowthWorkNode, float, str | None, str]]]:
    clauses = [clause.strip() for clause in re.split(r"[\n；;。！？!?]+", content) if clause.strip()]
    matched_by_node: dict[int, tuple[GrowthWorkNode, float, str | None, str]] = {}
    for clause in clauses:
        candidates = [
            (node, confidence)
            for node in nodes
            if (confidence := _node_match_confidence(node.title, clause)) >= 0.7
        ]
        if not candidates:
            continue
        node, confidence = max(candidates, key=lambda item: (item[1], -item[0].priority_order, -item[0].id))
        match = (node, confidence, _proposed_node_status(clause), clause)
        previous = matched_by_node.get(node.id)
        if previous is None or confidence > previous[1]:
            matched_by_node[node.id] = match
    matches = sorted(
        matched_by_node.values(),
        key=lambda item: (-item[1], item[0].priority_order, item[0].id),
    )
    if matches:
        suggestions = [
            {
                "action": "update",
                "title": node.title,
                "reason": "本地规则在这段更新中命中了已有节点；只是建议，需要你确认。",
                "node_id": node.id,
                "proposed_status": proposed_status or node.status,
            }
            for node, _, proposed_status, _ in matches[:10]
        ]
        return suggestions, matches[:10]
    return (
        [
            {
                "action": "create",
                "title": _create_node_suggestion_title(content),
                "reason": "这段更新未稳定命中已有节点，可在核对后新建；系统不会自动写入。",
                "node_id": None,
                "proposed_status": None,
            }
        ],
        [],
    )


def _fingerprint(text: str, *, use_ai: bool) -> str:
    normalized = "\n".join(line.strip() for line in text.strip().splitlines() if line.strip())
    message = f"growth-work-intake-v1\nmode={'ai' if use_ai else 'rules'}\n{normalized}"
    return hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"growth-emotion-v1:{settings.JWT_SECRET}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _candidate_payload(candidates: list[GrowthWorkCandidate], emotion: GrowthEmotionCandidate) -> dict[str, Any]:
    return {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "emotion": emotion.model_dump(mode="json"),
    }


def _payload_candidates(intake: GrowthWorkIntake) -> list[GrowthWorkCandidate]:
    payload = intake.candidate_payload if isinstance(intake.candidate_payload, dict) else {}
    return [GrowthWorkCandidate.model_validate(item) for item in payload.get("candidates", [])]


def _payload_emotion(intake: GrowthWorkIntake) -> GrowthEmotionCandidate:
    payload = intake.candidate_payload if isinstance(intake.candidate_payload, dict) else {}
    return GrowthEmotionCandidate.model_validate(payload.get("emotion") or {})


def _analysis_response(intake: GrowthWorkIntake) -> GrowthAnalyzeResponse:
    return GrowthAnalyzeResponse(
        intake_id=intake.id,
        request_id=intake.request_id,
        status=intake.status,
        analysis_mode=intake.analysis_mode,
        parser_version=intake.parser_version,
        provider_name=intake.provider_name,
        model=intake.model,
        candidates=_payload_candidates(intake),
        emotion=_payload_emotion(intake),
        original_text_persisted=False,
        privacy_notice=PRIVACY_NOTICE,
    )


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


def analyze_growth_intake(
    db: Session,
    *,
    user: User,
    data: GrowthAnalyzeRequest,
) -> GrowthAnalyzeResponse:
    user_id = user.id
    fingerprint = _fingerprint(data.text, use_ai=data.use_ai)
    existing = (
        db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == data.request_id,
        )
        .first()
    )
    if existing is not None:
        if not hmac.compare_digest(existing.input_fingerprint, fingerprint):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长工作输入")
        return _analysis_response(existing)

    expected_data_epoch = user.business_data_epoch
    result = analyze_with_ai(user_id=user_id, text=data.text) if data.use_ai else analyze_with_rules(data.text)

    # The analysis may release control to an external service. Lock and re-check
    # the owner so an earlier request cannot restore data after a clear-data call.
    db.rollback()
    owner = db.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None or owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise HTTPException(status_code=409, detail="业务数据已在整理期间清空，请重新提交")

    existing = (
        db.query(GrowthWorkIntake)
        .filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == data.request_id,
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        if not hmac.compare_digest(existing.input_fingerprint, fingerprint):
            db.rollback()
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长工作输入")
        db.rollback()
        return _analysis_response(existing)

    intake = GrowthWorkIntake(
        user_id=user_id,
        request_id=data.request_id,
        input_fingerprint=fingerprint,
        candidate_payload=_candidate_payload(result.candidates, result.emotion),
        parser_version=result.parser_version,
        analysis_mode=result.analysis_mode,
        provider_name=result.provider_name,
        model=result.model,
    )
    db.add(intake)
    try:
        db.flush()
        _audit(
            db,
            user_id=user_id,
            entity_type="growth_work_intake",
            entity_id=intake.id,
            action="analyzed",
            request_id=data.request_id,
            after={
                "analysis_mode": result.analysis_mode,
                "candidate_count": len(result.candidates),
                "emotion_detected": result.emotion.detected,
                "original_text_persisted": False,
            },
        )
        db.commit()
    except IntegrityError:
        # A concurrent replay can pass the first lookup. The database unique
        # key remains authoritative; recover the winner as the idempotent result.
        db.rollback()
        winner = db.query(GrowthWorkIntake).filter(
            GrowthWorkIntake.user_id == user_id,
            GrowthWorkIntake.request_id == data.request_id,
        ).first()
        if winner is None or not hmac.compare_digest(winner.input_fingerprint, fingerprint):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长工作输入")
        return _analysis_response(winner)
    db.refresh(intake)
    return _analysis_response(intake)


def analyze_growth_work_inbox(
    db: Session,
    *,
    user_id: int,
    data: GrowthWorkInboxAnalyzeRequest,
) -> GrowthWorkInboxAnalyzeResponse:
    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="统一入口内容不能为空")
    items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status.in_(ACTIVE_STATUSES),
        )
        .order_by(GrowthWorkItem.priority_order.asc(), GrowthWorkItem.id.asc())
        .limit(100)
        .all()
    )
    item_ids = [item.id for item in items]
    nodes = (
        db.query(GrowthWorkNode)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id.in_(item_ids),
            GrowthWorkNode.status != "cancelled",
        )
        .order_by(GrowthWorkNode.priority_order.asc(), GrowthWorkNode.id.asc())
        .all()
        if item_ids
        else []
    )
    nodes_by_item: dict[int, list[GrowthWorkNode]] = {}
    for node in nodes:
        nodes_by_item.setdefault(node.work_item_id, []).append(node)

    clauses = [clause.strip() for clause in re.split(r"[\n；;。！？!?]+", content) if clause.strip()]
    routing_candidates: list[dict[str, Any]] = []
    for item in items:
        _, matches = _analyze_node_suggestions(content, nodes_by_item.get(item.id, []))
        matched_node_ids = list(dict.fromkeys(match[0].id for match in matches))
        node_confidences = [match[1] for match in matches]
        title_confidence = max(
            (_node_match_confidence(item.title, clause) for clause in clauses),
            default=0.0,
        )
        confidence = max([title_confidence, *node_confidences], default=0.0)
        if confidence < 0.7:
            continue
        if matched_node_ids:
            matched_titles = [
                node.title
                for node in nodes_by_item.get(item.id, [])
                if node.id in matched_node_ids
            ]
            reason = (
                "本地规则按分句命中该事项的节点："
                + "、".join(matched_titles)
                + "；只返回路由候选，需要你选择后才会追加。"
            )
        else:
            reason = "本地规则命中父事项主题；未自动写入，需要你选择。"
        routing_candidates.append(
            {
                "work_item_id": item.id,
                "work_item_title": item.title,
                "confidence": round(confidence, 2),
                "reason": reason,
                "matched_node_ids": matched_node_ids,
            }
        )
    routing_candidates.sort(key=lambda candidate: (-candidate["confidence"], candidate["work_item_id"]))
    return GrowthWorkInboxAnalyzeResponse(
        request_id=data.request_id,
        routing_candidates=routing_candidates,
        rule_version=NODE_ANALYSIS_RULE_VERSION,
        persisted=False,
    )


def confirm_growth_intake(
    db: Session,
    *,
    user_id: int,
    intake_id: int,
    data: GrowthConfirmIntakeRequest,
) -> GrowthConfirmIntakeResponse:
    intake = (
        db.query(GrowthWorkIntake)
        .filter(GrowthWorkIntake.id == intake_id, GrowthWorkIntake.user_id == user_id)
        .with_for_update()
        .first()
    )
    if intake is None:
        raise HTTPException(status_code=404, detail="成长工作输入不存在")

    existing_items = (
        db.query(GrowthWorkItem)
        .filter(GrowthWorkItem.intake_id == intake.id, GrowthWorkItem.user_id == user_id)
        .order_by(GrowthWorkItem.priority_order.asc(), GrowthWorkItem.id.asc())
        .all()
    )
    existing_nodes = (
        db.query(GrowthWorkNode)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id.in_([item.id for item in existing_items]),
        )
        .order_by(GrowthWorkNode.work_item_id.asc(), GrowthWorkNode.priority_order.asc(), GrowthWorkNode.id.asc())
        .all()
        if existing_items
        else []
    )
    if intake.status == "confirmed":
        if any(item.deleted_at is not None for item in existing_items):
            raise HTTPException(status_code=409, detail="该输入中已有事项被删除，不能重复确认；请重新整理原文")
        selected_keys = {item.candidate_key for item in data.selected}
        existing_keys = {item.candidate_key for item in existing_items}
        if selected_keys != existing_keys:
            raise HTTPException(status_code=409, detail="该输入已按另一组候选完成确认")
        emotion_exists = db.query(GrowthEmotionNote.id).filter(
            GrowthEmotionNote.intake_id == intake.id,
            GrowthEmotionNote.user_id == user_id,
            GrowthEmotionNote.deleted_at.is_(None),
        ).first() is not None
        if data.retain_emotion != emotion_exists:
            raise HTTPException(status_code=409, detail="该输入已按另一种情绪保留选择完成确认")
        return GrowthConfirmIntakeResponse(
            intake_id=intake.id,
            status="confirmed",
            work_items=existing_items,
            work_nodes=existing_nodes,
            emotion_retained=emotion_exists,
        )
    if intake.status != "draft":
        raise HTTPException(status_code=409, detail="该成长工作输入当前不能确认")

    candidates = {candidate.candidate_key: candidate for candidate in _payload_candidates(intake)}
    unknown_keys = [item.candidate_key for item in data.selected if item.candidate_key not in candidates]
    if unknown_keys:
        raise HTTPException(status_code=422, detail="提交了不属于该输入的工作候选")

    career_event = CareerEvent(
        user_id=user_id,
        event_type="growth",
        title="成长守护·当下工作",
        status="active",
        stage="current_work",
    )
    db.add(career_event)
    db.flush()

    work_items: list[GrowthWorkItem] = []
    pending_nodes: list[tuple[GrowthWorkItem, list[Any]]] = []
    for order, selected in enumerate(data.selected, start=1):
        candidate = candidates[selected.candidate_key]
        candidate_nodes = selected.nodes if selected.nodes is not None else candidate.nodes
        node_keys = [node.node_key for node in candidate_nodes]
        if len(set(node_keys)) != len(node_keys):
            raise HTTPException(status_code=422, detail="同一事项的节点标识不能重复")
        known_node_keys = set(node_keys)
        if any(
            dependency == node.node_key or dependency not in known_node_keys
            for node in candidate_nodes
            for dependency in node.depends_on_node_keys
        ):
            raise HTTPException(status_code=422, detail="节点依赖必须引用同一事项内的其他节点")
        resource_links = selected.resource_links if selected.resource_links is not None else candidate.resource_links
        open_questions = selected.open_questions if selected.open_questions is not None else candidate.open_questions
        item = GrowthWorkItem(
            user_id=user_id,
            intake_id=intake.id,
            career_event_id=career_event.id,
            candidate_key=candidate.candidate_key,
            title=(selected.title or candidate.title).strip(),
            account_name=(
                (selected.account_name if selected.account_name is not None else candidate.account_name)
                or ""
            ).strip()
            or None,
            objective=(
                selected.objective if selected.objective is not None else candidate.objective
            ),
            success_criteria=(
                selected.success_criteria
                if selected.success_criteria is not None
                else candidate.success_criteria
            ),
            strategy_summary=(
                selected.strategy_summary
                if selected.strategy_summary is not None
                else candidate.strategy_summary
            ),
            key_constraints=(
                selected.key_constraints
                if selected.key_constraints is not None
                else candidate.key_constraints
            ),
            description=selected.description if selected.description is not None else candidate.description,
            fact_excerpt=selected.fact_excerpt if selected.fact_excerpt is not None else candidate.fact_excerpt,
            impact_level=selected.impact_level or candidate.impact_level,
            energy_level=selected.energy_level or candidate.energy_level,
            priority_order=order * 10,
            selection_reason=candidate.selection_reason,
            resource_links=[link.model_dump(mode="json") for link in resource_links],
            open_questions=open_questions,
            tracking_rule=selected.tracking_rule if selected.tracking_rule is not None else candidate.tracking_rule,
            status="planned",
            due_at=selected.due_at,
            next_follow_up_at=_normalized_datetime(selected.next_follow_up_at),
            stale_after_days=selected.stale_after_days or 14,
            reportable=selected.reportable,
        )
        db.add(item)
        work_items.append(item)
        pending_nodes.append((item, candidate_nodes))

    db.flush()
    work_nodes: list[GrowthWorkNode] = []
    for item, candidate_nodes in pending_nodes:
        for node in candidate_nodes:
            work_node = GrowthWorkNode(
                user_id=user_id,
                work_item_id=item.id,
                request_id=None,
                node_key=node.node_key,
                title=node.title,
                status="planned",
                priority_order=node.priority_order,
                depends_on_node_keys=node.depends_on_node_keys,
                time_hint=node.time_hint,
                source="intake",
            )
            db.add(work_node)
            work_nodes.append(work_node)

    db.flush()
    initial_update_ids: list[int] = []
    initial_evidence_ids: list[int] = []
    for item, _ in pending_nodes:
        source_content = (item.description or item.fact_excerpt or item.title).strip()
        request_digest = hashlib.sha256(
            f"{intake.id}:{item.candidate_key}".encode("utf-8")
        ).hexdigest()[:16]
        initial_update = GrowthWorkUpdate(
            user_id=user_id,
            work_item_id=item.id,
            request_id=f"intake-context-{intake.id}-{request_digest}",
            content=source_content,
            kind="context",
            assistant_summary="已随父事项确认保存初始上下文。",
            suggestions=[],
            star_hints=[],
            node_suggestions=[],
        )
        db.add(initial_update)
        db.flush()
        initial_update_ids.append(initial_update.id)
        for node in (candidate_node for candidate_node in work_nodes if candidate_node.work_item_id == item.id):
            node.source_update_id = initial_update.id
            evidence = GrowthWorkNodeEvidence(
                user_id=user_id,
                node_id=node.id,
                work_update_id=initial_update.id,
                relation_kind="context",
                evidence_excerpt=source_content[:2000],
                analysis_summary="父事项和该节点由用户在同一次确认中保留，来源为该父事项的原文片段。",
                confidence=1.0,
                status="confirmed",
                analysis_mode="rules",
                rule_version=NODE_ANALYSIS_RULE_VERSION,
                confirmed_at=_now(),
            )
            db.add(evidence)
            db.flush()
            initial_evidence_ids.append(evidence.id)
        _audit(
            db,
            user_id=user_id,
            entity_type="growth_work_update",
            entity_id=initial_update.id,
            action="initial_context_created",
            request_id=initial_update.request_id,
            after={"work_item_id": item.id, "kind": "context"},
        )

    if data.retain_emotion:
        encrypted = _fernet().encrypt(data.emotion_text.strip().encode("utf-8")).decode("ascii")
        db.add(
            GrowthEmotionNote(
                user_id=user_id,
                intake_id=intake.id,
                encrypted_content=encrypted,
                deidentified_fact=(data.deidentified_fact or "").strip() or None,
                privacy_level="private_deidentified" if data.deidentified_fact else "private",
            )
        )

    intake.status = "confirmed"
    intake.confirmed_at = _now()
    db.flush()
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_intake",
        entity_id=intake.id,
        action="confirmed",
        request_id=intake.request_id,
        after={
            "work_item_ids": [item.id for item in work_items],
            "work_node_ids": [node.id for node in work_nodes],
            "initial_update_ids": initial_update_ids,
            "initial_evidence_ids": initial_evidence_ids,
            "emotion_retained": data.retain_emotion,
        },
    )
    db.commit()
    for item in work_items:
        db.refresh(item)
    for node in work_nodes:
        db.refresh(node)
    return GrowthConfirmIntakeResponse(
        intake_id=intake.id,
        status="confirmed",
        work_items=work_items,
        work_nodes=work_nodes,
        emotion_retained=data.retain_emotion,
    )


def create_growth_work_update(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: GrowthWorkUpdateCreate,
) -> GrowthWorkUpdate:
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
        raise HTTPException(status_code=409, detail="已收起的事项不能继续追加记录；请先恢复跟进")

    content = data.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="任务更新内容不能为空")
    kind = _classify_work_update(content, data.kind)
    existing = (
        db.query(GrowthWorkUpdate)
        .filter(
            GrowthWorkUpdate.user_id == user_id,
            GrowthWorkUpdate.request_id == data.request_id,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.work_item_id != item.id
            or existing.content != content
            or existing.kind != kind
        ):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的任务更新")
        return existing

    assistant_summary, suggestions, star_hints = _work_update_coaching(kind)
    nodes = (
        db.query(GrowthWorkNode)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id == item.id,
            GrowthWorkNode.status != "cancelled",
        )
        .order_by(GrowthWorkNode.priority_order.asc(), GrowthWorkNode.id.asc())
        .all()
    )
    node_suggestions, node_matches = _analyze_node_suggestions(content, nodes)
    update = GrowthWorkUpdate(
        user_id=user_id,
        work_item_id=item.id,
        request_id=data.request_id,
        content=content,
        kind=kind,
        assistant_summary=assistant_summary,
        suggestions=suggestions,
        star_hints=star_hints,
        node_suggestions=node_suggestions,
    )
    db.add(update)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = (
            db.query(GrowthWorkUpdate)
            .filter(
                GrowthWorkUpdate.user_id == user_id,
                GrowthWorkUpdate.request_id == data.request_id,
            )
            .first()
        )
        if (
            winner is None
            or winner.work_item_id != item_id
            or winner.content != content
            or winner.kind != kind
        ):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的任务更新")
        return winner

    evidence_ids: list[int] = []
    for node, confidence, proposed_status, matched_clause in node_matches:
        evidence = GrowthWorkNodeEvidence(
            user_id=user_id,
            node_id=node.id,
            work_update_id=update.id,
            relation_kind=_node_relation_kind(kind, proposed_status),
            evidence_excerpt=matched_clause[:2000],
            analysis_summary=(
                f"本地规则命中已有节点「{node.title}」"
                + (f"，建议状态为 {proposed_status}" if proposed_status else "，未推断新状态")
                + "；需要用户确认。"
            ),
            confidence=confidence,
            status="suggested",
            analysis_mode="rules",
            rule_version=NODE_ANALYSIS_RULE_VERSION,
        )
        db.add(evidence)
        db.flush()
        evidence_ids.append(evidence.id)

    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_update",
        entity_id=update.id,
        action="appended",
        request_id=data.request_id,
        after={
            "work_item_id": item.id,
            "kind": kind,
            "node_suggestion_count": len(node_suggestions),
            "suggested_evidence_ids": evidence_ids,
            "analysis_mode": "rules",
            "rule_version": NODE_ANALYSIS_RULE_VERSION,
        },
    )
    db.commit()
    db.refresh(update)
    return update


def _get_node_source_update(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    source_update_id: int | None,
) -> GrowthWorkUpdate | None:
    if source_update_id is None:
        return None
    update = (
        db.query(GrowthWorkUpdate)
        .filter(
            GrowthWorkUpdate.id == source_update_id,
            GrowthWorkUpdate.user_id == user_id,
            GrowthWorkUpdate.work_item_id == item_id,
        )
        .first()
    )
    if update is None:
        raise HTTPException(status_code=404, detail="节点来源更新不存在")
    return update


def create_growth_work_node(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: GrowthWorkNodeCreate,
) -> GrowthWorkNode:
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
        raise HTTPException(status_code=409, detail="已收起的事项不能新增节点；请先恢复跟进")
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="节点标题不能为空")
    source_update = _get_node_source_update(
        db,
        user_id=user_id,
        item_id=item.id,
        source_update_id=data.source_update_id,
    )
    source = "work_update" if source_update is not None else "manual"
    expected_dependencies = list(dict.fromkeys(data.depends_on_node_keys))
    known_keys = {
        row[0]
        for row in db.query(GrowthWorkNode.node_key).filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id == item.id,
        )
    }
    if any(dependency not in known_keys for dependency in expected_dependencies):
        raise HTTPException(status_code=422, detail="节点依赖必须引用同一事项内的已确认节点")

    existing = (
        db.query(GrowthWorkNode)
        .filter(GrowthWorkNode.user_id == user_id, GrowthWorkNode.request_id == data.request_id)
        .first()
    )
    if existing is not None:
        if (
            existing.work_item_id != item.id
            or existing.title != title
            or existing.priority_order != data.priority_order
            or existing.depends_on_node_keys != expected_dependencies
            or existing.time_hint != data.time_hint
            or existing.source_update_id != data.source_update_id
        ):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的工作节点")
        return existing

    node = GrowthWorkNode(
        user_id=user_id,
        work_item_id=item.id,
        request_id=data.request_id,
        node_key=_node_key(item.id, data.request_id, title),
        title=title,
        status="planned",
        priority_order=data.priority_order,
        depends_on_node_keys=expected_dependencies,
        time_hint=(data.time_hint or "").strip() or None,
        source=source,
        source_update_id=data.source_update_id,
    )
    db.add(node)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthWorkNode).filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.request_id == data.request_id,
        ).first()
        if (
            winner is None
            or winner.work_item_id != item.id
            or winner.title != title
            or winner.priority_order != data.priority_order
            or winner.depends_on_node_keys != expected_dependencies
            or winner.time_hint != ((data.time_hint or "").strip() or None)
            or winner.source_update_id != data.source_update_id
        ):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的工作节点")
        return winner

    evidence_id: int | None = None
    if source_update is not None:
        proposed_status = _proposed_node_status(source_update.content)
        evidence = GrowthWorkNodeEvidence(
            user_id=user_id,
            node_id=node.id,
            work_update_id=source_update.id,
            relation_kind=_node_relation_kind(source_update.kind, proposed_status),
            evidence_excerpt=source_update.content[:2000],
            analysis_summary="用户确认从这条任务更新新建节点。",
            confidence=1.0,
            status="confirmed",
            analysis_mode="rules",
            rule_version=NODE_ANALYSIS_RULE_VERSION,
            confirmed_at=_now(),
        )
        db.add(evidence)
        db.flush()
        evidence_id = evidence.id

    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_node",
        entity_id=node.id,
        action="created",
        request_id=data.request_id,
        after={
            "work_item_id": item.id,
            "status": node.status,
            "source": node.source,
            "source_update_id": node.source_update_id,
            "confirmed_evidence_id": evidence_id,
        },
    )
    db.commit()
    db.refresh(node)
    return node


def update_growth_work_node(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    node_id: int,
    data: GrowthWorkNodeUpdate,
) -> GrowthWorkNode:
    node = (
        db.query(GrowthWorkNode)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkNode.work_item_id)
        .filter(
            GrowthWorkNode.id == node_id,
            GrowthWorkNode.work_item_id == item_id,
            GrowthWorkNode.user_id == user_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if node is None:
        raise HTTPException(status_code=404, detail="工作节点不存在")
    if node.version != data.expected_version:
        raise HTTPException(status_code=409, detail="工作节点已被更新，请刷新后重试")
    if data.status not in NODE_TRANSITIONS[node.status]:
        raise HTTPException(status_code=409, detail=f"工作节点不能从 {node.status} 变更为 {data.status}")

    evidence: GrowthWorkNodeEvidence | None = None
    if data.source_update_id is not None:
        source_update = _get_node_source_update(
            db,
            user_id=user_id,
            item_id=item_id,
            source_update_id=data.source_update_id,
        )
        matching_suggestion = next(
            (
                suggestion
                for suggestion in (source_update.node_suggestions or [])
                if suggestion.get("action") == "update" and suggestion.get("node_id") == node.id
            ),
            None,
        )
        if matching_suggestion is None or matching_suggestion.get("proposed_status") != data.status:
            raise HTTPException(status_code=422, detail="提交的节点状态与这条更新的待确认建议不一致")
        evidence = (
            db.query(GrowthWorkNodeEvidence)
            .filter(
                GrowthWorkNodeEvidence.user_id == user_id,
                GrowthWorkNodeEvidence.node_id == node.id,
                GrowthWorkNodeEvidence.work_update_id == data.source_update_id,
                GrowthWorkNodeEvidence.status == "suggested",
            )
            .with_for_update()
            .first()
        )
        if evidence is None:
            raise HTTPException(status_code=422, detail="这条更新没有该节点的待确认分析证据")

    before = {"status": node.status, "version": node.version}
    node.status = data.status
    node.version += 1
    if data.status == "completed":
        node.completed_at = node.completed_at or _now()
    if evidence is not None:
        evidence.status = "confirmed"
        evidence.confirmed_at = _now()
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_node",
        entity_id=node.id,
        action="status_updated",
        before=before,
        after={
            "status": node.status,
            "version": node.version,
            "source_update_id": data.source_update_id,
            "confirmed_evidence_id": evidence.id if evidence is not None else None,
        },
    )
    db.commit()
    db.refresh(node)
    return node


def growth_workspace(db: Session, *, user_id: int) -> GrowthWorkspaceResponse:
    active_items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status.in_(ACTIVE_STATUSES),
        )
        .order_by(GrowthWorkItem.priority_order.asc(), GrowthWorkItem.updated_at.desc())
        .limit(100)
        .all()
    )
    cancelled_items = (
        db.query(GrowthWorkItem)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
            GrowthWorkItem.status == "cancelled",
        )
        .order_by(GrowthWorkItem.updated_at.desc(), GrowthWorkItem.id.desc())
        .limit(100)
        .all()
    )
    work_nodes = (
        db.query(GrowthWorkNode)
        .join(GrowthWorkItem, GrowthWorkItem.id == GrowthWorkNode.work_item_id)
        .filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.deleted_at.is_(None),
        )
        .order_by(GrowthWorkNode.work_item_id.asc(), GrowthWorkNode.priority_order.asc(), GrowthWorkNode.id.asc())
        .limit(500)
        .all()
    )
    node_evidence = (
        db.query(GrowthWorkNodeEvidence)
        .filter(GrowthWorkNodeEvidence.user_id == user_id)
        .order_by(GrowthWorkNodeEvidence.created_at.desc(), GrowthWorkNodeEvidence.id.desc())
        .limit(500)
        .all()
    )
    task_updates = (
        db.query(GrowthWorkUpdate)
        .filter(GrowthWorkUpdate.user_id == user_id)
        .order_by(GrowthWorkUpdate.created_at.desc(), GrowthWorkUpdate.id.desc())
        .limit(500)
        .all()
    )
    event_candidates = (
        db.query(GrowthWorkEvent)
        .filter(
            GrowthWorkEvent.user_id == user_id,
            GrowthWorkEvent.status.in_(("captured", "structured", "needs_more_evidence")),
        )
        .order_by(GrowthWorkEvent.updated_at.desc(), GrowthWorkEvent.id.desc())
        .limit(50)
        .all()
    )
    confirmed_events = (
        db.query(GrowthWorkEvent)
        .filter(
            GrowthWorkEvent.user_id == user_id,
            GrowthWorkEvent.status == "confirmed",
            GrowthWorkEvent.reportable.is_(True),
            GrowthWorkEvent.visibility.in_(("reportable", "career_asset")),
        )
        .order_by(GrowthWorkEvent.occurred_on.desc(), GrowthWorkEvent.id.desc())
        .limit(100)
        .all()
    )
    reports = (
        db.query(GrowthWeeklyReport)
        .filter(GrowthWeeklyReport.user_id == user_id, GrowthWeeklyReport.status != "archived")
        .order_by(GrowthWeeklyReport.week_start.desc(), GrowthWeeklyReport.version.desc())
        .limit(12)
        .all()
    )
    emotion_notes = (
        db.query(GrowthEmotionNote)
        .filter(GrowthEmotionNote.user_id == user_id, GrowthEmotionNote.deleted_at.is_(None))
        .order_by(GrowthEmotionNote.created_at.desc(), GrowthEmotionNote.id.desc())
        .limit(50)
        .all()
    )
    communication_rows = (
        db.query(GrowthCommunicationDraft)
        .filter(
            GrowthCommunicationDraft.user_id == user_id,
            GrowthCommunicationDraft.status != "superseded",
        )
        .order_by(GrowthCommunicationDraft.created_at.desc(), GrowthCommunicationDraft.id.desc())
        .limit(50)
        .all()
    )
    task_communications = [
        item
        for item in communication_rows
        if any(
            isinstance(ref, dict) and ref.get("source_type") == "work_item"
            for ref in (item.source_refs or [])
        )
    ][:20]
    active_item_ids = {item.id for item in active_items}
    blocked_item_ids = {item.id for item in active_items if item.status == "blocked"}
    blocked_item_ids.update(
        node.work_item_id
        for node in work_nodes
        if node.work_item_id in active_item_ids and node.status == "blocked"
    )
    attention_count = len(blocked_item_ids) + len(event_candidates)
    if active_items:
        summary = f"{len(active_items)} 项当下工作正在推进，{attention_count} 项需要你处理。"
    elif event_candidates:
        summary = f"当前没有进行中的工作，仍有 {len(event_candidates)} 条工作事件待确认。"
    else:
        summary = "记录当下工作，先由系统整理候选，再由你确认需要跟进的任务。"
    return GrowthWorkspaceResponse(
        active_items=active_items,
        cancelled_items=cancelled_items,
        work_nodes=work_nodes,
        node_evidence=node_evidence,
        task_updates=task_updates,
        recent_event_candidates=event_candidates,
        confirmed_reportable_events=confirmed_events,
        recent_reports=reports,
        private_emotion_notes=emotion_notes,
        task_communications=task_communications,
        summary=summary,
        attention_count=attention_count,
    )


def delete_growth_emotion_note(db: Session, *, user_id: int, note_id: int) -> None:
    note = (
        db.query(GrowthEmotionNote)
        .filter(
            GrowthEmotionNote.id == note_id,
            GrowthEmotionNote.user_id == user_id,
            GrowthEmotionNote.deleted_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if note is None:
        raise HTTPException(status_code=404, detail="私人情绪记录不存在")
    note.deleted_at = _now()
    note.encrypted_content = _fernet().encrypt(b"deleted").decode("ascii")
    note.deidentified_fact = None
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_emotion_note",
        entity_id=note.id,
        action="deleted",
        after={"deleted": True},
    )
    db.commit()


def delete_cancelled_growth_work_item(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    expected_version: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    owner = db.query(User).filter(User.id == user_id).with_for_update().first()
    if owner is None:
        raise HTTPException(status_code=404, detail="用户不存在")
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
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="工作项已被更新，请刷新后重试")
    if item.status != "cancelled":
        raise HTTPException(status_code=409, detail="只有已收起的事项才能删除")

    node_ids = [
        value.id
        for value in db.query(GrowthWorkNode.id).filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.work_item_id == item.id,
        ).all()
    ]
    update_ids = [
        value.id
        for value in db.query(GrowthWorkUpdate.id).filter(
            GrowthWorkUpdate.user_id == user_id,
            GrowthWorkUpdate.work_item_id == item.id,
        ).all()
    ]
    event_ids = [
        value.id
        for value in db.query(GrowthWorkEvent.id).filter(
            GrowthWorkEvent.user_id == user_id,
            GrowthWorkEvent.work_item_id == item.id,
        ).all()
    ]
    if event_ids:
        raise HTTPException(
            status_code=409,
            detail="该事项已经形成独立工作成果，不能从收起区直接删除；请先处理关联成果",
        )
    owner.business_data_epoch += 1
    evidence_count = 0
    if node_ids or update_ids:
        evidence_query = db.query(GrowthWorkNodeEvidence).filter(
            GrowthWorkNodeEvidence.user_id == user_id,
        )
        evidence_filters = []
        if node_ids:
            evidence_filters.append(GrowthWorkNodeEvidence.node_id.in_(node_ids))
        if update_ids:
            evidence_filters.append(GrowthWorkNodeEvidence.work_update_id.in_(update_ids))
        evidence_count = evidence_query.filter(or_(*evidence_filters)).delete(synchronize_session=False)

    communication_rows = (
        db.query(GrowthCommunicationDraft)
        .filter(GrowthCommunicationDraft.user_id == user_id)
        .with_for_update()
        .all()
    )
    communication_ids = [
        draft.id
        for draft in communication_rows
        if any(
            isinstance(ref, dict)
            and ref.get("source_type") == "work_item"
            and ref.get("source_id") == item.id
            for ref in (draft.source_refs or [])
        )
    ]
    if communication_ids:
        db.query(GrowthCommunicationDraft).filter(
            GrowthCommunicationDraft.user_id == user_id,
            GrowthCommunicationDraft.id.in_(communication_ids),
        ).delete(synchronize_session=False)

    inquiry_rows = (
        db.query(GrowthInquiry)
        .filter(GrowthInquiry.user_id == user_id)
        .with_for_update()
        .all()
    )
    inquiry_ids = [
        inquiry.id
        for inquiry in inquiry_rows
        if any(
            isinstance(ref, dict)
            and ref.get("source_type") in {"工作项", "work_item"}
            and ref.get("source_id") == item.id
            for ref in (inquiry.evidence_refs or [])
        )
    ]
    if inquiry_ids:
        db.query(GrowthInquiry).filter(
            GrowthInquiry.user_id == user_id,
            GrowthInquiry.id.in_(inquiry_ids),
        ).delete(synchronize_session=False)
    if node_ids:
        db.query(GrowthWorkNode).filter(
            GrowthWorkNode.user_id == user_id,
            GrowthWorkNode.id.in_(node_ids),
        ).delete(synchronize_session=False)
    if update_ids:
        db.query(GrowthWorkUpdate).filter(
            GrowthWorkUpdate.user_id == user_id,
            GrowthWorkUpdate.id.in_(update_ids),
        ).delete(synchronize_session=False)

    intake = (
        db.query(GrowthWorkIntake)
        .filter(GrowthWorkIntake.id == item.intake_id, GrowthWorkIntake.user_id == user_id)
        .with_for_update()
        .first()
    )
    if intake is not None and isinstance(intake.candidate_payload, dict):
        payload = dict(intake.candidate_payload)
        sibling_exists = db.query(GrowthWorkItem.id).filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.intake_id == item.intake_id,
            GrowthWorkItem.id != item.id,
            GrowthWorkItem.deleted_at.is_(None),
        ).first() is not None
        if sibling_exists:
            payload["candidates"] = [
                candidate
                for candidate in payload.get("candidates", [])
                if not isinstance(candidate, dict) or candidate.get("candidate_key") != item.candidate_key
            ]
        else:
            payload["candidates"] = []
            payload["emotion"] = {}
        intake.candidate_payload = payload

    before = {
        "status": item.status,
        "version": item.version,
        "node_count": len(node_ids),
        "update_count": len(update_ids),
        "evidence_count": evidence_count,
        "communication_count": len(communication_ids),
        "inquiry_count": len(inquiry_ids),
        "event_count": len(event_ids),
    }
    item.title = "已删除事项"
    item.candidate_key = f"deleted:{item.id}"
    item.description = None
    item.fact_excerpt = None
    item.selection_reason = None
    item.resource_links = []
    item.open_questions = []
    item.tracking_rule = None
    item.due_at = None
    item.progress_summary = None
    item.blocker_note = None
    item.next_action = None
    item.result_summary = None
    item.reportable = False
    item.impact_level = "unknown"
    item.energy_level = "unknown"
    item.career_event_id = None
    item.deleted_at = _now()
    item.version += 1
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_item",
        entity_id=item.id,
        action="deleted",
        request_id=request_id,
        before=before,
        after={"deleted": True, "content_scrubbed": True},
    )
    db.commit()
    return {
        "ok": True,
        "deleted_item_id": item_id,
        "deleted_node_count": len(node_ids),
        "deleted_update_count": len(update_ids),
        "deleted_evidence_count": evidence_count,
        "deleted_communication_count": len(communication_ids),
        "deleted_inquiry_count": len(inquiry_ids),
        "deleted_event_count": len(event_ids),
    }


def cleanup_cancelled_growth_work_items(
    db: Session,
    *,
    user_id: int,
    request_id: str,
) -> dict[str, Any]:
    """Delete every currently cancelled item through the audited single-item path.

    Items that have become protected or changed while the batch is running are
    deliberately retained and reported instead of aborting the rest of the
    cleanup.
    """
    rows = (
        db.query(GrowthWorkItem.id, GrowthWorkItem.title, GrowthWorkItem.version)
        .filter(
            GrowthWorkItem.user_id == user_id,
            GrowthWorkItem.status == "cancelled",
            GrowthWorkItem.deleted_at.is_(None),
        )
        .order_by(GrowthWorkItem.id.asc())
        .all()
    )
    deleted_count = 0
    skipped: list[dict[str, Any]] = []
    for item_id, title, version in rows:
        try:
            delete_cancelled_growth_work_item(
                db,
                user_id=user_id,
                item_id=item_id,
                expected_version=version,
                request_id=request_id,
            )
            deleted_count += 1
        except HTTPException as exc:
            db.rollback()
            detail = exc.detail
            if isinstance(detail, dict):
                reason = str(detail.get("message") or detail.get("detail") or "该事项当前不能清理")
            else:
                reason = str(detail)
            skipped.append({"id": item_id, "title": title, "reason": reason})
    return {
        "ok": True,
        "deleted_count": deleted_count,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def update_growth_work_item(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    data: GrowthUpdateWorkItemRequest,
) -> GrowthUpdateWorkItemResponse:
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
        raise HTTPException(status_code=409, detail="工作项已被更新，请刷新后重试")
    if data.status not in WORK_TRANSITIONS[item.status]:
        raise HTTPException(status_code=409, detail=f"工作项不能从 {item.status} 变更为 {data.status}")

    before = {
        "status": item.status,
        "version": item.version,
        "reportable": item.reportable,
        "has_result": bool(item.result_summary),
        "has_progress": bool(item.progress_summary),
        "has_blocker": bool(item.blocker_note),
        "has_next_action": bool(item.next_action),
    }
    item.status = data.status
    if data.result_summary is not None:
        item.result_summary = data.result_summary.strip() or None
    for field in ("progress_summary", "blocker_note", "next_action"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value.strip() or None)
    if data.reportable is not None:
        item.reportable = data.reportable
    if data.status == "completed":
        item.completed_at = item.completed_at or _now()
    if data.status == "blocked" and not item.blocker_note:
        raise HTTPException(status_code=422, detail="记录阻塞时必须说明当前卡点")
    item.version += 1

    event = (
        db.query(GrowthWorkEvent)
        .filter(GrowthWorkEvent.work_item_id == item.id, GrowthWorkEvent.user_id == user_id)
        .with_for_update()
        .first()
    )
    if data.status == "completed" and event is None:
        gaps = [
            field
            for field, value in (
                ("situation", None),
                ("action", None),
                ("result", item.result_summary),
                ("role", None),
            )
            if not value
        ]
        event = GrowthWorkEvent(
            user_id=user_id,
            work_item_id=item.id,
            situation=None,
            task=item.title,
            action=None,
            result=item.result_summary,
            role=None,
            occurred_on=(item.completed_at or _now()).date(),
            status="structured",
            visibility="reportable" if item.reportable else "private",
            reportable=item.reportable,
            evidence_gaps=gaps,
        )
        db.add(event)
    elif data.status == "completed" and event.status in {"captured", "structured", "needs_more_evidence"}:
        event.result = item.result_summary
        event.visibility = "reportable" if item.reportable else "private"
        event.reportable = item.reportable
        event.evidence_gaps = [
            field for field in ("situation", "action", "result", "role") if not getattr(event, field)
        ]
    db.flush()
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_item",
        entity_id=item.id,
        action="updated",
        before=before,
        after={
            "status": item.status,
            "version": item.version,
            "reportable": item.reportable,
            "has_result": bool(item.result_summary),
            "has_progress": bool(item.progress_summary),
            "has_blocker": bool(item.blocker_note),
            "has_next_action": bool(item.next_action),
            "event_candidate_id": event.id if event is not None else None,
        },
    )
    db.commit()
    db.refresh(item)
    if event is not None:
        db.refresh(event)
    return GrowthUpdateWorkItemResponse(work_item=item, event_candidate=event)


def update_growth_work_event(
    db: Session,
    *,
    user_id: int,
    event_id: int,
    data: GrowthUpdateWorkEventRequest,
) -> GrowthWorkEvent:
    event = (
        db.query(GrowthWorkEvent)
        .filter(GrowthWorkEvent.id == event_id, GrowthWorkEvent.user_id == user_id)
        .with_for_update()
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="成长工作事件不存在")
    if event.version != data.expected_version:
        raise HTTPException(status_code=409, detail="工作事件已被更新，请刷新后重试")
    if data.status not in EVENT_TRANSITIONS[event.status]:
        raise HTTPException(status_code=409, detail=f"工作事件不能从 {event.status} 变更为 {data.status}")

    before = {"status": event.status, "version": event.version, "evidence_gaps": event.evidence_gaps}
    for field in ("situation", "task", "action", "result", "role", "visibility", "reportable"):
        value = getattr(data, field)
        if value is not None:
            setattr(event, field, value.strip() if isinstance(value, str) else value)
    if not event.task.strip():
        raise HTTPException(status_code=422, detail="工作事件必须保留任务描述")
    gaps = [field for field in ("situation", "action", "result", "role") if not getattr(event, field)]
    event.evidence_gaps = gaps
    event.status = data.status
    event.confirmed_at = _now() if data.status == "confirmed" else event.confirmed_at
    event.archived_at = _now() if data.status == "archived" else event.archived_at
    if data.status == "confirmed" and event.visibility == "private":
        event.reportable = False
    event.version += 1
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_work_event",
        entity_id=event.id,
        action=data.status,
        before=before,
        after={
            "status": event.status,
            "version": event.version,
            "visibility": event.visibility,
            "reportable": event.reportable,
            "evidence_gaps": event.evidence_gaps,
        },
    )
    db.commit()
    db.refresh(event)
    return event


def _report_content(week_start: date, events: list[GrowthWorkEvent]) -> str:
    lines = [f"# {week_start.isoformat()} 周工作回顾", "", "## 已确认的工作成果", ""]
    for index, event in enumerate(events, start=1):
        lines.append(f"{index}. {event.task}")
        if event.result:
            lines.append(f"   - 结果：{event.result}")
        if event.action:
            lines.append(f"   - 行动：{event.action}")
        if event.role:
            lines.append(f"   - 我的角色：{event.role}")
    lines.extend(["", "以上内容仅来自本人确认且标记为可进入周报的工作事件。"])
    return "\n".join(lines)


def create_growth_weekly_report(
    db: Session,
    *,
    user_id: int,
    data: GrowthWeeklyReportCreate,
) -> GrowthWeeklyReport:
    week_end = data.week_start + timedelta(days=6)
    events = (
        db.query(GrowthWorkEvent)
        .filter(
            GrowthWorkEvent.user_id == user_id,
            GrowthWorkEvent.id.in_(data.event_ids),
            GrowthWorkEvent.status == "confirmed",
            GrowthWorkEvent.reportable.is_(True),
            GrowthWorkEvent.visibility.in_(("reportable", "career_asset")),
            GrowthWorkEvent.occurred_on >= data.week_start,
            GrowthWorkEvent.occurred_on <= week_end,
        )
        .order_by(GrowthWorkEvent.occurred_on.asc(), GrowthWorkEvent.id.asc())
        .all()
    )
    if {event.id for event in events} != set(data.event_ids):
        raise HTTPException(status_code=422, detail="周报只能引用本人已确认且明确标记为可汇报的工作事件")
    latest = (
        db.query(GrowthWeeklyReport)
        .filter(GrowthWeeklyReport.user_id == user_id, GrowthWeeklyReport.week_start == data.week_start)
        .order_by(GrowthWeeklyReport.version.desc())
        .with_for_update()
        .first()
    )
    report = GrowthWeeklyReport(
        user_id=user_id,
        week_start=data.week_start,
        version=(latest.version + 1) if latest else 1,
        status="draft",
        included_event_ids=[event.id for event in events],
        generated_content=_report_content(data.week_start, events),
    )
    db.add(report)
    db.flush()
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_weekly_report",
        entity_id=report.id,
        action="created",
        after={"week_start": data.week_start.isoformat(), "version": report.version, "event_ids": report.included_event_ids},
    )
    db.commit()
    db.refresh(report)
    return report


def update_growth_weekly_report(
    db: Session,
    *,
    user_id: int,
    report_id: int,
    data: GrowthWeeklyReportUpdate,
) -> GrowthWeeklyReport:
    report = (
        db.query(GrowthWeeklyReport)
        .filter(GrowthWeeklyReport.id == report_id, GrowthWeeklyReport.user_id == user_id)
        .with_for_update()
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="成长周报不存在")
    if report.version != data.expected_version:
        raise HTTPException(status_code=409, detail="周报版本不匹配，请刷新后重试")
    allowed = {
        "draft": {"draft", "reviewed", "archived"},
        "reviewed": {"reviewed", "exported", "archived"},
        "exported": {"exported", "archived"},
        "archived": {"archived"},
    }
    if data.status not in allowed[report.status]:
        raise HTTPException(status_code=409, detail=f"周报不能从 {report.status} 变更为 {data.status}")
    before = {"status": report.status, "has_edit": bool(report.edited_content)}
    if data.edited_content is not None:
        report.edited_content = data.edited_content.strip() or None
    report.status = data.status
    report.reviewed_at = _now() if data.status == "reviewed" else report.reviewed_at
    report.exported_at = _now() if data.status == "exported" else report.exported_at
    _audit(
        db,
        user_id=user_id,
        entity_type="growth_weekly_report",
        entity_id=report.id,
        action=data.status,
        before=before,
        after={"status": report.status, "has_edit": bool(report.edited_content)},
    )
    db.commit()
    db.refresh(report)
    return report
