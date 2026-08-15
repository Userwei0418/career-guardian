from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.career_event import ActionItem, CareerEvent, GuardianFinding
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
        "label": "收入守护",
        "empty_title": "入职后核对第一份工资",
        "empty_summary": "对比 Offer、合同和工资条，解释实发差异。",
        "empty_action": "添加工资条",
        "href": "/payslip",
    },
    "growth": {
        "label": "成长守护",
        "empty_title": "把目标岗位变成成长任务",
        "empty_summary": "根据目标岗位技能要求，记录差距、行动和成长证据。",
        "empty_action": "设置成长目标",
        "href": "/profile",
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
                primary_action_href=config["href"],
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
