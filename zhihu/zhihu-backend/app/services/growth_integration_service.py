from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.growth import (
    GrowthAuditEvent,
    GrowthCommunicationDraft,
    GrowthEvidenceItem,
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthHandoff,
    GrowthMarketSignal,
    GrowthMilestone,
    GrowthPortfolioItem,
    GrowthReflection,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
    GrowthWeeklyReport,
    GrowthWorkEvent,
    GrowthWorkItem,
)
from app.models.user import User
from app.schemas.growth_integration import (
    CommunicationDraftCreate,
    CommunicationDraftRevise,
    GrowthFullExport,
    GrowthIntegrationWorkspace,
    HandoffCreate,
)


SOURCE_SCOPE_LABELS = {
    "work_event": "已确认工作事件",
    "portfolio": "已确认作品",
    "evidence": "已确认成长证据",
    "skill": "已确认能力事实",
    "target": "已确认未来目标",
    "gap": "已确认差距快照",
    "milestone": "已确认里程碑",
}
TARGET_LABELS = {
    "opportunity": "机会守护",
    "decision": "决策守护",
    "rights": "权益守护",
    "income": "收支守护",
    "resume": "简历候选区",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fingerprint(data: Any, *, exclude: set[str] | None = None) -> str:
    payload = data.model_dump(mode="json", exclude=exclude or {"request_id"})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    db.add(GrowthAuditEvent(
        user_id=user_id,
        actor_user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        request_id=request_id,
        before_payload=before,
        after_payload=after,
    ))


def _source_snapshot(db: Session, *, user_id: int, source_type: str, source_id: int) -> dict[str, Any]:
    if source_type == "work_event":
        item = db.query(GrowthWorkEvent).filter(GrowthWorkEvent.id == source_id, GrowthWorkEvent.user_id == user_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长工作事件不存在")
        if item.status not in {"confirmed", "archived"}:
            raise HTTPException(status_code=422, detail="只能引用本人已确认的工作事件")
        return {
            "title": item.task,
            "summary": item.result or "结果尚未量化",
            "evidence_refs": [{"source_type": source_type, "source_id": item.id, "occurred_on": item.occurred_on.isoformat()}],
        }
    if source_type == "portfolio":
        item = db.query(GrowthPortfolioItem).filter(
            GrowthPortfolioItem.id == source_id,
            GrowthPortfolioItem.user_id == user_id,
            GrowthPortfolioItem.deleted_at.is_(None),
        ).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长作品不存在")
        if item.status != "active":
            raise HTTPException(status_code=422, detail="只能引用本人已确认且可用的作品")
        return {
            "title": item.title,
            "summary": item.summary or "作品摘要尚未补充",
            "evidence_refs": [{"source_type": source_type, "source_id": item.id, "source_label": item.source_label}],
        }
    if source_type == "evidence":
        item = db.query(GrowthEvidenceItem).filter(
            GrowthEvidenceItem.id == source_id,
            GrowthEvidenceItem.user_id == user_id,
            GrowthEvidenceItem.deleted_at.is_(None),
        ).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长证据不存在")
        if item.status != "confirmed":
            raise HTTPException(status_code=422, detail="只能引用本人已确认且可用的成长证据")
        return {
            "title": item.title,
            "summary": item.summary,
            "evidence_refs": [{"source_type": source_type, "source_id": item.id, "source_label": item.source_label}],
        }
    if source_type == "skill":
        item = db.query(GrowthSkillAssessment).filter(
            GrowthSkillAssessment.id == source_id,
            GrowthSkillAssessment.user_id == user_id,
        ).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长能力不存在")
        if item.status != "confirmed":
            raise HTTPException(status_code=422, detail="只能引用本人已确认的能力")
        evidence_ids = [row.evidence_id for row in db.query(GrowthSkillEvidenceLink).filter(GrowthSkillEvidenceLink.assessment_id == item.id).all()]
        summary = f"能力层级：{item.source_layer}；证据充分度：{item.evidence_sufficiency}。"
        if not evidence_ids:
            summary += "当前仍缺少已关联证据，不应作为独立能力证明。"
        return {
            "title": item.skill_name,
            "summary": summary,
            "evidence_refs": [{"source_type": "evidence", "source_id": value} for value in evidence_ids],
        }
    if source_type == "target":
        item = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.id == source_id, GrowthFutureTarget.user_id == user_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail="未来目标不存在")
        if item.status not in {"active", "paused", "completed"}:
            raise HTTPException(status_code=422, detail="只能引用本人已确认的未来目标")
        return {
            "title": item.title,
            "summary": item.description or "目标细节尚未补充",
            "evidence_refs": [{"source_type": source_type, "source_id": item.id, "source_label": item.source_label}],
        }
    if source_type == "gap":
        item = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.id == source_id, GrowthGapSnapshot.user_id == user_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail="差距快照不存在")
        if item.status != "confirmed":
            raise HTTPException(status_code=422, detail="只能引用本人已确认的差距快照")
        summary = "；".join(item.gap_items or []) or "尚未核清确定差距"
        if item.unknown_items:
            summary += f"。仍待核清：{'；'.join(item.unknown_items)}"
        return {
            "title": "已确认成长差距",
            "summary": summary,
            "evidence_refs": list(item.career_chip_refs or []),
        }
    if source_type == "milestone":
        item = db.query(GrowthMilestone).filter(GrowthMilestone.id == source_id, GrowthMilestone.user_id == user_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail="成长里程碑不存在")
        if item.status not in {"confirmed", "in_progress", "completed"}:
            raise HTTPException(status_code=422, detail="只能引用本人已确认的里程碑")
        return {
            "title": item.title,
            "summary": item.success_criteria,
            "evidence_refs": [{"source_type": source_type, "source_id": item.id, "due_on": item.due_on.isoformat() if item.due_on else None}],
        }
    raise HTTPException(status_code=422, detail="不支持的成长来源类型")


