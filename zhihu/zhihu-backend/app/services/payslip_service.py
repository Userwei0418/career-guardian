"""工资条解析与核对服务。"""
from __future__ import annotations

import re
import json
from datetime import date
from decimal import Decimal

from app.services.calculator_service import calculate_salary
from app.services.cashflow_privacy import redact_cashflow_text


DEDUCTION_FIELDS = (
    "social_insurance",
    "housing_fund",
    "individual_tax",
    "attendance_deductions",
    "meal_deductions",
    "other_deductions",
)


MONTHLY_SALARY_PATTERNS = (
    re.compile(
        r"(?:税前月薪|月薪|月工资|月基本工资|每月(?:工资|薪资)|工资标准)"
        r"[^\d]{0,16}(?:RMB|CNY|人民币|[¥￥])?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:元)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:RMB|CNY|人民币|[¥￥])?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元?\s*/\s*月",
        re.IGNORECASE,
    ),
)


def extract_contract_monthly_salary(salary_terms: str | None) -> float | None:
    """只从明确的“月薪/每月”表述中取值，避免把年薪、奖金或试用期总额当成月薪。"""
    if not salary_terms:
        return None
    compact = re.sub(r"\s+", " ", salary_terms)
    for pattern in MONTHLY_SALARY_PATTERNS:
        match = pattern.search(compact)
        if not match:
            continue
        amount = float(match.group(1).replace(",", ""))
        if 100 <= amount <= 10_000_000:
            return amount
    return None


def build_material_comparisons(gross_salary: float, offers: list, contracts: list) -> list[dict]:
    """逐份展示可计算的差异；不合并冲突，也不替用户选定哪份材料正确。"""
    comparisons: list[dict] = []

    def append_comparison(material_type: str, material_id: int, title: str, reference_amount: float | None):
        difference = gross_salary - reference_amount if reference_amount is not None else None
        if difference is None:
            status = "unknown"
            explanation = "该材料没有可靠的税前月薪数字，已保留原始口径，需要人工确认。"
        elif abs(difference) <= 100:
            status = "matched"
            explanation = f"工资条应发与该材料的月薪口径相差 {abs(difference):.2f} 元，在 100 元核对阈值内。"
        else:
            status = "different"
            direction = "低" if difference < 0 else "高"
            explanation = f"工资条应发比该材料月薪口径{direction} {abs(difference):.2f} 元，尚需结合试用期、考勤和绩效确认。"
        comparisons.append(
            {
                "material_type": material_type,
                "material_id": material_id,
                "material_title": title,
                "reference_amount": reference_amount,
                "gross_salary": gross_salary,
                "difference": difference,
                "status": status,
                "explanation": explanation,
            }
        )

    for offer in offers:
        title = offer.name or offer.company_name or f"Offer #{offer.id}"
        reference = float(offer.monthly_salary) if offer.monthly_salary is not None else None
        append_comparison("offer", offer.id, title, reference)
    for contract in contracts:
        title = contract.display_name or contract.employer or f"劳动合同 #{contract.id}"
        append_comparison(
            "contract",
            contract.id,
            title,
            extract_contract_monthly_salary(contract.salary_terms),
        )
    return comparisons


