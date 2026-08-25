from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.growth import (
    GrowthAuditEvent,
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthMarketSignal,
    GrowthMilestone,
    GrowthSkillAssessment,
    GrowthWorkIntake,
)
from app.models.user import User
from app.schemas.growth_direction import (
    DirectionWorkspace,
    FutureTargetConfirm,
    FutureTargetCreate,
    GapSnapshotConfirm,
    GapSnapshotCreate,
    MarketRefreshResponse,
    MarketSignalRefresh,
    MilestoneActionProposal,
    MilestoneCreate,
    MilestoneUpdate,
)
from app.schemas.market import SkillInsightResponse
from app.services.growth_asset_service import assets_workspace


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalized(value: str) -> str:
    return re.sub(r"[\s\-_/]+", "", value.strip().lower())[:180]


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _derived_request(prefix: str, entity_id: int, version: int) -> str:
    return f"{prefix}-{entity_id}-v{version}-{_hash([prefix, entity_id, version])[:12]}"


def _audit(db: Session, *, user_id: int, entity_type: str, entity_id: int | None, action: str, after: dict | None = None) -> None:
    db.add(GrowthAuditEvent(user_id=user_id, actor_user_id=user_id, entity_type=entity_type, entity_id=entity_id, action=action, after_payload=after))


def _target(db: Session, *, user_id: int, target_id: int, lock: bool = False) -> GrowthFutureTarget:
    query = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.id == target_id, GrowthFutureTarget.user_id == user_id)
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="未来目标不存在")
    return item


def _gap(db: Session, *, user_id: int, gap_id: int, lock: bool = False) -> GrowthGapSnapshot:
    query = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.id == gap_id, GrowthGapSnapshot.user_id == user_id)
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="差距快照不存在")
    return item


def _milestone(db: Session, *, user_id: int, milestone_id: int, lock: bool = False) -> GrowthMilestone:
    query = db.query(GrowthMilestone).filter(GrowthMilestone.id == milestone_id, GrowthMilestone.user_id == user_id)
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=404, detail="里程碑不存在")
    return item


def create_target(db: Session, *, user_id: int, data: FutureTargetCreate) -> GrowthFutureTarget:
    if db.query(User).filter(User.id == user_id).with_for_update().first() is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    fingerprint = _hash(data.model_dump(mode="json", exclude={"request_id"}))
    existing = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.request_id == data.request_id).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的未来目标")
        return existing
    key = _normalized(f"{data.target_type}:{data.title}")
    latest = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.target_key == key).order_by(GrowthFutureTarget.version.desc()).first()
    item = GrowthFutureTarget(
        user_id=user_id,
        supersedes_target_id=latest.id if latest else None,
        request_id=data.request_id,
        input_fingerprint=fingerprint,
        target_key=key,
        target_type=data.target_type,
        title=data.title.strip(),
        description=(data.description or "").strip() or None,
        source_label=(data.source_label or "").strip() or None,
        target_date=data.target_date,
        version=(latest.version + 1) if latest else 1,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.request_id == data.request_id).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="未来目标创建冲突，请刷新后重试")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_future_target", entity_id=item.id, action="draft_created", after={"target_type": item.target_type, "version": item.version})
    db.commit(); db.refresh(item)
    return item


def confirm_target(db: Session, *, user_id: int, target_id: int, data: FutureTargetConfirm) -> GrowthFutureTarget:
    current = _target(db, user_id=user_id, target_id=target_id, lock=True)
    if current.status != "draft" or current.version != data.expected_version:
        raise HTTPException(status_code=409, detail="目标草稿已变化，请刷新后重试")
    active_targets = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.status == "active").with_for_update().all()
    for item in active_targets:
        item.status = "superseded"
    current.status = "superseded"
    confirmed = GrowthFutureTarget(
        user_id=user_id,
        supersedes_target_id=current.id,
        request_id=_derived_request("target-confirm", current.id, current.version + 1),
        input_fingerprint=current.input_fingerprint,
        target_key=current.target_key,
        target_type=current.target_type,
        title=current.title,
        description=current.description,
        source_label=current.source_label,
        target_date=current.target_date,
        status="active",
        version=current.version + 1,
        confirmed_at=_now(),
    )
    db.add(confirmed); db.flush()
    _audit(db, user_id=user_id, entity_type="growth_future_target", entity_id=confirmed.id, action="confirmed", after={"supersedes": current.id, "version": confirmed.version})
    db.commit(); db.refresh(confirmed)
    return confirmed


