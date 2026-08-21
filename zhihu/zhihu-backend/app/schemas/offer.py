from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from decimal import Decimal


class OfferField(BaseModel):
    """带置信度的抽取字段"""
    value: Optional[str] = None
    confidence: float = 1.0
    evidence_text: Optional[str] = None


class OfferExtractedFields(BaseModel):
    """LLM 抽取的 Offer 结构化字段"""
    company_name: OfferField = OfferField()
    job_title: OfferField = OfferField()
    city: OfferField = OfferField()
    monthly_salary: OfferField = OfferField()
    salary_months: OfferField = OfferField()
    fixed_salary: OfferField = OfferField()
    variable_salary: OfferField = OfferField()
    bonus: OfferField = OfferField()
    allowance: OfferField = OfferField()
    probation_months: OfferField = OfferField()
    probation_salary_rate: OfferField = OfferField()
    work_location: OfferField = OfferField()
    working_hours: OfferField = OfferField()
    start_date: OfferField = OfferField()


class OfferCreateRequest(BaseModel):
    case_id: Optional[int] = None
    career_event_id: Optional[int] = None
    job_target_id: Optional[int] = Field(default=None, gt=0)
    source_attachment_id: Optional[int] = Field(default=None, gt=0)
    name: Optional[str] = None
    offer_kind: Literal["verbal", "written"] = "written"
    decision_status: Literal["evaluating", "on_hold", "accepted", "declined", "expired"] = "evaluating"
    response_deadline: Optional[datetime] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
    employment_type: Optional[str] = None
    department: Optional[str] = None
    job_level: Optional[str] = None
    work_mode: Optional[str] = None
    monthly_salary: Optional[float] = None
    salary_months: Optional[int] = Field(default=None, ge=12, le=36)
    fixed_salary: Optional[float] = None
    variable_salary: Optional[float] = None
    bonus: Optional[str] = None
    allowance: Optional[float] = None
    probation_months: Optional[int] = Field(default=None, ge=0, le=12)
    probation_salary_rate: Optional[float] = Field(default=None, ge=0, le=1)
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    start_date: Optional[str] = None
    extraction_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    confirm_facts: bool = False


class OfferUpdateRequest(BaseModel):
    job_target_id: Optional[int] = Field(default=None, gt=0)
    source_attachment_id: Optional[int] = Field(default=None, gt=0)
    name: Optional[str] = None
    offer_kind: Optional[Literal["verbal", "written"]] = None
    decision_status: Optional[Literal["evaluating", "on_hold", "accepted", "declined", "expired"]] = None
    response_deadline: Optional[datetime] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
    employment_type: Optional[str] = None
    department: Optional[str] = None
    job_level: Optional[str] = None
    work_mode: Optional[str] = None
    monthly_salary: Optional[float] = None
    salary_months: Optional[int] = Field(default=None, ge=12, le=36)
    fixed_salary: Optional[float] = None
    variable_salary: Optional[float] = None
    bonus: Optional[str] = None
    allowance: Optional[float] = None
    probation_months: Optional[int] = Field(default=None, ge=0, le=12)
    probation_salary_rate: Optional[float] = Field(default=None, ge=0, le=1)
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    start_date: Optional[str] = None
    extraction_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    confirm_facts: bool = False


class OfferResponse(BaseModel):
    id: int
    case_id: int
    career_event_id: Optional[int] = None
    job_target_id: Optional[int] = None
    source_attachment_id: Optional[int] = None
    name: Optional[str] = None
    offer_kind: Literal["verbal", "written"] = "written"
    decision_status: Literal["evaluating", "on_hold", "accepted", "declined", "expired"] = "evaluating"
    response_deadline: Optional[datetime] = None
    facts_confirmed_at: Optional[datetime] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
    employment_type: Optional[str] = None
    department: Optional[str] = None
    job_level: Optional[str] = None
    work_mode: Optional[str] = None
    monthly_salary: Optional[float] = None
    salary_months: Optional[int] = None
    fixed_salary: Optional[float] = None
    variable_salary: Optional[float] = None
    bonus: Optional[str] = None
    allowance: Optional[float] = None
    probation_months: Optional[int] = None
    probation_salary_rate: Optional[float] = None
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    start_date: Optional[str] = None
    extraction_confidence: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OfferDecisionAnalysisContext(BaseModel):
    living_cost: Optional[float] = Field(default=None, ge=0, le=200000)
    living_cost_source: Optional[str] = Field(default=None, max_length=100)
    variable_realization: Optional[float] = Field(default=None, ge=0, le=1)
    extra_salary_months_realization: Optional[float] = Field(default=None, ge=0, le=1)
    market_availability: Optional[str] = Field(default=None, max_length=50)
    market_data_mode: Optional[str] = Field(default=None, max_length=50)
    market_description: Optional[str] = Field(default=None, max_length=500)
    market_sample_size: Optional[int] = Field(default=None, ge=0)
    market_quality_grade: Optional[str] = Field(default=None, max_length=20)
    market_methodology_version: Optional[str] = Field(default=None, max_length=100)
    market_source_names: list[str] = Field(default_factory=list, max_length=20)
    captured_at: Optional[datetime] = None


