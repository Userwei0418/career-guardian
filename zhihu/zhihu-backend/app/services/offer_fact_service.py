"""Offer 字段事实、版本和决策前门禁。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.offer import FactAssertion, Offer, OfferDecisionContext, OfferRevision


FIELD_SPECS: tuple[dict[str, Any], ...] = (
    {"key": "company_name", "label": "公司", "decision_required": True},
    {"key": "job_title", "label": "岗位", "decision_required": True},
    {"key": "city", "label": "城市", "income_required": True},
    {"key": "monthly_salary", "label": "税前月薪", "unit": "元", "currency": "CNY", "period": "month", "income_required": True, "decision_required": True},
    {"key": "salary_months", "label": "年薪月数", "unit": "个月", "period": "year", "income_required": True},
    {"key": "fixed_salary", "label": "固定月薪", "unit": "元", "currency": "CNY", "period": "month"},
    {"key": "variable_salary", "label": "浮动收入", "unit": "元", "currency": "CNY", "period": "month"},
    {"key": "allowance", "label": "每月补贴", "unit": "元", "currency": "CNY", "period": "month"},
    {"key": "bonus", "label": "奖金条件"},
    {"key": "probation_months", "label": "试用期时长", "unit": "个月"},
    {"key": "probation_salary_rate", "label": "试用期工资比例", "unit": "%"},
    {"key": "work_location", "label": "工作地点"},
    {"key": "working_hours", "label": "工时制度"},
    {"key": "response_deadline", "label": "最晚回复时间", "decision_required": True},
)

FIELD_SPEC_BY_KEY = {item["key"]: item for item in FIELD_SPECS}


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _display_value(value: Any, spec: dict[str, Any]) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if spec.get("key") == "probation_salary_rate":
        return f"{float(value) * 100:g}%"
    if isinstance(value, (Decimal, float)):
        rendered = f"{float(value):,.2f}".rstrip("0").rstrip(".")
    else:
        rendered = str(value)
    unit = spec.get("unit")
    return f"{rendered} {unit}" if unit else rendered


def serialize_offer_facts(offer: Offer) -> dict[str, Any]:
    return {spec["key"]: _json_value(getattr(offer, spec["key"], None)) for spec in FIELD_SPECS}


def validate_offer_facts(offer: Offer) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    for spec in FIELD_SPECS:
        value = getattr(offer, spec["key"], None)
        if value not in (None, ""):
            continue
        if spec.get("income_required"):
            issues.append({
                "code": f"missing_{spec['key']}",
                "field_keys": [spec["key"]],
                "severity": "blocking",
                "title": f"{spec['label']}待确认",
                "explanation": f"没有确认{spec['label']}，不能生成可靠的收入与生活结余测算。",
                "action": f"补充或向 HR 确认{spec['label']}",
                "blocks_income": True,
                "blocks_decision": bool(spec.get("decision_required")),
            })
        elif spec.get("decision_required"):
            issues.append({
                "code": f"missing_{spec['key']}",
                "field_keys": [spec["key"]],
                "severity": "blocking",
                "title": f"{spec['label']}待确认",
                "explanation": f"{spec['label']}会直接影响是否接受、拒绝或暂缓。",
                "action": f"补充或向 HR 确认{spec['label']}",
                "blocks_income": False,
                "blocks_decision": True,
            })

    salary = float(offer.monthly_salary) if offer.monthly_salary is not None else None
    fixed = float(offer.fixed_salary) if offer.fixed_salary is not None else None
    variable = float(offer.variable_salary) if offer.variable_salary is not None else None
    if salary is not None and salary <= 0:
        issues.append({
            "code": "invalid_monthly_salary",
            "field_keys": ["monthly_salary"],
            "severity": "blocking",
            "title": "月薪口径无效",
            "explanation": "税前月薪需要大于 0，当前数值不能进入测算。",
            "action": "确认税前月薪的数值和单位",
            "blocks_income": True,
            "blocks_decision": True,
        })
    if salary and variable is not None and variable > salary * 1.25:
        issues.append({
            "code": "variable_salary_period_conflict",
            "field_keys": ["monthly_salary", "variable_salary"],
            "severity": "blocking",
            "title": "浮动收入的周期可能填错",
            "explanation": f"当前月薪为 {salary:,.0f} 元，浮动收入却记录为每月 {variable:,.0f} 元。它可能实际是年度奖金或年度绩效。",
            "action": "先确认浮动收入是月度、季度还是年度金额",
            "blocks_income": True,
            "blocks_decision": True,
        })
    if salary and fixed is not None and variable is not None and fixed + variable > salary * 1.05:
        issues.append({
            "code": "salary_breakdown_conflict",
            "field_keys": ["monthly_salary", "fixed_salary", "variable_salary"],
            "severity": "blocking",
            "title": "月薪与固定、浮动拆分不一致",
            "explanation": f"固定月薪与浮动收入合计 {fixed + variable:,.0f} 元，高于当前月薪口径 {salary:,.0f} 元。",
            "action": "统一确认月薪总额以及固定、浮动部分的包含关系",
            "blocks_income": True,
            "blocks_decision": True,
        })
    if offer.probation_months is not None and int(offer.probation_months) > 6:
        issues.append({
            "code": "probation_too_long",
            "field_keys": ["probation_months"],
            "severity": "warning",
            "title": "试用期时长需要重点核对",
            "explanation": f"当前记录的试用期为 {int(offer.probation_months)} 个月，请结合合同期限和适用规则核对。",
            "action": "要求 HR 在书面材料中明确试用期时长与转正标准",
            "blocks_income": False,
            "blocks_decision": False,
        })
    if offer.probation_salary_rate is not None and float(offer.probation_salary_rate) < 0.8:
        issues.append({
            "code": "probation_salary_rate_low",
            "field_keys": ["probation_salary_rate"],
            "severity": "warning",
            "title": "试用期工资比例偏低",
            "explanation": f"当前记录的试用期工资比例为 {float(offer.probation_salary_rate) * 100:g}%。",
            "action": "结合书面工资与适用规则核对，不要只依赖口头承诺",
            "blocks_income": False,
            "blocks_decision": False,
        })
    return issues


def _source_for_offer(offer: Offer) -> tuple[str, str]:
    if offer.source_attachment_id:
        return "offer_attachment", "user_confirmed"
    if offer.offer_kind == "verbal":
        return "user_recorded_hr", "user_confirmed"
    return "user_input", "user_confirmed"


def create_offer_revision(
    db: Session,
    offer: Offer,
    user_id: int,
    *,
    reason: str = "user_confirmation",
    source_type: str | None = None,
    evidence_id: int | None = None,
    source_field_key: str | None = None,
) -> OfferRevision:
    latest = (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_no.desc(), OfferRevision.id.desc())
        .first()
    )
    revision = OfferRevision(
        offer_id=offer.id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        facts_snapshot=serialize_offer_facts(offer),
        created_reason=reason,
        source_type=source_type or _source_for_offer(offer)[0],
        created_by_user_id=user_id,
        supersedes_revision_id=latest.id if latest else None,
    )
    db.add(revision)
    db.flush()

    previous = (
        db.query(FactAssertion)
        .filter(FactAssertion.offer_id == offer.id, FactAssertion.is_current.is_(True))
        .all()
    )
    previous_by_key = {item.field_key: item for item in previous}
    previous_meta_by_key = {
        item.field_key: {
            "source_type": item.source_type,
            "verification_status": item.verification_status,
            "evidence_id": item.evidence_id,
            "confidence": item.confidence,
            "observed_at": item.observed_at,
            "confirmed_by_user_id": item.confirmed_by_user_id,
            "confirmed_at": item.confirmed_at,
        }
        for item in previous
    }
    for item in previous:
        item.is_current = False
        item.verification_status = "superseded"

    default_source, default_status = _source_for_offer(offer)
    now = utc_now_naive()
    issue_fields = {
        key
        for issue in validate_offer_facts(offer)
        if issue["severity"] == "blocking"
        for key in issue["field_keys"]
    }
    for spec in FIELD_SPECS:
        value = getattr(offer, spec["key"], None)
        if value in (None, ""):
            continue
        previous_meta = previous_meta_by_key.get(spec["key"])
        if reason == "hr_confirmation" and spec["key"] == source_field_key:
            item_source = source_type or "hr_reply"
            status = "hr_reported"
            item_evidence_id = evidence_id
            item_confidence = 1
            observed_at = now
            confirmed_by_user_id = user_id
            confirmed_at = now
        elif reason == "hr_confirmation" and previous_meta:
            item_source = previous_meta["source_type"]
            status = previous_meta["verification_status"]
            if status == "conflict" and spec["key"] not in issue_fields:
                status = "hr_reported" if item_source == "hr_reply" else "user_confirmed" if item_source in {"user_input", "user_recorded_hr", "offer_attachment"} else "extracted"
            item_evidence_id = previous_meta["evidence_id"]
            item_confidence = previous_meta["confidence"]
            observed_at = previous_meta["observed_at"]
            confirmed_by_user_id = previous_meta["confirmed_by_user_id"]
            confirmed_at = previous_meta["confirmed_at"]
        elif reason == "hr_confirmation":
            item_source = "legacy_offer_record"
            status = "extracted"
            item_evidence_id = None
            item_confidence = float(offer.extraction_confidence) if offer.extraction_confidence is not None else None
            observed_at = offer.updated_at or now
            confirmed_by_user_id = None
            confirmed_at = None
        else:
            item_source = source_type or default_source
            status = default_status
            item_evidence_id = evidence_id
            item_confidence = float(offer.extraction_confidence) if offer.extraction_confidence is not None else None
            observed_at = now
            confirmed_by_user_id = user_id
            confirmed_at = now
        if spec["key"] in issue_fields:
            status = "conflict"
        assertion = FactAssertion(
            offer_id=offer.id,
            revision_id=revision.id,
            field_key=spec["key"],
            value_json={"value": _json_value(value)},
            unit=spec.get("unit"),
            currency=spec.get("currency"),
            period=spec.get("period"),
            source_type=item_source,
            verification_status=status,
            evidence_id=item_evidence_id,
            confidence=item_confidence,
            is_current=True,
            observed_at=observed_at,
            confirmed_by_user_id=confirmed_by_user_id,
            confirmed_at=confirmed_at,
            supersedes_assertion_id=previous_by_key.get(spec["key"]).id if previous_by_key.get(spec["key"]) else None,
        )
        db.add(assertion)
    offer.facts_confirmed_at = now
    db.flush()
    return revision


HR_APPLICABLE_FACT_KEYS = {
    "company_name",
    "job_title",
    "city",
    "monthly_salary",
    "salary_months",
    "fixed_salary",
    "variable_salary",
    "bonus",
    "allowance",
    "probation_months",
    "probation_salary_rate",
    "work_location",
    "working_hours",
    "response_deadline",
}


def normalize_hr_fact_value(field_key: str, raw_value: Any, *, period: str | None = None) -> Any:
    if field_key not in HR_APPLICABLE_FACT_KEYS:
        raise ValueError("该回复暂时不能直接写入 Offer 事实，请保留原话并在后续材料中核对")
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        raise ValueError("请填写要应用到事实账本的明确值")

    if field_key in {"monthly_salary", "fixed_salary", "variable_salary", "allowance"}:
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("金额需要填写为数字") from exc
        if value < 0:
            raise ValueError("金额不能小于 0")
        if field_key == "variable_salary" and period != "month":
            raise ValueError("浮动收入必须明确为每月金额；年度奖金请应用到“奖金条件”")
        return value

    if field_key in {"salary_months", "probation_months"}:
        try:
            value = int(str(raw_value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("月数需要填写为整数") from exc
        minimum, maximum = (12, 36) if field_key == "salary_months" else (0, 12)
        if not minimum <= value <= maximum:
            raise ValueError(f"该月数需要在 {minimum}–{maximum} 之间")
        return value

    if field_key == "probation_salary_rate":
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("试用期工资比例需要填写为数字") from exc
        if 1 < value <= 100:
            value /= 100
        if not 0 <= value <= 1:
            raise ValueError("试用期工资比例请填写 0–1，或填写 0–100 的百分数")
        return value

    if field_key == "response_deadline":
        if isinstance(raw_value, datetime):
            return raw_value
        try:
            parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("回复期限需要填写有效日期和时间") from exc
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed

    return str(raw_value).strip()


def build_offer_facts(db: Session, offer: Offer) -> dict[str, Any]:
    revision = (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_no.desc(), OfferRevision.id.desc())
        .first()
    )
    assertions = []
    if revision:
        assertions = (
            db.query(FactAssertion)
            .filter(FactAssertion.revision_id == revision.id, FactAssertion.is_current.is_(True))
            .all()
        )
    assertion_by_key = {item.field_key: item for item in assertions}
    conflict_fields = {
        key
        for issue in validate_offer_facts(offer)
        if issue["severity"] == "blocking"
        for key in issue["field_keys"]
    }
    items = []
    confirmed_count = 0
    conflict_count = 0
    for spec in FIELD_SPECS:
        value = getattr(offer, spec["key"], None)
        assertion = assertion_by_key.get(spec["key"])
        if spec["key"] in conflict_fields and value not in (None, ""):
            status = "conflict"
            conflict_count += 1
        elif value in (None, ""):
            status = "unknown"
        elif assertion:
            status = assertion.verification_status
        else:
            # 旧记录没有字段级版本证据；只能视为待复核的既有记录，不能因非空冒充已确认。
            status = "extracted"
        if status in {"user_confirmed", "hr_reported", "written_confirmed"}:
            confirmed_count += 1
        items.append({
            "field_key": spec["key"],
            "label": spec["label"],
            "value": _json_value(value),
            "display_value": _display_value(value, spec),
            "unit": spec.get("unit"),
            "currency": spec.get("currency"),
            "period": spec.get("period"),
            "source_type": assertion.source_type if assertion else ("offer_attachment" if offer.source_attachment_id else "legacy_offer_record"),
            "verification_status": status,
            "confidence": float(assertion.confidence) if assertion and assertion.confidence is not None else None,
            "revision_id": revision.id if revision else None,
            "updated_at": revision.created_at if revision else offer.updated_at,
        })
    return {
        "offer_id": offer.id,
        "revision_id": revision.id if revision else None,
        "revision_no": revision.revision_no if revision else None,
        "confirmed_at": offer.facts_confirmed_at,
        "confirmed_count": confirmed_count,
        "total_count": len(FIELD_SPECS),
        "unknown_count": len([item for item in items if item["verification_status"] == "unknown"]),
        "conflict_count": conflict_count,
        "items": items,
        "issues": validate_offer_facts(offer),
    }


def build_validation_result(offer: Offer) -> dict[str, Any]:
    issues = validate_offer_facts(offer)
    income_blocked = any(item["blocks_income"] for item in issues)
    decision_blocked = any(item["blocks_decision"] for item in issues)
    return {
        "offer_id": offer.id,
        "calculation_status": "blocked" if income_blocked else "ready",
        "decision_status": "blocked" if decision_blocked else "needs_facts" if issues else "ready",
        "issues": issues,
    }


def build_decision_preflight(db: Session, offer: Offer) -> dict[str, Any]:
    facts = build_offer_facts(db, offer)
    blocking = [item for item in facts["issues"] if item["blocks_decision"]]
    warnings = [item for item in facts["issues"] if not item["blocks_decision"]]
    unknown = [item for item in facts["items"] if item["verification_status"] == "unknown"]
    readiness = "blocked" if blocking else "needs_facts" if unknown or warnings else "ready"
    decision_context = (
        db.query(OfferDecisionContext)
        .filter(OfferDecisionContext.offer_id == offer.id)
        .first()
    )
    return {
        "offer_id": offer.id,
        "offer_revision_id": facts["revision_id"],
        "readiness": readiness,
        "blocking_issues": blocking,
        "unknown_items": unknown,
        "warnings": warnings,
        "requires_acknowledgement": bool(blocking or unknown),
        "decision_context": decision_context,
    }
