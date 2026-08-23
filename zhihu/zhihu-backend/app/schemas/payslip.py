from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional, List


class PayslipAnalyzeRequest(BaseModel):
    payslip: dict = Field(default_factory=dict)
    expected_salary: Optional[float] = None
    city: Optional[str] = None


class PayslipAnalyzeResponse(BaseModel):
    gross: float
    deductions: dict
    net_salary: float
    expected_net: Optional[float] = None
    diff_from_expected: Optional[float] = None
    insurance_diff: Optional[dict] = None
    findings: List[dict] = Field(default_factory=list)
    arithmetic_status: Literal["matched", "mismatch", "unknown"] = "unknown"
    calculated_net: Optional[float] = None
    arithmetic_diff: Optional[float] = None
    unknown_fields: List[str] = Field(default_factory=list)


class PayslipMaterialPreferenceInput(BaseModel):
    material_type: Literal["offer", "contract"]
    material_id: int = Field(gt=0)
    application_status: Literal["preferred", "reference", "unresolved"] = "unresolved"
    priority_rank: int = Field(default=100, ge=1, le=1000)
    user_note: Optional[str] = Field(default=None, max_length=500)


class PayslipCreateRequest(BaseModel):
    career_event_id: Optional[int] = None
    source_action_id: Optional[int] = None
    supersedes_payslip_id: Optional[int] = Field(default=None, ge=1)
    linked_offer_id: Optional[int] = None
    linked_offer_ids: List[int] = Field(default_factory=list, max_length=20)
    linked_contract_ids: List[int] = Field(default_factory=list, max_length=20)
    material_preferences: List[PayslipMaterialPreferenceInput] = Field(default_factory=list, max_length=40)
    pay_month: Optional[str] = None
    pay_date: Optional[date] = None
    agreed_pay_date: Optional[date] = None
    agreed_pay_date_source_contract_id: Optional[int] = Field(default=None, gt=0)
    agreed_pay_date_adjustment: Optional[Literal["contract_date", "advance", "defer"]] = None
    employer_name: Optional[str] = Field(default=None, max_length=255)
    gross_salary: float
    base_salary: Optional[float] = None
    performance: Optional[float] = None
    bonus: Optional[float] = None
    overtime_pay: Optional[float] = None
    allowance: Optional[float] = None
    social_insurance: Optional[float] = None
    housing_fund: Optional[float] = None
    individual_tax: Optional[float] = None
    attendance_deductions: Optional[float] = None
    meal_deductions: Optional[float] = None
    other_deductions: Optional[float] = None
    net_salary: float
    custom_items: List[dict[str, str]] = Field(default_factory=list, max_length=80)
    source_type: Literal["manual", "file", "ocr"] = "manual"
    recognition_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    raw_text: Optional[str] = Field(default=None, max_length=100_000)
    recognition_candidate_id: Optional[int] = Field(default=None, gt=0)
    recognition_candidate_version: Optional[int] = Field(default=None, gt=0)
    expected_salary: Optional[float] = None
    city: Optional[str] = None


class PayslipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    career_event_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    supersedes_payslip_id: Optional[int] = None
    record_status: Literal["active", "superseded", "deleted"] = "active"
    pay_month: Optional[str] = None
    pay_date: Optional[date] = None
    agreed_pay_date: Optional[date] = None
    agreed_pay_date_source_type: Optional[Literal["manual", "material_suggestion"]] = None
    agreed_pay_date_source_contract_id: Optional[int] = None
    agreed_pay_date_schedule: Optional[str] = None
    agreed_pay_date_adjustment: Optional[Literal["contract_date", "advance", "defer"]] = None
    agreed_pay_date_calendar_version: Optional[str] = None
    employer_name: Optional[str] = None
    gross_salary: Optional[float] = None
    base_salary: Optional[float] = None
    performance: Optional[float] = None
    bonus: Optional[float] = None
    overtime_pay: Optional[float] = None
    allowance: Optional[float] = None
    social_insurance: Optional[float] = None
    housing_fund: Optional[float] = None
    individual_tax: Optional[float] = None
    attendance_deductions: Optional[float] = None
    meal_deductions: Optional[float] = None
    other_deductions: Optional[float] = None
    net_salary: Optional[float] = None
    custom_items: Optional[List[dict[str, str]]] = None
    source_type: str = "manual"
    recognition_confidence: Optional[float] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime


