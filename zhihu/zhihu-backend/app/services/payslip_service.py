"""工资条解析与核对服务。"""
from app.services.calculator_service import calculate_salary, get_city_data


def analyze_payslip(
    payslip_data: dict,
    expected_salary: float = None,
    city: str = "杭州",
) -> dict:
    """分析工资条，与预期对比。

    Args:
        payslip_data: 工资条字段（gross_salary, base_salary, social_insurance, etc.）
        expected_salary: Offer 中约定的税前月薪
        city: 工作城市
    """
    gross = float(payslip_data.get("gross_salary", 0))
    base = float(payslip_data.get("base_salary", 0))
    performance = float(payslip_data.get("performance", 0))
    allowance = float(payslip_data.get("allowance", 0))
    social = float(payslip_data.get("social_insurance", 0))
    housing = float(payslip_data.get("housing_fund", 0))
    tax = float(payslip_data.get("individual_tax", 0))
    other = float(payslip_data.get("other_deductions", 0))
    net = float(payslip_data.get("net_salary", 0))

    # 计算预期
    expected_net = 0
    insurance_diff = None
    findings = []

    if expected_salary:
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
        actual_insurance = social + housing
        if abs(actual_insurance - expected_insurance) > 100:
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
    calculated_net = gross - social - housing - tax - other
    if abs(calculated_net - net) > 1:
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
            "other": other,
            "total": social + housing + tax + other,
        },
        "net_salary": net,
        "expected_net": expected_net,
        "diff_from_expected": net - expected_net if expected_net else None,
        "insurance_diff": insurance_diff,
        "findings": findings,
    }
