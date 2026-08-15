from pydantic import BaseModel
from typing import Optional
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
    name: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
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


class OfferUpdateRequest(BaseModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
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
    name: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    city: Optional[str] = None
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