def _communication_content(data: CommunicationDraftCreate) -> tuple[list[str], list[str], list[str], str]:
    fact_questions = [
        "这些事实中哪些有原始记录或可回溯证据？",
        "对方需要在什么时间前给出什么明确回应？",
    ]
    strategies = [
        "先给结论和目标，再按时间顺序陈述已知事实。",
        "说明事实造成的影响，最后提出一个可执行、可确认的请求。",
        "把尚未核实的判断改成问题，不替对方补充动机。",
    ]
    risk_notes = ["本草稿不会自动发送，导出前请逐条核对事实、对象和承诺。"]
    if any(token in data.scene for token in ("劳动", "争议", "仲裁", "离职", "薪资", "合同")):
        risk_notes.append("可能涉及劳动权益或争议，请保留原始证据；必要时转到权益守护核对。")
    facts = "\n".join(f"- {item.strip()}" for item in data.known_facts)
    content = (
        f"结论/目标：{data.goal.strip()}\n\n"
        f"已知事实：\n{facts}\n\n"
        "影响：请补充这些事实对进度、质量、成本或协作造成的可验证影响。\n\n"
        f"建议诉求：请 {data.audience.strip()} 围绕上述目标给出明确反馈或下一步安排。\n\n"
        f"语气：{data.tone.strip()}。尚未核实的判断不要写成事实。"
    )
    return fact_questions, strategies, risk_notes, content


