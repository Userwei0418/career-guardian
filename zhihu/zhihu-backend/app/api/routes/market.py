from __future__ import annotations

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


router = APIRouter()
client = MarketInsightClient(settings.MARKET_API_URL, settings.MARKET_API_TIMEOUT_SECONDS)


def get_market_client() -> MarketInsightClient:
    return client


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
    sort_by: Literal["default", "relevance"] = "default",
    match_major: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    match_skills: list[str] = []
    resume_skills: list[str] = []
    profile_skills: list[str] = []
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
    )
    if sort_by == "relevance":
        result.personalized = bool(resume_skills or profile_skills)
        result.ranking_basis = [
            *(["求职方向"] if job_title else []),
            *(["输入专业"] if match_major else []),
            *(["当前简历技能"] if resume_skills else []),
            *(["个人档案技能"] if profile_skills else []),
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
