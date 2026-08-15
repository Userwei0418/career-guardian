from pydantic import BaseModel
from typing import Optional, List, Any


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
