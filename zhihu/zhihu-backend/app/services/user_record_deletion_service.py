from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.models.contract import Contract
from app.models.finding import Finding
from app.models.journey_node import JourneyNode
from app.models.offer import Offer
from app.models.payslip import Payslip


def delete_event_graph(db: Session, event_ids: Iterable[int]) -> None:
    """Delete events owned by a record after the caller has verified ownership.

    The explicit order keeps MySQL foreign keys valid and makes the behavior
    independent from database-level cascade configuration.
    """

    normalized_ids = sorted({int(event_id) for event_id in event_ids if event_id is not None})
    if not normalized_ids:
        return
    db.query(Outcome).filter(Outcome.event_id.in_(normalized_ids)).delete(synchronize_session=False)
    db.query(DecisionRecord).filter(DecisionRecord.event_id.in_(normalized_ids)).delete(synchronize_session=False)
    db.query(ActionItem).filter(ActionItem.event_id.in_(normalized_ids)).delete(synchronize_session=False)
    db.query(GuardianFinding).filter(GuardianFinding.event_id.in_(normalized_ids)).delete(synchronize_session=False)
    db.query(Evidence).filter(Evidence.event_id.in_(normalized_ids)).delete(synchronize_session=False)
    db.query(CareerEvent).filter(CareerEvent.id.in_(normalized_ids)).delete(synchronize_session=False)


def delete_orphan_career_case(db: Session, case_id: int | None, user_id: int) -> bool:
    """Remove a legacy case only when no surviving business record uses it."""

    if case_id is None:
        return False
    still_used = any(
        query.first() is not None
        for query in (
            db.query(Offer.id).filter(Offer.case_id == case_id),
            db.query(Contract.id).filter(Contract.case_id == case_id),
            db.query(Payslip.id).filter(Payslip.case_id == case_id),
            db.query(CareerEvent.id).filter(CareerEvent.legacy_case_id == case_id),
            db.query(JourneyNode.id).filter(JourneyNode.case_id == case_id),
        )
    )
    if still_used:
        return False
    db.query(Finding).filter(Finding.case_id == case_id).delete(synchronize_session=False)
    deleted = db.query(CareerCase).filter(
        CareerCase.id == case_id,
        CareerCase.user_id == user_id,
    ).delete(synchronize_session=False)
    return bool(deleted)