def create_communication_draft(db: Session, *, user_id: int, data: CommunicationDraftCreate) -> GrowthCommunicationDraft:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthCommunicationDraft).filter(
        GrowthCommunicationDraft.user_id == user_id,
        GrowthCommunicationDraft.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的沟通草稿")
        return existing
    snapshots = [
        _source_snapshot(db, user_id=user_id, source_type=ref.source_type, source_id=ref.source_id)
        for ref in data.source_refs
    ]
    fact_questions, strategies, risk_notes, content = _communication_content(data)
    source_refs = [ref.model_dump(mode="json") for ref in data.source_refs]
    data_scope = list(dict.fromkeys(SOURCE_SCOPE_LABELS[ref.source_type] for ref in data.source_refs))
    if not data_scope:
        data_scope = ["本次手工输入的已知事实"]
    if snapshots:
        fact_questions.append("引用的成长记录是否适合向当前沟通对象披露？")
    key_seed = f"{user_id}|{data.audience.strip()}|{data.scene.strip()}|{data.goal.strip()}"
    item = GrowthCommunicationDraft(
        user_id=user_id,
        request_id=data.request_id,
        input_fingerprint=fingerprint,
        draft_key=hashlib.sha256(key_seed.encode("utf-8")).hexdigest()[:40],
        audience=data.audience.strip(),
        scene=data.scene.strip(),
        goal=data.goal.strip(),
        known_facts=[item.strip() for item in data.known_facts],
        tone=data.tone.strip(),
        fact_questions=fact_questions,
        strategies=strategies,
        risk_notes=risk_notes,
        source_refs=source_refs,
        data_scope=data_scope,
        generated_content=content,
        analysis_mode="rules",
        status="draft",
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthCommunicationDraft).filter(
            GrowthCommunicationDraft.user_id == user_id,
            GrowthCommunicationDraft.request_id == data.request_id,
        ).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的沟通草稿")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_communication_draft", entity_id=item.id, action="created", request_id=data.request_id, after={"status": "draft", "analysis_mode": "rules", "data_scope": data_scope})
    db.commit()
    db.refresh(item)
    return item


def revise_communication_draft(db: Session, *, user_id: int, draft_id: int, data: CommunicationDraftRevise) -> GrowthCommunicationDraft:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthCommunicationDraft).filter(
        GrowthCommunicationDraft.user_id == user_id,
        GrowthCommunicationDraft.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint or existing.supersedes_draft_id != draft_id:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的沟通草稿修订")
        return existing
    current = db.query(GrowthCommunicationDraft).filter(
        GrowthCommunicationDraft.id == draft_id,
        GrowthCommunicationDraft.user_id == user_id,
    ).with_for_update().first()
    if current is None:
        raise HTTPException(status_code=404, detail="沟通草稿不存在")
    if current.status == "superseded" or current.version != data.expected_version:
        raise HTTPException(status_code=409, detail="沟通草稿已更新，请刷新后重试")
    allowed = {
        "draft": {"draft", "reviewed", "archived"},
        "reviewed": {"reviewed", "exported", "archived"},
        "exported": {"exported", "archived"},
        "archived": {"archived"},
    }
    if data.status not in allowed[current.status]:
        raise HTTPException(status_code=409, detail=f"沟通草稿不能从 {current.status} 变更为 {data.status}")
    current.status = "superseded"
    successor = GrowthCommunicationDraft(
        user_id=user_id,
        supersedes_draft_id=current.id,
        request_id=data.request_id,
        input_fingerprint=fingerprint,
        draft_key=current.draft_key,
        version=current.version + 1,
        audience=current.audience,
        scene=current.scene,
        goal=current.goal,
        known_facts=current.known_facts,
        tone=current.tone,
        fact_questions=current.fact_questions,
        strategies=current.strategies,
        risk_notes=current.risk_notes,
        source_refs=current.source_refs,
        data_scope=current.data_scope,
        generated_content=current.generated_content,
        edited_content=data.edited_content.strip(),
        analysis_mode=current.analysis_mode,
        provider_name=current.provider_name,
        model=current.model,
        status=data.status,
        reviewed_at=_now() if data.status in {"reviewed", "exported"} else current.reviewed_at,
        exported_at=_now() if data.status == "exported" else None,
    )
    db.add(successor)
    db.flush()
    _audit(db, user_id=user_id, entity_type="growth_communication_draft", entity_id=successor.id, action="revised", request_id=data.request_id, before={"draft_id": current.id, "version": current.version}, after={"status": successor.status, "version": successor.version, "sent": False})
    db.commit()
    db.refresh(successor)
    return successor


def create_handoff(db: Session, *, user_id: int, data: HandoffCreate) -> GrowthHandoff:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthHandoff).filter(GrowthHandoff.user_id == user_id, GrowthHandoff.request_id == data.request_id).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的跨守护提案")
        return existing
    snapshot = _source_snapshot(db, user_id=user_id, source_type=data.source_type, source_id=data.source_id)
    target_label = TARGET_LABELS[data.target_domain]
    item = GrowthHandoff(
        user_id=user_id,
        request_id=data.request_id,
        input_fingerprint=fingerprint,
        target_domain=data.target_domain,
        source_type=data.source_type,
        source_id=data.source_id,
        title=snapshot["title"][:300],
        content_summary=snapshot["summary"],
        evidence_refs=snapshot["evidence_refs"],
        impact_summary=f"确认后写入{target_label}的成长交接收件箱；不会自动修改正式结论、简历或账本，可随时撤销。",
        status="proposed",
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthHandoff).filter(GrowthHandoff.user_id == user_id, GrowthHandoff.request_id == data.request_id).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的跨守护提案")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_handoff", entity_id=item.id, action="proposed", request_id=data.request_id, after={"target_domain": item.target_domain, "source_type": item.source_type, "source_id": item.source_id})
    db.commit()
    db.refresh(item)
    return item