def refresh_market_signals(
    db: Session,
    *,
    user_id: int,
    data: MarketSignalRefresh,
    insight: SkillInsightResponse,
) -> MarketRefreshResponse:
    target = _target(db, user_id=user_id, target_id=data.target_id, lock=True)
    if target.status != "active":
        raise HTTPException(status_code=422, detail="只能为本人已确认的当前目标更新市场信号")
    request_fingerprint = _hash({"target_id": target.id, "limit": data.limit})
    existing = db.query(GrowthMarketSignal).filter(GrowthMarketSignal.user_id == user_id, GrowthMarketSignal.batch_request_id == data.request_id).all()
    if existing:
        if any(item.target_id != target.id or item.request_fingerprint != request_fingerprint for item in existing):
            raise HTTPException(status_code=409, detail="request_id 已用于不同的市场信号请求")
        return MarketRefreshResponse(
            availability=existing[0].availability,
            data_mode=existing[0].data_mode,
            sample_size=existing[0].sample_size,
            quality_grade=existing[0].quality_grade,
            calculated_at=existing[0].calculated_at,
            signals=existing,
            note=existing[0].limitation,
        )
    limitation = insight.note
    if insight.availability == "insufficient_sample":
        limitation = limitation or "样本不足，只能作为弱信号，不能据此判断能力淘汰或职业去向。"
    elif insight.availability == "stale":
        limitation = limitation or "样本已过期，只用于提示核实方向。"
    elif insight.availability == "unavailable":
        limitation = limitation or "市场数据暂时不可用，未生成差距结论。"
    status = "active" if insight.availability == "available" and insight.quality_grade in {"A", "B"} else "expired" if insight.availability == "stale" else "weak"
    stored: list[GrowthMarketSignal] = []
    source_signals = list(insight.skills)
    if not source_signals:
        source_signals = [None]
    for signal in source_signals:
        signal_name = signal.name if signal is not None else "市场样本状态"
        occurrence_count = signal.count if signal is not None else 0
        share = signal.share if signal is not None else None
        item = GrowthMarketSignal(
            user_id=user_id,
            target_id=target.id,
            batch_request_id=data.request_id,
            request_fingerprint=request_fingerprint,
            signal_key=_normalized(signal_name) if signal is not None else "__availability__",
            skill_name=signal_name.strip(),
            occurrence_count=occurrence_count,
            share=share,
            recent_count=signal.recent_count if signal is not None else None,
            previous_count=signal.previous_count if signal is not None else None,
            recent_share=signal.recent_share if signal is not None else None,
            previous_share=signal.previous_share if signal is not None else None,
            share_delta=signal.share_delta if signal is not None else None,
            recent_sample_size=insight.recent_sample_size,
            previous_sample_size=insight.previous_sample_size,
            recent_window_start=insight.recent_window_start.replace(tzinfo=None) if insight.recent_window_start else None,
            recent_window_end=insight.recent_window_end.replace(tzinfo=None) if insight.recent_window_end else None,
            previous_window_start=insight.previous_window_start.replace(tzinfo=None) if insight.previous_window_start else None,
            previous_window_end=insight.previous_window_end.replace(tzinfo=None) if insight.previous_window_end else None,
            direction=signal.direction if signal is not None else "unknown",
            availability=insight.availability,
            data_mode=insight.data_mode,
            quality_grade=insight.quality_grade,
            sample_size=insight.sample_size,
            methodology_version=insight.methodology_version,
            sources=[source.model_dump(mode="json") for source in insight.sources],
            calculated_at=insight.calculated_at.replace(tzinfo=None),
            limitation=limitation,
            status=status,
        )
        db.add(item); stored.append(item)
    db.flush()
    _audit(db, user_id=user_id, entity_type="growth_market_signal_batch", entity_id=target.id, action="refreshed", after={"request_id": data.request_id, "availability": insight.availability, "quality_grade": insight.quality_grade, "sample_size": insight.sample_size, "signal_count": len(stored)})
    db.commit()
    for item in stored: db.refresh(item)
    return MarketRefreshResponse(availability=insight.availability, data_mode=insight.data_mode, sample_size=insight.sample_size, quality_grade=insight.quality_grade, calculated_at=insight.calculated_at, signals=stored, note=limitation)


