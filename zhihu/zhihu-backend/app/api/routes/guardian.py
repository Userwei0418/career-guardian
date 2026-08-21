from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.guardian import DemoJourneyResponse, GuardianStateResponse
from app.schemas.guardian import GrowthDraftRequest, GrowthDraftResponse
from app.api.routes.market import get_market_client
from app.services.growth_service import create_growth_draft
from app.services.integrated_demo_service import create_integrated_demo_journey
from app.services.market_insight_client import MarketInsightClient
from app.services.guardian_state_service import build_guardian_state


router = APIRouter()


@router.get("/state", response_model=GuardianStateResponse)
def get_guardian_state(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_guardian_state(db, user.id)


@router.post(
    "/demo-journey",
    response_model=DemoJourneyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_demo_journey(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """显式载入脱敏 fixture，用于 V2 连续链路演示。"""
    return create_integrated_demo_journey(db, user)


@router.post("/growth-draft", response_model=GrowthDraftResponse)
def build_growth_draft(
    data: GrowthDraftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    insight = market_client.skill_insight(data.job_family, data.limit)
    try:
        return create_growth_draft(
            db,
            user,
            data.job_family,
            insight,
            career_event_id=data.career_event_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
