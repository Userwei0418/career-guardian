import asyncio
import json
from threading import Event, Thread

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
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
    PortfolioAnalysisRequest,
    PortfolioAnalysisResponse,
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
    analyze_portfolio,
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
from app.schemas.growth_integration import (
    CommunicationDraftCreate,
    CommunicationDraftResponse,
    CommunicationDraftRevise,
    GrowthFullExport,
    GrowthIntegrationWorkspace,
    GrowthInquiryRequest,
    GrowthInquiryResponse,
    HandoffCreate,
    HandoffResponse,
    HandoffTransition,
)
from app.services.growth_integration_service import (
    confirm_handoff,
    create_communication_draft,
    create_handoff,
    full_growth_export,
    handoff_inbox,
    integration_workspace,
    revise_communication_draft,
    revoke_handoff,
)
from app.services.growth_inquiry_service import (
    GrowthInquiryCancelled,
    answer_growth_inquiry,
    list_growth_inquiries,
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


@router.post("/assets/portfolio/{item_id}/analyze", response_model=PortfolioAnalysisResponse)
def analyze_growth_portfolio(
    item_id: int,
    data: PortfolioAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return analyze_portfolio(db, user_id=user.id, item_id=item_id, data=data)


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


@router.get("/integration/workspace", response_model=GrowthIntegrationWorkspace)
def get_growth_integration_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return integration_workspace(db, user_id=user.id)


@router.post("/communication-drafts", response_model=CommunicationDraftResponse, status_code=status.HTTP_201_CREATED)
def create_growth_communication_draft(data: CommunicationDraftCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_communication_draft(db, user_id=user.id, data=data)


@router.post("/communication-drafts/{draft_id}/revisions", response_model=CommunicationDraftResponse, status_code=status.HTTP_201_CREATED)
def revise_growth_communication_draft(draft_id: int, data: CommunicationDraftRevise, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return revise_communication_draft(db, user_id=user.id, draft_id=draft_id, data=data)


@router.post("/handoffs", response_model=HandoffResponse, status_code=status.HTTP_201_CREATED)
def create_growth_handoff(data: HandoffCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_handoff(db, user_id=user.id, data=data)


@router.post("/handoffs/{handoff_id}/confirm", response_model=HandoffResponse)
def confirm_growth_handoff(handoff_id: int, data: HandoffTransition, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return confirm_handoff(db, user_id=user.id, handoff_id=handoff_id, expected_version=data.expected_version)


@router.post("/handoffs/{handoff_id}/revoke", response_model=HandoffResponse)
def revoke_growth_handoff(handoff_id: int, data: HandoffTransition, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return revoke_handoff(db, user_id=user.id, handoff_id=handoff_id, expected_version=data.expected_version)


@router.get("/handoffs/inbox/{target_domain}", response_model=list[HandoffResponse])
def get_growth_handoff_inbox(target_domain: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return handoff_inbox(db, user_id=user.id, target_domain=target_domain)


@router.get("/export", response_model=GrowthFullExport)
def export_growth_records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return full_growth_export(db, user_id=user.id)


@router.get("/inquiries", response_model=list[GrowthInquiryResponse])
def get_growth_inquiries(limit: int = Query(default=20, ge=1, le=50), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list_growth_inquiries(db, user_id=user.id, limit=limit)


@router.post("/inquiries", response_model=GrowthInquiryResponse)
def create_growth_inquiry(data: GrowthInquiryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return answer_growth_inquiry(db, user=user, data=data)


def _growth_stream_line(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")


@router.post("/inquiries/stream")
def stream_growth_inquiry(data: GrowthInquiryRequest, user: User = Depends(get_current_user)):
    request_id = data.request_id
    user_id = user.id

    async def event_stream():
        events: asyncio.Queue[dict | object] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stopped = Event()
        finished = object()

        def push_event(payload: dict) -> None:
            if stopped.is_set():
                raise GrowthInquiryCancelled("ClientCancelled")
            loop.call_soon_threadsafe(events.put_nowait, payload)

        def worker() -> None:
            try:
                from app.db.session import SessionLocal

                with SessionLocal() as stream_db:
                    stream_user = stream_db.get(User, user_id)
                    if stream_user is None:
                        raise HTTPException(status_code=404, detail="用户不存在")
                    response = answer_growth_inquiry(
                        stream_db,
                        user=stream_user,
                        data=data,
                        on_delta=lambda value: push_event({"type": "delta", "text": value}),
                        cancelled=stopped.is_set,
                    )
                    push_event({"type": "complete", "response": jsonable_encoder(GrowthInquiryResponse.model_validate(response))})
            except GrowthInquiryCancelled:
                pass
            except HTTPException as exc:
                if not stopped.is_set():
                    detail = exc.detail
                    message = detail.get("message") if isinstance(detail, dict) else str(detail)
                    push_event({"type": "error", "error": {"status": exc.status_code, "message": message}})
            except Exception:
                if not stopped.is_set():
                    push_event({"type": "error", "error": {"status": 500, "message": "成长问询暂时失败，请稍后重试"}})
            finally:
                if not stopped.is_set():
                    try:
                        loop.call_soon_threadsafe(events.put_nowait, finished)
                    except RuntimeError:
                        stopped.set()

        Thread(target=worker, name=f"growth-inquiry-{request_id[:8]}", daemon=True).start()
        try:
            yield _growth_stream_line({"type": "start", "request_id": request_id})
            yield _growth_stream_line({"type": "progress", "phase": "context", "message": "正在读取你选择的已确认成长记录"})
            while True:
                try:
                    event = await asyncio.wait_for(events.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield _growth_stream_line({"type": "heartbeat"})
                    continue
                if event is finished:
                    break
                assert isinstance(event, dict)
                yield _growth_stream_line(event)
                if event.get("type") in {"complete", "error"}:
                    break
        finally:
            stopped.set()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )
