from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.growth import (
    GrowthAnalyzeRequest,
    GrowthAnalyzeResponse,
    GrowthConfirmIntakeRequest,
    GrowthConfirmIntakeResponse,
    GrowthUpdateWorkEventRequest,
    GrowthUpdateWorkItemRequest,
    GrowthUpdateWorkItemResponse,
    GrowthWeeklyReportCreate,
    GrowthWeeklyReportResponse,
    GrowthWeeklyReportUpdate,
    GrowthWorkEventResponse,
    GrowthWorkspaceResponse,
)
from app.services.growth_work_service import (
    analyze_growth_intake,
    confirm_growth_intake,
    create_growth_weekly_report,
    delete_growth_emotion_note,
    growth_workspace,
    update_growth_weekly_report,
    update_growth_work_event,
    update_growth_work_item,
)


router = APIRouter()


@router.get("/workspace", response_model=GrowthWorkspaceResponse)
def get_growth_workspace(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return growth_workspace(db, user_id=user.id)


@router.post(
    "/intakes/analyze",
    response_model=GrowthAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_intake(
    data: GrowthAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return analyze_growth_intake(db, user=user, data=data)


@router.post(
    "/intakes/{intake_id}/confirm",
    response_model=GrowthConfirmIntakeResponse,
    status_code=status.HTTP_201_CREATED,
)
def confirm_intake(
    intake_id: int,
    data: GrowthConfirmIntakeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return confirm_growth_intake(db, user_id=user.id, intake_id=intake_id, data=data)


@router.patch("/work-items/{item_id}", response_model=GrowthUpdateWorkItemResponse)
def update_work_item(
    item_id: int,
    data: GrowthUpdateWorkItemRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_growth_work_item(db, user_id=user.id, item_id=item_id, data=data)


@router.patch("/work-events/{event_id}", response_model=GrowthWorkEventResponse)
def update_work_event(
    event_id: int,
    data: GrowthUpdateWorkEventRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_growth_work_event(db, user_id=user.id, event_id=event_id, data=data)


@router.post(
    "/weekly-reports",
    response_model=GrowthWeeklyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_weekly_report(
    data: GrowthWeeklyReportCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_growth_weekly_report(db, user_id=user.id, data=data)


@router.patch("/weekly-reports/{report_id}", response_model=GrowthWeeklyReportResponse)
def update_weekly_report(
    report_id: int,
    data: GrowthWeeklyReportUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_growth_weekly_report(db, user_id=user.id, report_id=report_id, data=data)


@router.delete("/emotion-notes/{note_id}")
def delete_emotion_note(
    note_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_growth_emotion_note(db, user_id=user.id, note_id=note_id)
    return {"ok": True}