class OfferDecisionContextUpdate(BaseModel):
    baseline_type: Optional[Literal["continue_search", "current_job", "other"]] = None
    baseline_label: Optional[str] = Field(default=None, max_length=200)
    baseline_monthly_take_home: Optional[float] = Field(default=None, ge=0, le=1000000)
    baseline_annual_bonus: Optional[float] = Field(default=None, ge=0, le=10000000)
    baseline_city: Optional[str] = Field(default=None, max_length=50)
    search_runway_months: Optional[int] = Field(default=None, ge=0, le=120)
    baseline_notes: Optional[str] = Field(default=None, max_length=2000)
    must_haves: list[str] = Field(default_factory=list, max_length=5)
    red_lines: list[str] = Field(default_factory=list, max_length=5)
    acceptable_tradeoffs: list[str] = Field(default_factory=list, max_length=5)

    @field_validator(
        "baseline_label",
        "baseline_city",
        "baseline_notes",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("must_haves", "red_lines", "acceptable_tradeoffs")
    @classmethod
    def normalize_lines(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = str(value).strip()
            if not item or item in normalized:
                continue
            if len(item) > 200:
                raise ValueError("每条底线或取舍不能超过 200 个字符")
            normalized.append(item)
        return normalized


class OfferDecisionContextResponse(OfferDecisionContextUpdate):
    id: int
    offer_id: int
    updated_at: datetime

    class Config:
        from_attributes = True


class OfferDecisionSetupRequest(BaseModel):
    priorities: list[Literal["income", "growth", "city_life"]] = Field(default_factory=list, max_length=3)
    monthly_budget: Optional[int] = Field(default=None, ge=0, le=1000000)
    savings_goal: Optional[int] = Field(default=None, ge=0, le=1000000)
    decision_context: OfferDecisionContextUpdate


class OfferDecisionSetupResponse(BaseModel):
    offer_id: int
    priorities: list[str]
    monthly_budget: Optional[int] = None
    savings_goal: Optional[int] = None
    decision_context: OfferDecisionContextResponse


class OfferDecisionRequest(BaseModel):
    choice: Literal["accepted", "declined", "on_hold"]
    rationale: str = Field(min_length=2, max_length=4000)
    next_review_at: Optional[datetime] = None
    acknowledge_blockers: bool = False
    offer_revision_id: Optional[int] = Field(default=None, gt=0)
    analysis_snapshot_id: Optional[int] = Field(default=None, gt=0)
    analysis_context: Optional[OfferDecisionAnalysisContext] = None


FactVerificationStatus = Literal[
    "unknown",
    "extracted",
    "user_confirmed",
    "hr_reported",
    "written_confirmed",
    "estimated",
    "conflict",
    "superseded",
]


class OfferFactItem(BaseModel):
    field_key: str
    label: str
    value: Any = None
    display_value: Optional[str] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    period: Optional[str] = None
    source_type: str
    verification_status: FactVerificationStatus
    confidence: Optional[float] = None
    revision_id: Optional[int] = None
    updated_at: Optional[datetime] = None


class OfferFactIssue(BaseModel):
    code: str
    field_keys: list[str] = Field(default_factory=list)
    severity: Literal["blocking", "warning", "info"]
    title: str
    explanation: str
    action: str
    blocks_income: bool = False
    blocks_decision: bool = False


class OfferFactsResponse(BaseModel):
    offer_id: int
    revision_id: Optional[int] = None
    revision_no: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    confirmed_count: int
    total_count: int
    unknown_count: int
    conflict_count: int
    items: list[OfferFactItem]
    issues: list[OfferFactIssue]


class OfferRevisionCreateRequest(BaseModel):
    reason: Literal["user_confirmation", "correction"] = "user_confirmation"


class OfferRevisionResponse(BaseModel):
    id: int
    offer_id: int
    revision_no: int
    created_reason: str
    source_type: str
    facts_snapshot: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class OfferValidationResponse(BaseModel):
    offer_id: int
    calculation_status: Literal["ready", "blocked"]
    decision_status: Literal["ready", "needs_facts", "blocked"]
    issues: list[OfferFactIssue]


class OfferDecisionPreflightResponse(BaseModel):
    offer_id: int
    offer_revision_id: Optional[int] = None
    readiness: Literal["ready", "needs_facts", "blocked"]
    blocking_issues: list[OfferFactIssue]
    unknown_items: list[OfferFactItem]
    warnings: list[OfferFactIssue]
    requires_acknowledgement: bool
    decision_context: Optional[OfferDecisionContextResponse] = None


class OfferDecisionHandoff(BaseModel):
    event_id: int
    event_type: Literal["rights", "income", "growth"]
    title: str
    action_id: int
    action_title: str
    href: str


class OfferDecisionResult(BaseModel):
    offer_id: int
    decision_status: Literal["accepted", "declined", "on_hold"]
    decision_record_id: int
    decision_event_id: int
    decided_at: datetime
    handoffs: list[OfferDecisionHandoff] = Field(default_factory=list)


class OfferDecisionAttentionResponse(BaseModel):
    offer_id: int
    response_deadline: Optional[datetime] = None
    review_due_at: Optional[datetime] = None
    next_due_at: Optional[datetime] = None
    next_kind: Optional[Literal["response_deadline", "review", "action"]] = None
    overdue_count: int = 0
    pending_count: int = 0
    is_overdue: bool = False
    is_urgent: bool = False
    primary_message: str
    primary_href: str


class CaseCreateRequest(BaseModel):
    type: str
    title: Optional[str] = None


class CaseResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: Optional[str] = None
    status: str
    current_step: int

    class Config:
        from_attributes = True
