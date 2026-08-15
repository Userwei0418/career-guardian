from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.market import (
    JobDetailResponse,
    JobSearchResponse,
    SalaryInsightResponse,
    SkillInsightResponse,
)
from app.services.market_insight_client import MarketInsightClient


router = APIRouter()
client = MarketInsightClient(settings.MARKET_API_URL, settings.MARKET_API_TIMEOUT_SECONDS)


def get_market_client() -> MarketInsightClient:
    return client


@router.get("/jobs", response_model=JobSearchResponse)
def search_jobs(
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    limit: Optional[int] = Query(None, ge=1, le=50),
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.search_jobs(keyword, city, page, limit or page_size)


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
            raise HTTPException(status_code=404, detail="岗位不存在或尚未通过质量门") from exc
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


@router.get("/insights/skills", response_model=SkillInsightResponse)
def skill_insight(
    job_family: str,
    limit: int = Query(8, ge=1, le=20),
    _user: User = Depends(get_current_user),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    return market_client.skill_insight(job_family, limit)
