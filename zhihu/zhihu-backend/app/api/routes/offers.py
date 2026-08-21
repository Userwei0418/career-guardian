from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.offer import FactAssertion, Offer, OfferAnalysisSnapshot, OfferDecisionContext, OfferRevision
from app.models.offer_comparison import OfferComparison
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Outcome
from app.models.contract import Contract
from app.models.opportunity_target import JobTarget
from app.models.payslip import Payslip
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user_profile import UserProfile
from app.schemas.career_event import DecisionRecordResponse, OutcomeResponse
from app.schemas.offer import (
    OfferCreateRequest,
    OfferDecisionAttentionResponse,
    OfferDecisionPreflightResponse,
    OfferDecisionContextResponse,
    OfferDecisionContextUpdate,
    OfferDecisionSetupRequest,
    OfferDecisionSetupResponse,
    OfferDecisionHandoff,
    OfferDecisionRequest,
    OfferDecisionResult,
    OfferFactsResponse,
    OfferResponse,
    OfferRevisionCreateRequest,
    OfferRevisionResponse,
    OfferUpdateRequest,
    OfferValidationResponse,
)
from app.services.offer_fact_service import (
    build_decision_preflight,
    build_offer_facts,
    build_validation_result,
    create_offer_revision,
)
from app.services.user_record_deletion_service import delete_event_graph, delete_orphan_career_case

router = APIRouter()


_ACCEPTANCE_HANDOFFS = (
    (
        "rights",
        "入职合同与承诺核对",
        "上传劳动合同并核对 Offer 承诺",
        "收到劳动合同后上传原件，逐项核对薪资、试用期、工作地点等承诺；当前只建立待办，不代表合同已经收到。",
        "/contract/new",
    ),
    (
        "income",
        "首份工资与 Offer 一致性核对",
        "收到首份工资条后核对 Offer—合同—工资",
        "入职并收到首份工资条后，核对实发、扣款和社保公积金口径；当前只建立待办，不代表工资已经发放。",
        "/payslip",
    ),
    (
        "growth",
        "入职阶段成长跟踪",
        "确认入职 30 天阶段任务",
        "入职后结合岗位目标确认前 30 天任务、需要补齐的能力和阶段成果；当前只建立待办。",
        "/growth",
    ),
)


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _offer_label(offer: Offer) -> str:
    return offer.name or " · ".join(filter(None, (offer.company_name, offer.job_title))) or f"Offer {offer.id}"


def _hold_action_title(offer: Offer) -> str:
    return f"重新评估：{_offer_label(offer)}"


def _build_offer_attention(
    offer: Offer,
    pending_actions: list[ActionItem],
    *,
    now: datetime,
) -> OfferDecisionAttentionResponse:
    review_action = next(
        (action for action in pending_actions if action.title == _hold_action_title(offer)),
        None,
    )
    candidates = []
    if offer.decision_status in {"evaluating", "on_hold"} and offer.response_deadline is not None:
        candidates.append((offer.response_deadline, "response_deadline", "Offer 回复期限"))
    for action in pending_actions:
        if action.due_at is not None:
            kind = "review" if action is review_action else "action"
            candidates.append((action.due_at, kind, action.title))
    candidates.sort(key=lambda item: item[0])
    next_due_at, next_kind, next_title = candidates[0] if candidates else (None, None, None)
    overdue_count = len([item for item in candidates if item[0] < now])
    urgent_threshold_seconds = 3 * 24 * 60 * 60
    is_urgent = bool(
        next_due_at
        and (next_due_at < now or (next_due_at - now).total_seconds() <= urgent_threshold_seconds)
    )
    if next_due_at is None:
        primary_message = "回复期限待确认；先记录不等于接受，可以向 HR 问清最晚时间。"
    elif next_due_at < now and next_kind == "response_deadline":
        primary_message = "记录的回复期限已经到了；先确认这份 Offer 是否仍可继续沟通。"
    elif next_due_at < now and next_kind == "review":
        primary_message = "你为暂缓决定设置的复盘时间已经到了；先看事实有没有变化。"
    elif next_due_at < now:
        primary_message = f"待办“{next_title}”已经到期；先确认是否仍需要推进。"
    elif next_kind == "response_deadline":
        primary_message = "回复期限临近；先处理最可能改变选择的事实，再决定是否需要申请更多时间。"
    elif next_kind == "review":
        primary_message = "下次复盘时间已记录；到时重新看事实和现实边界，不需要现在勉强决定。"
    else:
        primary_message = f"下一项待办是“{next_title}”；它不会替你自动联系任何人。"
    return OfferDecisionAttentionResponse(
        offer_id=offer.id,
        response_deadline=offer.response_deadline,
        review_due_at=review_action.due_at if review_action else None,
        next_due_at=next_due_at,
        next_kind=next_kind,
        overdue_count=overdue_count,
        pending_count=len(pending_actions) + (1 if offer.decision_status in {"evaluating", "on_hold"} and offer.response_deadline else 0),
        is_overdue=overdue_count > 0,
        is_urgent=is_urgent,
        primary_message=primary_message,
        primary_href=f"/decision?offerId={offer.id}&action=decide",
    )