def confirm_handoff(db: Session, *, user_id: int, handoff_id: int, expected_version: int) -> GrowthHandoff:
    item = db.query(GrowthHandoff).filter(GrowthHandoff.id == handoff_id, GrowthHandoff.user_id == user_id).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="跨守护提案不存在")
    if item.status == "confirmed" and item.version == expected_version + 1:
        return item
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="跨守护提案已变化，请刷新后重试")
    if item.status != "proposed":
        raise HTTPException(status_code=409, detail="只有待确认提案可以写入目标域")
    # Re-check the current source at the confirmation gate. A deleted or
    # downgraded source must not enter another guardian on a stale snapshot.
    _source_snapshot(db, user_id=user_id, source_type=item.source_type, source_id=item.source_id)
    item.status = "confirmed"
    item.version += 1
    item.confirmed_at = _now()
    _audit(db, user_id=user_id, entity_type="growth_handoff", entity_id=item.id, action="confirmed", after={"target_domain": item.target_domain, "version": item.version, "target_store": "growth_handoff_inbox"})
    db.commit()
    db.refresh(item)
    return item


def revoke_handoff(db: Session, *, user_id: int, handoff_id: int, expected_version: int) -> GrowthHandoff:
    item = db.query(GrowthHandoff).filter(GrowthHandoff.id == handoff_id, GrowthHandoff.user_id == user_id).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="跨守护交接不存在")
    if item.status == "revoked" and item.version == expected_version + 1:
        return item
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="跨守护交接已变化，请刷新后重试")
    if item.status != "confirmed":
        raise HTTPException(status_code=409, detail="只有已确认交接可以撤销")
    item.status = "revoked"
    item.version += 1
    item.revoked_at = _now()
    _audit(db, user_id=user_id, entity_type="growth_handoff", entity_id=item.id, action="revoked", after={"target_domain": item.target_domain, "version": item.version, "target_store": "growth_handoff_inbox"})
    db.commit()
    db.refresh(item)
    return item


