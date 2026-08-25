from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.career_event import ActionItem, CareerEvent, GuardianFinding
from app.models.growth import (
    GrowthEvidenceItem,
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthMilestone,
    GrowthPortfolioItem,
    GrowthSkillAssessment,
    GrowthWorkEvent,
    GrowthWorkItem,
)
from app.schemas.guardian import GuardianDomainState, GuardianStateResponse


DOMAIN_CONFIG = {
    "opportunity": {
        "label": "机会守护",
        "empty_title": "从一条真实岗位开始",
        "empty_summary": "验证岗位来源、企业和关键要求，再判断是否值得投入。",
        "empty_action": "添加目标岗位",
        "href": "/opportunity",
    },
    "decision": {
        "label": "决策守护",
        "empty_title": "还没有需要比较的 Offer",
        "empty_summary": "录入 Offer 后查看真实收入、市场位置和条件差距。",
        "empty_action": "录入 Offer",
        "href": "/offer/new",
    },
    "rights": {
        "label": "权益守护",
        "empty_title": "签约前再检查一次",
        "empty_summary": "合同、试用期、竞业和工时条款会逐项绑定原文解释。",
        "empty_action": "添加合同",
        "href": "/contract/new",
    },
    "income": {
        "label": "收支守护",
        "empty_title": "入职后核对第一份工资",
        "empty_summary": "对比 Offer、合同和工资条，解释实发差异。",
        "empty_action": "添加工资条",
        "href": "/payslip",
    },
    "growth": {
        "label": "成长守护",
        "empty_title": "从当下工作开始积累成长证据",
        "empty_summary": "先整理候选，再由你确认 1–3 项突破任务。",
        "empty_action": "记录当下工作",
        "href": "/growth",
    },
}


def build_guardian_state(db: Session, user_id: int) -> GuardianStateResponse:
    events = (
        db.query(CareerEvent)
        .filter(CareerEvent.user_id == user_id, CareerEvent.status != "archived")
        .order_by(CareerEvent.updated_at.desc(), CareerEvent.id.desc())
        .all()
    )
    latest_by_domain: dict[str, CareerEvent] = {}
    for event in events:
        if event.event_type in DOMAIN_CONFIG and event.event_type not in latest_by_domain:
            latest_by_domain[event.event_type] = event

    domain_states: list[GuardianDomainState] = []
    for domain, config in DOMAIN_CONFIG.items():
        if domain == "growth":
            active_items = db.query(GrowthWorkItem).filter(
                GrowthWorkItem.user_id == user_id,
                GrowthWorkItem.deleted_at.is_(None),
                GrowthWorkItem.status.in_(("captured", "planned", "in_progress", "blocked", "deferred")),
            ).all()
            pending_event_count = db.query(GrowthWorkEvent.id).filter(
                GrowthWorkEvent.user_id == user_id,
                GrowthWorkEvent.status.in_(("captured", "structured", "needs_more_evidence")),
            ).count()
            pending_asset_count = (
                db.query(GrowthPortfolioItem.id).filter(GrowthPortfolioItem.user_id == user_id, GrowthPortfolioItem.deleted_at.is_(None), GrowthPortfolioItem.status == "draft").count()
                + db.query(GrowthEvidenceItem.id).filter(GrowthEvidenceItem.user_id == user_id, GrowthEvidenceItem.deleted_at.is_(None), GrowthEvidenceItem.status == "candidate").count()
                + db.query(GrowthSkillAssessment.id).filter(GrowthSkillAssessment.user_id == user_id, GrowthSkillAssessment.status == "candidate").count()
            )
            pending_direction_count = (
                db.query(GrowthFutureTarget.id).filter(GrowthFutureTarget.user_id == user_id, GrowthFutureTarget.status == "draft").count()
                + db.query(GrowthGapSnapshot.id).filter(GrowthGapSnapshot.user_id == user_id, GrowthGapSnapshot.status == "candidate").count()
                + db.query(GrowthMilestone.id).filter(GrowthMilestone.user_id == user_id, GrowthMilestone.status == "proposed").count()
            )
            if not active_items and pending_event_count == 0 and pending_asset_count == 0 and pending_direction_count == 0:
                domain_states.append(
                    GuardianDomainState(
                        domain=domain,
                        label=config["label"],
                        status="empty",
                        title=config["empty_title"],
                        summary=config["empty_summary"],
                        primary_action=config["empty_action"],
                        primary_action_href=config["href"],
                    )
                )
                continue
            blocked_count = sum(item.status == "blocked" for item in active_items)
            attention_count = blocked_count + pending_event_count + pending_asset_count + pending_direction_count
            state = "attention" if attention_count else "active"
            summary = (
                f"{len(active_items)} 项工作正在推进，{attention_count} 项成长候选待处理。"
                if attention_count
                else f"{len(active_items)} 项工作正在推进。"
            )
            updated_at = max(
                (item.updated_at for item in active_items if item.updated_at is not None),
                default=None,
            )
            domain_states.append(
                GuardianDomainState(
                    domain=domain,
                    label=config["label"],
                    status=state,
                    title="当下工作与成长证据",
                    summary=summary,
                    primary_action="处理成长事项" if attention_count else "继续记录工作",
                    primary_action_href="/growth",
                    updated_at=updated_at,
                )
            )
            continue

        event = latest_by_domain.get(domain)
        if event is None:
            domain_states.append(
                GuardianDomainState(
                    domain=domain,
                    label=config["label"],
                    status="empty",
                    title=config["empty_title"],
                    summary=config["empty_summary"],
                    primary_action=config["empty_action"],
                    primary_action_href=config["href"],
                )
            )
            continue

        high_finding = (
            db.query(GuardianFinding)
            .filter(
                GuardianFinding.event_id == event.id,
                GuardianFinding.status == "open",
                GuardianFinding.severity == "high",
            )
            .order_by(GuardianFinding.created_at.desc(), GuardianFinding.id.desc())
            .first()
        )
        finding = high_finding or (
            db.query(GuardianFinding)
            .filter(
                GuardianFinding.event_id == event.id,
                GuardianFinding.status == "open",
            )
            .order_by(GuardianFinding.created_at.desc(), GuardianFinding.id.desc())
            .first()
        )
        action = (
            db.query(ActionItem)
            .filter(
                ActionItem.event_id == event.id,
                ActionItem.status.in_(["draft", "pending"]),
            )
            .order_by(ActionItem.priority.asc(), ActionItem.due_at.asc(), ActionItem.id.asc())
            .first()
        )

        if event.status == "completed":
            state = "complete"
            summary = "这项职业事件已完成，结论和结果已保留。"
        elif high_finding is not None:
            state = "attention"
            summary = high_finding.title
        else:
            state = "active"
            summary = finding.title if finding is not None else "这项职业事件正在推进中。"

        domain_states.append(
            GuardianDomainState(
                domain=domain,
                label=config["label"],
                status=state,
                title=event.title,
                summary=summary,
                event_id=event.id,
                primary_action=action.title if action is not None else "查看事件详情",
                primary_action_href=f"/events/{event.id}",
                updated_at=event.updated_at,
            )
        )

    priority = {"attention": 0, "active": 1, "empty": 2, "complete": 3, "unavailable": 4}
    primary = min(domain_states, key=lambda item: priority[item.status]).domain if domain_states else None
    return GuardianStateResponse(
        generated_at=datetime.now(timezone.utc),
        domains=domain_states,
        primary_domain=primary,
    )