def create_gap_snapshot(db: Session, *, user_id: int, data: GapSnapshotCreate) -> GrowthGapSnapshot:
    target = _target(db, user_id=user_id, target_id=data.target_id, lock=True)
    if target.status != "active":
        raise HTTPException(status_code=422, detail="只能对本人当前已确认目标生成差距候选")
    signals = db.query(GrowthMarketSignal).filter(GrowthMarketSignal.user_id == user_id, GrowthMarketSignal.target_id == target.id, GrowthMarketSignal.status.in_(("active", "weak", "expired"))).order_by(GrowthMarketSignal.calculated_at.desc(), GrowthMarketSignal.id.desc()).all()
    if signals:
        latest_batch = signals[0].batch_request_id
        signals = [item for item in signals if item.batch_request_id == latest_batch]
    skills = db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id, GrowthSkillAssessment.status == "confirmed").all()
    assets = assets_workspace(db, user_id=user_id)
    fingerprint = _hash({"target_id": target.id, "target_version": target.version, "signals": [item.id for item in signals], "skills": [item.id for item in skills], "chips": [[item.chip_type, item.source_id] for item in assets.career_chips]})
    existing = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.request_id == data.request_id).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的差距输入")
        return existing
    skill_names = [item.skill_name for item in skills if item.source_layer == "evidence_confirmed"]
    claimed_skill_names = [item.skill_name for item in skills if item.source_layer == "user_claimed"]
    skill_signals = [item for item in signals if item.signal_key != "__availability__"]
    reliable = bool(skill_signals) and signals[0].availability == "available" and signals[0].quality_grade in {"A", "B", "C"}
    matched = [signal.skill_name for signal in skill_signals if any(_normalized(signal.skill_name) in _normalized(skill) or _normalized(skill) in _normalized(signal.skill_name) for skill in skill_names)]
    unmatched = [signal.skill_name for signal in skill_signals if signal.skill_name not in matched]
    claimed_only = [signal for signal in unmatched if any(_normalized(signal) in _normalized(skill) or _normalized(skill) in _normalized(signal) for skill in claimed_skill_names)]
    gaps = [signal for signal in unmatched if signal not in claimed_only] if reliable else []
    unknown = ([f"{signal}（仅本人自述，待补证据）" for signal in claimed_only] if reliable else unmatched)
    if not skill_signals:
        unknown = ["尚无可用市场技能样本，差距未核清"]
    availability = signals[0].availability if signals else "unavailable"
    grade = signals[0].quality_grade if signals else "insufficient"
    quality = "stale" if availability == "stale" else "insufficient" if availability in {"unavailable", "insufficient_sample"} or grade == "insufficient" else "strong" if grade in {"A", "B"} and signals[0].sample_size >= 10 else "limited"
    confidence = {"strong": 0.85, "limited": 0.6, "insufficient": 0.25, "stale": 0.3}[quality]
    limitation = signals[0].limitation if signals else "市场样本缺失；当前只展示已确认筹码，不形成确定差距。"
    latest = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.target_id == target.id).order_by(GrowthGapSnapshot.version.desc()).first()
    if latest and latest.status != "superseded": latest.status = "superseded"
    item = GrowthGapSnapshot(
        user_id=user_id, target_id=target.id, request_id=data.request_id, input_fingerprint=fingerprint,
        version=(latest.version + 1) if latest else 1,
        market_signal_ids=[signal.id for signal in signals],
        career_chip_refs=[{"type": chip.chip_type, "id": chip.source_id, "title": chip.title} for chip in assets.career_chips],
        matched_items=matched, gap_items=gaps, unknown_items=unknown,
        quality=quality, confidence=confidence, limitation=limitation,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.request_id == data.request_id).first()
        if winner is None or winner.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="差距快照创建冲突，请刷新后重试")
        return winner
    _audit(db, user_id=user_id, entity_type="growth_gap_snapshot", entity_id=item.id, action="candidate_created", after={"quality": quality, "gap_count": len(gaps), "unknown_count": len(unknown)})
    db.commit(); db.refresh(item)
    return item


