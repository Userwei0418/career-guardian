"""规则引擎 — 从数据库加载规则并执行匹配。"""
import json
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.review_rule import ReviewRule


def _parse_condition_values(condition_type: str, condition_value: str) -> list:
    if condition_type in {"contains_any", "contains_all"}:
        try:
            parsed = json.loads(condition_value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in re.split(r"[,\n]+", condition_value) if item.strip()]
    return [condition_value]


def _match_rule(rule: ReviewRule, raw_text: str) -> Optional[str]:
    values = _parse_condition_values(rule.condition_type, rule.condition_value)
    if rule.condition_type == "keyword":
        keyword = values[0]
        return keyword if keyword in raw_text else None
    if rule.condition_type == "regex":
        match = re.search(values[0], raw_text, flags=re.MULTILINE)
        return match.group(0) if match else None
    if rule.condition_type == "contains_any":
        return next((v for v in values if v in raw_text), None)
    if rule.condition_type == "contains_all":
        return " && ".join(values) if values and all(v in raw_text for v in values) else None
    return None


def list_active_rules(db: Session) -> list:
    return db.scalars(
        select(ReviewRule)
        .where(ReviewRule.is_active.is_(True), ReviewRule.is_deleted.is_(False))
        .order_by(ReviewRule.priority.asc(), ReviewRule.id.asc())
    ).all()


def evaluate_rules(db: Session, raw_text: str) -> list:
    risks = []
    rules = list_active_rules(db)
    lowered = raw_text.replace(" ", "")

    for rule in rules:
        matched_text = _match_rule(rule, lowered)
        if not matched_text:
            continue

        idx = lowered.find(matched_text.replace(" ", ""))
        start = max(0, idx - 30)
        end = min(len(raw_text), idx + len(matched_text) + 30)
        evidence = raw_text[start:end]

        risks.append({
            "code": rule.rule_code,
            "title": rule.name,
            "severity": rule.risk_level,
            "description": rule.risk_type,
            "recommendation": rule.suggestion,
            "evidence_text": evidence,
            "source": "rule",
            "confidence": 0.9,
            "rule_id": rule.id,
        })
    return risks
