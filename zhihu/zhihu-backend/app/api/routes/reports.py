"""Offer 分析报告 + HR 话术 + 薪资计算 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_user
from app.api.ownership import get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.offer import Offer
from app.models.user_profile import UserProfile
from app.models.career_event import ActionItem, Evidence, GuardianFinding
from app.api.routes.market import get_market_client
from app.services.market_insight_client import MarketInsightClient
from app.services.report_service import generate_offer_report, generate_hr_questions
from app.services.calculator_service import calculate_salary, get_city_data, get_cost_breakdown, CITY_INSURANCE_DATA, CITY_COST_BREAKDOWN
from app.schemas.report import (
    CityData,
    CostBreakdownResponse,
    HRConfirmationRequest,
    HRConfirmationResponse,
    HRQuestionsResponse,
    SalaryCalcResult,
)

router = APIRouter()


@router.get("/offer/{offer_id}")
def get_offer_report(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    offer = get_owned_offer(db, offer_id, user)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    priorities = profile.priorities if profile else []

    market_insight = (
        market_client.salary_insight(offer.job_title, offer.city or "杭州")
        if offer.job_title
        else None
    )
    return generate_offer_report(offer, priorities, market_insight)


@router.get("/offer/{offer_id}/hr-questions", response_model=HRQuestionsResponse)
def get_hr_questions(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = get_owned_offer(db, offer_id, user)

    report = generate_offer_report(offer)
    questions = generate_hr_questions(offer, report.get("findings", []))
    return HRQuestionsResponse(offer_id=offer_id, questions=questions)


@router.post(
    "/offer/{offer_id}/hr-confirmations",
    response_model=HRConfirmationResponse,
)
def record_hr_confirmation(
    offer_id: int,
    data: HRConfirmationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    if offer.career_event_id is None:
        raise HTTPException(status_code=409, detail="Offer 尚未关联决策守护事件")

    evidence = Evidence(
        event_id=offer.career_event_id,
        evidence_type="hr_reply",
        source_type="user_material",
        title=data.question_title,
        content_excerpt=data.reply,
        source_ref=f"offer:{offer.id}:hr-confirmation",
        extra_data={
            "private_user_material": True,
            "question_script": data.question_script,
            "confirmed_by_user": True,
        },
        confidence=1,
    )
    db.add(evidence)
    db.flush()
    finding = GuardianFinding(
        event_id=offer.career_event_id,
        evidence_id=evidence.id,
        domain="decision",
        category="hr_confirmation",
        severity="warning" if data.follow_up_action else "info",
        status="open" if data.follow_up_action else "confirmed",
        title=data.conclusion or "HR 回复已保留，待与合同原文核对",
        explanation="该结论来自用户录入的 HR 回复，不是市场事实或系统推测。",
        source_type="user_material",
        confidence=1,
    )
    db.add(finding)
    db.flush()
    action = None
    if data.follow_up_action:
        action = ActionItem(
            event_id=offer.career_event_id,
            finding_id=finding.id,
            title=data.follow_up_action,
            status="pending",
            priority=20,
            requires_confirmation=True,
        )
        db.add(action)
        db.flush()
    db.commit()
    return HRConfirmationResponse(
        offer_id=offer.id,
        event_id=offer.career_event_id,
        evidence_id=evidence.id,
        finding_id=finding.id,
        action_id=action.id if action else None,
        status="follow_up" if action else "confirmed",
    )


@router.get("/salary/calculate")
def calc_salary(
    salary: float,
    city: str = "杭州",
    housing_ratio: float = None,
    special_deduction: float = 0,
    living_cost: float = None,
    performance: float = 0,
    meal_subsidy: float = 0,
    transport_subsidy: float = 0,
    housing_subsidy: float = 0,
    communication_subsidy: float = 0,
    supplementary_housing_ratio: float = 0,
    supplementary_medical: float = 0,
    social_insurance_base: float = None,
    bonus_months: float = 0,
    user: User = Depends(get_current_user),
):
    result = calculate_salary(
        monthly_salary=salary,
        city=city,
        housing_ratio=housing_ratio,
        special_deduction=special_deduction,
        living_cost=living_cost,
        performance=performance,
        meal_subsidy=meal_subsidy,
        transport_subsidy=transport_subsidy,
        housing_subsidy=housing_subsidy,
        communication_subsidy=communication_subsidy,
        supplementary_housing_ratio=supplementary_housing_ratio,
        supplementary_medical=supplementary_medical,
        social_insurance_base=social_insurance_base,
        bonus_months=bonus_months,
    )
    return {
        "city": city,
        "gross": result.gross_salary,
        "performance": result.performance,
        "subsidies": result.subsidies,
        "total_income": result.total_income,
        "insurance": {
            "pension": result.pension,
            "medical": result.medical,
            "unemployment": result.unemployment,
            "housing_fund": result.housing_fund,
            "supplementary_housing": result.supplementary_housing,
            "supplementary_medical": result.supplementary_medical,
            "total": result.total_insurance,
        },
        "special_deduction": result.special_deduction,
        "taxable_income": result.taxable_income,
        "income_tax": result.income_tax,
        "take_home": result.take_home,
        "employer": {
            "insurance": result.employer_insurance,
            "housing": result.employer_housing,
            "total_cost": result.employer_cost,
        },
        "bonus": {
            "months": result.bonus_months,
            "amount": result.bonus_amount,
            "tax_separate": result.bonus_tax_separate,
            "tax_combined": result.bonus_tax_combined,
            "tax": result.bonus_tax,
            "after_tax": result.bonus_after_tax,
            "recommendation": "单独计税" if result.bonus_tax_separate <= result.bonus_tax_combined else "合并计税",
        },
        "annual": {
            "gross": result.annual_gross,
            "take_home": result.annual_take_home,
            "tax": result.annual_tax,
            "housing_fund_total": result.annual_housing_fund_total,
            "real_package": result.real_annual_package,
        },
        "monthly_living_cost": result.monthly_living_cost,
        "monthly_savings": result.monthly_savings,
        "annual_savings": result.annual_savings,
        "savings_rate": result.savings_rate,
    }


@router.get("/salary/cities", response_model=List[CityData])
def get_city_list(user: User = Depends(get_current_user)):
    cities = []
    for name, data in CITY_INSURANCE_DATA.items():
        cost = CITY_COST_BREAKDOWN.get(name, {})
        cities.append(CityData(
            name=name,
            pension=data["pension"],
            medical=data["medical"],
            unemployment=data["unemployment"],
            housing=data["housing"],
            living_cost=data["living_cost"],
            cost_breakdown=cost,
        ))
    return cities


@router.get("/salary/cost-breakdown", response_model=CostBreakdownResponse)
def get_cost_detail(city: str = "杭州", user: User = Depends(get_current_user)):
    return CostBreakdownResponse(city=city, breakdown=get_cost_breakdown(city))
