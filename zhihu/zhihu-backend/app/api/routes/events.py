from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_event
from app.db.session import get_db
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.models.user import User
from app.schemas.career_event import (
    ActionItemCreate,
    ActionItemResponse,
    ActionItemUpdate,
    CareerEventCreate,
    CareerEventDetail,
    CareerEventResponse,
    CareerEventUpdate,
    DecisionRecordCreate,
    DecisionRecordResponse,
    EvidenceCreate,
    EvidenceResponse,
    GuardianFindingCreate,
    GuardianFindingResponse,
    GuardianFindingUpdate,
    OutcomeCreate,
    OutcomeResponse,
)


router = APIRouter()


def _build_detail(db: Session, event: CareerEvent) -> CareerEventDetail:
    return CareerEventDetail(
        **CareerEventResponse.model_validate(event).model_dump(),
        evidence=db.query(Evidence).filter(Evidence.event_id == event.id).order_by(Evidence.id).all(),
        findings=db.query(GuardianFinding)
        .filter(GuardianFinding.event_id == event.id)
        .order_by(GuardianFinding.id)
        .all(),
        actions=db.query(ActionItem).filter(ActionItem.event_id == event.id).order_by(ActionItem.id).all(),
        decisions=db.query(DecisionRecord)
        .filter(DecisionRecord.event_id == event.id)
        .order_by(DecisionRecord.id)
        .all(),
        outcomes=db.query(Outcome).filter(Outcome.event_id == event.id).order_by(Outcome.id).all(),
    )


@router.get("/", response_model=list[CareerEventResponse])
def list_events(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(CareerEvent)
        .filter(CareerEvent.user_id == user.id)
        .order_by(CareerEvent.updated_at.desc(), CareerEvent.id.desc())
        .all()
    )


@router.post("/", response_model=CareerEventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    data: CareerEventCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = CareerEvent(user_id=user.id, **data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/{event_id}", response_model=CareerEventResponse)
def update_event(
    event_id: int,
    data: CareerEventUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = get_owned_event(db, event_id, user)
    if data.status == "completed":
        open_action = (
            db.query(ActionItem)
            .filter(
                ActionItem.event_id == event_id,
                ActionItem.status.in_(("draft", "pending")),
            )
            .first()
        )
        if open_action is not None:
            raise HTTPException(status_code=409, detail="仍有待处理行动，完成后才能关闭事件")
        open_finding = (
            db.query(GuardianFinding)
            .filter(
                GuardianFinding.event_id == event_id,
                GuardianFinding.status == "open",
                GuardianFinding.severity.in_(("high", "warning")),
            )
            .first()
        )
        if open_finding is not None:
            raise HTTPException(status_code=409, detail="仍有待确认结论，处理后才能关闭事件")
    event.status = data.status
    event.completed_at = (
        datetime.now(timezone.utc).replace(tzinfo=None)
        if data.status == "completed"
        else None
    )
    db.commit()
    db.refresh(event)
    return event


@router.get("/{event_id}", response_model=CareerEventDetail)
def get_event(
    event_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _build_detail(db, get_owned_event(db, event_id, user))


@router.post("/{event_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def add_evidence(
    event_id: int,
    data: EvidenceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    evidence = Evidence(event_id=event_id, **data.model_dump())
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{event_id}/findings", response_model=GuardianFindingResponse, status_code=status.HTTP_201_CREATED)
def add_finding(
    event_id: int,
    data: GuardianFindingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event = get_owned_event(db, event_id, user)
    if data.domain != event.event_type:
        raise HTTPException(status_code=400, detail="结论领域必须与职业事件一致")
    if data.evidence_id is not None:
        evidence = (
            db.query(Evidence)
            .filter(Evidence.id == data.evidence_id, Evidence.event_id == event_id)
            .first()
        )
        if evidence is None:
            raise HTTPException(status_code=404, detail="证据不存在")
    finding = GuardianFinding(event_id=event_id, **data.model_dump())
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.patch(
    "/{event_id}/findings/{finding_id}",
    response_model=GuardianFindingResponse,
)
def update_finding(
    event_id: int,
    finding_id: int,
    data: GuardianFindingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    finding = (
        db.query(GuardianFinding)
        .filter(GuardianFinding.id == finding_id, GuardianFinding.event_id == event_id)
        .first()
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="结论不存在")
    finding.status = data.status
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/{event_id}/actions", response_model=ActionItemResponse, status_code=status.HTTP_201_CREATED)
def add_action(
    event_id: int,
    data: ActionItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    if data.finding_id is not None:
        finding = (
            db.query(GuardianFinding)
            .filter(GuardianFinding.id == data.finding_id, GuardianFinding.event_id == event_id)
            .first()
        )
        if finding is None:
            raise HTTPException(status_code=404, detail="结论不存在")
    action = ActionItem(event_id=event_id, **data.model_dump())
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@router.patch(
    "/{event_id}/actions/{action_id}",
    response_model=ActionItemResponse,
)
def update_action(
    event_id: int,
    action_id: int,
    data: ActionItemUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    action = (
        db.query(ActionItem)
        .filter(ActionItem.id == action_id, ActionItem.event_id == event_id)
        .first()
    )
    if action is None:
        raise HTTPException(status_code=404, detail="行动不存在")
    if (
        action.requires_confirmation
        and action.confirmed_at is None
        and data.status in {"pending", "completed"}
        and not data.confirm
    ):
        raise HTTPException(status_code=409, detail="该行动需要用户确认后才能执行")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    action.status = data.status
    if data.confirm or data.status == "completed":
        action.confirmed_at = action.confirmed_at or now
    action.completed_at = now if data.status == "completed" else None
    db.commit()
    db.refresh(action)
    return action


@router.post("/{event_id}/decisions", response_model=DecisionRecordResponse, status_code=status.HTTP_201_CREATED)
def add_decision(
    event_id: int,
    data: DecisionRecordCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    decision = DecisionRecord(event_id=event_id, **data.model_dump())
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


@router.post("/{event_id}/outcomes", response_model=OutcomeResponse, status_code=status.HTTP_201_CREATED)
def add_outcome(
    event_id: int,
    data: OutcomeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_event(db, event_id, user)
    if data.action_id is not None:
        action = (
            db.query(ActionItem)
            .filter(ActionItem.id == data.action_id, ActionItem.event_id == event_id)
            .first()
        )
        if action is None:
            raise HTTPException(status_code=404, detail="行动不存在")
    outcome = Outcome(event_id=event_id, **data.model_dump())
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return outcome
