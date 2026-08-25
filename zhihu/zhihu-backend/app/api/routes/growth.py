from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.growth import GrowthFutureTarget
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
from app.schemas.growth_assets import (
    EvidenceCreate,
    EvidenceResponse,
    EvidenceUpdate,
    GrowthAssetsExport,
    GrowthAssetsWorkspace,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
    ReflectionCreate,
    ReflectionResponse,
    ReflectionUpdate,
    SkillAssessmentResponse,
    SkillCandidateCreate,
    SkillConfirmRequest,
)
from app.services.growth_asset_service import (
    assets_workspace,
    confirm_skill,
    create_evidence,
    create_portfolio,
    create_reflection,
    create_skill_candidate,
    delete_evidence,
    delete_portfolio,
    export_assets,
    update_evidence,
    update_portfolio,
    update_reflection,
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
from app.api.routes.market import get_market_client
from app.schemas.growth_direction import (
    DirectionWorkspace,
    FutureTargetConfirm,
    FutureTargetCreate,
    FutureTargetResponse,
    GapSnapshotConfirm,
    GapSnapshotCreate,
    GapSnapshotResponse,
    MarketRefreshResponse,
    MarketSignalRefresh,
    MilestoneActionProposal,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneUpdate,
)
from app.services.growth_direction_service import (
    confirm_gap_snapshot,
    confirm_target,
    create_gap_snapshot,
    create_milestone,
    create_target,
    direction_workspace,
    propose_milestone_action,
    refresh_market_signals,
    update_milestone,
)
from app.services.market_insight_client import MarketInsightClient


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


@router.get("/assets/workspace", response_model=GrowthAssetsWorkspace)
def get_growth_assets_workspace(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return assets_workspace(db, user_id=user.id)


@router.get("/assets/export", response_model=GrowthAssetsExport)
def get_growth_assets_export(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return export_assets(db, user_id=user.id)


@router.post("/assets/portfolio", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_growth_portfolio(
    data: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_portfolio(db, user_id=user.id, data=data)


@router.patch("/assets/portfolio/{item_id}", response_model=PortfolioResponse)
def update_growth_portfolio(
    item_id: int,
    data: PortfolioUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_portfolio(db, user_id=user.id, item_id=item_id, data=data)


@router.delete("/assets/portfolio/{item_id}")
def delete_growth_portfolio(
    item_id: int,
    detach_evidence: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_portfolio(db, user_id=user.id, item_id=item_id, detach_evidence=detach_evidence)


@router.post("/assets/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
def create_growth_evidence(
    data: EvidenceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_evidence(db, user_id=user.id, data=data)


@router.patch("/assets/evidence/{evidence_id}", response_model=EvidenceResponse)
def update_growth_evidence(
    evidence_id: int,
    data: EvidenceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_evidence(db, user_id=user.id, evidence_id=evidence_id, data=data)


@router.delete("/assets/evidence/{evidence_id}")
def delete_growth_evidence(
    evidence_id: int,
    detach_skills: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_evidence(db, user_id=user.id, evidence_id=evidence_id, detach_skills=detach_skills)


@router.post("/assets/skills", response_model=SkillAssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_growth_skill_candidate(
    data: SkillCandidateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_skill_candidate(db, user_id=user.id, data=data)


@router.post("/assets/skills/{assessment_id}/confirm", response_model=SkillAssessmentResponse)
def confirm_growth_skill(
    assessment_id: int,
    data: SkillConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return confirm_skill(db, user_id=user.id, assessment_id=assessment_id, data=data)


@router.post("/assets/reflections", response_model=ReflectionResponse, status_code=status.HTTP_201_CREATED)
def create_growth_reflection(
    data: ReflectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_reflection(db, user_id=user.id, data=data)


@router.patch("/assets/reflections/{reflection_id}", response_model=ReflectionResponse)
def update_growth_reflection(
    reflection_id: int,
    data: ReflectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_reflection(db, user_id=user.id, reflection_id=reflection_id, data=data)


@router.get("/direction/workspace", response_model=DirectionWorkspace)
def get_growth_direction_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return direction_workspace(db, user_id=user.id)


@router.post("/direction/targets", response_model=FutureTargetResponse, status_code=status.HTTP_201_CREATED)
def create_growth_target(data: FutureTargetCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_target(db, user_id=user.id, data=data)


@router.post("/direction/targets/{target_id}/confirm", response_model=FutureTargetResponse)
def confirm_growth_target(target_id: int, data: FutureTargetConfirm, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return confirm_target(db, user_id=user.id, target_id=target_id, data=data)


@router.post("/direction/market-signals/refresh", response_model=MarketRefreshResponse)
def refresh_growth_market_signals(
    data: MarketSignalRefresh,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    target = db.query(GrowthFutureTarget).filter(
        GrowthFutureTarget.id == data.target_id,
        GrowthFutureTarget.user_id == user.id,
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="未来目标不存在")
    if target.status != "active":
        raise HTTPException(status_code=422, detail="只能为本人当前已确认目标更新市场信号")
    insight = market_client.skill_insight(target.title, data.limit)
    return refresh_market_signals(db, user_id=user.id, data=data, insight=insight)


@router.post("/direction/gaps", response_model=GapSnapshotResponse, status_code=status.HTTP_201_CREATED)
def create_growth_gap_snapshot(data: GapSnapshotCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_gap_snapshot(db, user_id=user.id, data=data)


@router.post("/direction/gaps/{gap_id}/confirm", response_model=GapSnapshotResponse)
def confirm_growth_gap_snapshot(gap_id: int, data: GapSnapshotConfirm, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return confirm_gap_snapshot(db, user_id=user.id, gap_id=gap_id, data=data)


@router.post("/direction/milestones", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_growth_milestone(data: MilestoneCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_milestone(db, user_id=user.id, data=data)


@router.patch("/direction/milestones/{milestone_id}", response_model=MilestoneResponse)
def update_growth_milestone(milestone_id: int, data: MilestoneUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_milestone(db, user_id=user.id, milestone_id=milestone_id, data=data)


@router.post("/direction/milestones/{milestone_id}/action-proposal", response_model=MilestoneActionProposal)
def create_growth_milestone_action_proposal(milestone_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return propose_milestone_action(db, user_id=user.id, milestone_id=milestone_id)