def confirm_gap_snapshot(db: Session, *, user_id: int, gap_id: int, data: GapSnapshotConfirm) -> GrowthGapSnapshot:
    current = _gap(db, user_id=user_id, gap_id=gap_id, lock=True)
    if current.status != "candidate" or current.version != data.expected_version:
        raise HTTPException(status_code=409, detail="差距候选已变化，请刷新后重试")
    current.status = "superseded"
    confirmed = GrowthGapSnapshot(
        user_id=user_id, target_id=current.target_id,
        request_id=_derived_request("gap-confirm", current.id, current.version + 1), input_fingerprint=current.input_fingerprint,
        version=current.version + 1, market_signal_ids=current.market_signal_ids, career_chip_refs=current.career_chip_refs,
        matched_items=current.matched_items, gap_items=current.gap_items, unknown_items=current.unknown_items,
        quality=current.quality, confidence=current.confidence, limitation=current.limitation,
        status="confirmed", confirmed_at=_now(),
    )
    db.add(confirmed); db.flush()
    _audit(db, user_id=user_id, entity_type="growth_gap_snapshot", entity_id=confirmed.id, action="confirmed", after={"supersedes": current.id, "version": confirmed.version})
    db.commit(); db.refresh(confirmed)
    return confirmed


def create_milestone(db: Session, *, user_id: int, data: MilestoneCreate) -> GrowthMilestone:
    target = _target(db, user_id=user_id, target_id=data.target_id, lock=True)
    if target.status != "active": raise HTTPException(status_code=422, detail="只能为当前已确认目标创建里程碑")
    if data.gap_snapshot_id is not None:
        gap = _gap(db, user_id=user_id, gap_id=data.gap_snapshot_id)
        if gap.target_id != target.id or gap.status != "confirmed": raise HTTPException(status_code=422, detail="里程碑只能引用同一目标下本人已确认的差距快照")
    fingerprint = _hash(data.model_dump(mode="json", exclude={"request_id"}))
    existing = db.query(GrowthMilestone).filter(GrowthMilestone.user_id == user_id, GrowthMilestone.request_id == data.request_id).first()
    if existing is not None:
        if existing.input_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="request_id 已用于不同的里程碑")
        return existing
    days = {"30d": 30, "60d": 60, "90d": 90, "quarter": 90}.get(data.timeframe)
    due_on = data.due_on or (date.today() + timedelta(days=days) if days else None)
    key = _normalized(f"{target.id}:{data.title}")
    latest = db.query(GrowthMilestone).filter(GrowthMilestone.user_id == user_id, GrowthMilestone.milestone_key == key).order_by(GrowthMilestone.version.desc()).first()
    item = GrowthMilestone(user_id=user_id, supersedes_milestone_id=latest.id if latest else None, target_id=target.id, gap_snapshot_id=data.gap_snapshot_id, request_id=data.request_id, input_fingerprint=fingerprint, milestone_key=key, title=data.title.strip(), success_criteria=data.success_criteria.strip(), timeframe=data.timeframe, due_on=due_on, version=(latest.version + 1) if latest else 1)
    db.add(item); db.flush(); _audit(db, user_id=user_id, entity_type="growth_milestone", entity_id=item.id, action="proposed", after={"timeframe": item.timeframe, "due_on": str(item.due_on)})
    db.commit(); db.refresh(item); return item


def update_milestone(db: Session, *, user_id: int, milestone_id: int, data: MilestoneUpdate) -> GrowthMilestone:
    current = _milestone(db, user_id=user_id, milestone_id=milestone_id, lock=True)
    transitions = {"proposed": {"confirmed", "cancelled"}, "confirmed": {"in_progress", "completed", "cancelled"}, "in_progress": {"completed", "cancelled"}, "completed": set(), "cancelled": set(), "superseded": set()}
    if current.version != data.expected_version or data.status not in transitions[current.status]:
        raise HTTPException(status_code=409, detail="里程碑状态或版本已变化")
    current.status = "superseded"
    successor = GrowthMilestone(
        user_id=user_id, supersedes_milestone_id=current.id, target_id=current.target_id, gap_snapshot_id=current.gap_snapshot_id,
        request_id=_derived_request("milestone", current.id, current.version + 1), input_fingerprint=current.input_fingerprint, milestone_key=current.milestone_key,
        title=current.title, success_criteria=current.success_criteria, timeframe=current.timeframe, due_on=current.due_on,
        status=data.status, version=current.version + 1,
        confirmed_at=_now() if data.status == "confirmed" else current.confirmed_at,
        completed_at=_now() if data.status == "completed" else None,
    )
    db.add(successor); db.flush(); _audit(db, user_id=user_id, entity_type="growth_milestone", entity_id=successor.id, action=data.status, after={"supersedes": current.id, "version": successor.version})
    db.commit(); db.refresh(successor); return successor


