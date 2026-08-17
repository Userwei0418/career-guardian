from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.resume import ResumeVersion
from app.models.user_profile import UserProfile
from app.schemas.market import (
    DirectionResolveRequest,
    DirectionResolveResponse,
    JobDetailResponse,
    JobSearchResponse,
    MarketOverviewResponse,
    SalaryInsightResponse,
    SkillInsightResponse,
)
from app.services.major_direction_service import resolve_major_direction
from app.services.market_insight_client import MarketInsightClient
from app.services.opportunity_analysis_service import _education_level, _experience_years, score_resume_against_job


router = APIRouter()
client = MarketInsightClient(settings.MARKET_API_URL, settings.MARKET_API_TIMEOUT_SECONDS)


def get_market_client() -> MarketInsightClient:
    return client


def _job_payload(detail: JobDetailResponse) -> dict:
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


def _apply_consistent_match_scores(
    result: JobSearchResponse,
    *,
    resume: ResumeVersion | None,
    market_client: MarketInsightClient,
) -> None:
    """Use the detail-page scoring function for every displayed recommendation.

    The market service still performs broad recall and inexpensive reranking. Numeric
    scores shown to users must come from the same evidence function used on the detail
    page, otherwise a job can appear as 70% in the list and 84% after opening it.
    """
    if resume is None or not result.jobs:
        for job in result.jobs:
            job.match_score = None
        return

    profile = resume.structured_profile or {}

    def score_job(job_id: str):
        try:
            detail = market_client.get_job(job_id)
            return score_resume_against_job(
                resume.content_text,
                list(resume.extracted_skills or []),
                _job_payload(detail),
                profile,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            return None

    scores: dict[str, tuple[int, dict] | None] = {}
    worker_count = min(8, len(result.jobs))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {pool.submit(score_job, job.job_id): job.job_id for job in result.jobs}
        for future in as_completed(futures):
            scores[futures[future]] = future.result()

    for job in result.jobs:
        scored = scores.get(job.job_id)
        if scored is None:
            job.match_score = None
            continue
        score, _breakdown = scored
        job.match_score = score
        job.match_reasons = [*job.match_reasons, "与详情采用同一证据评分口径"]

    result.jobs.sort(key=lambda item: item.match_score if item.match_score is not None else -1, reverse=True)


@router.get("/jobs", response_model=JobSearchResponse)
def search_jobs(
    keyword: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    major: Optional[str] = None,
    recruitment_type: Optional[Literal["campus", "internship", "social"]] = None,
    city: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    limit: Optional[int] = Query(None, ge=1, le=50),
    sort_by: Literal[
        "default",
        "relevance",
        "observed_desc",
        "observed_asc",
        "published_desc",
        "published_asc",
    ] = "default",
    match_major: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    match_skills: list[str] = []
    resume_skills: list[str] = []
    profile_skills: list[str] = []
    match_experience_months: int | None = None
    match_education_level: int | None = None
    resume: ResumeVersion | None = None
    if sort_by == "relevance":
        resume = (
            db.query(ResumeVersion)
            .filter(ResumeVersion.user_id == user.id, ResumeVersion.is_active.is_(True))
            .order_by(ResumeVersion.version_number.desc())
            .first()
        )
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        resume_skills = list(resume.extracted_skills or []) if resume else []
        profile_skills = list(profile.skills or []) if profile else []
        for value in [*resume_skills, *profile_skills]:
            skill = str(value).strip()
            if skill and skill.lower() not in {item.lower() for item in match_skills}:
                match_skills.append(skill)
            if len(match_skills) >= 20:
                break
        resume_text = resume.content_text if resume else ""
        extracted_years = _experience_years(resume_text)
        profile_years = max(0, int(profile.years_of_experience or 0)) if profile else 0
        match_experience_months = max(extracted_years, profile_years) * 12
        match_education_level = _education_level(resume_text)
    result = market_client.search_jobs(
        keyword,
        city,
        page,
        limit or page_size,
        company=company,
        job_title=job_title,
        major=major,
        recruitment_type=recruitment_type,
        sort_by=sort_by,
        match_major=match_major,
        match_skills=match_skills,
        match_experience_months=match_experience_months,
        match_education_level=match_education_level,
    )
    if sort_by == "relevance":
        _apply_consistent_match_scores(result, resume=resume, market_client=market_client)
        result.personalized = bool(resume_skills or profile_skills)
        result.ranking_basis = [
            *(["求职方向"] if job_title else []),
            *(["输入专业"] if match_major else []),
            *(["当前简历技能"] if resume_skills else []),
            *(["个人档案技能"] if profile_skills else []),
            "经历与学历门槛",
            "岗位信息完整度",
        ]
        result.candidate_total = result.candidate_total if result.candidate_total is not None else result.total
        result.total = min(result.total, result.page_size * 2)
        result.total_pages = min(result.total_pages, 2)
        result.has_previous = result.page > 1
        result.has_next = result.page < result.total_pages
    return result


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def job_detail(
    job_id: str,
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    try:
        return market_client.get_job(job_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="岗位不存在或暂不提供展示") from exc
        raise HTTPException(status_code=503, detail="岗位详情服务暂时不可用") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="岗位详情服务暂时不可用") from exc


@router.get("/insights/salary", response_model=SalaryInsightResponse)
def salary_insight(
    job_family: str,
    city: str,
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.salary_insight(job_family, city)


@router.get("/insights/overview", response_model=MarketOverviewResponse)
def market_overview(
    job_family: Optional[str] = None,
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.overview(job_family)


@router.post("/directions/resolve", response_model=DirectionResolveResponse)
def resolve_direction(
    request: DirectionResolveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    overview = MarketOverviewResponse.model_validate(market_client.overview())
    if overview.availability == "unavailable" or not overview.job_families:
        raise HTTPException(status_code=503, detail="市场方向数据暂时不可用")
    return resolve_major_direction(request.query, overview, db, user.id)


@router.get("/insights/skills", response_model=SkillInsightResponse)
def skill_insight(
    job_family: str,
    limit: int = Query(8, ge=1, le=20),
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.skill_insight(job_family, limit)
