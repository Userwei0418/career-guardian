"""工资条解析与核对服务。"""
from app.services.calculator_service import calculate_salary, get_city_data


DEDUCTION_FIELDS = (
    "social_insurance",
    "housing_fund",
    "individual_tax",
    "attendance_deductions",
    "meal_deductions",
    "other_deductions",
)


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
