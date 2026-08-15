"""审查规则 CRUD 服务。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_rule import ReviewRule
from app.models.user import User
from app.schemas.review_rule import ReviewRuleCreateRequest, ReviewRuleUpdateRequest, ReviewRuleResponse


def _serialize(rule: ReviewRule) -> ReviewRuleResponse:
    return ReviewRuleResponse(
        id=rule.id,
        name=rule.name,
        rule_code=rule.rule_code,
        risk_type=rule.risk_type,
        condition_type=rule.condition_type,
        condition_value=rule.condition_value,
        risk_level=rule.risk_level,
        suggestion=rule.suggestion,
        priority=rule.priority,
        is_active=rule.is_active,
        is_deleted=rule.is_deleted,
        created_by=rule.created_by,
        created_at=rule.created_at.isoformat() if rule.created_at else "",
        updated_at=rule.updated_at.isoformat() if rule.updated_at else "",
    )


def list_review_rules(db: Session) -> list:
    rules = db.scalars(select(ReviewRule).order_by(ReviewRule.priority.asc())).all()
    return [_serialize(r) for r in rules]


def create_review_rule(db: Session, payload: ReviewRuleCreateRequest, actor: User) -> ReviewRuleResponse:
    existing = db.scalar(select(ReviewRule).where(ReviewRule.rule_code == payload.rule_code))
    if existing:
        raise ValueError("规则编码已存在")
    rule = ReviewRule(
        name=payload.name,
        rule_code=payload.rule_code,
        risk_type=payload.risk_type,
        condition_type=payload.condition_type,
        condition_value=payload.condition_value,
        risk_level=payload.risk_level,
        suggestion=payload.suggestion,
        priority=payload.priority,
        is_active=payload.is_active,
        created_by=actor.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


def update_review_rule(db: Session, rule_id: int, payload: ReviewRuleUpdateRequest, actor: User) -> ReviewRuleResponse:
    rule = db.scalar(select(ReviewRule).where(ReviewRule.id == rule_id))
    if not rule:
        raise ValueError("规则不存在")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return _serialize(rule)
