"""Offer 分析报告 + HR 话术 + 薪资计算 API"""
from copy import copy

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_current_user
from app.api.ownership import get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.offer import Offer, OfferAnalysisSnapshot, OfferDecisionContext, OfferRevision
from app.models.user_profile import UserProfile
from app.models.opportunity_target import JobTarget
from app.models.career_event import ActionItem, Evidence, GuardianFinding
from app.api.routes.market import get_market_client
from app.services.market_insight_client import MarketInsightClient
from app.services.report_service import generate_offer_report, generate_hr_questions, generate_negotiation_brief
from app.services.offer_fact_service import (
    FIELD_SPEC_BY_KEY,
    build_offer_facts,
    create_offer_revision,
    normalize_hr_fact_value,
    validate_offer_facts,
)
from app.services.calculator_service import calculate_salary, get_city_data, get_cost_breakdown, CITY_INSURANCE_DATA, CITY_COST_BREAKDOWN
from app.schemas.report import (
    CityData,
    CostBreakdownResponse,
    HRConfirmationRequest,
    HRConfirmationResponse,
    HRFactApplyRequest,
    HRFactApplyResponse,
    HRConfirmationItem,
    HRConfirmationsResponse,
    HRQuestionsResponse,
    NegotiationBriefResponse,
    OfferAnalysisSnapshotCreate,
    OfferAnalysisSnapshotResponse,
    SalaryCalcResult,
)

router = APIRouter()


def _analysis_snapshot_response(
    db: Session,
    *,
    offer: Offer,
    snapshot: OfferAnalysisSnapshot,
    profile: Optional[UserProfile] = None,
    decision_context: Optional[OfferDecisionContext] = None,
) -> OfferAnalysisSnapshotResponse:
    current_revision = (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_no.desc(), OfferRevision.id.desc())
        .first()
    )
    stale_reasons = []
    if (current_revision.id if current_revision else None) != snapshot.offer_revision_id:
        stale_reasons.append("Offer 事实版本已经变化")
    if offer.updated_at and snapshot.created_at and offer.updated_at > snapshot.created_at:
        stale_reasons.append("Offer 档案在保存后有更新")
    if profile and profile.updated_at and snapshot.created_at and profile.updated_at > snapshot.created_at:
        stale_reasons.append("个人优先项或生活底线已经变化")
    if decision_context and decision_context.updated_at and snapshot.created_at and decision_context.updated_at > snapshot.created_at:
        stale_reasons.append("现实替代、红线或取舍已经变化")
    return OfferAnalysisSnapshotResponse(
        id=snapshot.id,
        offer_id=snapshot.offer_id,
        offer_revision_id=snapshot.offer_revision_id,
        assumptions=snapshot.assumptions or {},
        result_snapshot=snapshot.result_snapshot or {},
        created_at=snapshot.created_at,
        is_stale=bool(stale_reasons),
        stale_reasons=stale_reasons,
    )


def _confirmation_items(db: Session, offer: Offer) -> list[HRConfirmationItem]:
    if offer.career_event_id is None:
        return []
    evidence_rows = (
        db.query(Evidence)
        .filter(Evidence.event_id == offer.career_event_id, Evidence.evidence_type == "hr_reply")
        .order_by(Evidence.created_at.desc(), Evidence.id.desc())
        .all()
    )
    items = []
    for evidence in evidence_rows:
        finding = (
            db.query(GuardianFinding)
            .filter(GuardianFinding.evidence_id == evidence.id, GuardianFinding.category == "hr_confirmation")
            .order_by(GuardianFinding.id.desc())
            .first()
        )
        action = None
        if finding:
            action = db.query(ActionItem).filter(ActionItem.finding_id == finding.id).order_by(ActionItem.id.desc()).first()
        extra = evidence.extra_data or {}
        items.append(HRConfirmationItem(
            evidence_id=evidence.id,
            question_title=evidence.title,
            question_script=extra.get("question_script"),
            reply=evidence.content_excerpt or "",
            fact_key=extra.get("fact_key"),
            status="confirmed" if finding and finding.status == "confirmed" else "follow_up",
            conclusion=finding.title if finding else "HR 回复已保留",
            follow_up_action=action.title if action else None,
            applied_field_key=extra.get("applied_field_key"),
            applied_value=extra.get("applied_value"),
            applied_period=extra.get("applied_period"),
            applied_revision_id=extra.get("applied_revision_id"),
            applied_revision_no=extra.get("applied_revision_no"),
            applied_at=extra.get("applied_at"),
            created_at=evidence.created_at,
        ))
    return items


