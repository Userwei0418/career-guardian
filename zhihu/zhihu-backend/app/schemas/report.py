from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Literal, Optional, List


class InsuranceDetail(BaseModel):
    pension: float
    medical: float
    unemployment: float
    housing_fund: float
    supplementary_housing: float = 0
    supplementary_medical: float = 0
    total: float


class BonusDetail(BaseModel):
    months: float
    amount: float
    tax_separate: float
    tax_combined: float
    tax: float
    after_tax: float
    recommendation: str


class AnnualDetail(BaseModel):
    gross: float
    take_home: float
    tax: float
    housing_fund_total: float
    real_package: float


class SalaryCalcResult(BaseModel):
    city: str
    gross: float
    performance: float
    subsidies: float
    total_income: float
    insurance: InsuranceDetail
    special_deduction: float
    taxable_income: float
    income_tax: float
    take_home: float
    employer: dict
    bonus: BonusDetail
    annual: AnnualDetail
    monthly_living_cost: float
    monthly_savings: float
    annual_savings: float
    savings_rate: float


class CityData(BaseModel):
    name: str
    pension: float
    medical: float
    unemployment: float
    housing: float
    living_cost: float
    cost_breakdown: dict


class CostBreakdownResponse(BaseModel):
    city: str
    breakdown: dict


class HRQuestionsResponse(BaseModel):
    offer_id: int
    questions: List[Any]


class OfferAnalysisSnapshotCreate(BaseModel):
    living_cost: Optional[float] = Field(default=None, ge=0, le=200000)
    variable_realization: float = Field(default=0.7, ge=0, le=1)
    extra_salary_months_realization: float = Field(default=1, ge=0, le=1)


class OfferAnalysisSnapshotResponse(BaseModel):
    id: int
    offer_id: int
    offer_revision_id: Optional[int] = None
    assumptions: dict
    result_snapshot: dict
    created_at: datetime
    is_stale: bool
    stale_reasons: List[str]


class HRConfirmationRequest(BaseModel):
    question_title: str = Field(min_length=1, max_length=300)
    question_script: Optional[str] = None
    reply: str = Field(min_length=1)
    conclusion: Optional[str] = None
    follow_up_action: Optional[str] = Field(default=None, max_length=300)
    fact_key: Optional[str] = Field(default=None, max_length=50)


class HRConfirmationResponse(BaseModel):
    offer_id: int
    event_id: int
    evidence_id: int
    finding_id: int
    action_id: Optional[int] = None
    status: str


class HRConfirmationItem(BaseModel):
    evidence_id: int
    question_title: str
    question_script: Optional[str] = None
    reply: str
    fact_key: Optional[str] = None
    status: str
    conclusion: str
    follow_up_action: Optional[str] = None
    applied_field_key: Optional[str] = None
    applied_value: Any = None
    applied_period: Optional[str] = None
    applied_revision_id: Optional[int] = None
    applied_revision_no: Optional[int] = None
    applied_at: Any = None
    created_at: Any


class HRConfirmationsResponse(BaseModel):
    offer_id: int
    items: List[HRConfirmationItem]


class HRFactApplyRequest(BaseModel):
    field_key: str = Field(min_length=1, max_length=80)
    value: Any
    period: Optional[Literal["month", "year"]] = None
    confirm: bool = False


class HRFactApplyResponse(BaseModel):
    offer_id: int
    evidence_id: int
    field_key: str
    field_label: str
    previous_value: Any = None
    normalized_value: Any
    period: Optional[str] = None
    issues_before: List[dict]
    issues_after: List[dict]
    applied: bool
    revision_id: Optional[int] = None
    revision_no: Optional[int] = None


class NegotiationBriefResponse(BaseModel):
    offer_id: int
    readiness: str
    summary: str
    anchors: List[str]
    requests: List[dict]
    opening_script: str
    fallback_script: str
    cautions: List[str]
