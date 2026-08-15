from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.models.contract import Contract
from app.models.offer import Offer
from app.models.payslip import Payslip
from app.models.user import User
from app.models.user_profile import UserProfile


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures/integrated_graduate_journey.json"


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event_ids(db: Session, user_id: int) -> dict[str, int]:
    return {
        event.event_type: event.id
        for event in db.query(CareerEvent)
        .filter(CareerEvent.user_id == user_id, CareerEvent.stage.like("demo_%"))
        .order_by(CareerEvent.id)
        .all()
    }


def create_integrated_demo_journey(db: Session, user: User) -> dict:
    existing_ids = _event_ids(db, user.id)
    if existing_ids:
        return {
            "fixture_id": "graduate-demo-2026-v1",
            "data_mode": "fixture",
            "created": False,
            "event_ids": existing_ids,
            "message": "该账号已有脱敏连续守护案例，未重复写入。",
        }

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    now = utc_now_naive()
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile is None:
        profile = UserProfile(user_id=user.id, **payload["profile"])
        db.add(profile)

    case = CareerCase(
        user_id=user.id,
        type="integrated_demo",
        title=payload["label"],
        status="in_progress",
        current_step=8,
    )
    db.add(case)
    db.flush()

    job = payload["job"]
    opportunity = CareerEvent(
        user_id=user.id,
        event_type="opportunity",
        title=f"{job['company_name']} · {job['title']}",
        status="completed",
        stage="demo_opportunity",
        completed_at=now,
    )
    decision = CareerEvent(
        user_id=user.id,
        legacy_case_id=case.id,
        event_type="decision",
        title=f"{job['company_name']} Offer 决策",
        status="completed",
        stage="demo_decision",
        completed_at=now,
    )
    rights = CareerEvent(
        user_id=user.id,
        event_type="rights",
        title=f"{job['company_name']} 签约检查",
        status="completed",
        stage="demo_rights",
        completed_at=now,
    )
    income = CareerEvent(
        user_id=user.id,
        event_type="income",
        title="2026 年 7 月首月工资核对",
        status="attention",
        stage="demo_income",
    )
    growth = CareerEvent(
        user_id=user.id,
        event_type="growth",
        title=f"{payload['growth']['target_role']} 90 天成长计划",
        status="active",
        stage="demo_growth",
    )
    db.add_all([opportunity, decision, rights, income, growth])
    db.flush()

    job_evidence = Evidence(
        event_id=opportunity.id,
        evidence_type="job_posting",
        source_type="market_data",
        title=f"{job['title']}岗位事实",
        content_excerpt=f"{job['city']}，月薪 {job['salary_min']}–{job['salary_max']} 元",
        source_ref=job["source_url"],
        extra_data={
            "job_id": job["job_id"],
            "data_mode": "fixture",
            "source_id": job["source_id"],
            "observed_at": job["observed_at"],
            "quality_grade": job["quality_grade"],
            "public_market_fact": True,
        },
        confidence=0.8,
    )
    db.add(job_evidence)
    db.flush()
    db.add_all(
        [
            GuardianFinding(
                event_id=opportunity.id,
                evidence_id=job_evidence.id,
                domain="opportunity",
                category="job_fact",
                severity="info",
                status="resolved",
                title="岗位来源、城市和薪资区间已保留",
                source_type="market_data",
                confidence=0.8,
            ),
            ActionItem(
                event_id=opportunity.id,
                title="完成岗位事实核对",
                status="completed",
                priority=20,
                requires_confirmation=True,
                confirmed_at=now,
                completed_at=now,
            ),
            Outcome(
                event_id=opportunity.id,
                outcome_type="job_selected",
                result="选择海岳科技数据分析师作为第一条连续守护主线。",
            ),
        ]
    )

    offer_data = payload["offer"]
    offer = Offer(
        case_id=case.id,
        career_event_id=decision.id,
        name="脱敏应届生 Offer",
        extraction_confidence=1,
        **offer_data,
    )
    db.add(offer)
    db.flush()
    offer_evidence = Evidence(
        event_id=decision.id,
        evidence_type="offer",
        source_type="user_material",
        title="已确认的脱敏 Offer 金额",
        content_excerpt="月薪 15000 元：固定 13000 元 + 绩效 2000 元",
        source_ref=f"offer:{offer.id}",
        extra_data={"private_user_material": True, "data_mode": "fixture", "confirmed": True},
        confidence=1,
    )
    hr_evidence = Evidence(
        event_id=decision.id,
        evidence_type="hr_reply",
        source_type="user_material",
        title=payload["hr_confirmation"]["question"],
        content_excerpt=payload["hr_confirmation"]["reply"],
        source_ref=f"offer:{offer.id}:hr-confirmation",
        extra_data={"private_user_material": True, "confirmed": True},
        confidence=1,
    )
    db.add_all([offer_evidence, hr_evidence])
    db.flush()
    db.add_all(
        [
            GuardianFinding(
                event_id=decision.id,
                evidence_id=hr_evidence.id,
                domain="decision",
                category="hr_confirmation",
                severity="warning",
                status="confirmed",
                title=payload["hr_confirmation"]["conclusion"],
                source_type="user_material",
                confidence=1,
            ),
            ActionItem(
                event_id=decision.id,
                title="保留 HR 关于绩效的书面回复",
                status="completed",
                priority=20,
                requires_confirmation=True,
                confirmed_at=now,
                completed_at=now,
            ),
            DecisionRecord(
                event_id=decision.id,
                decision_type="offer_choice",
                choice="条件确认后接受 Offer",
                rationale="薪资位于脱敏市场样本 P50 附近，已向 HR 确认绩效口径。",
            ),
            Outcome(
                event_id=decision.id,
                outcome_type="offer_accepted",
                result="Offer 已接受，进入合同检查。",
            ),
        ]
    )

    contract_data = payload["contract"]
    contract = Contract(
        case_id=case.id,
        career_event_id=rights.id,
        linked_offer_id=offer.id,
        **contract_data,
    )
    db.add(contract)
    db.flush()
    contract_evidence = Evidence(
        event_id=rights.id,
        evidence_type="contract",
        source_type="user_material",
        title="脱敏劳动合同关键条款",
        content_excerpt=contract_data["non_compete"],
        source_ref=f"contract:{contract.id}",
        extra_data={"private_user_material": True, "linked_offer_id": offer.id},
        confidence=1,
    )
    db.add(contract_evidence)
    db.flush()
    db.add_all(
        [
            GuardianFinding(
                event_id=rights.id,
                evidence_id=contract_evidence.id,
                domain="rights",
                category="non_compete",
                severity="high",
                status="confirmed",
                title="竞业限制范围和补偿标准未写明",
                explanation="这是需要向 HR 确认的条款差距，不由系统自动判定违法。",
                source_type="rule",
                confidence=1,
            ),
            ActionItem(
                event_id=rights.id,
                title="确认竞业范围和补偿并保留书面记录",
                status="completed",
                priority=10,
                requires_confirmation=True,
                confirmed_at=now,
                completed_at=now,
            ),
            Outcome(
                event_id=rights.id,
                outcome_type="contract_signed",
                result="关键条款经人工确认后完成签约。",
            ),
        ]
    )

    payslip_data = payload["payslip"]
    payslip = Payslip(
        case_id=case.id,
        career_event_id=income.id,
        linked_offer_id=offer.id,
        **payslip_data,
    )
    db.add(payslip)
    db.flush()
    payslip_evidence = Evidence(
        event_id=income.id,
        evidence_type="payslip",
        source_type="user_material",
        title="2026 年 7 月脱敏工资条",
        content_excerpt="Offer 月薪 15000 元，首月应发 13800 元，差额 1200 元",
        source_ref=f"payslip:{payslip.id}",
        extra_data={
            "private_user_material": True,
            "linked_offer_id": offer.id,
            "offer_monthly_salary": 15000,
            "gross_salary": 13800,
            "difference": -1200,
        },
        confidence=1,
    )
    db.add(payslip_evidence)
    db.flush()
    income_finding = GuardianFinding(
        event_id=income.id,
        evidence_id=payslip_evidence.id,
        domain="income",
        category="offer_payslip_difference",
        severity="high",
        status="open",
        title="首月应发比 Offer 月薪少 1200 元",
        explanation="可能与入职日、试用期或绩效折算有关，需要薪酬人员确认。",
        source_type="calculation",
        confidence=1,
    )
    db.add(income_finding)
    db.flush()
    db.add(
        ActionItem(
            event_id=income.id,
            finding_id=income_finding.id,
            title="向薪酬确认首月少发 1200 元的原因",
            description="核对入职日折算、试用期比例和绩效计算明细。",
            status="pending",
            priority=5,
            requires_confirmation=True,
        )
    )

    growth_data = payload["growth"]
    growth_evidence = Evidence(
        event_id=growth.id,
        evidence_type="skill_gap",
        source_type="market_data",
        title=f"{growth_data['target_role']}技能差距",
        content_excerpt=f"已确认：{'、'.join(growth_data['confirmed_skills'])}；待提升：{'、'.join(growth_data['gaps'])}",
        source_ref="fixture-market-skill-001",
        extra_data={
            "data_mode": "fixture",
            "public_market_fact": True,
            "market_skills": growth_data["market_skills"],
            "confirmed_user_skills": growth_data["confirmed_skills"],
        },
        confidence=0.8,
    )
    db.add(growth_evidence)
    db.flush()
    growth_finding = GuardianFinding(
        event_id=growth.id,
        evidence_id=growth_evidence.id,
        domain="growth",
        category="skill_gap",
        severity="info",
        status="open",
        title=f"当前优先差距：{'、'.join(growth_data['gaps'])}",
        explanation="差距来自脱敏岗位样本与用户已确认技能的对比。",
        source_type="market_data",
        confidence=0.8,
    )
    db.add(growth_finding)
    db.flush()
    db.add(
        ActionItem(
            event_id=growth.id,
            finding_id=growth_finding.id,
            title=growth_data["first_action"],
            status="draft",
            priority=40,
            requires_confirmation=True,
        )
    )

    db.commit()
    return {
        "fixture_id": payload["fixture_id"],
        "data_mode": payload["data_mode"],
        "created": True,
        "event_ids": {
            "opportunity": opportunity.id,
            "decision": decision.id,
            "rights": rights.id,
            "income": income.id,
            "growth": growth.id,
        },
        "offer_id": offer.id,
        "contract_id": contract.id,
        "payslip_id": payslip.id,
        "message": "已载入脱敏应届生连续守护案例。",
    }
