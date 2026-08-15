from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketSourceRef(BaseModel):
    source_id: str
    source_name: str
    source_url: Optional[str] = None
    observed_at: datetime


class SalaryInsightResponse(BaseModel):
    availability: Literal["available", "insufficient_sample", "stale", "unavailable"]
    job_family: str
    city: str
    currency: str = "CNY"
    period: Literal["month", "year"] = "month"
    p25: Optional[float] = None
    p50: Optional[float] = None
    p75: Optional[float] = None
    sample_size: int = Field(ge=0)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    calculated_at: datetime
    methodology_version: str
    quality_grade: Literal["A", "B", "C", "insufficient"]
    sources: list[MarketSourceRef]
