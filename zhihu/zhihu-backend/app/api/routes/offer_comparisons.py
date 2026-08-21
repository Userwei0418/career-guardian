from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_offer
from app.api.routes.market import get_market_client
from app.db.session import get_db
from app.models.offer_comparison import OfferComparison
from app.models.opportunity_target import JobTarget
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.career_event import Evidence, GuardianFinding
from app.schemas.offer_comparison import OfferComparisonCreateRequest, OfferComparisonResponse
from app.services.market_insight_client import MarketInsightClient
from app.services.offer_comparison_service import build_comparison_result, build_offer_snapshot
from app.services.offer_fact_service import build_offer_facts
from app.services.report_service import generate_offer_report

router = APIRouter()


def _target(db: Session, user_id: int, offer):
    if not offer.job_target_id:
        return None
    return db.query(JobTarget).filter(JobTarget.id == offer.job_target_id, JobTarget.user_id == user_id).first()


def _report(db, user, profile, offer, living_cost, variable_realization, extra_salary_months_realization, market_client):
    market = market_client.salary_insight(offer.job_title, offer.city) if offer.job_title and offer.city else None
    confirmations = []
    if offer.career_event_id:
        confirmations = (
            db.query(Evidence, GuardianFinding)
            .join(GuardianFinding, GuardianFinding.evidence_id == Evidence.id)
            .filter(
                Evidence.event_id == offer.career_event_id,
                Evidence.evidence_type == "hr_reply",
                GuardianFinding.category == "hr_confirmation",
            )
            .all()
        )
    fact_view = build_offer_facts(db, offer)
    confirmed_fact_keys = {
        item["field_key"]
        for item in fact_view["items"]
        if item["verification_status"] in {"user_confirmed", "hr_reported", "written_confirmed"}
    }
    return generate_offer_report(
        offer,
        profile.priorities if profile else [],
        market,
        profile=profile,
        target=_target(db, user.id, offer),
        living_cost=living_cost,
        variable_realization=variable_realization,
        extra_salary_months_realization=extra_salary_months_realization,
        confirmed_fact_keys=confirmed_fact_keys,
        confirmation_count=len(confirmations),
    )


@router.get("/", response_model=list[OfferComparisonResponse])
def list_comparisons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(OfferComparison)
        .filter(OfferComparison.user_id == user.id)
        .order_by(OfferComparison.updated_at.desc(), OfferComparison.id.desc())
        .all()
    )


@router.get("/{comparison_id}", response_model=OfferComparisonResponse)
def get_comparison(comparison_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    comparison = db.query(OfferComparison).filter(OfferComparison.id == comparison_id, OfferComparison.user_id == user.id).first()
    if comparison is None:
        raise HTTPException(status_code=404, detail="Offer 对比记录不存在")
    return comparison


@router.post("/", response_model=OfferComparisonResponse)
def create_comparison(
    req: OfferComparisonCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    market_client: MarketInsightClient = Depends(get_market_client),
):
    if req.offer_a_id == req.offer_b_id:
        raise HTTPException(status_code=400, detail="请选择两份不同的 Offer")
    offer_a = get_owned_offer(db, req.offer_a_id, user)
    offer_b = get_owned_offer(db, req.offer_b_id, user)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    priorities = list(req.priorities if req.priorities is not None else (profile.priorities or [] if profile else []))[:3]
    assumptions = req.assumptions
    report_a = _report(
        db, user, profile, offer_a, assumptions.offer_a_living_cost,
        assumptions.offer_a_variable_realization if assumptions.offer_a_variable_realization is not None else assumptions.variable_realization,
        assumptions.offer_a_extra_salary_months_realization if assumptions.offer_a_extra_salary_months_realization is not None else assumptions.extra_salary_months_realization,
        market_client,
    )
    report_b = _report(
        db, user, profile, offer_b, assumptions.offer_b_living_cost,
        assumptions.offer_b_variable_realization if assumptions.offer_b_variable_realization is not None else assumptions.variable_realization,
        assumptions.offer_b_extra_salary_months_realization if assumptions.offer_b_extra_salary_months_realization is not None else assumptions.extra_salary_months_realization,
        market_client,
    )
    blocked = [
        {"offer_id": offer.id, "offer_name": offer.name or offer.company_name, "blockers": report["calculation"]["blockers"]}
        for offer, report in ((offer_a, report_a), (offer_b, report_b))
        if report["calculation"]["status"] == "blocked"
    ]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail="两份 Offer 的收入口径尚不可比，请先分别处理缺失或冲突事实。",
        )
    snapshots = {"a": build_offer_snapshot(offer_a), "b": build_offer_snapshot(offer_b)}
    preference_snapshot = {
        "priorities": priorities,
        "monthly_budget": profile.monthly_budget if profile else None,
        "savings_goal": profile.savings_goal if profile else None,
    }
    assumption_snapshot = {
        "a": report_a["assumptions"],
        "b": report_b["assumptions"],
    }
    result = build_comparison_result(report_a, report_b, snapshots, priorities)
    comparison = OfferComparison(
        user_id=user.id,
        offer_a_id=offer_a.id,
        offer_b_id=offer_b.id,
        title=req.title or f"{snapshots['a']['company_name'] or 'Offer A'} 与 {snapshots['b']['company_name'] or 'Offer B'}",
        preference_snapshot=jsonable_encoder(preference_snapshot),
        assumption_snapshot=jsonable_encoder(assumption_snapshot),
        offer_snapshot=jsonable_encoder(snapshots),
        result_snapshot=jsonable_encoder(result),
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)
    return comparison
