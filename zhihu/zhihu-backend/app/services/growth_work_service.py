from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.career_event import CareerEvent
from app.models.growth import (
    GrowthAuditEvent,
    GrowthEmotionNote,
    GrowthWeeklyReport,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
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
    GrowthWorkspaceResponse,
)
from app.services.growth_ai_service import analyze_with_ai, analyze_with_rules


PRIVACY_NOTICE = (
    "原始工作输入不入库；系统只保存整理后的候选。情绪原文默认不保存，"
    "只有你明确选择保留时才加密存储，且不会进入周报或职业资产。"
)
ACTIVE_STATUSES = ("captured", "planned", "in_progress", "blocked", "deferred")
WORK_TRANSITIONS = {
    "captured": {"captured", "planned", "in_progress", "blocked", "completed", "deferred", "cancelled"},
    "planned": {"planned", "in_progress", "blocked", "completed", "deferred", "cancelled"},
    "in_progress": {"in_progress", "blocked", "completed", "deferred", "cancelled"},
    "blocked": {"blocked", "in_progress", "completed", "deferred", "cancelled"},
    "deferred": {"deferred", "planned", "in_progress", "cancelled"},
    "completed": {"completed"},
    "cancelled": {"cancelled"},
}
EVENT_TRANSITIONS = {
    "captured": {"confirmed", "needs_more_evidence", "discarded"},
    "structured": {"confirmed", "needs_more_evidence", "discarded"},
    "needs_more_evidence": {"confirmed", "needs_more_evidence", "discarded"},
    "confirmed": {"confirmed", "archived"},
    "discarded": {"discarded"},
    "archived": {"archived"},
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    if intake.status == "confirmed":
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
    for order, selected in enumerate(data.selected, start=1):
        candidate = candidates[selected.candidate_key]
        item = GrowthWorkItem(
            user_id=user_id,
            intake_id=intake.id,
            career_event_id=career_event.id,
            candidate_key=candidate.candidate_key,
            title=(selected.title or candidate.title).strip(),
            description=selected.description if selected.description is not None else candidate.description,
            fact_excerpt=selected.fact_excerpt if selected.fact_excerpt is not None else candidate.fact_excerpt,
            impact_level=selected.impact_level or candidate.impact_level,
            energy_level=selected.energy_level or candidate.energy_level,
            priority_order=order * 10,
            selection_reason=candidate.selection_reason,
            status="planned",
            due_at=selected.due_at,
            reportable=selected.reportable,
        )
        db.add(item)
        work_items.append(item)

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
            "emotion_retained": data.retain_emotion,
        },
    )
    db.commit()
    for item in work_items:
        db.refresh(item)
    return GrowthConfirmIntakeResponse(
        intake_id=intake.id,
        status="confirmed",
        work_items=work_items,
        emotion_retained=data.retain_emotion,
    )


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
    attention_count = sum(item.status == "blocked" for item in active_items) + len(event_candidates)
    if active_items:
        summary = f"{len(active_items)} 项当下工作正在推进，{attention_count} 项需要你处理。"
    elif event_candidates:
        summary = f"当前没有进行中的工作，仍有 {len(event_candidates)} 条工作事件待确认。"
    else:
        summary = "记录当下工作，先由系统整理候选，再由你确认 1–3 项突破任务。"
    return GrowthWorkspaceResponse(
        active_items=active_items,
        recent_event_candidates=event_candidates,
        confirmed_reportable_events=confirmed_events,
        recent_reports=reports,
        private_emotion_notes=emotion_notes,
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
    }
    item.status = data.status
    if data.result_summary is not None:
        item.result_summary = data.result_summary.strip() or None
    if data.reportable is not None:
        item.reportable = data.reportable
    if data.status == "completed":
        if not item.result_summary:
            raise HTTPException(status_code=422, detail="完成工作项时必须记录结果")
        item.completed_at = item.completed_at or _now()
    item.version += 1

    event = (
        db.query(GrowthWorkEvent)
        .filter(GrowthWorkEvent.work_item_id == item.id, GrowthWorkEvent.user_id == user_id)
        .with_for_update()
        .first()
    )
    if data.status == "completed" and event is None:
        gaps = ["situation", "action", "role"]
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
