"""薪资计算保存 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.salary_calculation import SalaryCalculation
from app.schemas.salary import SalaryCalcCreate, SalaryCalcSummary, SalaryCalcDetail, SalaryCalcDeleteResponse

router = APIRouter()


def _result_json(calc: SalaryCalculation) -> dict:
    return calc.result_json if isinstance(calc.result_json, dict) else {}


def _source_context(calc: SalaryCalculation) -> Optional[dict]:
    context = _result_json(calc).get("source_context")
    return context if isinstance(context, dict) else None


def _monthly_savings(calc: SalaryCalculation) -> Optional[float]:
    value = _result_json(calc).get("monthly_savings")
    return float(value) if isinstance(value, (int, float)) else None


def _summary(calc: SalaryCalculation) -> SalaryCalcSummary:
    return SalaryCalcSummary(
        id=calc.id,
        name=calc.name,
        city=calc.city,
        monthly_salary=float(calc.monthly_salary) if calc.monthly_salary is not None else None,
        result_take_home=float(calc.result_take_home) if calc.result_take_home is not None else None,
        result_annual_take_home=float(calc.result_annual_take_home) if calc.result_annual_take_home is not None else None,
        result_savings_rate=float(calc.result_savings_rate) if calc.result_savings_rate is not None else None,
        result_monthly_savings=_monthly_savings(calc),
        source_context=_source_context(calc),
        created_at=calc.created_at.isoformat() if calc.created_at else None,
    )


@router.get("/", response_model=List[SalaryCalcSummary])
def list_calculations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    calcs = db.query(SalaryCalculation).filter(
        SalaryCalculation.user_id == user.id
    ).order_by(SalaryCalculation.created_at.desc()).all()
    return [_summary(calc) for calc in calcs]


@router.post("/", response_model=SalaryCalcSummary)
def save_calculation(
    data: SalaryCalcCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    calc = SalaryCalculation(
        user_id=user.id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(calc)
    db.commit()
    db.refresh(calc)
    return _summary(calc)


@router.get("/{calc_id}", response_model=SalaryCalcDetail)
def get_calculation(
    calc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    calc = db.query(SalaryCalculation).filter(
        SalaryCalculation.id == calc_id,
        SalaryCalculation.user_id == user.id,
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="计算记录不存在")
    return SalaryCalcDetail(
        id=calc.id,
        name=calc.name,
        city=calc.city,
        monthly_salary=float(calc.monthly_salary) if calc.monthly_salary is not None else None,
        performance=float(calc.performance) if calc.performance is not None else 0,
        subsidies=calc.subsidies,
        housing_ratio=float(calc.housing_ratio) if calc.housing_ratio is not None else 12,
        supplementary_housing_ratio=float(calc.supplementary_housing_ratio) if calc.supplementary_housing_ratio is not None else 0,
        supplementary_medical=float(calc.supplementary_medical) if calc.supplementary_medical is not None else 0,
        special_deduction=float(calc.special_deduction) if calc.special_deduction is not None else 0,
        social_insurance_base=float(calc.social_insurance_base) if calc.social_insurance_base is not None else None,
        bonus_months=float(calc.bonus_months) if calc.bonus_months is not None else 0,
        living_cost=float(calc.living_cost) if calc.living_cost is not None else None,
        result_take_home=float(calc.result_take_home) if calc.result_take_home is not None else None,
        result_annual_take_home=float(calc.result_annual_take_home) if calc.result_annual_take_home is not None else None,
        result_savings_rate=float(calc.result_savings_rate) if calc.result_savings_rate is not None else None,
        result_monthly_savings=_monthly_savings(calc),
        result_json=calc.result_json,
        source_context=_source_context(calc),
        created_at=calc.created_at.isoformat() if calc.created_at else None,
    )


@router.delete("/{calc_id}", response_model=SalaryCalcDeleteResponse)
def delete_calculation(
    calc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    calc = db.query(SalaryCalculation).filter(
        SalaryCalculation.id == calc_id,
        SalaryCalculation.user_id == user.id,
    ).first()
    if not calc:
        raise HTTPException(status_code=404, detail="计算记录不存在")
    db.delete(calc)
    db.commit()
    return SalaryCalcDeleteResponse(ok=True)