@router.get("/offer/{offer_id}")
def get_offer_report(
    offer_id: int,
    living_cost: Optional[float] = Query(default=None, ge=0, le=200000),
    variable_realization: float = Query(default=0.7, ge=0, le=1),
    extra_salary_months_realization: float = Query(default=1, ge=0, le=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    offer = get_owned_offer(db, offer_id, user)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    decision_context = (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer.id,
            OfferDecisionContext.user_id == user.id,
        )
        .first()
    )
    priorities = profile.priorities if profile else []

    market_insight = market_client.salary_insight(offer.job_title, offer.city) if offer.job_title and offer.city else None
    target = None
    if offer.job_target_id:
        target = (
            db.query(JobTarget)
            .filter(JobTarget.id == offer.job_target_id, JobTarget.user_id == user.id)
            .first()
        )
    confirmations = _confirmation_items(db, offer)
    fact_view = build_offer_facts(db, offer)
    confirmed_fact_keys = {
        item["field_key"]
        for item in fact_view["items"]
        if item["verification_status"] in {"user_confirmed", "hr_reported", "written_confirmed"}
    }
    report = generate_offer_report(
        offer,
        priorities,
        market_insight,
        profile=profile,
        target=target,
        living_cost=living_cost,
        variable_realization=variable_realization,
        extra_salary_months_realization=extra_salary_months_realization,
        confirmed_fact_keys=confirmed_fact_keys,
        confirmation_count=len(confirmations),
    )
    report["facts"] = fact_view
    revisions = (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_no.desc(), OfferRevision.id.desc())
        .all()
    )
    revision_by_id = {revision.id: revision for revision in revisions}
    revision_items = []
    for revision in revisions:
        previous = revision_by_id.get(revision.supersedes_revision_id)
        current_snapshot = revision.facts_snapshot or {}
        previous_snapshot = previous.facts_snapshot if previous else {}
        changed_fields = [
            FIELD_SPEC_BY_KEY[field_key]["label"]
            for field_key in FIELD_SPEC_BY_KEY
            if current_snapshot.get(field_key) != previous_snapshot.get(field_key)
        ]
        revision_items.append({
            "id": revision.id,
            "revision_no": revision.revision_no,
            "created_reason": revision.created_reason,
            "source_type": revision.source_type,
            "changed_fields": changed_fields,
            "created_at": revision.created_at,
        })
    report["fact_revisions"] = revision_items
    report["personal_context"] = {
        "priorities": list(priorities or []),
        "monthly_budget": profile.monthly_budget if profile else None,
        "savings_goal": profile.savings_goal if profile else None,
        "decision_context": jsonable_encoder(decision_context) if decision_context else None,
        "profile_updated_at": profile.updated_at if profile else None,
    }
    return report


@router.get(
    "/offer/{offer_id}/snapshots",
    response_model=List[OfferAnalysisSnapshotResponse],
)
def list_offer_analysis_snapshots(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    decision_context = (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer.id,
            OfferDecisionContext.user_id == user.id,
        )
        .first()
    )
    snapshots = (
        db.query(OfferAnalysisSnapshot)
        .filter(
            OfferAnalysisSnapshot.offer_id == offer.id,
            OfferAnalysisSnapshot.user_id == user.id,
        )
        .order_by(OfferAnalysisSnapshot.created_at.desc(), OfferAnalysisSnapshot.id.desc())
        .limit(20)
        .all()
    )
    return [
        _analysis_snapshot_response(
            db,
            offer=offer,
            snapshot=snapshot,
            profile=profile,
            decision_context=decision_context,
        )
        for snapshot in snapshots
    ]