def integration_workspace(db: Session, *, user_id: int) -> GrowthIntegrationWorkspace:
    drafts = db.query(GrowthCommunicationDraft).filter(
        GrowthCommunicationDraft.user_id == user_id,
        GrowthCommunicationDraft.status != "superseded",
    ).order_by(GrowthCommunicationDraft.created_at.desc(), GrowthCommunicationDraft.id.desc()).limit(20).all()
    handoffs = db.query(GrowthHandoff).filter(GrowthHandoff.user_id == user_id).order_by(GrowthHandoff.updated_at.desc(), GrowthHandoff.id.desc()).limit(50).all()
    inbox = [item for item in handoffs if item.status == "confirmed"]
    sources: list[dict[str, Any]] = []
    for item in db.query(GrowthWorkEvent).filter(GrowthWorkEvent.user_id == user_id, GrowthWorkEvent.status.in_(("confirmed", "archived"))).order_by(GrowthWorkEvent.occurred_on.desc()).limit(30).all():
        sources.append({"source_type": "work_event", "source_id": item.id, "title": item.task, "source_label": "已确认工作事件"})
    for item in db.query(GrowthPortfolioItem).filter(GrowthPortfolioItem.user_id == user_id, GrowthPortfolioItem.deleted_at.is_(None), GrowthPortfolioItem.status == "active").order_by(GrowthPortfolioItem.created_at.desc()).limit(30).all():
        sources.append({"source_type": "portfolio", "source_id": item.id, "title": item.title, "source_label": "已确认作品"})
    for item in db.query(GrowthEvidenceItem).filter(GrowthEvidenceItem.user_id == user_id, GrowthEvidenceItem.deleted_at.is_(None), GrowthEvidenceItem.status == "confirmed").order_by(GrowthEvidenceItem.created_at.desc()).limit(30).all():
        sources.append({"source_type": "evidence", "source_id": item.id, "title": item.title, "source_label": "已确认成长证据"})
    for item in db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id, GrowthSkillAssessment.status == "confirmed").order_by(GrowthSkillAssessment.created_at.desc()).limit(30).all():
        sources.append({"source_type": "skill", "source_id": item.id, "title": item.skill_name, "source_label": "已确认能力事实"})
    for item in db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.status.in_(("active", "paused", "completed"))).order_by(GrowthFutureTarget.created_at.desc()).limit(20).all():
        sources.append({"source_type": "target", "source_id": item.id, "title": item.title, "source_label": "已确认未来目标"})
    for item in db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.status == "confirmed").order_by(GrowthGapSnapshot.created_at.desc()).limit(20).all():
        sources.append({"source_type": "gap", "source_id": item.id, "title": "已确认成长差距", "source_label": "已确认差距快照"})
    for item in db.query(GrowthMilestone).filter(GrowthMilestone.user_id == user_id, GrowthMilestone.status.in_(("confirmed", "in_progress", "completed"))).order_by(GrowthMilestone.created_at.desc()).limit(30).all():
        sources.append({"source_type": "milestone", "source_id": item.id, "title": item.title, "source_label": "已确认里程碑"})
    return GrowthIntegrationWorkspace(
        communication_drafts=drafts,
        handoff_sources=sources,
        handoff_proposals=handoffs,
        handoff_inbox=inbox,
        summary={
            "drafts": sum(item.status == "draft" for item in drafts),
            "reviewed_or_exported": sum(item.status in {"reviewed", "exported"} for item in drafts),
            "handoffs_pending": sum(item.status == "proposed" for item in handoffs),
            "handoffs_active": len(inbox),
        },
        safety_note="沟通内容只生成、复核和导出草稿，不会代发；跨守护记录仅在本人确认后进入共享收件箱，并可撤销。",
    )


def handoff_inbox(db: Session, *, user_id: int, target_domain: str) -> list[GrowthHandoff]:
    if target_domain not in TARGET_LABELS:
        raise HTTPException(status_code=422, detail="不支持的目标域")
    return db.query(GrowthHandoff).filter(
        GrowthHandoff.user_id == user_id,
        GrowthHandoff.target_domain == target_domain,
        GrowthHandoff.status == "confirmed",
    ).order_by(GrowthHandoff.confirmed_at.desc(), GrowthHandoff.id.desc()).all()


def _record(item: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(item, field) for field in fields}


