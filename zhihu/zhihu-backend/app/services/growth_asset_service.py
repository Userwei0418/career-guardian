from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.growth import (
    GrowthAuditEvent,
    GrowthEvidenceItem,
    GrowthPortfolioItem,
    GrowthReflection,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
    GrowthWorkEvent,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.schemas.growth_assets import (
    CareerChip,
    EvidenceCreate,
    EvidenceUpdate,
    GrowthAssetsExport,
    GrowthAssetsWorkspace,
    PortfolioCreate,
    PortfolioUpdate,
    ReflectionCreate,
    ReflectionUpdate,
    SkillAssessmentResponse,
    SkillCandidateCreate,
    SkillConfirmRequest,
)


PORTFOLIO_TRANSITIONS = {
    "draft": {"draft", "active", "unavailable", "archived"},
    "active": {"active", "unavailable", "archived"},
    "unavailable": {"unavailable", "active", "archived"},
    "archived": {"archived"},
}
EVIDENCE_TRANSITIONS = {
    "candidate": {"candidate", "confirmed", "unavailable", "archived"},
    "confirmed": {"confirmed", "unavailable", "archived"},
    "unavailable": {"unavailable", "candidate", "archived"},
    "archived": {"archived"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fingerprint(data: Any) -> str:
    payload = data.model_dump(mode="json", exclude={"request_id"})
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit(
    db: Session,
    *,
    user_id: int,
    entity_type: str,
    entity_id: int | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(GrowthAuditEvent(
        user_id=user_id,
        actor_user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_payload=before,
        after_payload=after,
    ))


def _owned_event(db: Session, *, user_id: int, event_id: int) -> GrowthWorkEvent:
    event = db.query(GrowthWorkEvent).filter(
        GrowthWorkEvent.id == event_id,
        GrowthWorkEvent.user_id == user_id,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail="成长工作事件不存在")
    return event


def _owned_portfolio(db: Session, *, user_id: int, item_id: int, lock: bool = False) -> GrowthPortfolioItem:
    query = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.id == item_id,
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.deleted_at.is_(None),
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长作品不存在")
    return item


def _owned_evidence(db: Session, *, user_id: int, evidence_id: int, lock: bool = False) -> GrowthEvidenceItem:
    query = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.id == evidence_id,
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.deleted_at.is_(None),
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长证据不存在")
    return item


def create_portfolio(db: Session, *, user_id: int, data: PortfolioCreate) -> GrowthPortfolioItem:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长作品")
        return existing
    if data.source_work_event_id is not None:
        event = _owned_event(db, user_id=user_id, event_id=data.source_work_event_id)
        if event.status not in {"confirmed", "archived"}:
            raise HTTPException(status_code=422, detail="只能从本人已确认的工作事件沉淀作品")
    if data.source_attachment_id is not None:
        attachment = db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.id == data.source_attachment_id,
            PersonalAttachmentVersion.user_id == user_id,
            PersonalAttachmentVersion.is_active.is_(True),
        ).first()
        if attachment is None:
            raise HTTPException(status_code=404, detail="可用的本人附件版本不存在")
    item = GrowthPortfolioItem(user_id=user_id, input_fingerprint=fingerprint, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthPortfolioItem).filter(
            GrowthPortfolioItem.user_id == user_id,
            GrowthPortfolioItem.request_id == data.request_id,
        ).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长作品")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="created", after={"status": "draft", "item_type": item.item_type})
    db.commit()
    db.refresh(item)
    return item


def update_portfolio(db: Session, *, user_id: int, item_id: int, data: PortfolioUpdate) -> GrowthPortfolioItem:
    item = _owned_portfolio(db, user_id=user_id, item_id=item_id, lock=True)
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="作品已被更新，请刷新后重试")
    if data.status not in PORTFOLIO_TRANSITIONS[item.status]:
        raise HTTPException(status_code=409, detail=f"作品不能从 {item.status} 变更为 {data.status}")
    if data.status == "active" and not any((item.source_work_event_id, item.source_attachment_id, (data.source_url or item.source_url or "").strip(), (data.source_label or item.source_label or "").strip())):
        raise HTTPException(status_code=422, detail="确认作品前必须补充工作事件、附件、HTTPS 链接或明确来源")
    before = {"status": item.status, "version": item.version, "privacy_level": item.privacy_level}
    for field in ("title", "summary", "source_url", "source_label", "occurred_on", "privacy_level", "unavailable_reason"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    item.status = data.status
    item.confirmed_at = _now() if data.status == "active" and item.confirmed_at is None else item.confirmed_at
    item.archived_at = _now() if data.status == "archived" else item.archived_at
    if data.status != "unavailable":
        item.unavailable_reason = None
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="updated", before=before, after={"status": item.status, "version": item.version, "privacy_level": item.privacy_level})
    db.commit()
    db.refresh(item)
    return item


def delete_portfolio(db: Session, *, user_id: int, item_id: int, detach_evidence: bool) -> dict[str, Any]:
    item = _owned_portfolio(db, user_id=user_id, item_id=item_id, lock=True)
    linked = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.portfolio_item_id == item.id,
        GrowthEvidenceItem.deleted_at.is_(None),
    ).with_for_update().all()
    if linked and not detach_evidence:
        raise HTTPException(status_code=409, detail={"code": "portfolio_has_evidence", "message": "该作品仍关联成长证据，请先确认是否解除关联", "linked_evidence_ids": [value.id for value in linked]})
    for evidence in linked:
        evidence.portfolio_item_id = None
        if evidence.work_event_id is None and not (evidence.source_label or "").strip():
            evidence.status = "unavailable"
            evidence.unavailable_reason = "原关联作品已删除，当前证据缺少可追溯来源"
        evidence.version += 1
    item.deleted_at = _now()
    item.status = "archived"
    item.archived_at = item.deleted_at
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_portfolio_item", entity_id=item.id, action="deleted", after={"detached_evidence_ids": [value.id for value in linked]})
    db.commit()
    return {"ok": True, "detached_evidence_ids": [value.id for value in linked]}


def create_evidence(db: Session, *, user_id: int, data: EvidenceCreate) -> GrowthEvidenceItem:
    fingerprint = _fingerprint(data)
    existing = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.request_id == data.request_id,
    ).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长证据")
        return existing
    if data.portfolio_item_id is not None:
        _owned_portfolio(db, user_id=user_id, item_id=data.portfolio_item_id)
    if data.work_event_id is not None:
        event = _owned_event(db, user_id=user_id, event_id=data.work_event_id)
        if event.status not in {"confirmed", "archived"}:
            raise HTTPException(status_code=422, detail="只能引用本人已确认的工作事件")
    item = GrowthEvidenceItem(user_id=user_id, input_fingerprint=fingerprint, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthEvidenceItem).filter(
            GrowthEvidenceItem.user_id == user_id,
            GrowthEvidenceItem.request_id == data.request_id,
        ).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的成长证据")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action="created", after={"status": "candidate", "evidence_type": item.evidence_type})
    db.commit()
    db.refresh(item)
    return item


