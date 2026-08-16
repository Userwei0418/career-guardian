from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.offer import Offer
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord
from app.models.opportunity_target import JobTarget
from app.models.personal_attachment import PersonalAttachmentVersion
from app.schemas.career_event import DecisionRecordResponse
from app.schemas.offer import (
    OfferCreateRequest,
    OfferDecisionHandoff,
    OfferDecisionRequest,
    OfferDecisionResult,
    OfferResponse,
    OfferUpdateRequest,
)

router = APIRouter()


_ACCEPTANCE_HANDOFFS = (
    (
        "rights",
        "入职合同与承诺核对",
        "上传劳动合同并核对 Offer 承诺",
        "收到劳动合同后上传原件，逐项核对薪资、试用期、工作地点等承诺；当前只建立待办，不代表合同已经收到。",
        "/rights",
    ),
    (
        "income",
        "首份工资与 Offer 一致性核对",
        "收到首份工资条后核对 Offer—合同—工资",
        "入职并收到首份工资条后，核对实发、扣款和社保公积金口径；当前只建立待办，不代表工资已经发放。",
        "/income",
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
    db: Session, user_id: int, offer: Offer
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
                href=href,
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
    _validate_offer_links(db, user.id, offer_data)
    offer_data["case_id"] = case.id
    offer_data["facts_confirmed_at"] = datetime.now(timezone.utc)

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
    db.commit()
    db.refresh(offer)
    return offer


@router.get("/{offer_id}", response_model=OfferResponse)
def get_offer(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_offer(db, offer_id, user)


@router.put("/{offer_id}", response_model=OfferResponse)
def update_offer(offer_id: int, req: OfferUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = get_owned_offer(db, offer_id, user)
    update_data = req.model_dump(exclude_unset=True)
    _validate_offer_links(db, user.id, update_data)
    for key, value in update_data.items():
        setattr(offer, key, value)
    offer.facts_confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(offer)
    return offer


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
    now = _naive_utc_now()
    next_review_at = data.next_review_at
    if next_review_at is not None and next_review_at.tzinfo is not None:
        next_review_at = next_review_at.astimezone(timezone.utc).replace(tzinfo=None)
    if data.choice == "on_hold":
        if next_review_at is None:
            raise HTTPException(status_code=400, detail="暂缓决定时需要填写下次复盘时间")
        if next_review_at <= now:
            raise HTTPException(status_code=400, detail="下次复盘时间必须晚于当前时间")

    latest = (
        db.query(DecisionRecord)
        .filter(
            DecisionRecord.event_id == event.id,
            DecisionRecord.decision_type == "offer_decision",
        )
        .order_by(DecisionRecord.decided_at.desc(), DecisionRecord.id.desc())
        .first()
    )
    if latest is not None and latest.choice == data.choice and latest.rationale == data.rationale:
        decision = latest
    else:
        decision = DecisionRecord(
            event_id=event.id,
            decision_type="offer_decision",
            choice=data.choice,
            rationale=data.rationale,
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
            handoffs = _upsert_acceptance_handoffs(db, user.id, offer)
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
