from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.market import JobSearchResponse, SalaryInsightResponse, SkillInsightResponse
from app.services.market_insight_client import MarketInsightClient


router = APIRouter()
client = MarketInsightClient(settings.MARKET_API_URL, settings.MARKET_API_TIMEOUT_SECONDS)


def get_market_client() -> MarketInsightClient:
    return client


@router.get("/jobs", response_model=JobSearchResponse)
def search_jobs(
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = Query(10, ge=1, le=20),
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.search_jobs(keyword, city, limit)


@router.get("/insights/salary", response_model=SalaryInsightResponse)
def salary_insight(
    job_family: str,
    city: str,
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.salary_insight(job_family, city)


@router.get("/insights/skills", response_model=SkillInsightResponse)
def skill_insight(
    job_family: str,
    limit: int = Query(8, ge=1, le=20),
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.skill_insight(job_family, limit)