def update_evidence(db: Session, *, user_id: int, evidence_id: int, data: EvidenceUpdate) -> GrowthEvidenceItem:
    item = _owned_evidence(db, user_id=user_id, evidence_id=evidence_id, lock=True)
    if item.version != data.expected_version:
        raise HTTPException(status_code=409, detail="证据已被更新，请刷新后重试")
    if data.status not in EVIDENCE_TRANSITIONS[item.status]:
        raise HTTPException(status_code=409, detail=f"证据不能从 {item.status} 变更为 {data.status}")
    before = {"status": item.status, "version": item.version, "privacy_level": item.privacy_level}
    for field in ("title", "summary", "source_label", "occurred_on", "role", "result_type", "privacy_level", "unavailable_reason"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    item.status = data.status
    item.confirmed_at = _now() if data.status == "confirmed" and item.confirmed_at is None else item.confirmed_at
    item.archived_at = _now() if data.status == "archived" else item.archived_at
    if data.status != "unavailable":
        item.unavailable_reason = None
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action=data.status, before=before, after={"status": item.status, "version": item.version, "privacy_level": item.privacy_level})
    db.commit()
    db.refresh(item)
    return item


def delete_evidence(db: Session, *, user_id: int, evidence_id: int, detach_skills: bool) -> dict[str, Any]:
    item = _owned_evidence(db, user_id=user_id, evidence_id=evidence_id, lock=True)
    links = db.query(GrowthSkillEvidenceLink).filter(
        GrowthSkillEvidenceLink.user_id == user_id,
        GrowthSkillEvidenceLink.evidence_id == item.id,
    ).with_for_update().all()
    if links and not detach_skills:
        raise HTTPException(status_code=409, detail={"code": "evidence_supports_skills", "message": "该证据仍支撑能力事实，请先确认是否解除关联", "assessment_ids": [link.assessment_id for link in links]})
    assessment_ids = list(dict.fromkeys(link.assessment_id for link in links))
    revisions: list[int] = []
    if detach_skills:
        for assessment_id in assessment_ids:
            assessment = db.query(GrowthSkillAssessment).filter(
                GrowthSkillAssessment.id == assessment_id,
                GrowthSkillAssessment.user_id == user_id,
            ).with_for_update().first()
            if assessment is None or assessment.status not in {"candidate", "confirmed"}:
                continue
            remaining_ids = [
                link.evidence_id
                for link in db.query(GrowthSkillEvidenceLink).filter(
                    GrowthSkillEvidenceLink.assessment_id == assessment.id,
                    GrowthSkillEvidenceLink.evidence_id != item.id,
                ).all()
            ]
            remaining = _confirmed_evidences(db, user_id=user_id, evidence_ids=remaining_ids)
            was_confirmed = assessment.status == "confirmed"
            assessment.status = "superseded"
            successor = GrowthSkillAssessment(
                user_id=user_id,
                supersedes_assessment_id=assessment.id,
                skill_key=assessment.skill_key,
                skill_name=assessment.skill_name,
                version=assessment.version + 1,
                source_layer=(
                    "evidence_confirmed"
                    if remaining and was_confirmed
                    else "user_claimed"
                    if was_confirmed
                    else assessment.source_layer
                ),
                status="confirmed" if was_confirmed else "candidate",
                evidence_sufficiency="supported" if len(remaining) >= 2 else "partial" if remaining else "none",
                user_note=assessment.user_note,
                latest_used_on=max((value.occurred_on for value in remaining if value.occurred_on), default=None),
                confirmed_at=assessment.confirmed_at,
            )
            db.add(successor)
            db.flush()
            revisions.append(successor.id)
            for remaining_evidence in remaining:
                db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=successor.id, evidence_id=remaining_evidence.id))
    for link in links:
        db.delete(link)
    item.deleted_at = _now()
    item.status = "archived"
    item.archived_at = item.deleted_at
    item.version += 1
    _audit(db, user_id=user_id, entity_type="growth_evidence_item", entity_id=item.id, action="deleted", after={"detached_assessment_ids": assessment_ids, "successor_assessment_ids": revisions})
    db.commit()
    return {"ok": True, "detached_assessment_ids": assessment_ids, "successor_assessment_ids": revisions}


