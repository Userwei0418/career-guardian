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


class PayslipCreateRequest(BaseModel):
    career_event_id: Optional[int] = None
    source_action_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    linked_offer_ids: List[int] = Field(default_factory=list, max_length=20)
    linked_contract_ids: List[int] = Field(default_factory=list, max_length=20)
    pay_month: Optional[str] = None
    pay_date: Optional[date] = None
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
    expected_salary: Optional[float] = None
    city: Optional[str] = None


class PayslipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    career_event_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    pay_month: Optional[str] = None
    pay_date: Optional[date] = None
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
    created_at: datetime


class PayslipRecognitionCandidate(BaseModel):
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
    source_type: Literal["file", "ocr"]
    original_filename: str
    original_file_retained: bool = False
    raw_text: Optional[str] = None
    candidates: List[PayslipRecognitionCandidate] = Field(min_length=1, max_length=200)


class PayslipMaterialSummary(BaseModel):
    material_type: Literal["offer", "contract"]
    material_id: int
    title: str
    salary_reference: Optional[str] = None


class PayslipMaterialComparison(BaseModel):
    material_type: Literal["offer", "contract"]
    material_id: int
    material_title: str
    reference_amount: Optional[float] = None
    gross_salary: float
    difference: Optional[float] = None
    status: Literal["matched", "different", "unknown"]
    explanation: str


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
    amount: Decimal
    suggested_allocation: Decimal
    transaction_date: date
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
    allocated_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reasons: List[str] = Field(default_factory=list, max_length=12)


class PayslipArrivalLinkCreateRequest(BaseModel):
    links: List[PayslipArrivalLinkItem] = Field(min_length=1, max_length=20)


class PayslipArrivalLinkResponse(BaseModel):
    id: int
    transaction_id: int
    allocated_amount: Decimal
    transaction_date: date
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
