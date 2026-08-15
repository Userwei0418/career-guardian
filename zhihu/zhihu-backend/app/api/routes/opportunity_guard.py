from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_current_user
from app.api.routes.market import get_market_client
from app.db.session import get_db
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.opportunity_target import JobTarget
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.user import User
from app.schemas.resume import OpportunityGuardRequest, OpportunityGuardResponse
from app.services.market_insight_client import MarketInsightClient
from app.services.opportunity_analysis_service import SCORING_VERSION, analyze_resume_against_job, score_resume_against_job
from app.services.opportunity_target_service import build_target_advice


router = APIRouter()


def _response(analysis: OpportunityAnalysis, reused: bool) -> OpportunityGuardResponse:
    return OpportunityGuardResponse(
        event_id=analysis.event_id,
        analysis_id=analysis.id,
        analysis_mode=analysis.analysis_mode,
        match_score=analysis.match_score,
        scoring_version=analysis.scoring_version,
        score_breakdown=analysis.score_breakdown or {},
        matched_skills=analysis.matched_skills or [],
        missing_skills=analysis.missing_skills or [],
        strengths=analysis.strengths or [],
        risks=analysis.risks or [],
        suggestions=analysis.suggestions or [],
        summary=analysis.summary,
        reused=reused,
    )


def _job_payload(detail) -> dict:
    payload = detail.job.model_dump(mode="json")
    payload.update(
        {
            "requirements": detail.requirements,
            "responsibilities": detail.responsibilities or detail.description,
            "education_requirement": detail.education_requirement,
            "education_level": detail.education_level,
            "experience_requirement": detail.experience_requirement,
            "major_requirement": detail.major_requirement,
        }
    )
    return payload


def _sync_target_advice(db: Session, analysis: OpportunityAnalysis) -> None:
    target = (
        db.query(JobTarget)
        .filter(JobTarget.user_id == analysis.user_id, JobTarget.job_id == analysis.job_id)
        .first()
    )
    if target is None:
        return
    kind, summary = build_target_advice(analysis.match_score, analysis.score_breakdown or {}, analysis.missing_skills or [])
    target.advice_kind = kind
    target.advice_summary = summary
    target.advice_source_analysis_id = analysis.id
    target.advice_updated_at = datetime.now()


def _sync_finding_score(db: Session, analysis: OpportunityAnalysis) -> None:
    finding = (
        db.query(GuardianFinding)
        .filter(GuardianFinding.event_id == analysis.event_id, GuardianFinding.category == "resume_job_match")
        .first()
    )
    if finding is not None:
        finding.severity = "warning" if analysis.match_score < 50 else "info"
        finding.title = f"这份简历与岗位的综合证据匹配度为 {analysis.match_score}%"


