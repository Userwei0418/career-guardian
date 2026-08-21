from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class SalaryCalcCreate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    monthly_salary: Optional[float] = None
    performance: float = 0
    subsidies: Optional[Any] = None
    housing_ratio: float = 12
    supplementary_housing_ratio: float = 0
    supplementary_medical: float = 0
    special_deduction: float = 0
    social_insurance_base: Optional[float] = None
    bonus_months: float = 0
    living_cost: Optional[float] = None
    result_take_home: Optional[float] = None
    result_annual_take_home: Optional[float] = None
    result_savings_rate: Optional[float] = None
    result_monthly_savings: Optional[float] = None
    result_json: Optional[Any] = None


class SalaryCalcSummary(BaseModel):
    id: int
    name: Optional[str] = None
    city: Optional[str] = None
    monthly_salary: Optional[float] = None
    result_take_home: Optional[float] = None
    result_annual_take_home: Optional[float] = None
    result_savings_rate: Optional[float] = None
    result_monthly_savings: Optional[float] = None
    source_context: Optional[Any] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class SalaryCalcDetail(BaseModel):
    id: int
    name: Optional[str] = None
    city: Optional[str] = None
    monthly_salary: Optional[float] = None
    performance: float = 0
    subsidies: Optional[Any] = None
    housing_ratio: float = 12
    supplementary_housing_ratio: float = 0
    supplementary_medical: float = 0
    special_deduction: float = 0
    social_insurance_base: Optional[float] = None
    bonus_months: float = 0
    living_cost: Optional[float] = None
    result_take_home: Optional[float] = None
    result_annual_take_home: Optional[float] = None
    result_savings_rate: Optional[float] = None
    result_json: Optional[Any] = None
    source_context: Optional[Any] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class SalaryCalcDeleteResponse(BaseModel):
    ok: bool