def build_arrival_suggestions(
    *,
    net_salary: float,
    reference_date: date,
    employer_name: str | None,
    transactions: list,
    linked_transaction_ids: set[int],
) -> list[dict]:
    """确定性规则先找工资到账候选，不自动建立关联。"""
    employer = (employer_name or "").strip().lower()
    suggestions: list[dict] = []
    for transaction in transactions:
        amount = float(transaction.amount)
        amount_diff = abs(amount - net_salary)
        day_diff = abs((transaction.transaction_date - reference_date).days)
        haystack = f"{transaction.merchant or ''} {transaction.description or ''}".lower()
        employer_hit = bool(employer and len(employer) >= 2 and employer in haystack)
        linked_elsewhere = transaction.id in linked_transaction_ids
        score = max(0, 20 - min(day_diff, 20))
        reasons: list[str] = [f"与工资参考日相差 {day_diff} 天"]
        if amount_diff <= 1:
            score += 65
            reasons.insert(0, "到账金额与工资条实发一致")
        elif amount_diff <= max(100, net_salary * 0.02):
            score += 45
            reasons.insert(0, f"到账金额与实发相差 {amount_diff:.2f} 元")
        elif 0 < amount < net_salary and amount >= net_salary * 0.1:
            score += 25
            reasons.insert(0, "金额小于实发，可能是拆分到账的一部分")
        else:
            score += 5
            reasons.insert(0, "金额与实发差距较大")
        if employer_hit:
            score += 15
            reasons.append("交易摘要命中发薪单位")
        if linked_elsewhere:
            score -= 30
            reasons.append("该流水已关联其他工资条，必须再次人工确认")
        score = max(0, min(score, 100))
        if score >= 80 and not linked_elsewhere:
            tier = "high"
        elif score >= 40:
            tier = "medium"
        else:
            tier = "low"
        suggestions.append(
            {
                "transaction_id": transaction.id,
                "amount": transaction.amount,
                "suggested_allocation": min(Decimal(transaction.amount), Decimal(str(net_salary))),
                "transaction_date": transaction.transaction_date,
                "merchant": transaction.merchant,
                "description": transaction.description,
                "score": score,
                "confidence_tier": tier,
                "reasons": reasons,
                "linked_to_other_payslip": linked_elsewhere,
                "requires_ai_review": tier != "high",
                "ai_status": "not_needed" if tier == "high" else "unavailable",
            }
        )
    exact_candidates = [item for item in suggestions if item["confidence_tier"] == "high"]
    if len(exact_candidates) > 1:
        for item in exact_candidates:
            item["confidence_tier"] = "medium"
            item["requires_ai_review"] = True
            item["ai_status"] = "unavailable"
            item["reasons"].append("同时存在多笔高匹配流水，程序无法唯一确定")
    return sorted(suggestions, key=lambda item: (-item["score"], item["transaction_date"]))


def enrich_arrival_suggestions_with_ai(
    suggestions: list[dict],
    *,
    payslip_id: int,
    pay_month: str | None,
    net_salary: float,
    employer_name: str | None,
    user_id: int,
    expected_data_epoch: int | None,
) -> list[dict]:
    """AI 只评议程序无法确定的候选，不改变等级、不建立关联。"""
    ambiguous = [item for item in suggestions if item.get("requires_ai_review")][:10]
    if not ambiguous:
        return suggestions
    from app.services.payslip_intake_service import _call_payslip_llm

    rows = [
        {
            "transaction_id": item["transaction_id"],
            "amount": str(item["amount"]),
            "transaction_date": item["transaction_date"].isoformat(),
            "merchant": redact_cashflow_text(item.get("merchant") or "", max_length=120),
            "description": redact_cashflow_text(item.get("description") or "", max_length=200),
            "program_reasons": item.get("reasons") or [],
        }
        for item in ambiguous
    ]
    prompt = """你是收支守护的工资到账疑难判断助手。程序已经按金额、日期和摘要筛选候选，你只分析语义，不能修改账本、不能代替用户确认。
判断每笔候选是否可能是这份工资条的实际到账：
- likely：有明确语义证据支持；
- unlikely：有明确证据表明不是；
- uncertain：信息不足或多种解释均可能。
只输出严格 JSON：{{"assessments":[{{"transaction_id":1,"assessment":"likely|unlikely|uncertain","reason":"一句可核对理由"}}]}}
工资条：ID {payslip_id}，工资月份 {pay_month}，实发 {net_salary}，发薪单位 {employer_name}
候选：{rows}
""".format(
        payslip_id=payslip_id,
        pay_month=pay_month or "未知",
        net_salary=f"{net_salary:.2f}",
        employer_name=redact_cashflow_text(employer_name or "未知", max_length=120),
        rows=json.dumps(rows, ensure_ascii=False),
    )
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="payslip_arrival_reasoning",
        max_tokens=1200,
    )
    if not output:
        return suggestions
    text = output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return suggestions
    assessments = payload.get("assessments") if isinstance(payload, dict) else None
    if not isinstance(assessments, list):
        return suggestions
    by_id = {item["transaction_id"]: item for item in suggestions}
    for assessment in assessments:
        if not isinstance(assessment, dict):
            continue
        target = by_id.get(assessment.get("transaction_id"))
        verdict = assessment.get("assessment")
        if target is None or verdict not in {"likely", "unlikely", "uncertain"}:
            continue
        target["ai_status"] = "completed"
        target["ai_assessment"] = verdict
        reason = re.sub(r"\s+", " ", str(assessment.get("reason") or "")).strip()
        target["ai_reason"] = reason[:300] or "AI 未提供可核对理由"
    return suggestions


