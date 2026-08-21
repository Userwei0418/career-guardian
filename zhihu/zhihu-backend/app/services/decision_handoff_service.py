from typing import Optional

from sqlalchemy.orm import Session

from app.models.career_case import CareerCase
from app.models.career_event import CareerEvent, Outcome
from app.models.offer import Offer


def record_decision_handoff_outcome(
    db: Session,
    *,
    user_id: int,
    handoff_event: CareerEvent,
    outcome_type: str,
    result: str,
    action_id: Optional[int] = None,
) -> Optional[Outcome]:
    """把真实交接结果回写到原 Offer 决策事件，并保持幂等。"""
    stage = handoff_event.stage or ""
    if not stage.startswith("offer:"):
        return None
    try:
        offer_id = int(stage.split(":", 1)[1])
    except (TypeError, ValueError):
        return None
    offer = (
        db.query(Offer)
        .join(CareerCase, CareerCase.id == Offer.case_id)
        .filter(Offer.id == offer_id, CareerCase.user_id == user_id)
        .first()
    )
    if offer is None or offer.career_event_id is None:
        return None
    existing = (
        db.query(Outcome)
        .filter(
            Outcome.event_id == offer.career_event_id,
            Outcome.outcome_type == outcome_type,
            Outcome.result == result,
        )
        .first()
    )
    if existing is not None:
        return existing
    # Outcome.action_id 的产品语义是“当前事件内的行动”。交接行动属于下游事件，
    # 不能把它挂到原 Offer 决策事件上形成跨事件的伪关联。
    outcome_action_id = action_id if handoff_event.id == offer.career_event_id else None
    outcome = Outcome(
        event_id=offer.career_event_id,
        action_id=outcome_action_id,
        outcome_type=outcome_type,
        result=result,
    )
    db.add(outcome)
    db.flush()
    return outcome
