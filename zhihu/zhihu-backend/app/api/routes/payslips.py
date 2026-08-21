"""工资条 API"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.offer import Offer
from app.models.payslip import Payslip
from app.models.user import User
from app.services.payslip_service import analyze_payslip
from app.services.decision_handoff_service import record_decision_handoff_outcome
from app.schemas.payslip import (
    PayslipAnalyzeRequest,
    PayslipAnalyzeResponse,
    PayslipCreateRequest,
    PayslipCreateResponse,
    PayslipResponse,
)

router = APIRouter()


@router.get("/", response_model=list[PayslipResponse])
def list_payslips(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case_ids = [item.id for item in db.query(CareerCase.id).filter(CareerCase.user_id == user.id).all()]
    if not case_ids:
        return []
    return (
        db.query(Payslip)
        .filter(Payslip.case_id.in_(case_ids))
        .order_by(Payslip.created_at.desc(), Payslip.id.desc())
        .all()
    )


@router.get("/{payslip_id}", response_model=PayslipResponse)
def get_payslip(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(Payslip.id == payslip_id, CareerCase.user_id == user.id)
        .first()
    )
    if payslip is None:
        raise HTTPException(status_code=404, detail="工资条不存在")
    return payslip


@router.post("/", response_model=PayslipCreateResponse)
def create_payslip(
    data: PayslipCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer: Optional[Offer] = None
    if data.linked_offer_id is not None:
        offer = get_owned_offer(db, data.linked_offer_id, user)
        case_id = offer.case_id
    else:
        case = CareerCase(
            user_id=user.id,
            type="payslip_review",
            title=f"{data.pay_month or '本月'}工资核对",
        )
        db.add(case)
        db.flush()
        case_id = case.id

    if data.career_event_id is not None:
        event = get_owned_event(db, data.career_event_id, user)
        if event.event_type != "income":
            raise HTTPException(status_code=400, detail="工资条必须关联收入守护事件")
    else:
        event = CareerEvent(
            user_id=user.id,
            event_type="income",
            title=f"{data.pay_month or '本月'}工资核对",
            status="active",
            stage="payslip_review",
        )
        db.add(event)
        db.flush()
    model_data = data.model_dump(
        exclude={"expected_salary", "city", "career_event_id", "source_action_id"},
        exclude_unset=True,
    )
    payslip = Payslip(
        case_id=case_id,
        career_event_id=event.id,
        **model_data,
    )
    db.add(payslip)
    db.flush()

    expected_salary = (
        float(offer.monthly_salary)
        if offer is not None and offer.monthly_salary is not None
        else data.expected_salary
    )
    city = offer.city if offer is not None and offer.city else data.city
    analysis_data = {
        "gross_salary": data.gross_salary,
        "base_salary": data.base_salary or 0,
        "performance": data.performance or 0,
        "allowance": data.allowance or 0,
        "social_insurance": data.social_insurance or 0,
        "housing_fund": data.housing_fund or 0,
        "individual_tax": data.individual_tax or 0,
        "other_deductions": data.other_deductions or 0,
        "net_salary": data.net_salary,
    }
    analysis = PayslipAnalyzeResponse.model_validate(
        analyze_payslip(analysis_data, expected_salary, city)
    )
    gross_difference = data.gross_salary - expected_salary if expected_salary is not None else None
    evidence = Evidence(
        event_id=event.id,
        evidence_type="payslip",
        source_type="user_material",
        title=f"{data.pay_month or '本月'}工资条金额",
        content_excerpt=f"应发 {data.gross_salary:.0f} 元，实发 {data.net_salary:.0f} 元",
        source_ref=f"payslip:{payslip.id}",
        extra_data={
            "private_user_material": True,
            "linked_offer_id": offer.id if offer else None,
            "offer_monthly_salary": expected_salary,
            "gross_salary": data.gross_salary,
            "difference": gross_difference,
        },
        confidence=1,
    )
    db.add(evidence)
    db.flush()
    if gross_difference is not None and abs(gross_difference) > 100:
        direction = "少" if gross_difference < 0 else "多"
        finding_title = f"本月应发比 Offer {direction} {abs(gross_difference):.0f} 元"
        severity = "high"
        finding_status = "open"
        action_title = f"向薪酬确认本月{direction}发 {abs(gross_difference):.0f} 元的原因"
    else:
        finding_title = "本月应发与已知 Offer 口径基本一致"
        severity = "info"
        finding_status = "confirmed"
        action_title = None
    finding = GuardianFinding(
        event_id=event.id,
        evidence_id=evidence.id,
        domain="income",
        category="offer_payslip_difference",
        severity=severity,
        status=finding_status,
        title=finding_title,
        explanation="差额只是核对线索，需结合入职日、试用期、请假和绩效明细确认。",
        source_type="calculation",
        confidence=1,
    )
    db.add(finding)
    db.flush()
    action = None
    if action_title:
        action = ActionItem(
            event_id=event.id,
            finding_id=finding.id,
            title=action_title,
            status="pending",
            priority=5,
            requires_confirmation=True,
        )
        db.add(action)
        db.flush()
        event.status = "attention"
    if data.source_action_id is not None:
        source_action = (
            db.query(ActionItem)
            .filter(ActionItem.id == data.source_action_id, ActionItem.event_id == event.id)
            .first()
        )
        if source_action is None:
            raise HTTPException(status_code=404, detail="收入守护待办不存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source_action.status = "completed"
        source_action.confirmed_at = source_action.confirmed_at or now
        source_action.completed_at = now
        record_decision_handoff_outcome(
            db,
            user_id=user.id,
            handoff_event=event,
            outcome_type="first_payslip_recorded",
            result=f"{data.pay_month or '本月'}工资条 {payslip.id} 已保存并进入收入核对",
            action_id=source_action.id,
        )
    db.commit()
    db.refresh(payslip)
    return PayslipCreateResponse(
        payslip=payslip,
        analysis=analysis,
        difference_from_offer_gross=gross_difference,
        finding_id=finding.id,
        action_id=action.id if action else None,
    )


@router.post("/analyze", response_model=PayslipAnalyzeResponse)
def analyze(
    data: PayslipAnalyzeRequest,
    user: User = Depends(get_current_user),
):
    result = analyze_payslip(data.payslip, data.expected_salary, data.city)
    return result
