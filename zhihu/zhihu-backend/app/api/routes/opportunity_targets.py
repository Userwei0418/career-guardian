from __future__ import annotations

from datetime import datetime
import hashlib

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.market import get_market_client
from app.api.routes.resumes import _store_resume
from app.db.session import SessionLocal, get_db
from app.models.opportunity_target import JobTarget, ResumeTailoringDraft
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.user import User
from app.schemas.opportunity_target import (
    JobTargetResponse,
    JobTargetUpdateRequest,
    JobTargetUpsertRequest,
    LearningPlanResponse,
    TailoringDraftResponse,
)
from app.schemas.resume import ResumeVersionResponse
from app.services.market_insight_client import MarketInsightClient
from app.services.opportunity_analysis_service import SCORING_VERSION
from app.services.opportunity_target_service import build_learning_plan, build_tailoring_draft, build_target_advice
from app.services.speech_service import synthesize_plan_summary


router = APIRouter()


def _draft_response(db: Session, draft: ResumeTailoringDraft, source_text: str = "") -> TailoringDraftResponse:
    response = TailoringDraftResponse.model_validate(draft)
    response.source_text = source_text
    target = db.get(JobTarget, draft.job_target_id)
    if target is not None:
        analysis = (
            db.query(OpportunityAnalysis)
            .filter(
                OpportunityAnalysis.user_id == draft.user_id,
                OpportunityAnalysis.job_id == target.job_id,
                OpportunityAnalysis.resume_version_id == draft.source_resume_version_id,
            )
            .order_by(OpportunityAnalysis.created_at.desc())
            .first()
        )
        response.match_score = (
            analysis.match_score
            if analysis is not None and analysis.scoring_version == SCORING_VERSION
            else None
        )
    return response


def _generate_learning_plan_background(target_id: int, user_id: int) -> None:
    db = SessionLocal()
    try:
        target = db.query(JobTarget).filter(JobTarget.id == target_id, JobTarget.user_id == user_id).first()
        if target is None:
            return
        target.plan_status = "running"
        db.commit()
        resume = db.query(ResumeVersion).filter(ResumeVersion.id == target.resume_version_id, ResumeVersion.user_id == user_id).first()
        if resume is None:
            raise ValueError("绑定的简历版本已不存在")
        plan, mode = build_learning_plan(
            resume.content_text,
            list(resume.extracted_skills or []),
            target.job_snapshot or {},
            db,
            user_id,
        )
        target = db.get(JobTarget, target_id)
        target.learning_plan = plan
        target.plan_mode = mode
        target.plan_status = "ready"
        target.plan_error = None
        target.plan_generated_at = datetime.now()
        target.plan_audio = None
        target.plan_audio_content_type = None
        target.plan_audio_summary_hash = None
        target.plan_audio_generated_at = None
        db.commit()
    except Exception:
        db.rollback()
        target = db.query(JobTarget).filter(JobTarget.id == target_id, JobTarget.user_id == user_id).first()
        if target is not None:
            target.plan_status = "failed"
            target.plan_error = "能力路线生成没有完成，请稍后重试。已有结果不会被覆盖。"
            db.commit()
    finally:
        db.close()


def _generate_resume_draft_background(draft_id: int, user_id: int) -> None:
    db = SessionLocal()
    try:
        draft = db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.id == draft_id, ResumeTailoringDraft.user_id == user_id).first()
        if draft is None:
            return
        target = db.query(JobTarget).filter(JobTarget.id == draft.job_target_id, JobTarget.user_id == user_id).first()
        resume = db.query(ResumeVersion).filter(ResumeVersion.id == draft.source_resume_version_id, ResumeVersion.user_id == user_id).first()
        if target is None or resume is None:
            raise ValueError("目标岗位或简历版本已不存在")
        tailored, changes, warnings, mode = build_tailoring_draft(
            resume.content_text,
            target.job_snapshot or {},
            db,
            user_id,
            fit_context=target.learning_plan or {},
        )
        draft = db.get(ResumeTailoringDraft, draft_id)
        draft.tailored_text = tailored
        draft.changes = changes
        draft.warnings = warnings
        draft.generation_mode = mode
        draft.status = "draft"
        draft.error_message = None
        draft.generation_completed_at = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        draft = db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.id == draft_id, ResumeTailoringDraft.user_id == user_id).first()
        if draft is not None:
            draft.status = "failed"
            draft.error_message = "简历草稿生成没有完成，请稍后重试。原简历没有被修改。"
            draft.generation_completed_at = datetime.now()
            db.commit()
    finally:
        db.close()