def _archive_acceptance_handoffs(db: Session, user_id: int, offer_id: int) -> None:
    events = (
        db.query(CareerEvent)
        .filter(
            CareerEvent.user_id == user_id,
            CareerEvent.stage == f"offer:{offer_id}",
            CareerEvent.event_type.in_(("rights", "income", "growth")),
            CareerEvent.status.in_(("active", "attention")),
        )
        .all()
    )
    for event in events:
        event.status = "archived"


def _upsert_acceptance_handoffs(
    db: Session, user_id: int, offer: Offer, decision_record_id: int
) -> list[OfferDecisionHandoff]:
    results: list[OfferDecisionHandoff] = []
    offer_label = _offer_label(offer)
    for event_type, title, action_title, description, href in _ACCEPTANCE_HANDOFFS:
        event = (
            db.query(CareerEvent)
            .filter(
                CareerEvent.user_id == user_id,
                CareerEvent.event_type == event_type,
                CareerEvent.stage == f"offer:{offer.id}",
            )
            .first()
        )
        if event is None:
            event = CareerEvent(
                user_id=user_id,
                event_type=event_type,
                title=f"{offer_label}：{title}"[:200],
                status="active",
                stage=f"offer:{offer.id}",
            )
            db.add(event)
            db.flush()
        elif event.status == "archived":
            event.status = "active"
            event.completed_at = None

        action = (
            db.query(ActionItem)
            .filter(ActionItem.event_id == event.id, ActionItem.title == action_title)
            .first()
        )
        if action is None:
            action = ActionItem(
                event_id=event.id,
                title=action_title,
                description=description,
                status="pending",
                priority=30,
                requires_confirmation=True,
            )
            db.add(action)
            db.flush()
        results.append(
            OfferDecisionHandoff(
                event_id=event.id,
                event_type=event_type,
                title=event.title,
                action_id=action.id,
                action_title=action.title,
                href=f"{href}?offerId={offer.id}&eventId={event.id}&actionId={action.id}&decisionRecordId={decision_record_id}",
            )
        )
    return results


def _validate_offer_links(db: Session, user_id: int, data: dict) -> None:
    target_id = data.get("job_target_id")
    if target_id is not None:
        target = db.query(JobTarget).filter(JobTarget.id == target_id, JobTarget.user_id == user_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="目标岗位不存在")

    attachment_id = data.get("source_attachment_id")
    if attachment_id is not None:
        attachment = (
            db.query(PersonalAttachmentVersion)
            .filter(
                PersonalAttachmentVersion.id == attachment_id,
                PersonalAttachmentVersion.user_id == user_id,
                PersonalAttachmentVersion.document_type == "offer",
            )
            .first()
        )
        if attachment is None:
            raise HTTPException(status_code=404, detail="Offer 附件版本不存在")


def _upsert_decision_context(
    db: Session,
    *,
    offer_id: int,
    user_id: int,
    data: OfferDecisionContextUpdate,
) -> OfferDecisionContext:
    context_row = (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer_id,
            OfferDecisionContext.user_id == user_id,
        )
        .first()
    )
    if context_row is None:
        context_row = OfferDecisionContext(offer_id=offer_id, user_id=user_id)
        db.add(context_row)
    for key, value in data.model_dump().items():
        setattr(context_row, key, value)
    return context_row


@router.get("/", response_model=list[OfferResponse])
def list_offers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case_ids = [c.id for c in db.query(CareerCase).filter(CareerCase.user_id == user.id).all()]
    if not case_ids:
        return []
    offers = (
        db.query(Offer)
        .filter(Offer.case_id.in_(case_ids))
        .order_by(Offer.updated_at.desc(), Offer.id.desc())
        .all()
    )
    return offers