def propose_milestone_action(db: Session, *, user_id: int, milestone_id: int) -> MilestoneActionProposal:
    milestone = _milestone(db, user_id=user_id, milestone_id=milestone_id, lock=True)
    if milestone.status not in {"confirmed", "in_progress"}:
        raise HTTPException(status_code=422, detail="只有本人已确认的里程碑可以生成当下行动候选")
    request_id = _derived_request("milestone-action", milestone.id, milestone.version)
    existing = db.query(GrowthWorkIntake).filter(GrowthWorkIntake.user_id == user_id, GrowthWorkIntake.request_id == request_id).first()
    candidate_key = f"milestone:{milestone.id}:v{milestone.version}"
    if existing is None:
        candidate = {"candidate_key": candidate_key, "title": milestone.title, "description": milestone.success_criteria, "fact_excerpt": "来自本人已确认的未来里程碑", "impact_level": "high", "energy_level": "unknown", "priority_order": 50, "selection_reason": "由已确认里程碑反推；仍需本人选择后才进入正式工作项", "confidence": 1.0}
        existing = GrowthWorkIntake(user_id=user_id, request_id=request_id, input_fingerprint=_hash(candidate), candidate_payload={"candidates": [candidate], "emotion": {"detected": False}}, parser_version="growth-milestone-v1", analysis_mode="rules", status="draft")
        db.add(existing); db.flush(); _audit(db, user_id=user_id, entity_type="growth_work_intake", entity_id=existing.id, action="milestone_action_proposed", after={"milestone_id": milestone.id})
        db.commit(); db.refresh(existing)
    return MilestoneActionProposal(milestone_id=milestone.id, intake_id=existing.id, candidate_key=candidate_key, title=milestone.title, note="这只是当下行动候选；请在确认步骤中选择后才会创建工作项。")


def direction_workspace(db: Session, *, user_id: int) -> DirectionWorkspace:
    targets = db.query(GrowthFutureTarget).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.status != "superseded").order_by(GrowthFutureTarget.created_at.desc()).all()
    current = next((item for item in targets if item.status == "active"), None)
    signals = db.query(GrowthMarketSignal).filter(GrowthMarketSignal.user_id == user_id, GrowthMarketSignal.target_id == current.id).order_by(GrowthMarketSignal.calculated_at.desc(), GrowthMarketSignal.occurrence_count.desc()).all() if current else []
    if signals:
        latest_batch = signals[0].batch_request_id
        signals = [item for item in signals if item.batch_request_id == latest_batch]
    gaps = db.query(GrowthGapSnapshot).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.status != "superseded").order_by(GrowthGapSnapshot.created_at.desc()).all()
    milestone_rows = db.query(GrowthMilestone).filter(GrowthMilestone.user_id == user_id).order_by(GrowthMilestone.milestone_key.asc(), GrowthMilestone.version.desc()).all()
    milestones: list[GrowthMilestone] = []
    seen: set[str] = set()
    for item in milestone_rows:
        if item.milestone_key not in seen and item.status != "superseded": milestones.append(item)
        seen.add(item.milestone_key)
    skills = db.query(GrowthSkillAssessment).filter(GrowthSkillAssessment.user_id == user_id, GrowthSkillAssessment.status == "confirmed", GrowthSkillAssessment.source_layer == "evidence_confirmed").all()
    chip_count = len(assets_workspace(db, user_id=user_id).career_chips)
    return DirectionWorkspace(targets=targets, current_target=current, market_signals=signals, gap_snapshots=gaps, milestones=milestones, confirmed_skill_names=[item.skill_name for item in skills], career_chip_count=chip_count, summary={"draft_targets": sum(item.status == "draft" for item in targets), "weak_signals": sum(item.status != "active" for item in signals), "pending_gaps": sum(item.status == "candidate" for item in gaps), "confirmed_milestones": sum(item.status in {"confirmed", "in_progress"} for item in milestones)})
