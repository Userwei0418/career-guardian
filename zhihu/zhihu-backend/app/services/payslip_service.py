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

PAYSLIP_CHANGE_FIELDS = (
    ("gross_salary", "应发工资"),
    ("base_salary", "基本工资"),
    ("performance", "绩效"),
    ("bonus", "奖金"),
    ("overtime_pay", "加班费"),
    ("allowance", "津贴补贴"),
    ("social_insurance", "社保个人缴纳"),
    ("housing_fund", "公积金个人缴纳"),
    ("individual_tax", "个税"),
    ("attendance_deductions", "考勤扣款"),
    ("meal_deductions", "餐费扣款"),
    ("other_deductions", "其他扣款"),
    ("net_salary", "实发工资"),
)


def build_month_comparison(current, previous) -> dict:
    changes: list[dict] = []
    if previous is not None:
        for field, label in PAYSLIP_CHANGE_FIELDS:
            current_value = getattr(current, field, None)
            previous_value = getattr(previous, field, None)
            if current_value is None or previous_value is None:
                continue
            current_amount = float(current_value)
            previous_amount = float(previous_value)
            difference = current_amount - previous_amount
            if abs(difference) < 0.01:
                continue
            changes.append(
                {
                    "field": field,
                    "label": label,
                    "previous_amount": previous_amount,
                    "current_amount": current_amount,
                    "difference": difference,
                }
            )
    return {
        "payslip_id": current.id,
        "previous_payslip_id": previous.id if previous is not None else None,
        "current_pay_month": current.pay_month,
        "previous_pay_month": previous.pay_month if previous is not None else None,
        "changes": sorted(changes, key=lambda item: abs(item["difference"]), reverse=True),
    }


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


def _payslip_value(source, field: str):
    if isinstance(source, dict):
        return source.get(field)
    return getattr(source, field, None)