class PayslipRecognitionCandidate(BaseModel):
    candidate_id: Optional[int] = Field(default=None, gt=0)
    review_status: Literal["pending", "confirmed", "excluded"] = "pending"
    version: int = Field(default=1, ge=1)
    payslip_id: Optional[int] = Field(default=None, gt=0)
    row_number: int = Field(ge=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    confidence_tier: Literal["high", "medium", "low"] = "low"
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    employer_name: Optional[str] = None
    pay_month: Optional[str] = None
    pay_date: Optional[date] = None
    gross_salary: Optional[Decimal] = None
    base_salary: Optional[Decimal] = None
    performance: Optional[Decimal] = None
    bonus: Optional[Decimal] = None
    overtime_pay: Optional[Decimal] = None
    allowance: Optional[Decimal] = None
    social_insurance: Optional[Decimal] = None
    housing_fund: Optional[Decimal] = None
    individual_tax: Optional[Decimal] = None
    attendance_deductions: Optional[Decimal] = None
    meal_deductions: Optional[Decimal] = None
    other_deductions: Optional[Decimal] = None
    net_salary: Optional[Decimal] = None
    custom_items: List[dict[str, str]] = Field(default_factory=list)
    unknown_fields: List[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)


class PayslipRecognitionResponse(BaseModel):
    batch_id: Optional[int] = Field(default=None, gt=0)
    batch_status: Literal["review", "completed"] = "review"
    resumed_existing_batch: bool = False
    source_type: Literal["file", "ocr"]
    original_filename: str
    original_file_retained: bool = False
    raw_text: Optional[str] = None
    candidates: List[PayslipRecognitionCandidate] = Field(min_length=1, max_length=200)


class PayslipRecognitionBatchSummary(BaseModel):
    batch_id: int
    batch_status: Literal["review", "completed"]
    source_type: Literal["file", "ocr"]
    original_filename: str
    total_count: int
    pending_count: int
    confirmed_count: int
    excluded_count: int
    created_at: datetime
    updated_at: datetime


class PayslipRecognitionCandidateUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    candidate: PayslipRecognitionCandidate


class PayslipRecognitionBulkConfirmItem(BaseModel):
    candidate_id: int = Field(gt=0)
    version: int = Field(ge=1)


class PayslipRecognitionBulkConfirmRequest(BaseModel):
    items: List[PayslipRecognitionBulkConfirmItem] = Field(min_length=1, max_length=50)
    linked_offer_ids: List[int] = Field(default_factory=list, max_length=20)
    linked_contract_ids: List[int] = Field(default_factory=list, max_length=20)
    material_preferences: List[PayslipMaterialPreferenceInput] = Field(default_factory=list, max_length=40)
    expected_salary: Optional[float] = None
    city: Optional[str] = Field(default=None, max_length=100)


class PayslipRecognitionBulkConfirmResponse(BaseModel):
    batch: PayslipRecognitionResponse
    payslip_ids: List[int]


class PayslipPayDateSuggestionRequest(BaseModel):
    pay_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    linked_contract_ids: List[int] = Field(min_length=1, max_length=20)
    material_preferences: List[PayslipMaterialPreferenceInput] = Field(default_factory=list, max_length=20)


class PayslipPayDateOption(BaseModel):
    date: date
    adjustment: Literal["contract_date", "advance", "defer"]
    label: str
    reason: str


class PayslipPayDateSuggestion(BaseModel):
    contract_id: int
    contract_title: str
    document_kind: str
    application_status: Literal["preferred", "reference", "unresolved"]
    schedule_text: Optional[str] = None
    base_date: Optional[date] = None
    recommended_date: Optional[date] = None
    recommended_adjustment: Optional[Literal["contract_date", "advance", "defer"]] = None
    calendar_covered: bool = False
    calendar_version: Optional[str] = None
    calendar_source_title: Optional[str] = None
    calendar_source_url: Optional[str] = None
    status: Literal[
        "ready",
        "needs_adjustment_choice",
        "calendar_unknown",
        "schedule_not_found",
        "ambiguous_period",
        "invalid_schedule",
    ]
    reasons: List[str] = Field(default_factory=list)
    options: List[PayslipPayDateOption] = Field(default_factory=list)
    requires_user_confirmation: bool = True


class PayslipPayDateSuggestionResponse(BaseModel):
    pay_month: str
    suggestions: List[PayslipPayDateSuggestion] = Field(default_factory=list)


class PayslipMaterialSummary(BaseModel):
    material_type: Literal["offer", "contract"]
    material_id: int
    title: str
    salary_reference: Optional[str] = None
    document_kind: Optional[str] = None
    application_status: Literal["preferred", "reference", "unresolved"] = "unresolved"
    priority_rank: int = 100
    user_note: Optional[str] = None


class PayslipFieldComparison(BaseModel):
    field: str
    label: str
    reference_value: Optional[str] = None
    observed_value: Optional[str] = None
    difference: Optional[float] = None
    status: Literal["matched", "different", "unknown"]
    explanation: str


class PayslipMaterialComparison(BaseModel):
    material_type: Literal["offer", "contract"]
    material_id: int
    material_title: str
    reference_amount: Optional[float] = None
    gross_salary: float
    difference: Optional[float] = None
    status: Literal["matched", "different", "unknown"]
    attention_count: int = Field(default=0, ge=0)
    explanation: str
    field_checks: List[PayslipFieldComparison] = Field(default_factory=list)
    document_kind: Optional[str] = None
    application_status: Literal["preferred", "reference", "unresolved"] = "unresolved"
    priority_rank: int = 100
    user_note: Optional[str] = None


class PayslipDetailResponse(PayslipResponse):
    materials: List[PayslipMaterialSummary] = Field(default_factory=list)
    material_comparisons: List[PayslipMaterialComparison] = Field(default_factory=list)


class PayslipCreateResponse(BaseModel):
    payslip: PayslipResponse
    analysis: PayslipAnalyzeResponse
    difference_from_offer_gross: Optional[float] = None
    materials: List[PayslipMaterialSummary] = Field(default_factory=list)
    material_comparisons: List[PayslipMaterialComparison] = Field(default_factory=list)
    finding_id: int
    action_id: Optional[int] = None


class PayslipArrivalSuggestion(BaseModel):
    transaction_id: int
    economic_fact_id: int
    amount: Decimal
    available_amount: Decimal
    source_transaction_amount: Decimal
    suggested_allocation: Decimal
    transaction_date: date
    fact_title: str
    is_split_component: bool = False
    merchant: Optional[str] = None
    description: Optional[str] = None
    score: int = Field(ge=0, le=100)
    confidence_tier: Literal["high", "medium", "low"]
    reasons: List[str] = Field(default_factory=list)
    linked_to_other_payslip: bool = False
    requires_ai_review: bool = False
    ai_status: Literal["not_needed", "completed", "unavailable"] = "not_needed"
    ai_assessment: Optional[Literal["likely", "unlikely", "uncertain"]] = None
    ai_reason: Optional[str] = None


class PayslipArrivalSuggestionResponse(BaseModel):
    payslip_id: int
    net_salary: Decimal
    suggestions: List[PayslipArrivalSuggestion] = Field(default_factory=list)


class PayslipArrivalLinkItem(BaseModel):
    transaction_id: int
    economic_fact_id: Optional[int] = Field(default=None, gt=0)
    allocated_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reasons: List[str] = Field(default_factory=list, max_length=12)


class PayslipArrivalLinkCreateRequest(BaseModel):
    links: List[PayslipArrivalLinkItem] = Field(min_length=1, max_length=20)


class PayslipArrivalLinkResponse(BaseModel):
    id: int
    transaction_id: int
    economic_fact_id: int
    allocated_amount: Decimal
    transaction_date: date
    fact_title: str
    fact_amount: Decimal
    is_split_component: bool = False
    ledger_revision: Optional[int] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    status: Literal["confirmed", "reversed"]
    match_reason: List[str] = Field(default_factory=list)
    confirmed_at: datetime
    reversed_at: Optional[datetime] = None


class PayslipArrivalLinkSummary(BaseModel):
    payslip_id: int
    net_salary: Decimal
    confirmed_amount: Decimal
    remaining_amount: Decimal
    match_status: Literal["unmatched", "partial", "matched"]
    links: List[PayslipArrivalLinkResponse] = Field(default_factory=list)


class PayslipArrivalLinkRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    link_id: int
    link_revision: int = Field(ge=1)
    ledger_revision: int = Field(ge=1)
    operation: Literal["confirm", "reverse"]
    before_snapshot: Optional[dict] = None
    after_snapshot: dict
    reason: Optional[str] = None
    created_at: datetime


class PayslipComponentChange(BaseModel):
    field: str
    label: str
    previous_amount: float
    current_amount: float
    difference: float


class PayslipMonthComparison(BaseModel):
    payslip_id: int
    previous_payslip_id: Optional[int] = None
    current_pay_month: Optional[str] = None
    previous_pay_month: Optional[str] = None
    changes: List[PayslipComponentChange] = Field(default_factory=list)


class PayslipGuardianCheck(BaseModel):
    key: str
    status: Literal["confirmed", "attention", "unverified"]
    severity: Literal["info", "medium", "high"]
    title: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)


class PayslipGuardianSummary(BaseModel):
    payslip_id: int
    checks: List[PayslipGuardianCheck] = Field(default_factory=list)
    attention_count: int = Field(default=0, ge=0)
    unverified_count: int = Field(default=0, ge=0)
    hr_questions: List[str] = Field(default_factory=list)
    materials_to_prepare: List[str] = Field(default_factory=list)
