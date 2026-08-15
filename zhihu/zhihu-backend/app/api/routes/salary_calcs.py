"""薪资计算保存 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.salary_calculation import SalaryCalculation
from app.schemas.salary import SalaryCalcCreate, SalaryCalcSummary, SalaryCalcDetail, SalaryCalcDeleteResponse

router = APIRouter()


@router.get("/", response_model=List[SalaryCalcSummary])
def list_calculations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    calcs = db.query(SalaryCalculation).filter(
        SalaryCalculation.user_id == user.id
    ).order_by(SalaryCalculation.created_at.desc()).all()
    return [
        SalaryCalcSummary(
            id=c.id,
            name=c.name,
            city=c.city,
            monthly_salary=float(c.monthly_salary) if c.monthly_salary else None,
            result_take_home=float(c.result_take_home) if c.result_take_home else None,
            result_annual_take_home=float(c.result_annual_take_home) if c.result_annual_take_home else None,
            result_savings_rate=float(c.result_savings_rate) if c.result_savings_rate else None,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in calcs
    ]


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
    return SalaryCalcSummary(
        id=calc.id,
        name=calc.name,
        city=calc.city,
        monthly_salary=float(calc.monthly_salary) if calc.monthly_salary else None,
        result_take_home=float(calc.result_take_home) if calc.result_take_home else None,
        result_annual_take_home=float(calc.result_annual_take_home) if calc.result_annual_take_home else None,
        result_savings_rate=float(calc.result_savings_rate) if calc.result_savings_rate else None,
        created_at=calc.created_at.isoformat() if calc.created_at else None,
    )


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
        monthly_salary=float(calc.monthly_salary) if calc.monthly_salary else None,
        performance=float(calc.performance) if calc.performance else 0,
        subsidies=calc.subsidies,
        housing_ratio=float(calc.housing_ratio) if calc.housing_ratio else 12,
        supplementary_housing_ratio=float(calc.supplementary_housing_ratio) if calc.supplementary_housing_ratio else 0,
        supplementary_medical=float(calc.supplementary_medical) if calc.supplementary_medical else 0,
        special_deduction=float(calc.special_deduction) if calc.special_deduction else 0,
        social_insurance_base=float(calc.social_insurance_base) if calc.social_insurance_base else None,
        bonus_months=float(calc.bonus_months) if calc.bonus_months else 0,
        living_cost=float(calc.living_cost) if calc.living_cost else None,
        result_take_home=float(calc.result_take_home) if calc.result_take_home else None,
        result_annual_take_home=float(calc.result_annual_take_home) if calc.result_annual_take_home else None,
        result_savings_rate=float(calc.result_savings_rate) if calc.result_savings_rate else None,
        result_json=calc.result_json,
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