@router.post(
    "/offer/{offer_id}/snapshots",
    response_model=OfferAnalysisSnapshotResponse,
)
def save_offer_analysis_snapshot(
    offer_id: int,
    data: OfferAnalysisSnapshotCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    offer = get_owned_offer(db, offer_id, user)
    report = get_offer_report(
        offer_id=offer_id,
        living_cost=data.living_cost,
        variable_realization=data.variable_realization,
        extra_salary_months_realization=data.extra_salary_months_realization,
        user=user,
        db=db,
        market_client=market_client,
    )
    if report.get("calculation", {}).get("status") != "ready":
        raise HTTPException(status_code=409, detail="当前事实仍阻断收入分析，请先修正后再保存分析快照")
    encoded_assumptions = jsonable_encoder(report.get("assumptions") or {})
    encoded_report = jsonable_encoder(report)
    latest_snapshot = (
        db.query(OfferAnalysisSnapshot)
        .filter(
            OfferAnalysisSnapshot.offer_id == offer.id,
            OfferAnalysisSnapshot.user_id == user.id,
        )
        .order_by(OfferAnalysisSnapshot.created_at.desc(), OfferAnalysisSnapshot.id.desc())
        .first()
    )
    if (
        latest_snapshot is not None
        and latest_snapshot.offer_revision_id == report.get("facts", {}).get("revision_id")
        and latest_snapshot.assumptions == encoded_assumptions
        and latest_snapshot.result_snapshot == encoded_report
    ):
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        decision_context = (
            db.query(OfferDecisionContext)
            .filter(
                OfferDecisionContext.offer_id == offer.id,
                OfferDecisionContext.user_id == user.id,
            )
            .first()
        )
        return _analysis_snapshot_response(
            db,
            offer=offer,
            snapshot=latest_snapshot,
            profile=profile,
            decision_context=decision_context,
        )
    snapshot = OfferAnalysisSnapshot(
        offer_id=offer.id,
        user_id=user.id,
        offer_revision_id=report.get("facts", {}).get("revision_id"),
        assumptions=encoded_assumptions,
        result_snapshot=encoded_report,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    decision_context = (
        db.query(OfferDecisionContext)
        .filter(
            OfferDecisionContext.offer_id == offer.id,
            OfferDecisionContext.user_id == user.id,
        )
        .first()
    )
    return _analysis_snapshot_response(
        db,
        offer=offer,
        snapshot=snapshot,
        profile=profile,
        decision_context=decision_context,
    )


@router.get("/offer/{offer_id}/hr-questions", response_model=HRQuestionsResponse)
def get_hr_questions(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = get_owned_offer(db, offer_id, user)

    report = generate_offer_report(offer)
    questions = generate_hr_questions(offer, report.get("findings", []))
    return HRQuestionsResponse(offer_id=offer_id, questions=questions)


@router.get("/offer/{offer_id}/hr-confirmations", response_model=HRConfirmationsResponse)
def get_hr_confirmations(offer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = get_owned_offer(db, offer_id, user)
    return HRConfirmationsResponse(offer_id=offer.id, items=_confirmation_items(db, offer))


@router.get("/offer/{offer_id}/negotiation-brief", response_model=NegotiationBriefResponse)
def get_negotiation_brief(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    offer = get_owned_offer(db, offer_id, user)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    market_insight = market_client.salary_insight(offer.job_title, offer.city) if offer.job_title and offer.city else None
    target = None
    if offer.job_target_id:
        target = db.query(JobTarget).filter(JobTarget.id == offer.job_target_id, JobTarget.user_id == user.id).first()
    confirmations = _confirmation_items(db, offer)
    fact_view = build_offer_facts(db, offer)
    confirmed_fact_keys = {
        item["field_key"]
        for item in fact_view["items"]
        if item["verification_status"] in {"user_confirmed", "hr_reported", "written_confirmed"}
    }
    report = generate_offer_report(
        offer,
        profile.priorities if profile else [],
        market_insight,
        profile=profile,
        target=target,
        confirmed_fact_keys=confirmed_fact_keys,
        confirmation_count=len(confirmations),
    )
    return generate_negotiation_brief(offer, report)


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
            "fact_key": data.fact_key,
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


@router.post(
    "/offer/{offer_id}/hr-confirmations/{evidence_id}/apply",
    response_model=HRFactApplyResponse,
)
def apply_hr_confirmation_to_fact(
    offer_id: int,
    evidence_id: int,
    data: HRFactApplyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    offer = get_owned_offer(db, offer_id, user)
    if offer.career_event_id is None:
        raise HTTPException(status_code=409, detail="Offer 尚未关联决策守护事件")
    evidence = (
        db.query(Evidence)
        .filter(
            Evidence.id == evidence_id,
            Evidence.event_id == offer.career_event_id,
            Evidence.evidence_type == "hr_reply",
        )
        .first()
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="HR 回复证据不存在")

    try:
        normalized = normalize_hr_fact_value(data.field_key, data.value, period=data.period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    previous_value = getattr(offer, data.field_key, None)
    issues_before = validate_offer_facts(offer)
    preview_offer = copy(offer)
    setattr(preview_offer, data.field_key, normalized)
    issues_after = validate_offer_facts(preview_offer)
    spec = FIELD_SPEC_BY_KEY[data.field_key]
    response = {
        "offer_id": offer.id,
        "evidence_id": evidence.id,
        "field_key": data.field_key,
        "field_label": spec["label"],
        "previous_value": previous_value,
        "normalized_value": normalized,
        "period": data.period,
        "issues_before": issues_before,
        "issues_after": issues_after,
        "applied": False,
        "revision_id": None,
        "revision_no": None,
    }
    if not data.confirm:
        return response

    extra = dict(evidence.extra_data or {})
    existing_revision_id = extra.get("applied_revision_id")
    if existing_revision_id and extra.get("applied_field_key") == data.field_key and extra.get("applied_value") == jsonable_encoder(normalized):
        revision = (
            db.query(OfferRevision)
            .filter(OfferRevision.id == existing_revision_id, OfferRevision.offer_id == offer.id)
            .first()
        )
        if revision is not None and getattr(offer, data.field_key, None) == normalized:
            return {**response, "applied": True, "revision_id": revision.id, "revision_no": revision.revision_no}

    setattr(offer, data.field_key, normalized)
    revision = create_offer_revision(
        db,
        offer,
        user.id,
        reason="hr_confirmation",
        source_type="hr_reply",
        evidence_id=evidence.id,
        source_field_key=data.field_key,
    )
    db.refresh(revision)
    extra.update({
        "applied_field_key": data.field_key,
        "applied_value": jsonable_encoder(normalized),
        "applied_period": data.period,
        "applied_revision_id": revision.id,
        "applied_revision_no": revision.revision_no,
        "applied_at": revision.created_at.isoformat() if revision.created_at else None,
        "applied_by_user": True,
    })
    evidence.extra_data = extra
    finding = (
        db.query(GuardianFinding)
        .filter(GuardianFinding.evidence_id == evidence.id, GuardianFinding.category == "hr_confirmation")
        .order_by(GuardianFinding.id.desc())
        .first()
    )
    if finding is not None and finding.status != "open":
        finding.status = "confirmed"
        finding.title = f"{spec['label']}已由用户确认写入 Offer 事实"
    db.commit()
    db.refresh(revision)
    return {
        **response,
        "applied": True,
        "revision_id": revision.id,
        "revision_no": revision.revision_no,
    }


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
