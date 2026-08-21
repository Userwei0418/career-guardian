from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any, List


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


class PayslipCreateRequest(BaseModel):
    career_event_id: Optional[int] = None
    source_action_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    pay_month: Optional[str] = None
    gross_salary: float
    base_salary: Optional[float] = None
    performance: Optional[float] = None
    allowance: Optional[float] = None
    social_insurance: Optional[float] = None
    housing_fund: Optional[float] = None
    individual_tax: Optional[float] = None
    other_deductions: Optional[float] = None
    net_salary: float
    raw_text: Optional[str] = None
    expected_salary: Optional[float] = None
    city: Optional[str] = None


class PayslipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    career_event_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    pay_month: Optional[str] = None
    gross_salary: Optional[float] = None
    base_salary: Optional[float] = None
    performance: Optional[float] = None
    allowance: Optional[float] = None
    social_insurance: Optional[float] = None
    housing_fund: Optional[float] = None
    individual_tax: Optional[float] = None
    other_deductions: Optional[float] = None
    net_salary: Optional[float] = None
    created_at: datetime


class PayslipCreateResponse(BaseModel):
    payslip: PayslipResponse
    analysis: PayslipAnalyzeResponse
    difference_from_offer_gross: Optional[float] = None
    finding_id: int
    action_id: Optional[int] = None