def _skill_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return normalized[:160]


def _confirmed_evidences(db: Session, *, user_id: int, evidence_ids: list[int]) -> list[GrowthEvidenceItem]:
    if not evidence_ids:
        return []
    unique_ids = list(dict.fromkeys(evidence_ids))
    items = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.id.in_(unique_ids),
        GrowthEvidenceItem.deleted_at.is_(None),
        GrowthEvidenceItem.status == "confirmed",
    ).all()
    if {item.id for item in items} != set(unique_ids):
        raise HTTPException(status_code=422, detail="能力只能关联本人已确认且仍可用的成长证据")
    return items


def _skill_response(db: Session, item: GrowthSkillAssessment) -> SkillAssessmentResponse:
    links = db.query(GrowthSkillEvidenceLink).filter(GrowthSkillEvidenceLink.assessment_id == item.id).all()
    evidence_ids = [link.evidence_id for link in links]
    return SkillAssessmentResponse(
        id=item.id,
        skill_name=item.skill_name,
        version=item.version,
        source_layer=item.source_layer,
        status=item.status,
        evidence_sufficiency=item.evidence_sufficiency,
        evidence_ids=evidence_ids,
        evidence_count=len(evidence_ids),
        latest_used_on=item.latest_used_on,
        user_note=item.user_note,
        confirmed_at=item.confirmed_at,
        created_at=item.created_at,
    )


def create_skill_candidate(db: Session, *, user_id: int, data: SkillCandidateCreate) -> SkillAssessmentResponse:
    if db.query(User).filter(User.id == user_id).with_for_update().first() is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    key = _skill_key(data.skill_name)
    existing = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.user_id == user_id,
        GrowthSkillAssessment.skill_key == key,
        GrowthSkillAssessment.status.in_(("candidate", "confirmed")),
    ).order_by(GrowthSkillAssessment.version.desc()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该能力已有待确认或已确认版本")
    evidences = _confirmed_evidences(db, user_id=user_id, evidence_ids=data.evidence_ids)
    latest = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.user_id == user_id,
        GrowthSkillAssessment.skill_key == key,
    ).order_by(GrowthSkillAssessment.version.desc()).first()
    item = GrowthSkillAssessment(
        user_id=user_id,
        supersedes_assessment_id=latest.id if latest else None,
        skill_key=key,
        skill_name=data.skill_name.strip(),
        version=(latest.version + 1) if latest else 1,
        source_layer=data.source_layer,
        status="candidate",
        evidence_sufficiency="partial" if evidences else "none",
        user_note=(data.user_note or "").strip() or None,
        latest_used_on=max((value.occurred_on for value in evidences if value.occurred_on), default=None),
    )
    db.add(item)
    db.flush()
    for evidence in evidences:
        db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=item.id, evidence_id=evidence.id))
    _audit(db, user_id=user_id, entity_type="growth_skill_assessment", entity_id=item.id, action="candidate_created", after={"source_layer": item.source_layer, "evidence_ids": [value.id for value in evidences]})
    db.commit()
    db.refresh(item)
    return _skill_response(db, item)