def _owned_resume(db: Session, user_id: int, resume_id: int | None) -> ResumeVersion | None:
    if resume_id is None:
        return None
    resume = db.query(ResumeVersion).filter(ResumeVersion.id == resume_id, ResumeVersion.user_id == user_id).first()
    if resume is None:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    return resume


def _target(db: Session, user_id: int, target_id: int) -> JobTarget:
    target = db.query(JobTarget).filter(JobTarget.id == target_id, JobTarget.user_id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="目标岗位不存在")
    return target


def _snapshot(detail) -> dict:
    return {
        "title": detail.job.title,
        "company_name": detail.job.company_name,
        "city": detail.job.city,
        "recruitment_type": detail.job.recruitment_type,
        "salary_min": detail.job.salary_min,
        "salary_max": detail.job.salary_max,
        "salary_period": detail.job.salary_period,
        "skills": detail.job.skills,
        "status": detail.job.status,
        "requirements": detail.requirements,
        "responsibilities": detail.responsibilities or detail.description,
        "description": detail.description,
        "education_requirement": detail.education_requirement,
        "experience_requirement": detail.experience_requirement,
        "major_requirement": detail.major_requirement,
        "last_seen_at": detail.last_seen_at.isoformat(),
    }


def _apply_analysis_advice(target: JobTarget, analysis: OpportunityAnalysis | None) -> bool:
    if analysis is None or analysis.scoring_version != SCORING_VERSION:
        return False
    kind, summary = build_target_advice(analysis.match_score, analysis.score_breakdown or {}, analysis.missing_skills or [])
    target.advice_kind = kind
    target.advice_summary = summary
    target.advice_source_analysis_id = analysis.id
    target.advice_updated_at = datetime.now()
    return True


@router.get("/targets", response_model=list[JobTargetResponse])
def list_targets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    targets = db.query(JobTarget).filter(JobTarget.user_id == user.id).order_by(JobTarget.updated_at.desc()).all()
    changed = False
    for target in targets:
        if target.advice_summary:
            continue
        analysis = (
            db.query(OpportunityAnalysis)
            .filter(
                OpportunityAnalysis.user_id == user.id,
                OpportunityAnalysis.job_id == target.job_id,
                OpportunityAnalysis.resume_version_id == target.resume_version_id,
            )
            .order_by(OpportunityAnalysis.created_at.desc())
            .first()
        )
        if _apply_analysis_advice(target, analysis):
            changed = True
    if changed:
        db.commit()
    return targets


@router.post("/targets", response_model=JobTargetResponse, status_code=status.HTTP_201_CREATED)
def upsert_target(
    data: JobTargetUpsertRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    resume = _owned_resume(db, user.id, data.resume_version_id)
    if data.status == "target" and resume is None:
        resume = db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id, ResumeVersion.is_active.is_(True)).first()
    try:
        detail = market_client.get_job(data.job_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="岗位不存在或暂不提供展示") from exc
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc
    target = db.query(JobTarget).filter(JobTarget.user_id == user.id, JobTarget.job_id == data.job_id).first()
    if target is None:
        target = JobTarget(user_id=user.id, job_id=data.job_id)
        db.add(target)
    target.status = data.status
    target.resume_version_id = resume.id if resume else None
    target.job_snapshot = _snapshot(detail)
    analysis = None
    if resume is not None:
        analysis = (
            db.query(OpportunityAnalysis)
            .filter(
                OpportunityAnalysis.user_id == user.id,
                OpportunityAnalysis.job_id == data.job_id,
                OpportunityAnalysis.resume_version_id == resume.id,
            )
            .order_by(OpportunityAnalysis.created_at.desc())
            .first()
        )
    _apply_analysis_advice(target, analysis)
    db.commit()
    db.refresh(target)
    return target


