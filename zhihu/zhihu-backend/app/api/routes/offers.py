from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.offer import Offer
from app.models.career_case import CareerCase
from app.models.career_event import CareerEvent
from app.models.opportunity_target import JobTarget
from app.models.personal_attachment import PersonalAttachmentVersion
from app.schemas.offer import OfferCreateRequest, OfferUpdateRequest, OfferResponse

router = APIRouter()


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
