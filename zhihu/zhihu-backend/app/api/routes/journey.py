"""旅程 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.journey_node import JourneyNode
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.services.journey_service import (
    get_journey_template,
    get_journey_stages,
    get_total_topic_count,
    get_next_action,
)

router = APIRouter()


@router.get("/")
def get_journey(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取 6 阶段旅程地图 + 完成状态"""
    nodes = db.query(JourneyNode).filter(JourneyNode.user_id == user.id).order_by(JourneyNode.sort_order).all()
    completed_titles = [n.title for n in nodes if n.is_completed]

    # 线性模板（向后兼容）
    template = get_journey_template()
    next_action = get_next_action(completed_titles)

    # 6 阶段地图
    stages = get_journey_stages()
    total_topics = get_total_topic_count()

    # 计算已完成阶段主题数（基于后端里程碑节点）
    milestone_completed = len(completed_titles)
    career_events = (
        db.query(CareerEvent)
        .filter(CareerEvent.user_id == user.id, CareerEvent.status != "archived")
        .order_by(CareerEvent.started_at.asc(), CareerEvent.id.asc())
        .all()
    )

    return {
        # 6 阶段地图数据
        "stages": stages,
        "total_topics": total_topics,
        "milestone_completed": milestone_completed,
        # 线性时间线（向后兼容）
        "nodes": [
            {
                "title": t["title"],
                "description": t["description"],
                "sort_order": t["sort_order"],
                "is_completed": t["title"] in completed_titles,
            }
            for t in template
        ],
        "next_action": next_action,
        "completed_count": milestone_completed,
        "total_count": len(template),
        "career_events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "title": event.title,
                "status": event.status,
                "stage": event.stage,
                "started_at": event.started_at,
                "completed_at": event.completed_at,
                "evidence_count": db.query(Evidence).filter(Evidence.event_id == event.id).count(),
                "finding_count": db.query(GuardianFinding)
                .filter(GuardianFinding.event_id == event.id)
                .count(),
                "action_count": db.query(ActionItem).filter(ActionItem.event_id == event.id).count(),
                "latest_finding": (
                    lambda finding: {
                        "title": finding.title,
                        "severity": finding.severity,
                        "status": finding.status,
                    }
                    if finding
                    else None
                )(
                    db.query(GuardianFinding)
                    .filter(GuardianFinding.event_id == event.id)
                    .order_by(GuardianFinding.created_at.desc(), GuardianFinding.id.desc())
                    .first()
                ),
                "next_action": (
                    lambda action: {"title": action.title, "status": action.status} if action else None
                )(
                    db.query(ActionItem)
                    .filter(ActionItem.event_id == event.id, ActionItem.status.in_(["draft", "pending"]))
                    .order_by(ActionItem.priority.asc(), ActionItem.id.asc())
                    .first()
                ),
            }
            for event in career_events
        ],
    }


@router.post("/{node_id}/complete")
def complete_node(node_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    node = db.query(JourneyNode).filter(JourneyNode.id == node_id, JourneyNode.user_id == user.id).first()
    if node:
        node.is_completed = True
        node.status = "completed"
        node.completed_at = func.now()
        db.commit()
    return {"ok": True}


@router.post("/complete-by-title")
def complete_by_title(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """按标题标记节点完成（前端调用）"""
    title = data.get("title", "")
    node = db.query(JourneyNode).filter(
        JourneyNode.user_id == user.id,
        JourneyNode.title == title,
    ).first()
    if node:
        node.is_completed = True
        node.status = "completed"
        node.completed_at = func.now()
    else:
        # 自动创建并标记完成
        template = next((t for t in get_journey_template() if t["title"] == title), None)
        if template:
            node = JourneyNode(
                user_id=user.id,
                title=title,
                description=template["description"],
                sort_order=template["sort_order"],
                is_completed=True,
                status="completed",
                completed_at=func.now(),
            )
            db.add(node)
    db.commit()
    return {"ok": True}