def _as_amount(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _amount_check(
    field: str,
    label: str,
    observed,
    reference,
    *,
    tolerance: float = 100,
    unknown_reason: str | None = None,
) -> dict:
    observed_amount = _as_amount(observed)
    reference_amount = _as_amount(reference)
    difference = (
        observed_amount - reference_amount
        if observed_amount is not None and reference_amount is not None
        else None
    )
    if unknown_reason:
        status = "unknown"
        explanation = unknown_reason
    elif reference_amount is None:
        status = "unknown"
        explanation = f"材料中未能可靠取得{label}，不自动填 0。"
    elif observed_amount is None:
        status = "unknown"
        explanation = f"工资条未列出{label}，不能与材料数字直接比较。"
    elif abs(difference or 0) <= tolerance:
        status = "matched"
        explanation = f"两份证据相差 {abs(difference or 0):.2f} 元，在 {tolerance:.0f} 元核对阈值内。"
    else:
        status = "different"
        direction = "低" if (difference or 0) < 0 else "高"
        explanation = f"工资条中该项比材料口径{direction} {abs(difference or 0):.2f} 元，需要核对。"
    return {
        "field": field,
        "label": label,
        "reference_value": None if reference_amount is None else f"{reference_amount:.2f} 元",
        "observed_value": None if observed_amount is None else f"{observed_amount:.2f} 元",
        "difference": difference,
        "status": status,
        "explanation": explanation,
    }


def _normalize_employer(value: str | None) -> str:
    return re.sub(r"[\s\-_（）()]", "", value or "").lower()


def _employer_check(observed: str | None, reference: str | None) -> dict:
    left = _normalize_employer(observed)
    right = _normalize_employer(reference)
    if not right:
        status = "unknown"
        explanation = "材料中未可靠取得用人单位。"
    elif not left:
        status = "unknown"
        explanation = "工资条未列出发薪单位。"
    elif left in right or right in left:
        status = "matched"
        explanation = "发薪单位与材料中的用人单位名称基本一致。"
    else:
        status = "unknown"
        explanation = "两处单位名称不同，可能是关联公司或委托代发，需人工确认。"
    return {
        "field": "employer_name",
        "label": "发薪单位",
        "reference_value": reference,
        "observed_value": observed,
        "difference": None,
        "status": status,
        "explanation": explanation,
    }


def _parse_start_date(value: str | None) -> date | None:
    text = (value or "").strip()
    for pattern in (r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{4})/(\d{1,2})/(\d{1,2})", r"(\d{4})年(\d{1,2})月(\d{1,2})日"):
        match = re.search(pattern, text)
        if match:
            try:
                return date(*(int(part) for part in match.groups()))
            except ValueError:
                return None
    return None


def _offer_gross_reference(offer, pay_month: str | None) -> tuple[float | None, str | None, str]:
    monthly = _as_amount(getattr(offer, "monthly_salary", None))
    months = getattr(offer, "probation_months", None)
    rate = _as_amount(getattr(offer, "probation_salary_rate", None))
    if not months or rate is None:
        return monthly, None, "约定税前月薪"
    start = _parse_start_date(getattr(offer, "start_date", None))
    match = re.fullmatch(r"(\d{4})-(\d{2})", pay_month or "")
    if start is None or match is None:
        return monthly, "Offer 包含试用期工资口径，但入职日或工资所属月份尚未核清。", "试用期应发"
    pay_year, pay_month_number = (int(value) for value in match.groups())
    month_offset = (pay_year - start.year) * 12 + pay_month_number - start.month
    if month_offset < 0 or month_offset >= int(months):
        return monthly, None, "约定税前月薪"
    expected = monthly * rate if monthly is not None else None
    if month_offset == 0 and start.day > 1:
        return expected, "本月是入职首月，可能按实际出勤天数折算，程序不直接判定少发。", "试用期应发"
    return expected, None, "试用期应发"


def _extract_monthly_bonus(text: str | None) -> float | None:
    if not text or "月" not in text:
        return None
    patterns = (
        r"(?:每月|月度)[^\d]{0,12}([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元",
        r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元?\s*/\s*月",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _extract_contract_pay_schedule(text: str | None) -> tuple[str, int] | None:
    match = re.search(r"((?:当月|次月|每月))\s*([0-3]?\d)\s*(?:日|号)", text or "")
    if not match:
        return None
    day = int(match.group(2))
    if not 1 <= day <= 31:
        return None
    return match.group(1), day


def _pay_schedule_check(agreed_pay_date, salary_terms: str | None) -> dict | None:
    schedule = _extract_contract_pay_schedule(salary_terms)
    if schedule is None:
        return None
    period, day = schedule
    observed = agreed_pay_date
    if isinstance(observed, str):
        try:
            observed = date.fromisoformat(observed)
        except ValueError:
            observed = None
    if observed is None:
        status = "unknown"
        explanation = "合同已识别到约定发薪日，但工资记录尚未确认对应日期。"
    elif observed.day == day:
        status = "matched"
        explanation = "工资记录中的约定发薪日与合同日期一致。"
    else:
        status = "different"
        explanation = "工资记录中的约定日与合同不同，应先确认哪个日期有效。"
    return {
        "field": "agreed_pay_date",
        "label": "约定发薪日",
        "reference_value": f"{period}{day}日",
        "observed_value": observed.isoformat() if isinstance(observed, date) else None,
        "difference": None,
        "status": status,
        "explanation": explanation,
    }


def build_material_comparisons(payslip, offers: list, contracts: list) -> list[dict]:
    """逐份、逐字段展示差异；不合并冲突，也不替用户选定哪份材料正确。"""
    if isinstance(payslip, (int, float, Decimal)):
        payslip = {"gross_salary": float(payslip)}
    gross_salary = _as_amount(_payslip_value(payslip, "gross_salary")) or 0.0
    comparisons: list[dict] = []

    def append_comparison(material_type: str, material_id: int, title: str, reference_amount: float | None, checks: list[dict]):
        different_count = sum(item["status"] == "different" for item in checks)
        unknown_count = sum(item["status"] == "unknown" for item in checks)
        matched_count = sum(item["status"] == "matched" for item in checks)
        difference = gross_salary - reference_amount if reference_amount is not None else None
        if different_count:
            status = "different"
            explanation = f"发现 {different_count} 个字段与工资条不同，请逐项确认适用口径。"
        elif matched_count:
            status = "matched"
            explanation = f"{matched_count} 个可计算字段基本一致" + (f"，另有 {unknown_count} 项信息尚未核清。" if unknown_count else "。")
        else:
            status = "unknown"
            explanation = "该材料的关键薪资口径暂无法与工资条可靠比较。"
        comparisons.append(
            {
                "material_type": material_type,
                "material_id": material_id,
                "material_title": title,
                "reference_amount": reference_amount,
                "gross_salary": gross_salary,
                "difference": difference,
                "status": status,
                "attention_count": different_count + unknown_count,
                "explanation": explanation,
                "field_checks": checks,
            }
        )

    for offer in offers:
        title = getattr(offer, "name", None) or getattr(offer, "company_name", None) or f"Offer #{offer.id}"
        reference, gross_unknown_reason, gross_label = _offer_gross_reference(offer, _payslip_value(payslip, "pay_month"))
        checks = [
            _amount_check("gross_salary", gross_label, _payslip_value(payslip, "gross_salary"), reference, unknown_reason=gross_unknown_reason)
        ]
        company_name = getattr(offer, "company_name", None)
        if company_name:
            checks.append(_employer_check(_payslip_value(payslip, "employer_name"), company_name))
        for field, label, offer_field in (
            ("base_salary", "基本/固定工资", "fixed_salary"),
            ("performance", "绩效/变动工资", "variable_salary"),
            ("allowance", "津贴补贴", "allowance"),
        ):
            expected = getattr(offer, offer_field, None)
            if expected is not None:
                checks.append(_amount_check(field, label, _payslip_value(payslip, field), expected))
        bonus_text = getattr(offer, "bonus", None)
        if bonus_text:
            monthly_bonus = _extract_monthly_bonus(bonus_text)
            checks.append(
                _amount_check(
                    "bonus",
                    "月度奖金",
                    _payslip_value(payslip, "bonus"),
                    monthly_bonus,
                    unknown_reason=None if monthly_bonus is not None else f"Offer 奖金口径为“{bonus_text}”，不是可直接计入当月的确定数字。",
                )
            )
        append_comparison("offer", offer.id, title, reference, checks)

    for contract in contracts:
        title = getattr(contract, "display_name", None) or getattr(contract, "employer", None) or f"劳动合同 #{contract.id}"
        salary_terms = getattr(contract, "salary_terms", None)
        reference = extract_contract_monthly_salary(salary_terms)
        checks = [_amount_check("gross_salary", "约定税前月薪", _payslip_value(payslip, "gross_salary"), reference)]
        employer = getattr(contract, "employer", None)
        if employer:
            checks.append(_employer_check(_payslip_value(payslip, "employer_name"), employer))
        schedule_check = _pay_schedule_check(_payslip_value(payslip, "agreed_pay_date"), salary_terms)
        if schedule_check is not None:
            checks.append(schedule_check)
        probation_text = " ".join(filter(None, [getattr(contract, "probation", None), salary_terms]))
        if "试用" in probation_text:
            checks.append(
                {
                    "field": "probation_terms",
                    "label": "试用期工资",
                    "reference_value": probation_text[:200],
                    "observed_value": None,
                    "difference": None,
                    "status": "unknown",
                    "explanation": "合同包含试用期口径，但还需结合入职日和工资所属月份确认本月是否适用。",
                }
            )
        append_comparison("contract", contract.id, title, reference, checks)
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


def build_payslip_guardian_summary(
    *,
    payslip,
    material_comparisons: list[dict],
    arrival_summary,
    month_comparison: dict,
    offers: list,
) -> dict:
    """将工资条、承诺材料和真实到账组装成可核对的收入守护结论。

    程序只对数字和已确认证据下结论；证据不足始终保留为“尚未核清”。
    """
    payslip_data = {
        field: _payslip_value(payslip, field)
        for field, _ in PAYSLIP_CHANGE_FIELDS
    }
    analysis = analyze_payslip(payslip_data)
    checks: list[dict] = []
    questions: list[str] = []
    materials = ["工资条当前版本"]

    def add_check(key: str, status: str, severity: str, title: str, explanation: str, evidence: list[str] | None = None):
        checks.append(
            {
                "key": key,
                "status": status,
                "severity": severity,
                "title": title,
                "explanation": explanation,
                "evidence": evidence or [],
            }
        )

    if analysis["arithmetic_status"] == "matched":
        add_check(
            "arithmetic",
            "confirmed",
            "info",
            "工资条加减关系可对上",
            "已列出的应发和全部扣款之差与实发相符。",
            [f"应发 {analysis['gross']:.2f} 元", f"扣款合计 {analysis['deductions']['total']:.2f} 元", f"实发 {analysis['net_salary']:.2f} 元"],
        )
    elif analysis["arithmetic_status"] == "mismatch":
        difference = abs(float(analysis["arithmetic_diff"] or 0))
        add_check(
            "arithmetic",
            "attention",
            "high",
            f"工资条仍有 {difference:.2f} 元无法用已列项目解释",
            "应发减去已列扣款不等于实发；这是数字异常，不自动认定公司多扣。",
            [f"程序计算实发 {float(analysis['calculated_net'] or 0):.2f} 元", f"工资条实发 {analysis['net_salary']:.2f} 元"],
        )
        questions.append(f"请说明工资条中尚未列明的 {difference:.2f} 元差额由哪些项目构成？")
    else:
        missing_labels = [dict(PAYSLIP_CHANGE_FIELDS).get(field, field) for field in analysis["unknown_fields"]]
        add_check(
            "arithmetic",
            "unverified",
            "medium",
            "扣款项目不完整，加减关系尚未核清",
            "空白字段保持未知，不当作 0，因此不做多扣或少发判定。",
            ["待补充：" + "、".join(missing_labels)],
        )

    material_checks = [
        (item, check)
        for item in material_comparisons
        for check in item.get("field_checks", [])
    ]
    material_differences = [(item, check) for item, check in material_checks if check["status"] == "different"]
    material_unknowns = [(item, check) for item, check in material_checks if check["status"] == "unknown"]
    if material_differences:
        add_check(
            "material_consistency",
            "attention",
            "high",
            f"Offer/合同与工资条有 {len(material_differences)} 个字段不同",
            "每份材料均保留自己的口径，系统不自动选定哪份材料更有效。",
            [f"{item['material_title']}：{check['label']}" for item, check in material_differences[:8]],
        )
        for item, check in material_differences[:8]:
            questions.append(f"请确认《{item['material_title']}》中“{check['label']}”与本月工资条不同的原因和适用口径。")
    elif material_comparisons:
        status = "unverified" if material_unknowns else "confirmed"
        add_check(
            "material_consistency",
            status,
            "medium" if material_unknowns else "info",
            f"可计算的材料字段已对上" + (f"，{len(material_unknowns)} 项尚未核清" if material_unknowns else ""),
            "未核清项不会被自动填值或认定为差异。",
            [f"{item['material_title']}：{check['label']}" for item, check in material_unknowns[:8]],
        )
    else:
        add_check(
            "material_consistency",
            "unverified",
            "info",
            "本次未关联 Offer 或合同",
            "可以分析工资条组成，但不会生成 Offer—合同一致性结论。",
        )
    if material_comparisons:
        materials.append("已关联的 Offer/合同当前版本")

    insurance_cities = {
        str(offer.city).strip()
        for offer in offers
        if getattr(offer, "city", None)
    }
    gross_for_insurance = _as_amount(_payslip_value(payslip, "gross_salary"))
    social = _as_amount(_payslip_value(payslip, "social_insurance"))
    housing = _as_amount(_payslip_value(payslip, "housing_fund"))
    tax = _as_amount(_payslip_value(payslip, "individual_tax"))
    if len(insurance_cities) == 1 and gross_for_insurance is not None and social is not None and housing is not None:
        city = next(iter(insurance_cities))
        expected = calculate_salary(gross_for_insurance, city)
        actual_total = social + housing
        difference = actual_total - expected.total_insurance
        threshold = max(100, expected.total_insurance * 0.05)
        add_check(
            "insurance_housing",
            "attention" if abs(difference) > threshold else "confirmed",
            "medium" if abs(difference) > threshold else "info",
            f"社保公积金与基础估算{'相差较大' if abs(difference) > threshold else '接近'}",
            "这只是基于已知城市和月薪的基础估算，未纳入当地上下限、公司申报基数和补充公积金，不能单独用于认定缴费错误。",
            [f"工资条个人社保+公积金 {actual_total:.2f} 元", f"{city}基础估算 {expected.total_insurance:.2f} 元"],
        )
        if abs(difference) > threshold:
            questions.append("请提供本月社保和公积金的缴费基数、个人比例及调整说明。")
    else:
        missing = []
        if len(insurance_cities) != 1:
            missing.append("唯一明确的工作城市")
        if gross_for_insurance is None:
            missing.append("应发工资")
        if social is None:
            missing.append("社保个人扣款")
        if housing is None:
            missing.append("公积金个人扣款")
        add_check(
            "insurance_housing",
            "unverified",
            "medium",
            "社保公积金缴费口径尚未核清",
            "缺少缴费基数或唯一可用材料时，系统不使用默认城市直接判定对错。",
            ["待补充：" + "、".join(missing)] if missing else [],
        )

    add_check(
        "individual_tax",
        "unverified",
        "info",
        "个税需要累计年度信息才能准确核对",
        "工资条只有当月个税不足以重建累计预扣；还需累计收入、已缴税额和专项附加扣除。",
        [f"本月工资条个税 {tax:.2f} 元"] if tax is not None else ["本月个税未知"],
    )

    if arrival_summary.match_status == "matched":
        add_check(
            "arrival_amount",
            "confirmed",
            "info",
            "工资条实发已与真实到账对上",
            "到账金额来自用户确认的正式收入流水，不是由工资条自动创建。",
            [f"已确认到账 {float(arrival_summary.confirmed_amount):.2f} 元"],
        )
        materials.append("已确认的银行/钱包到账流水")
    elif arrival_summary.match_status == "partial":
        add_check(
            "arrival_amount",
            "attention",
            "high",
            f"仍有 {float(arrival_summary.remaining_amount):.2f} 元未对上到账证据",
            "可继续关联分次到账；在证据完整前只标记差额待核，不直接认定漏发。",
            [f"工资条实发 {float(arrival_summary.net_salary):.2f} 元", f"已对上 {float(arrival_summary.confirmed_amount):.2f} 元"],
        )
        questions.append(f"工资条实发与已确认到账仍差 {float(arrival_summary.remaining_amount):.2f} 元，是否还有分次发放或其他到账安排？")
    else:
        due_passed = _payslip_value(payslip, "agreed_pay_date") is not None and date.today() > _payslip_value(payslip, "agreed_pay_date")
        add_check(
            "arrival_amount",
            "unverified",
            "medium",
            "约定发薪日已过，实际到账尚未核清" if due_passed else "尚未关联真实工资到账",
            "工资条是权益证据，不是现金流；只有关联真实收入流水后才能判断迟发或漏发。",
        )

    agreed_date = _payslip_value(payslip, "agreed_pay_date")
    if arrival_summary.match_status == "matched" and agreed_date is not None:
        latest_arrival = max(link.transaction_date for link in arrival_summary.links)
        delay_days = (latest_arrival - agreed_date).days
        if delay_days > 0:
            add_check(
                "arrival_time",
                "attention",
                "high",
                f"实际到账比已知约定日晚 {delay_days} 天",
                "日期差已核清，但是否构成迟发还需结合有效合同口径、节假日和发放批次。",
                [f"约定日 {agreed_date.isoformat()}", f"最后一笔到账 {latest_arrival.isoformat()}"],
            )
            questions.append(f"请说明本月工资比已知约定日晚 {delay_days} 天到账的原因，以及后续发薪日口径。")
        else:
            add_check(
                "arrival_time",
                "confirmed",
                "info",
                "实际到账未晚于已知约定日",
                "已使用用户确认的到账流水和约定日进行比较。",
            )
    else:
        add_check(
            "arrival_time",
            "unverified",
            "info",
            "迟发或漏发尚未核清",
            "需要同时具备有效约定发薪日和已确认实际到账日，缺一不作结论。",
        )

    changes = month_comparison.get("changes") or []
    if month_comparison.get("previous_payslip_id") is None:
        add_check(
            "month_change",
            "unverified",
            "info",
            "暂无同单位上月工资条可对比",
            "首份工资条可以分析当月组成，录入后续月份后再进行变化归因。",
        )
    else:
        meaningful = [item for item in changes if abs(float(item["difference"])) > 100]
        net_drop = next((item for item in changes if item["field"] == "net_salary" and item["difference"] < -100), None)
        add_check(
            "month_change",
            "attention" if net_drop else "confirmed",
            "medium" if net_drop else "info",
            f"实发比上月减少 {abs(float(net_drop['difference'])):.2f} 元" if net_drop else (f"与上月有 {len(meaningful)} 个明显变化项" if meaningful else "与上月可比项没有明显变化"),
            "月度变化只是线索，需要结合绩效、考勤、奖金和扣款明细解释。",
            [f"{item['label']}：{float(item['difference']):+.2f} 元" for item in meaningful[:8]],
        )
        materials.append("同单位上月工资条")
        if net_drop:
            questions.append(f"请按绩效、奖金、考勤和其他扣款逐项说明本月实发减少 {abs(float(net_drop['difference'])):.2f} 元的原因。")

    unique_questions = list(dict.fromkeys(questions))[:12]
    return {
        "payslip_id": int(_payslip_value(payslip, "id")),
        "checks": checks,
        "attention_count": sum(item["status"] == "attention" for item in checks),
        "unverified_count": sum(item["status"] == "unverified" for item in checks),
        "hr_questions": unique_questions,
        "materials_to_prepare": list(dict.fromkeys(materials)),
    }