@router.post("/", response_model=OfferResponse)
def create_offer(req: OfferCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.case_id:
        case = db.query(CareerCase).filter(CareerCase.id == req.case_id, CareerCase.user_id == user.id).first()
        if not case:
            raise HTTPException(status_code=404, detail="任务不存在")
    else:
        case = CareerCase(user_id=user.id, type="offer_analysis", title=f"{req.company_name or '新'} Offer 分析")
        db.add(case)
        db.flush()
    offer_data = req.model_dump(exclude_unset=True)
    confirm_facts = bool(offer_data.pop("confirm_facts", False))
    _validate_offer_links(db, user.id, offer_data)
    offer_data["case_id"] = case.id

    if req.career_event_id is not None:
        event = get_owned_event(db, req.career_event_id, user)
        if event.event_type != "decision":
            raise HTTPException(status_code=400, detail="Offer 必须关联决策守护事件")
    else:
        event = CareerEvent(
            user_id=user.id,
            event_type="decision",
            title=f"{req.company_name or '新'} Offer 决策",
            status="active",
        )
        db.add(event)
        db.flush()
        offer_data["career_event_id"] = event.id

    offer = Offer(**offer_data)
    db.add(offer)
    db.flush()
    if confirm_facts:
        create_offer_revision(db, offer, user.id, reason="user_confirmation")
    db.commit()
    db.refresh(offer)
    return offer


@router.get("/{offer_id}", response_model=OfferResponse)
def get_offer(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_offer(db, offer_id, user)


@router.delete("/{offer_id}")
def delete_offer(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete an uncommitted Offer archive without erasing audited outcomes."""

    offer = get_owned_offer(db, offer_id, user)
    event_id = offer.career_event_id
    case_id = offer.case_id
    revision_ids = [item.id for item in db.query(OfferRevision.id).filter(OfferRevision.offer_id == offer.id).all()]
    snapshot_ids = [item.id for item in db.query(OfferAnalysisSnapshot.id).filter(OfferAnalysisSnapshot.offer_id == offer.id).all()]

    blockers: list[str] = []
    if offer.decision_status not in {"evaluating", "on_hold"}:
        blockers.append("已经记录接受、拒绝或过期状态")
    if db.query(OfferComparison.id).filter(or_(OfferComparison.offer_a_id == offer.id, OfferComparison.offer_b_id == offer.id)).first():
        blockers.append("已经进入 Offer 比较历史")
    contract_filters = [Contract.linked_offer_id == offer.id, Contract.case_id == case_id]
    payslip_filters = [Payslip.linked_offer_id == offer.id, Payslip.case_id == case_id]
    if event_id is not None:
        contract_filters.append(Contract.career_event_id == event_id)
        payslip_filters.append(Payslip.career_event_id == event_id)
    if db.query(Contract.id).filter(or_(*contract_filters)).first():
        blockers.append("已经关联合同")
    if db.query(Payslip.id).filter(or_(*payslip_filters)).first():
        blockers.append("已经关联工资条")
    decision_filters = []
    if event_id is not None:
        decision_filters.append(DecisionRecord.event_id == event_id)
    if revision_ids:
        decision_filters.append(DecisionRecord.offer_revision_id.in_(revision_ids))
    if snapshot_ids:
        decision_filters.append(DecisionRecord.analysis_snapshot_id.in_(snapshot_ids))
    if decision_filters and db.query(DecisionRecord.id).filter(or_(*decision_filters)).first():
        blockers.append("已经保存决定历史")
    if event_id is not None and db.query(Outcome.id).filter(Outcome.event_id == event_id).first():
        blockers.append("已经产生决定后的结果")
    if blockers:
        raise HTTPException(
            status_code=409,
            detail=f"这份 Offer 不能直接删除：{'；'.join(blockers)}。为保留决定依据，请留在历史档案中。",
        )

    db.query(FactAssertion).filter(FactAssertion.offer_id == offer.id).update(
        {FactAssertion.supersedes_assertion_id: None}, synchronize_session=False
    )
    db.query(FactAssertion).filter(FactAssertion.offer_id == offer.id).delete(synchronize_session=False)
    db.query(OfferDecisionContext).filter(OfferDecisionContext.offer_id == offer.id).delete(synchronize_session=False)
    db.query(OfferAnalysisSnapshot).filter(OfferAnalysisSnapshot.offer_id == offer.id).delete(synchronize_session=False)
    db.query(OfferRevision).filter(OfferRevision.offer_id == offer.id).update(
        {OfferRevision.supersedes_revision_id: None}, synchronize_session=False
    )
    db.query(OfferRevision).filter(OfferRevision.offer_id == offer.id).delete(synchronize_session=False)
    attachment_retained = offer.source_attachment_id is not None
    db.delete(offer)
    db.flush()
    if event_id is not None:
        delete_event_graph(db, [event_id])
    delete_orphan_career_case(db, case_id, user.id)
    db.commit()
    return {
        "ok": True,
        "offer_id": offer_id,
        "message": "Offer 档案已删除",
        "source_attachment_retained": attachment_retained,
    }


@router.put("/{offer_id}", response_model=OfferResponse)
def update_offer(offer_id: int, req: OfferUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = get_owned_offer(db, offer_id, user)
    update_data = req.model_dump(exclude_unset=True)
    confirm_facts = bool(update_data.pop("confirm_facts", False))
    _validate_offer_links(db, user.id, update_data)
    for key, value in update_data.items():
        setattr(offer, key, value)
    if confirm_facts:
        create_offer_revision(db, offer, user.id, reason="user_confirmation")
    db.commit()
    db.refresh(offer)
    return offer


@router.get("/{offer_id}/facts", response_model=OfferFactsResponse)
def get_offer_facts(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    return build_offer_facts(db, offer)


@router.get(
    "/{offer_id}/decision-context",
    response_model=Optional[OfferDecisionContextResponse],
)
def get_offer_decision_context(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_offer(db, offer_id, user)
    return (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer_id,
            OfferDecisionContext.user_id == user.id,
        )
        .first()
    )


@router.put(
    "/{offer_id}/decision-context",
    response_model=OfferDecisionContextResponse,
)
def update_offer_decision_context(
    offer_id: int,
    data: OfferDecisionContextUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_offer(db, offer_id, user)
    context_row = _upsert_decision_context(
        db,
        offer_id=offer_id,
        user_id=user.id,
        data=data,
    )
    db.commit()
    db.refresh(context_row)
    return context_row


@router.put(
    "/{offer_id}/decision-setup",
    response_model=OfferDecisionSetupResponse,
)
def update_offer_decision_setup(
    offer_id: int,
    data: OfferDecisionSetupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_offer(db, offer_id, user)
    context_row = _upsert_decision_context(
        db,
        offer_id=offer_id,
        user_id=user.id,
        data=data.decision_context,
    )
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.priorities = list(data.priorities)
    profile.monthly_budget = data.monthly_budget
    profile.savings_goal = data.savings_goal
    db.commit()
    db.refresh(context_row)
    return OfferDecisionSetupResponse(
        offer_id=offer_id,
        priorities=list(profile.priorities or []),
        monthly_budget=profile.monthly_budget,
        savings_goal=profile.savings_goal,
        decision_context=OfferDecisionContextResponse.model_validate(context_row),
    )


@router.post("/{offer_id}/revisions", response_model=OfferRevisionResponse)
def create_revision(
    offer_id: int,
    data: OfferRevisionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    revision = create_offer_revision(db, offer, user.id, reason=data.reason)
    db.commit()
    db.refresh(revision)
    return revision


@router.post("/{offer_id}/validate", response_model=OfferValidationResponse)
def validate_offer(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    return build_validation_result(offer)


@router.post("/{offer_id}/decision-preflight", response_model=OfferDecisionPreflightResponse)
def decision_preflight(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    return build_decision_preflight(db, offer)


@router.get("/{offer_id}/decisions", response_model=list[DecisionRecordResponse])
def list_offer_decisions(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    if offer.career_event_id is None:
        return []
    return (
        db.query(DecisionRecord)
        .filter(
            DecisionRecord.event_id == offer.career_event_id,
            DecisionRecord.decision_type == "offer_decision",
        )
        .order_by(DecisionRecord.decided_at.desc(), DecisionRecord.id.desc())
        .all()
    )


@router.get("/{offer_id}/outcomes", response_model=list[OutcomeResponse])
def list_offer_outcomes(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    if offer.career_event_id is None:
        return []
    return (
        db.query(Outcome)
        .filter(Outcome.event_id == offer.career_event_id)
        .order_by(Outcome.recorded_at.desc(), Outcome.id.desc())
        .all()
    )


@router.get(
    "/{offer_id}/attention",
    response_model=OfferDecisionAttentionResponse,
)
def get_offer_decision_attention(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    now = _naive_utc_now()
    pending_actions = []
    if offer.career_event_id is not None:
        pending_actions = (
            db.query(ActionItem)
            .filter(
                ActionItem.event_id == offer.career_event_id,
                ActionItem.status.in_(("draft", "pending")),
            )
            .order_by(ActionItem.due_at.asc(), ActionItem.priority.asc(), ActionItem.id.asc())
            .all()
        )
    return _build_offer_attention(offer, pending_actions, now=now)


@router.post("/{offer_id}/decision", response_model=OfferDecisionResult)
def decide_offer(
    offer_id: int,
    data: OfferDecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    if offer.career_event_id is None:
        raise HTTPException(status_code=409, detail="Offer 尚未关联决策事件")
    event = get_owned_event(db, offer.career_event_id, user)
    preflight = build_decision_preflight(db, offer)
    if preflight["requires_acknowledgement"] and not data.acknowledge_blockers:
        raise HTTPException(status_code=409, detail="这份 Offer 仍有待确认或冲突事实，请先查看决定前检查并明确知晓后再记录决定")
    if data.offer_revision_id is not None:
        revision = (
            db.query(OfferRevision)
            .filter(OfferRevision.id == data.offer_revision_id, OfferRevision.offer_id == offer.id)
            .first()
        )
        if revision is None:
            raise HTTPException(status_code=409, detail="决定所依据的 Offer 版本已不可用，请重新检查当前事实")
        if preflight["offer_revision_id"] != revision.id:
            raise HTTPException(status_code=409, detail="Offer 事实已经变化，请重新查看决定前检查")
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    decision_context = (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer.id,
            OfferDecisionContext.user_id == user.id,
        )
        .first()
    )
    analysis_snapshot = None
    if data.analysis_snapshot_id is not None:
        analysis_snapshot = (
            db.query(OfferAnalysisSnapshot)
            .filter(
                OfferAnalysisSnapshot.id == data.analysis_snapshot_id,
                OfferAnalysisSnapshot.offer_id == offer.id,
                OfferAnalysisSnapshot.user_id == user.id,
            )
            .first()
        )
        if analysis_snapshot is None:
            raise HTTPException(status_code=409, detail="保存的分析快照不存在或不属于这份 Offer")
        if analysis_snapshot.offer_revision_id != preflight["offer_revision_id"]:
            raise HTTPException(status_code=409, detail="Offer 事实已变化，请重新分析并保存当前快照")
        if offer.updated_at and analysis_snapshot.created_at and offer.updated_at > analysis_snapshot.created_at:
            raise HTTPException(status_code=409, detail="Offer 档案在分析后有更新，请重新保存分析快照")
        if profile and profile.updated_at and analysis_snapshot.created_at and profile.updated_at > analysis_snapshot.created_at:
            raise HTTPException(status_code=409, detail="个人优先项或生活底线已变化，请重新保存分析快照")
        if decision_context and decision_context.updated_at and analysis_snapshot.created_at and decision_context.updated_at > analysis_snapshot.created_at:
            raise HTTPException(status_code=409, detail="现实替代、红线或取舍已变化，请重新保存分析快照")
    now = _naive_utc_now()
    next_review_at = data.next_review_at
    if next_review_at is not None and next_review_at.tzinfo is not None:
        next_review_at = next_review_at.astimezone(timezone.utc).replace(tzinfo=None)
    if data.choice == "on_hold":
        if next_review_at is None:
            raise HTTPException(status_code=400, detail="暂缓决定时需要填写下次复盘时间")
        if next_review_at <= now:
            raise HTTPException(status_code=400, detail="下次复盘时间必须晚于当前时间")

    fact_snapshot = build_offer_facts(db, offer)
    analysis_context = jsonable_encoder(data.analysis_context) if data.analysis_context else None
    if analysis_snapshot is not None:
        saved_report = analysis_snapshot.result_snapshot or {}
        saved_assumptions = analysis_snapshot.assumptions or {}
        saved_market = saved_report.get("market") or {}
        analysis_context = {
            "living_cost": saved_assumptions.get("living_cost"),
            "living_cost_source": saved_assumptions.get("living_cost_source"),
            "variable_realization": saved_assumptions.get("variable_realization"),
            "extra_salary_months_realization": saved_assumptions.get("extra_salary_months_realization"),
            "market_availability": saved_market.get("availability"),
            "market_data_mode": saved_market.get("data_mode"),
            "market_description": saved_market.get("description"),
            "market_sample_size": saved_market.get("sample_size"),
            "market_quality_grade": saved_market.get("quality_grade"),
            "market_methodology_version": saved_market.get("methodology_version"),
            "market_source_names": [
                source.get("source_name")
                for source in (saved_market.get("sources") or [])[:20]
                if source.get("source_name")
            ],
            "captured_at": analysis_snapshot.created_at,
        }
    preflight_snapshot = {
        **jsonable_encoder(preflight),
        "offer_snapshot": jsonable_encoder(OfferResponse.model_validate(offer)),
        "fact_snapshot": jsonable_encoder(fact_snapshot),
        "preference_snapshot": {
            "priorities": list(profile.priorities or []) if profile else [],
            "monthly_budget": profile.monthly_budget if profile else None,
            "savings_goal": profile.savings_goal if profile else None,
        },
        "analysis_context": jsonable_encoder(analysis_context),
        "analysis_snapshot_id": analysis_snapshot.id if analysis_snapshot else None,
        "snapshot_scope": "offer_facts_preferences_and_displayed_analysis_context",
    }
    latest = (
        db.query(DecisionRecord)
        .filter(
            DecisionRecord.event_id == event.id,
            DecisionRecord.decision_type == "offer_decision",
        )
        .order_by(DecisionRecord.decided_at.desc(), DecisionRecord.id.desc())
        .first()
    )
    latest_preflight = latest.preflight_snapshot if latest is not None else None
    same_decision_basis = bool(
        latest_preflight
        and latest_preflight.get("fact_snapshot") == preflight_snapshot.get("fact_snapshot")
        and latest_preflight.get("preference_snapshot") == preflight_snapshot.get("preference_snapshot")
        and latest_preflight.get("analysis_context") == preflight_snapshot.get("analysis_context")
        and latest_preflight.get("analysis_snapshot_id") == preflight_snapshot.get("analysis_snapshot_id")
    )
    if (
        latest is not None
        and latest.choice == data.choice
        and latest.rationale == data.rationale
        and latest.offer_revision_id == data.offer_revision_id
        and latest.analysis_snapshot_id == (analysis_snapshot.id if analysis_snapshot else None)
        and same_decision_basis
        and latest.acknowledged_unknowns == data.acknowledge_blockers
    ):
        decision = latest
    else:
        decision = DecisionRecord(
            event_id=event.id,
            decision_type="offer_decision",
            choice=data.choice,
            rationale=data.rationale,
            offer_revision_id=data.offer_revision_id,
            analysis_snapshot_id=analysis_snapshot.id if analysis_snapshot else None,
            preflight_snapshot=preflight_snapshot,
            acknowledged_unknowns=data.acknowledge_blockers,
            decided_at=now,
        )
        db.add(decision)
        db.flush()

    offer.decision_status = data.choice
    event.stage = data.choice
    handoffs: list[OfferDecisionHandoff] = []
    hold_action = (
        db.query(ActionItem)
        .filter(ActionItem.event_id == event.id, ActionItem.title == _hold_action_title(offer))
        .first()
    )
    if data.choice == "on_hold":
        event.status = "attention"
        event.deadline = next_review_at
        event.completed_at = None
        if hold_action is None:
            hold_action = ActionItem(
                event_id=event.id,
                title=_hold_action_title(offer),
                description="按已记录的决定理由重新检查条件变化，并在回复期限前完成最终选择。",
                status="pending",
                priority=20,
                due_at=next_review_at,
                requires_confirmation=True,
            )
            db.add(hold_action)
        else:
            hold_action.status = "pending"
            hold_action.due_at = next_review_at
            hold_action.completed_at = None
        _archive_acceptance_handoffs(db, user.id, offer.id)
    else:
        event.status = "completed"
        event.deadline = offer.response_deadline
        event.completed_at = now
        if hold_action is not None and hold_action.status in ("draft", "pending"):
            hold_action.status = "completed"
            hold_action.completed_at = now
        if data.choice == "accepted":
            handoffs = _upsert_acceptance_handoffs(db, user.id, offer, decision.id)
        else:
            _archive_acceptance_handoffs(db, user.id, offer.id)

    db.commit()
    db.refresh(decision)
    return OfferDecisionResult(
        offer_id=offer.id,
        decision_status=data.choice,
        decision_record_id=decision.id,
        decision_event_id=event.id,
        decided_at=decision.decided_at,
        handoffs=handoffs,
    )
