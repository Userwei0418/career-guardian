from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OfferComparisonAssumptions(BaseModel):
    offer_a_living_cost: Optional[float] = Field(default=None, ge=0, le=200000)
    offer_b_living_cost: Optional[float] = Field(default=None, ge=0, le=200000)
    offer_a_variable_realization: Optional[float] = Field(default=None, ge=0, le=1)
    offer_b_variable_realization: Optional[float] = Field(default=None, ge=0, le=1)
    offer_a_extra_salary_months_realization: Optional[float] = Field(default=None, ge=0, le=1)
    offer_b_extra_salary_months_realization: Optional[float] = Field(default=None, ge=0, le=1)
    # 兼容旧客户端；新页面使用每份 Offer 独立假设。
    variable_realization: float = Field(default=0.7, ge=0, le=1)
    extra_salary_months_realization: float = Field(default=1, ge=0, le=1)


class OfferComparisonCreateRequest(BaseModel):
    offer_a_id: int = Field(gt=0)
    offer_b_id: int = Field(gt=0)
    title: Optional[str] = Field(default=None, max_length=300)
    priorities: Optional[list[str]] = Field(default=None, max_length=3)
    assumptions: OfferComparisonAssumptions = Field(default_factory=OfferComparisonAssumptions)

class OfferComparisonResponse(BaseModel):
    id: int
    offer_a_id: int
    offer_b_id: int
    title: str
    status: str
    preference_snapshot: dict
    assumption_snapshot: dict
    offer_snapshot: dict
    result_snapshot: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