def confirm_skill(db: Session, *, user_id: int, assessment_id: int, data: SkillConfirmRequest) -> SkillAssessmentResponse:
    current = db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.id == assessment_id,
        GrowthSkillAssessment.user_id == user_id,
    ).with_for_update().first()
    if current is None:
        raise HTTPException(status_code=404, detail="能力候选不存在")
    if current.status != "candidate" or current.version != data.expected_version:
        raise HTTPException(status_code=409, detail="能力候选已变化，请刷新后重试")
    evidences = _confirmed_evidences(db, user_id=user_id, evidence_ids=data.evidence_ids)
    current_links = db.query(GrowthSkillEvidenceLink).filter(GrowthSkillEvidenceLink.assessment_id == current.id).all()
    merged_ids = list(dict.fromkeys([link.evidence_id for link in current_links] + [item.id for item in evidences]))
    merged = _confirmed_evidences(db, user_id=user_id, evidence_ids=merged_ids)
    current.status = "superseded"
    confirmed = GrowthSkillAssessment(
        user_id=user_id,
        supersedes_assessment_id=current.id,
        skill_key=current.skill_key,
        skill_name=current.skill_name,
        version=current.version + 1,
        source_layer="evidence_confirmed" if merged else "user_claimed",
        status="confirmed",
        evidence_sufficiency="supported" if len(merged) >= 2 else "partial" if merged else "none",
        user_note=(data.user_note or current.user_note or "").strip() or None,
        latest_used_on=max((value.occurred_on for value in merged if value.occurred_on), default=None),
        confirmed_at=_now(),
    )
    db.add(confirmed)
    db.flush()
    for evidence in merged:
        db.add(GrowthSkillEvidenceLink(user_id=user_id, assessment_id=confirmed.id, evidence_id=evidence.id))
    _audit(db, user_id=user_id, entity_type="growth_skill_assessment", entity_id=confirmed.id, action="confirmed", before={"candidate_id": current.id, "source_layer": current.source_layer}, after={"source_layer": confirmed.source_layer, "evidence_ids": merged_ids})
    db.commit()
    db.refresh(confirmed)
    return _skill_response(db, confirmed)


def create_reflection(db: Session, *, user_id: int, data: ReflectionCreate) -> GrowthReflection:
    event = _owned_event(db, user_id=user_id, event_id=data.work_event_id)
    if event.status not in {"confirmed", "archived"}:
        raise HTTPException(status_code=422, detail="只能对本人已确认的工作事件发起反思")
    existing = db.query(GrowthReflection).filter(
        GrowthReflection.user_id == user_id,
        GrowthReflection.work_event_id == event.id,
        GrowthReflection.status != "archived",
    ).first()
    if existing is not None:
        return existing
    if "action" in (event.evidence_gaps or []):
        question = "如果重做一次，你最想调整的一个行动是什么？"
    elif event.result:
        question = "这次经历中，哪项方法最值得在别的项目复用？"
    else:
        question = "哪个结果仍缺少可以核对的证据？"
    item = GrowthReflection(user_id=user_id, work_event_id=event.id, question=question)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthReflection).filter(
            GrowthReflection.user_id == user_id,
            GrowthReflection.work_event_id == event.id,
        ).first()
        if winner is None:
            raise HTTPException(status_code=409, detail="反思创建冲突，请刷新后重试")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_reflection", entity_id=item.id, action="prompted", after={"work_event_id": event.id})
    db.commit()
    db.refresh(item)
    return item


