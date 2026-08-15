"""财务规划 API"""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User
from app.services.finance_service import estimate_pension, estimate_medical_retirement, estimate_housing_fund, get_default_retire_age
from app.schemas.finance import RetirementAgeResponse, PensionResponse, MedicalResponse, HousingFundResponse

router = APIRouter()


@router.get("/retirement-age", response_model=RetirementAgeResponse)
def get_retirement_age(gender: str = "male", worker_type: str = "management", user: User = Depends(get_current_user)):
    return RetirementAgeResponse(
        gender=gender,
        worker_type=worker_type,
        default_age=get_default_retire_age(gender, worker_type),
    )


@router.get("/pension", response_model=PensionResponse)
def get_pension_estimate(
    current_age: int = 25,
    retire_age: int = 60,
    salary: float = 15000,
    city: str = "杭州",
    salary_growth: float = 0.05,
    gender: str = "male",
    user: User = Depends(get_current_user),
):
    r = estimate_pension(current_age, retire_age, salary, city, salary_growth, gender)
    return r


@router.get("/medical", response_model=MedicalResponse)
def get_medical_retirement(
    current_age: int = 25,
    retire_age: int = 60,
    city: str = "杭州",
    gender: str = "male",
    salary: float = 15000,
    user: User = Depends(get_current_user),
):
    r = estimate_medical_retirement(current_age, retire_age, city, gender, salary)
    return r


@router.get("/housing-fund", response_model=HousingFundResponse)
def get_housing_fund(
    monthly_contribution: float = 3600,
    months_paid: int = 24,
    user: User = Depends(get_current_user),
):
    r = estimate_housing_fund(monthly_contribution, months_paid)
    return r
