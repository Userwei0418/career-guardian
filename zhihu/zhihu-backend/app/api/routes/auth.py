from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.contract import Contract
from app.models.payslip import Payslip
from app.models.finding import Finding
from app.models.journey_node import JourneyNode
from app.models.salary_calculation import SalaryCalculation
from app.models.user_profile import UserProfile
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.personal_attachment import (
    PersonalAttachmentCleanupJob,
    PersonalAttachmentVersion,
)
from app.models.opportunity_target import JobTarget, ResumeTailoringDraft
from app.models.ai_configuration import AIInvocationLog, CareerImageGeneration
from app.models.cashflow import (
    CashflowConversation,
    CashflowConversationTurn,
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRelation,
    EconomicFactRelationRevision,
    FinancialBudget,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialMonthClose,
    FinancialRecurringDecision,
    FinancialTransaction,
    FinancialTransactionRevision,
)
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.growth import (
    GrowthAuditEvent,
    GrowthEmotionNote,
    GrowthEvidenceItem,
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthMarketSignal,
    GrowthMilestone,
    GrowthPortfolioItem,
    GrowthReflection,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
    GrowthWeeklyReport,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.api.deps import get_current_user, require_admin
from app.services.cashflow_service import (
    commit_financial_ledger,
    lock_financial_ledger_owner,
)
from app.services.personal_attachment_service import (
    enqueue_user_attachment_cleanup,
    process_attachment_cleanup_jobs,
)

router = APIRouter()


def _delete_business_data(user_id: int, db: Session) -> list[int]:
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    # In-flight parsing/model calls capture this epoch before releasing their
    # request transaction. Incrementing it under the same user lock prevents a
    # request started before "clear data" from repopulating data afterwards.
    owner.business_data_epoch += 1
    owner.financial_ledger_revision += 1
    attachment_cleanup_ids = enqueue_user_attachment_cleanup(db, user_id)
    # Import candidates are deliberately separate from the formal ledger.  The
    # account-retaining data-clear endpoint does not trigger user FK cascades,
    # so remove the whole cashflow boundary explicitly and in dependency order.
    db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(CashflowConversationTurn).filter(
        CashflowConversationTurn.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(CashflowConversation).filter(
        CashflowConversation.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id
    ).delete(synchronize_session=False)
    fact_ids = [
        fact.id
        for fact in db.query(EconomicFact.id).filter(EconomicFact.user_id == user_id).all()
    ]
    db.query(EconomicFactRelationRevision).filter(
        EconomicFactRelationRevision.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(EconomicFactRelation).filter(
        EconomicFactRelation.user_id == user_id
    ).delete(synchronize_session=False)
    if fact_ids:
        db.query(EconomicFactAllocation).filter(
            EconomicFactAllocation.fact_id.in_(fact_ids)
        ).delete(synchronize_session=False)
    db.query(EconomicFact).filter(
        EconomicFact.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialTransactionRevision).filter(
        FinancialTransactionRevision.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialLedgerRevisionEvent).filter(
        FinancialLedgerRevisionEvent.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialTransaction).filter(
        FinancialTransaction.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialBudget).filter(
        FinancialBudget.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialMonthClose).filter(
        FinancialMonthClose.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialRecurringDecision).filter(
        FinancialRecurringDecision.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(FinancialCategory).filter(
        FinancialCategory.user_id == user_id
    ).delete(synchronize_session=False)
    # Growth notes and candidate payloads are private business data. Remove
    # every layer explicitly because this endpoint keeps the user account and
    # therefore cannot rely on user FK cascades.
    db.query(GrowthAuditEvent).filter(
        GrowthAuditEvent.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthMilestone).filter(
        GrowthMilestone.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthGapSnapshot).filter(
        GrowthGapSnapshot.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthMarketSignal).filter(
        GrowthMarketSignal.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthFutureTarget).filter(
        GrowthFutureTarget.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthReflection).filter(
        GrowthReflection.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthSkillEvidenceLink).filter(
        GrowthSkillEvidenceLink.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthSkillAssessment).filter(
        GrowthSkillAssessment.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthEvidenceItem).filter(
        GrowthEvidenceItem.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthPortfolioItem).filter(
        GrowthPortfolioItem.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthWeeklyReport).filter(
        GrowthWeeklyReport.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthWorkEvent).filter(
        GrowthWorkEvent.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthEmotionNote).filter(
        GrowthEmotionNote.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthWorkItem).filter(
        GrowthWorkItem.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(GrowthWorkIntake).filter(
        GrowthWorkIntake.user_id == user_id
    ).delete(synchronize_session=False)
    # Generated imagery contains a derived summary of the user's career data and
    # therefore belongs to the same privacy deletion boundary as resumes.
    db.query(CareerImageGeneration).filter(CareerImageGeneration.user_id == user_id).delete(
        synchronize_session=False
    )
    # Operational usage statistics can remain, but must no longer identify a
    # user after their business data or account has been deleted.
    db.query(AIInvocationLog).filter(AIInvocationLog.user_id == user_id).update(
        {AIInvocationLog.user_id: None}, synchronize_session=False
    )
    db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.user_id == user_id).delete(synchronize_session=False)
    db.query(JobTarget).filter(JobTarget.user_id == user_id).delete(synchronize_session=False)
    event_ids = [event.id for event in db.query(CareerEvent.id).filter(CareerEvent.user_id == user_id).all()]
    if event_ids:
        db.query(OpportunityAnalysis).filter(OpportunityAnalysis.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Outcome).filter(Outcome.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(DecisionRecord).filter(DecisionRecord.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(ActionItem).filter(ActionItem.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(GuardianFinding).filter(GuardianFinding.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Evidence).filter(Evidence.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Offer).filter(Offer.career_event_id.in_(event_ids)).update(
            {Offer.career_event_id: None}, synchronize_session=False
        )
        db.query(Contract).filter(Contract.career_event_id.in_(event_ids)).update(
            {Contract.career_event_id: None}, synchronize_session=False
        )
        db.query(Payslip).filter(Payslip.career_event_id.in_(event_ids)).update(
            {Payslip.career_event_id: None}, synchronize_session=False
        )
        db.query(CareerEvent).filter(CareerEvent.id.in_(event_ids)).delete(synchronize_session=False)

    case_ids = [case.id for case in db.query(CareerCase.id).filter(CareerCase.user_id == user_id).all()]
    if case_ids:
        db.query(Offer).filter(Offer.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Contract).filter(Contract.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Payslip).filter(Payslip.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Finding).filter(Finding.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(JourneyNode).filter(JourneyNode.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(CareerCase).filter(CareerCase.id.in_(case_ids)).delete(synchronize_session=False)
    db.query(SalaryCalculation).filter(SalaryCalculation.user_id == user_id).delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id == user_id).delete(synchronize_session=False)
    db.query(OpportunityAnalysis).filter(OpportunityAnalysis.user_id == user_id).delete(synchronize_session=False)
    db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).delete(synchronize_session=False)
    db.query(PersonalAttachmentVersion).filter(PersonalAttachmentVersion.user_id == user_id).delete(synchronize_session=False)
    db.query(JourneyNode).filter(JourneyNode.user_id == user_id, JourneyNode.case_id.is_(None)).delete(synchronize_session=False)
    return attachment_cleanup_ids


def _process_committed_attachment_jobs(db: Session, cleanup_ids: list[int]) -> dict:
    try:
        report = process_attachment_cleanup_jobs(db, cleanup_ids)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "attachment_cleanup_pending",
                "message": "业务数据已清空，附件清理任务已保留，请稍后重试",
                "cleanup_ids": cleanup_ids,
            },
        ) from exc
    if report["failed_ids"]:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "attachment_cleanup_pending",
                "message": "业务数据已清空，部分附件清理待重试",
                "cleanup_ids": report["failed_ids"],
            },
        )
    return report


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username, is_demo=user.is_demo, is_admin=user.is_admin)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username, is_demo=user.is_demo, is_admin=user.is_admin)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.delete("/data")
def delete_user_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除用户所有业务数据（保留账号）"""
    user_id = user.id
    db.rollback()
    cleanup_ids = _delete_business_data(user_id, db)
    commit_financial_ledger(db)
    cleanup = _process_committed_attachment_jobs(db, cleanup_ids)
    return {"ok": True, "message": "已清空所有业务数据", "attachment_cleanup": cleanup}


@router.delete("/account")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除整个账号及所有关联数据"""
    user_id = user.id
    db.rollback()
    cleanup_ids = _delete_business_data(user_id, db)
    locked_user = db.get(User, user_id)
    if locked_user is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(locked_user)
    commit_financial_ledger(db)
    cleanup = _process_committed_attachment_jobs(db, cleanup_ids)
    return {"ok": True, "message": "账号已删除", "attachment_cleanup": cleanup}


@router.get("/users", response_model=list[UserResponse])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员：获取所有用户列表"""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员：删除指定用户及所有数据"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    target_id = target.id
    target_username = target.username
    db.rollback()
    cleanup_ids = _delete_business_data(target_id, db)
    locked_target = db.get(User, target_id)
    if locked_target is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(locked_target)
    commit_financial_ledger(db)
    cleanup = _process_committed_attachment_jobs(db, cleanup_ids)
    return {"ok": True, "message": f"用户 {target_username} 已删除", "attachment_cleanup": cleanup}


@router.post("/attachment-cleanups/{cleanup_id}/retry")
def retry_attachment_cleanup(
    cleanup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(PersonalAttachmentCleanupJob).filter(
        PersonalAttachmentCleanupJob.id == cleanup_id,
    ).first()
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="附件清理任务不存在")
    report = _process_committed_attachment_jobs(db, [cleanup_id])
    return {"ok": True, "attachment_cleanup": report}


@router.get("/attachment-cleanups")
def list_attachment_cleanups(
    status: Optional[str] = Query(default=None, pattern="^(pending|processing|failed|completed)$"),
    target_user_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(PersonalAttachmentCleanupJob)
    if user.is_admin and target_user_id is not None:
        query = query.filter(PersonalAttachmentCleanupJob.user_id == target_user_id)
    else:
        query = query.filter(PersonalAttachmentCleanupJob.user_id == user.id)
    if status is not None:
        query = query.filter(PersonalAttachmentCleanupJob.status == status)
    jobs = query.order_by(PersonalAttachmentCleanupJob.id.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": job.id,
                "user_id": job.user_id if user.is_admin else None,
                "status": job.status,
                "attempts": job.attempts,
                "last_error": job.last_error,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "completed_at": job.completed_at,
            }
            for job in jobs
        ]
    }