def update_reflection(db: Session, *, user_id: int, reflection_id: int, data: ReflectionUpdate) -> GrowthReflection:
    item = db.query(GrowthReflection).filter(
        GrowthReflection.id == reflection_id,
        GrowthReflection.user_id == user_id,
    ).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="成长反思不存在")
    if item.version != data.expected_version or item.status in {"confirmed", "archived"}:
        raise HTTPException(status_code=409, detail="成长反思已变化，请刷新后重试")
    item.answer = data.answer.strip()
    item.privacy_level = data.privacy_level
    item.status = "confirmed" if data.confirm_as_method else "answered"
    item.confirmed_at = _now() if data.confirm_as_method else item.confirmed_at
    item.version += 1
    if data.confirm_as_method:
        evidence = GrowthEvidenceItem(
            user_id=user_id,
            request_id=f"reflection-{item.id}-v{item.version + 1}",
            input_fingerprint=hashlib.sha256(f"reflection:{item.id}:{item.version + 1}".encode("utf-8")).hexdigest(),
            work_event_id=item.work_event_id,
            evidence_type="method",
            title=item.question[:300],
            summary=item.answer,
            source_label="本人确认的成长反思",
            privacy_level="shared" if data.privacy_level == "shared" else "private",
            status="confirmed",
            confirmed_at=_now(),
        )
        db.add(evidence)
        db.flush()
        item.evidence_id = evidence.id
    _audit(db, user_id=user_id, entity_type="growth_reflection", entity_id=item.id, action=item.status, after={"privacy_level": item.privacy_level, "evidence_id": item.evidence_id})
    db.commit()
    db.refresh(item)
    return item


def _latest_skills(db: Session, *, user_id: int) -> list[GrowthSkillAssessment]:
    rows = db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id).order_by(
        GrowthSkillAssessment.skill_key.asc(), GrowthSkillAssessment.version.desc()
    ).all()
    latest: dict[str, GrowthSkillAssessment] = {}
    for item in rows:
        latest.setdefault(item.skill_key, item)
    return [item for item in latest.values() if item.status not in {"superseded", "archived", "rejected"}]


def assets_workspace(db: Session, *, user_id: int) -> GrowthAssetsWorkspace:
    available_work_events = db.query(GrowthWorkEvent).filter(
        GrowthWorkEvent.user_id == user_id,
        GrowthWorkEvent.status.in_(("confirmed", "archived")),
    ).order_by(GrowthWorkEvent.occurred_on.desc(), GrowthWorkEvent.id.desc()).limit(100).all()
    portfolios = db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.user_id == user_id,
        GrowthPortfolioItem.deleted_at.is_(None),
    ).order_by(GrowthPortfolioItem.updated_at.desc()).all()
    evidences = db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id,
        GrowthEvidenceItem.deleted_at.is_(None),
    ).order_by(GrowthEvidenceItem.updated_at.desc()).all()
    skills = [_skill_response(db, item) for item in _latest_skills(db, user_id=user_id)]
    reflections = db.query(GrowthReflection).filter(
        GrowthReflection.user_id == user_id,
        GrowthReflection.status != "archived",
    ).order_by(GrowthReflection.updated_at.desc()).all()
    chips: list[CareerChip] = []
    for item in portfolios:
        if item.status == "active":
            chips.append(CareerChip(chip_type="portfolio", title=item.title, source_id=item.id, source_label="已确认作品", occurred_on=item.occurred_on, privacy_level=item.privacy_level))
    for item in evidences:
        if item.status == "confirmed":
            chips.append(CareerChip(chip_type="evidence", title=item.title, source_id=item.id, source_label="已确认成长证据", occurred_on=item.occurred_on, privacy_level=item.privacy_level))
    for item in skills:
        if item.status == "confirmed" and item.source_layer == "evidence_confirmed":
            chips.append(CareerChip(chip_type="skill", title=item.skill_name, source_id=item.id, source_label="证据确认能力", occurred_on=item.latest_used_on, evidence_count=item.evidence_count))
    return GrowthAssetsWorkspace(
        available_work_events=available_work_events,
        portfolios=portfolios,
        evidences=evidences,
        skills=skills,
        reflections=reflections,
        career_chips=chips,
        summary={
            "active_portfolios": sum(item.status == "active" for item in portfolios),
            "confirmed_evidences": sum(item.status == "confirmed" for item in evidences),
            "confirmed_skills": sum(item.status == "confirmed" for item in skills),
            "pending_confirmations": sum(item.status == "draft" for item in portfolios) + sum(item.status == "candidate" for item in evidences) + sum(item.status == "candidate" for item in skills),
        },
    )


def export_assets(db: Session, *, user_id: int) -> GrowthAssetsExport:
    workspace = assets_workspace(db, user_id=user_id)
    return GrowthAssetsExport(
        generated_at=_now(),
        portfolios=[item for item in workspace.portfolios if item.status == "active"],
        evidences=[item for item in workspace.evidences if item.status == "confirmed"],
        skills=[item for item in workspace.skills if item.status == "confirmed"],
        reflections=[item for item in workspace.reflections if item.status == "confirmed" and item.privacy_level == "shared"],
        note="仅导出本人已确认的成长资产；私人情绪和私人反思不在此导出中。",
    )