def _optional_amount(payslip_data: dict, field: str):
    value = payslip_data.get(field)
    if value is None or value == "":
        return None
    return float(value)


def analyze_payslip(
    payslip_data: dict,
    expected_salary: float = None,
    city: str = None,
) -> dict:
    """分析工资条，与预期对比。

    Args:
        payslip_data: 工资条字段（gross_salary, base_salary, social_insurance, etc.）
        expected_salary: Offer 中约定的税前月薪
        city: 工作城市
    """
    gross = float(payslip_data.get("gross_salary", 0))
    base = _optional_amount(payslip_data, "base_salary")
    performance = _optional_amount(payslip_data, "performance")
    allowance = _optional_amount(payslip_data, "allowance")
    social = _optional_amount(payslip_data, "social_insurance")
    housing = _optional_amount(payslip_data, "housing_fund")
    tax = _optional_amount(payslip_data, "individual_tax")
    attendance = _optional_amount(payslip_data, "attendance_deductions")
    meal = _optional_amount(payslip_data, "meal_deductions")
    other = _optional_amount(payslip_data, "other_deductions")
    net = float(payslip_data.get("net_salary", 0))
    deduction_values = {
        "social_insurance": social,
        "housing_fund": housing,
        "individual_tax": tax,
        "attendance_deductions": attendance,
        "meal_deductions": meal,
        "other_deductions": other,
    }
    unknown_fields = [field for field, value in deduction_values.items() if value is None]

    # 计算预期
    expected_net = 0
    insurance_diff = None
    findings = []

    if expected_salary and city:
        expected = calculate_salary(expected_salary, city)
        expected_net = expected.take_home

        # 对比实发
        diff = net - expected_net
        if abs(diff) > 100:
            findings.append({
                "title": "实发工资与预期不符",
                "description": f"本月实发比入职前预估{'少' if diff < 0 else '多'} ¥{abs(diff):,.0f}",
                "severity": "warning",
            })

        # 检查五险一金
        expected_insurance = expected.total_insurance
        actual_insurance = None if social is None or housing is None else social + housing
        if actual_insurance is not None and abs(actual_insurance - expected_insurance) > 100:
            insurance_diff = {
                "expected": expected_insurance,
                "actual": actual_insurance,
                "diff": actual_insurance - expected_insurance,
            }
            findings.append({
                "title": "五险一金扣除金额与预期不同",
                "description": f"预期扣除 ¥{expected_insurance}，实际扣除 ¥{actual_insurance}",
                "severity": "warning",
            })

    # 检查绩效是否发放
    if expected_salary and performance == 0:
        # 无法确定是否有绩效，只是提示
        pass

    # 计算验证
    calculated_net = None
    arithmetic_diff = None
    arithmetic_status = "unknown"
    if not unknown_fields:
        calculated_net = gross - sum(value for value in deduction_values.values() if value is not None)
        arithmetic_diff = net - calculated_net
        arithmetic_status = "matched" if abs(arithmetic_diff) <= 1 else "mismatch"
    if arithmetic_status == "mismatch":
        findings.append({
            "title": "工资条数字校验异常",
            "description": f"应发 - 扣除 ≠ 实发（计算值 ¥{calculated_net:,.0f}，实发 ¥{net:,.0f}）",
            "severity": "error",
        })

    return {
        "gross": gross,
        "deductions": {
            "social_insurance": social,
            "housing_fund": housing,
            "income_tax": tax,
            "attendance": attendance,
            "meal": meal,
            "other": other,
            "total": None if unknown_fields else sum(value for value in deduction_values.values() if value is not None),
        },
        "net_salary": net,
        "expected_net": expected_net,
        "diff_from_expected": net - expected_net if expected_net else None,
        "insurance_diff": insurance_diff,
        "findings": findings,
        "arithmetic_status": arithmetic_status,
        "calculated_net": calculated_net,
        "arithmetic_diff": arithmetic_diff,
        "unknown_fields": unknown_fields,
    }