def full_growth_export(db: Session, *, user_id: int) -> GrowthFullExport:
    work_items = db.query(GrowthWorkItem).filter(GrowthWorkItem.user_id == user_id, GrowthWorkItem.deleted_at.is_(None)).all()
    events = db.query(GrowthWorkEvent).filter(GrowthWorkEvent.user_id == user_id, GrowthWorkEvent.status.in_(("confirmed", "archived"))).all()
    reports = db.query(GrowthWeeklyReport).filter(GrowthWeeklyReport.user_id == user_id, GrowthWeeklyReport.status.in_(("reviewed", "exported"))).all()
    portfolios = db.query(GrowthPortfolioItem).filter(GrowthPortfolioItem.user_id == user_id, GrowthPortfolioItem.deleted_at.is_(None), GrowthPortfolioItem.status == "active").all()
    evidences = db.query(GrowthEvidenceItem).filter(GrowthEvidenceItem.user_id == user_id, GrowthEvidenceItem.deleted_at.is_(None), GrowthEvidenceItem.status == "confirmed").all()
    skills = db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id, GrowthSkillAssessment.status == "confirmed").all()
    reflections = db.query(GrowthReflection).filter(GrowthReflection.user_id == user_id, GrowthReflection.status == "confirmed", GrowthReflection.privacy_level == "shared").all()
    targets = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.status.in_(("active", "paused", "completed"))).all()
    gaps = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.status == "confirmed").all()
    milestones = db.query(GrowthMilestone).filter(GrowthMilestone.user_id == user_id, GrowthMilestone.status.in_(("confirmed", "in_progress", "completed", "cancelled"))).all()
    market_signals = db.query(GrowthMarketSignal).filter(GrowthMarketSignal.user_id == user_id, GrowthMarketSignal.status.in_(("active", "weak", "expired"))).all()
    drafts = db.query(GrowthCommunicationDraft).filter(GrowthCommunicationDraft.user_id == user_id, GrowthCommunicationDraft.status.in_(("reviewed", "exported"))).all()
    handoffs = db.query(GrowthHandoff).filter(GrowthHandoff.user_id == user_id).all()
    return GrowthFullExport(
        generated_at=datetime.now(timezone.utc),
        work={
            "items": [_record(item, ("id", "title", "description", "status", "due_at", "result_summary", "reportable", "confirmed_at", "completed_at")) for item in work_items],
            "events": [_record(item, ("id", "work_item_id", "situation", "task", "action", "result", "role", "occurred_on", "visibility", "reportable", "confirmed_at")) for item in events],
            "weekly_reports": [_record(item, ("id", "week_start", "version", "status", "included_event_ids", "generated_content", "edited_content", "reviewed_at", "exported_at")) for item in reports],
        },
        assets={
            "portfolios": [_record(item, ("id", "item_type", "title", "summary", "source_url", "source_label", "occurred_on", "privacy_level", "confirmed_at")) for item in portfolios],
            "evidences": [_record(item, ("id", "evidence_type", "title", "summary", "source_label", "occurred_on", "role", "result_type", "privacy_level", "confirmed_at")) for item in evidences],
            "skills": [_record(item, ("id", "skill_name", "version", "source_layer", "evidence_sufficiency", "latest_used_on", "user_note", "confirmed_at")) for item in skills],
            "reflections": [_record(item, ("id", "work_event_id", "evidence_id", "question", "answer", "version", "confirmed_at")) for item in reflections],
        },
        direction={
            "targets": [_record(item, ("id", "target_type", "title", "description", "source_label", "target_date", "status", "version", "confirmed_at")) for item in targets],
            "market_signals": [_record(item, ("id", "target_id", "skill_name", "occurrence_count", "share", "direction", "availability", "quality_grade", "sample_size", "methodology_version", "sources", "calculated_at", "limitation", "status")) for item in market_signals],
            "gap_snapshots": [_record(item, ("id", "target_id", "version", "matched_items", "gap_items", "unknown_items", "quality", "confidence", "limitation", "confirmed_at")) for item in gaps],
            "milestones": [_record(item, ("id", "target_id", "gap_snapshot_id", "title", "success_criteria", "timeframe", "due_on", "status", "version", "confirmed_at", "completed_at")) for item in milestones],
        },
        communication={
            "drafts": [_record(item, ("id", "version", "audience", "scene", "goal", "known_facts", "tone", "fact_questions", "strategies", "risk_notes", "source_refs", "data_scope", "generated_content", "edited_content", "analysis_mode", "status", "reviewed_at", "exported_at")) for item in drafts],
        },
        handoffs=[_record(item, ("id", "target_domain", "source_type", "source_id", "title", "content_summary", "evidence_refs", "impact_summary", "status", "version", "confirmed_at", "revoked_at")) for item in handoffs],
        exclusions=[
            "原始情绪及其密文默认排除",
            "未确认的工作事件、作品、证据、能力、目标、差距和里程碑候选默认排除",
            "私人反思默认排除，只有本人确认共享的方法反思会纳入",
            "沟通草稿仅导出本人已复核或标记导出的版本，系统不表示已发送",
            "成长问询问题与回答不进入通用分类导出，可在成长首页单独查看最近记录",
        ],
    )
