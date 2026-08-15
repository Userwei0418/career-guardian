from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.market import get_market_client
from app.db.session import get_db
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.user import User
from app.schemas.resume import OpportunityGuardRequest, OpportunityGuardResponse
from app.services.market_insight_client import MarketInsightClient
from app.services.opportunity_analysis_service import analyze_resume_against_job


router = APIRouter()


def _response(analysis: OpportunityAnalysis, reused: bool) -> OpportunityGuardResponse:
    return OpportunityGuardResponse(
        event_id=analysis.event_id,
        analysis_id=analysis.id,
        analysis_mode=analysis.analysis_mode,
        match_score=analysis.match_score,
        matched_skills=analysis.matched_skills or [],
        missing_skills=analysis.missing_skills or [],
        strengths=analysis.strengths or [],
        risks=analysis.risks or [],
        suggestions=analysis.suggestions or [],
        summary=analysis.summary,
        reused=reused,
    )


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
    if existing is not None:
        return _response(existing, reused=True)

    try:
        detail = market_client.get_job(data.job_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="岗位不存在或暂不提供展示") from exc
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="岗位信息暂时无法读取") from exc

    job_payload = detail.job.model_dump(mode="json")
    job_payload.update(
        {
            "requirements": detail.requirements,
            "responsibilities": detail.responsibilities or detail.description,
            "education_requirement": detail.education_requirement,
            "experience_requirement": detail.experience_requirement,
            "major_requirement": detail.major_requirement,
        }
    )
    result = analyze_resume_against_job(
        resume.content_text,
        list(resume.extracted_skills or []),
        job_payload,
        resume_profile=resume.structured_profile or {},
        db=db,
    )
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
        title=f"简历与岗位明示要求匹配度 {result.match_score}%",
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
                description="这是分析草稿，请确认是否纳入自己的求职行动。",
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
        matched_skills=result.matched_skills,
        missing_skills=result.missing_skills,
        strengths=result.strengths,
        risks=result.risks,
        suggestions=result.suggestions,
        summary=result.summary,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return _response(analysis, reused=False)
