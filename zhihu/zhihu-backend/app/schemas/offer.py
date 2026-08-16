from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
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
    salary_months: int = 12
    fixed_salary: Optional[float] = None
    variable_salary: Optional[float] = None
    bonus: Optional[str] = None
    allowance: Optional[float] = None
    probation_months: int = 0
    probation_salary_rate: float = 0.80
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    start_date: Optional[str] = None
    extraction_confidence: Optional[float] = Field(default=None, ge=0, le=1)


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
    salary_months: int = 12
    fixed_salary: Optional[float] = None
    variable_salary: Optional[float] = None
    bonus: Optional[str] = None
    allowance: Optional[float] = None
    probation_months: int = 0
    probation_salary_rate: float = 0.80
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    start_date: Optional[str] = None
    extraction_confidence: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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