@router.patch("/targets/{target_id}", response_model=JobTargetResponse)
def update_target(target_id: int, data: JobTargetUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    if data.status is not None:
        target.status = data.status
    if data.resume_version_id is not None:
        target.resume_version_id = _owned_resume(db, user.id, data.resume_version_id).id
        analysis = (
            db.query(OpportunityAnalysis)
            .filter(
                OpportunityAnalysis.user_id == user.id,
                OpportunityAnalysis.job_id == target.job_id,
                OpportunityAnalysis.resume_version_id == target.resume_version_id,
            )
            .order_by(OpportunityAnalysis.created_at.desc())
            .first()
        )
        if not _apply_analysis_advice(target, analysis):
            target.advice_kind = None
            target.advice_summary = None
            target.advice_source_analysis_id = None
            target.advice_updated_at = None
    db.commit()
    db.refresh(target)
    return target


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    db.delete(target)
    db.commit()
    return {"ok": True}


@router.post("/targets/{target_id}/learning-plan", response_model=LearningPlanResponse)
def generate_learning_plan(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    resume = _owned_resume(db, user.id, target.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=400, detail="请先为目标岗位选择一份简历")
    plan, mode = build_learning_plan(resume.content_text, list(resume.extracted_skills or []), target.job_snapshot or {}, db, user.id)
    target.learning_plan = plan
    target.plan_mode = mode
    target.plan_status = "ready"
    target.plan_error = None
    target.plan_generated_at = datetime.now()
    target.plan_audio = None
    target.plan_audio_content_type = None
    target.plan_audio_summary_hash = None
    target.plan_audio_generated_at = None
    db.commit()
    db.refresh(target)
    return LearningPlanResponse(target_id=target.id, mode=mode, plan=plan, generated_at=target.plan_generated_at)


@router.post("/targets/{target_id}/learning-plan/audio")
def learning_plan_audio(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = _target(db, user.id, target_id)
    summary = str((target.learning_plan or {}).get("summary") or "").strip()
    if target.plan_status != "ready" or not summary:
        raise HTTPException(status_code=409, detail="能力路线摘要还没有生成完成")
    summary_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    if target.plan_audio and target.plan_audio_summary_hash == summary_hash:
        audio = target.plan_audio
        content_type = target.plan_audio_content_type or "audio/mpeg"
    else:
        try:
            audio, content_type = synthesize_plan_summary(db, user_id=user.id, text=summary)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        target.plan_audio = audio
        target.plan_audio_content_type = content_type
        target.plan_audio_summary_hash = summary_hash
        target.plan_audio_generated_at = datetime.now()
        db.commit()
    return Response(
        content=audio,
        media_type=content_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/targets/{target_id}/learning-plan-task", response_model=JobTargetResponse, status_code=status.HTTP_202_ACCEPTED)
def start_learning_plan_task(
    target_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = _target(db, user.id, target_id)
    if _owned_resume(db, user.id, target.resume_version_id) is None:
        raise HTTPException(status_code=400, detail="请先为目标岗位选择一份简历")
    if target.plan_status in {"queued", "running"}:
        return target
    target.plan_status = "queued"
    target.plan_error = None
    target.plan_started_at = datetime.now()
    db.commit()
    db.refresh(target)
    background_tasks.add_task(_generate_learning_plan_background, target.id, user.id)
    return target


@router.post("/targets/{target_id}/resume-drafts", response_model=TailoringDraftResponse, status_code=status.HTTP_201_CREATED)
def generate_resume_draft(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    resume = _owned_resume(db, user.id, target.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=400, detail="请先为目标岗位选择一份简历")
    tailored, changes, warnings, mode = build_tailoring_draft(
        resume.content_text,
        target.job_snapshot or {},
        db,
        user.id,
        fit_context=target.learning_plan or {},
    )
    draft = ResumeTailoringDraft(
        user_id=user.id,
        job_target_id=target.id,
        source_resume_version_id=resume.id,
        tailored_text=tailored,
        changes=changes,
        warnings=warnings,
        generation_mode=mode,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _draft_response(db, draft, resume.content_text)


@router.post("/targets/{target_id}/resume-draft-task", response_model=TailoringDraftResponse, status_code=status.HTTP_202_ACCEPTED)
def start_resume_draft_task(
    target_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = _target(db, user.id, target_id)
    resume = _owned_resume(db, user.id, target.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=400, detail="请先为目标岗位选择一份简历")
    generating = (
        db.query(ResumeTailoringDraft)
        .filter(
            ResumeTailoringDraft.user_id == user.id,
            ResumeTailoringDraft.job_target_id == target.id,
            ResumeTailoringDraft.source_resume_version_id == resume.id,
            ResumeTailoringDraft.status == "generating",
        )
        .order_by(ResumeTailoringDraft.created_at.desc())
        .first()
    )
    if generating is not None:
        return _draft_response(db, generating, resume.content_text)
    draft = ResumeTailoringDraft(
        user_id=user.id,
        job_target_id=target.id,
        source_resume_version_id=resume.id,
        status="generating",
        tailored_text=resume.content_text,
        changes=[],
        warnings=[],
        generation_mode="pending",
        generation_started_at=datetime.now(),
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    response = _draft_response(db, draft, resume.content_text)
    background_tasks.add_task(_generate_resume_draft_background, draft.id, user.id)
    return response


@router.get("/targets/{target_id}/resume-drafts", response_model=list[TailoringDraftResponse])
def list_resume_drafts(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    drafts = db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.user_id == user.id, ResumeTailoringDraft.job_target_id == target.id).order_by(ResumeTailoringDraft.created_at.desc()).all()
    resume_ids = {draft.source_resume_version_id for draft in drafts}
    resumes = {item.id: item for item in db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id, ResumeVersion.id.in_(resume_ids)).all()} if resume_ids else {}
    result = []
    for draft in drafts:
        result.append(_draft_response(db, draft, resumes[draft.source_resume_version_id].content_text if draft.source_resume_version_id in resumes else ""))
    return result


@router.get("/resume-drafts/latest", response_model=list[TailoringDraftResponse])
def latest_resume_drafts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    drafts = (
        db.query(ResumeTailoringDraft)
        .filter(ResumeTailoringDraft.user_id == user.id)
        .order_by(ResumeTailoringDraft.job_target_id, ResumeTailoringDraft.created_at.desc(), ResumeTailoringDraft.id.desc())
        .all()
    )
    latest = []
    seen_targets = set()
    for draft in drafts:
        if draft.job_target_id in seen_targets:
            continue
        seen_targets.add(draft.job_target_id)
        resume = db.query(ResumeVersion).filter(ResumeVersion.id == draft.source_resume_version_id, ResumeVersion.user_id == user.id).first()
        latest.append(_draft_response(db, draft, resume.content_text if resume else ""))
    return latest


@router.post("/resume-drafts/{draft_id}/confirm", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
def confirm_resume_draft(draft_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    draft = db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.id == draft_id, ResumeTailoringDraft.user_id == user.id).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    if draft.status == "confirmed" and draft.confirmed_resume_version_id:
        confirmed = _owned_resume(db, user.id, draft.confirmed_resume_version_id)
        if confirmed:
            return confirmed
    if draft.status != "draft":
        raise HTTPException(status_code=409, detail="该草稿已经处理")
    target = _target(db, user.id, draft.job_target_id)
    source = _owned_resume(db, user.id, draft.source_resume_version_id)
    if source is None:
        raise HTTPException(status_code=409, detail="原简历版本已不存在")
    meaningful_changes = [
        item for item in (draft.changes or [])
        if isinstance(item, dict) and str(item.get("before") or "").strip() != str(item.get("after") or "").strip()
    ]
    if not meaningful_changes or draft.tailored_text.strip() == source.content_text.strip():
        raise HTTPException(status_code=409, detail="草稿没有可确认的有效修改，不创建重复简历版本")
    title = str((target.job_snapshot or {}).get("title") or "目标岗位")
    confirmed = _store_resume(
        db,
        user,
        f"{source.display_name} · {title}投递版"[:200],
        draft.tailored_text,
        None,
        "ai_text" if draft.generation_mode == "ai" else "text",
        parent_resume_version_id=source.id,
        creation_source="ai_tailored",
        source_job_id=target.job_id,
    )
    draft = db.get(ResumeTailoringDraft, draft.id)
    draft.status = "confirmed"
    draft.confirmed_resume_version_id = confirmed.id
    draft.confirmed_at = datetime.now()
    db.commit()
    db.refresh(confirmed)
    return confirmed
