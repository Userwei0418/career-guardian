from pydantic import BaseModel
from typing import Optional, List


class RetirementAgeResponse(BaseModel):
    gender: str
    worker_type: str
    default_age: int


class PensionResponse(BaseModel):
    current_age: int
    retire_age: int
    contribution_years: int
    min_required_years: int
    is_enough: bool
    monthly_contribution: float
    account_balance: float
    basic_pension: float
    personal_pension: float
    monthly_pension: float
    replacement_rate: float
    payback_years: float
    total_personal_paid: float
    avg_salary_at_retire: float


class MedicalResponse(BaseModel):
    city: str
    gender: str
    min_years: int
    current_age: int
    retire_age: int
    contribution_years: int
    remaining_years: int
    is_enough: bool
    reimbursement_rate: float
    monthly_account: float
    account_balance: float
    in_service_reimbursement: float


class HousingWithdrawalRule(BaseModel):
    scene: str
    condition: str
    amount: str


class HousingFundResponse(BaseModel):
    monthly_contribution: float
    months_paid: int
    current_balance: float
    balance_1y: float
    balance_3y: float
    balance_5y: float
    balance_10y: float
    withdrawal_rules: List[HousingWithdrawalRule]
