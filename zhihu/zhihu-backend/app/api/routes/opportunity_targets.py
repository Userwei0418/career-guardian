from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.market import get_market_client
from app.api.routes.resumes import _store_resume
from app.db.session import get_db
from app.models.opportunity_target import JobTarget, ResumeTailoringDraft
from app.models.resume import ResumeVersion
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
from app.services.opportunity_target_service import build_learning_plan, build_tailoring_draft


router = APIRouter()


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


@router.get("/targets", response_model=list[JobTargetResponse])
def list_targets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(JobTarget).filter(JobTarget.user_id == user.id).order_by(JobTarget.updated_at.desc()).all()


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
    target.plan_generated_at = datetime.now()
    db.commit()
    db.refresh(target)
    return LearningPlanResponse(target_id=target.id, mode=mode, plan=plan, generated_at=target.plan_generated_at)


@router.post("/targets/{target_id}/resume-drafts", response_model=TailoringDraftResponse, status_code=status.HTTP_201_CREATED)
def generate_resume_draft(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    resume = _owned_resume(db, user.id, target.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=400, detail="请先为目标岗位选择一份简历")
    tailored, changes, warnings, mode = build_tailoring_draft(resume.content_text, target.job_snapshot or {}, db, user.id)
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
    response = TailoringDraftResponse.model_validate(draft)
    response.source_text = resume.content_text
    return response


@router.get("/targets/{target_id}/resume-drafts", response_model=list[TailoringDraftResponse])
def list_resume_drafts(target_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = _target(db, user.id, target_id)
    drafts = db.query(ResumeTailoringDraft).filter(ResumeTailoringDraft.user_id == user.id, ResumeTailoringDraft.job_target_id == target.id).order_by(ResumeTailoringDraft.created_at.desc()).all()
    resume_ids = {draft.source_resume_version_id for draft in drafts}
    resumes = {item.id: item for item in db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id, ResumeVersion.id.in_(resume_ids)).all()} if resume_ids else {}
    result = []
    for draft in drafts:
        response = TailoringDraftResponse.model_validate(draft)
        response.source_text = resumes[draft.source_resume_version_id].content_text if draft.source_resume_version_id in resumes else ""
        result.append(response)
    return result


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