@router.get("/guard", response_model=Optional[OpportunityGuardResponse])
def latest_guard_result(
    job_id: str,
    resume_version_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    analysis = (
        db.query(OpportunityAnalysis)
        .filter(
            OpportunityAnalysis.user_id == user.id,
            OpportunityAnalysis.resume_version_id == resume_version_id,
            OpportunityAnalysis.job_id == job_id,
        )
        .first()
    )
    if analysis is None:
        return None
    if analysis.scoring_version != SCORING_VERSION:
        resume = db.query(ResumeVersion).filter(ResumeVersion.id == resume_version_id, ResumeVersion.user_id == user.id).first()
        try:
            detail = market_client.get_job(job_id)
        except (httpx.HTTPError, ValueError, KeyError):
            detail = None
        if resume is not None and detail is not None:
            score, breakdown = score_resume_against_job(
                resume.content_text,
                list(resume.extracted_skills or []),
                _job_payload(detail),
                resume.structured_profile or {},
            )
            analysis.match_score = score
            analysis.scoring_version = SCORING_VERSION
            analysis.score_breakdown = breakdown
            _sync_finding_score(db, analysis)
            _sync_target_advice(db, analysis)
            db.commit()
            db.refresh(analysis)
    return _response(analysis, reused=True)


@router.post("/guard", response_model=OpportunityGuardResponse, status_code=status.HTTP_201_CREATED)
def guard_opportunity(
    data: OpportunityGuardRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    resume = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.id == data.resume_version_id, ResumeVersion.user_id == user.id)
        .first()
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    existing = (
        db.query(OpportunityAnalysis)
        .filter(
            OpportunityAnalysis.user_id == user.id,
            OpportunityAnalysis.resume_version_id == resume.id,
            OpportunityAnalysis.job_id == data.job_id,
        )
        .first()
    )
    if existing is not None and not data.force_refresh:
        return _response(existing, reused=True)

    try:
        detail = market_client.get_job(data.job_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="岗位不存在或暂不提供展示") from exc
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc

    job_payload = _job_payload(detail)
    result = analyze_resume_against_job(
        resume.content_text,
        list(resume.extracted_skills or []),
        job_payload,
        resume_profile=resume.structured_profile or {},
        db=db,
        user_id=user.id,
    )
    if existing is not None:
        existing.analysis_mode = result.analysis_mode
        existing.match_score = result.match_score
        existing.scoring_version = result.scoring_version
        existing.score_breakdown = result.score_breakdown
        existing.matched_skills = result.matched_skills
        existing.missing_skills = result.missing_skills
        existing.strengths = result.strengths
        existing.risks = result.risks
        existing.suggestions = result.suggestions
        existing.summary = result.summary
        event = db.get(CareerEvent, existing.event_id)
        if event is not None:
            event.status = "attention" if result.match_score < 50 else "active"
            finding = (
                db.query(GuardianFinding)
                .filter(
                    GuardianFinding.event_id == event.id,
                    GuardianFinding.category == "resume_job_match",
                )
                .first()
            )
            if finding is not None:
                finding.severity = "warning" if result.match_score < 50 else "info"
                finding.title = f"这份简历与岗位的综合证据匹配度为 {result.match_score}%"
                finding.explanation = result.summary
                finding.source_type = "ai_assistance" if result.analysis_mode == "ai" else "calculation"
                finding.confidence = 0.8 if result.analysis_mode == "ai" else 0.65
                for action in db.query(ActionItem).filter(
                    ActionItem.event_id == event.id,
                    ActionItem.finding_id == finding.id,
                    ActionItem.status == "draft",
                ):
                    db.delete(action)
                for priority, suggestion in enumerate(result.suggestions[:5], start=20):
                    db.add(
                        ActionItem(
                            event_id=event.id,
                            finding_id=finding.id,
                            title=suggestion[:300],
                            description="如果这条建议适合你，可以确认后加入自己的求职行动。",
                            status="draft",
                            priority=priority,
                            requires_confirmation=True,
                        )
                    )
        _sync_target_advice(db, existing)
        db.commit()
        db.refresh(existing)
        return _response(existing, reused=False)
    source = detail.job.sources[0]
    event = CareerEvent(
        user_id=user.id,
        event_type="opportunity",
        title=f"{detail.job.company_name} · {detail.job.title}",
        stage="resume_match",
        status="attention" if result.match_score < 50 else "active",
    )
    db.add(event)
    db.flush()
    job_evidence = Evidence(
        event_id=event.id,
        evidence_type="job_posting",
        source_type="market_data",
        title=f"{detail.job.title}岗位事实",
        content_excerpt=f"{detail.job.company_name}，{detail.job.city or '城市待确认'}，最后观察 {source.observed_at.date()}",
        source_ref=source.source_url or source.source_id,
        extra_data={"job_id": detail.job.job_id, "observed_at": source.observed_at.isoformat()},
        confidence=0.9 if source.source_url else 0.75,
    )
    db.add(job_evidence)
    resume_evidence = Evidence(
        event_id=event.id,
        evidence_type="resume_version",
        source_type="user_material",
        title=f"简历 v{resume.version_number} · {resume.display_name}",
        content_excerpt=("已识别技能：" + "、".join((resume.extracted_skills or [])[:12])) if resume.extracted_skills else "已保存简历文本，暂无稳定技能标签",
        source_ref=f"resume:{resume.id}",
        extra_data={"resume_version_id": resume.id, "version_number": resume.version_number},
        confidence=1,
    )
    db.add(resume_evidence)
    db.flush()
    finding = GuardianFinding(
        event_id=event.id,
        evidence_id=resume_evidence.id,
        domain="opportunity",
        category="resume_job_match",
        severity="warning" if result.match_score < 50 else "info",
        title=f"这份简历与岗位的综合证据匹配度为 {result.match_score}%",
        explanation=result.summary,
        source_type="ai_assistance" if result.analysis_mode == "ai" else "calculation",
        confidence=0.8 if result.analysis_mode == "ai" else 0.65,
    )
    db.add(finding)
    db.flush()
    for priority, suggestion in enumerate(result.suggestions[:5], start=20):
        db.add(
            ActionItem(
                event_id=event.id,
                finding_id=finding.id,
                title=suggestion[:300],
                description="如果这条建议适合你，可以确认后加入自己的求职行动。",
                status="draft",
                priority=priority,
                requires_confirmation=True,
            )
        )
    analysis = OpportunityAnalysis(
        user_id=user.id,
        event_id=event.id,
        resume_version_id=resume.id,
        job_id=data.job_id,
        analysis_mode=result.analysis_mode,
        match_score=result.match_score,
        scoring_version=result.scoring_version,
        score_breakdown=result.score_breakdown,
        matched_skills=result.matched_skills,
        missing_skills=result.missing_skills,
        strengths=result.strengths,
        risks=result.risks,
        suggestions=result.suggestions,
        summary=result.summary,
    )
    db.add(analysis)
    db.flush()
    _sync_target_advice(db, analysis)
    db.commit()
    db.refresh(analysis)
    return _response(analysis, reused=False)
