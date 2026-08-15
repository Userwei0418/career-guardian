"""Offer 分析报告生成 + HR 话术生成。"""
from typing import Optional
from decimal import Decimal

from app.services.calculator_service import calculate_salary, get_city_data, get_cost_breakdown
from app.models.offer import Offer
from app.schemas.market import SalaryInsightResponse


def build_market_position(salary: float, insight: Optional[SalaryInsightResponse]) -> dict:
    if insight is None or insight.availability == "unavailable":
        return {
            "availability": "unavailable",
            "data_mode": "unknown",
            "description": "市场数据暂时不可用",
            "advice": "暂不基于市场分位作决定，先核对 Offer 中的确定条件。",
            "offer_salary": salary,
            "p25": None,
            "p50": None,
            "p75": None,
            "sample_size": 0,
            "quality_grade": "insufficient",
            "methodology_version": "unavailable-v1",
            "sources": [],
            "note": insight.note if insight else "市场洞察响应未提供。",
        }

    payload = insight.model_dump(mode="json")
    p25, p50, p75 = insight.p25, insight.p50, insight.p75
    if insight.availability != "available" or None in {p25, p50, p75}:
        return {
            **payload,
            "description": "样本不足，暂不判断市场位置",
            "advice": "把这份数据当作线索，不作为接受或拒绝 Offer 的单一依据。",
            "offer_salary": salary,
        }

    if salary <= p25:
        description = "低于市场 P25"
        advice = "薪资低于大部分同类样本，建议核对成长机会、奖金和其他补偿。"
    elif salary <= p50:
        description = "位于市场 P25–P50"
        advice = "薪资位于样本中下区间，可结合已确认的职责和筹码尝试沟通。"
    elif salary <= p75:
        description = "位于市场 P50–P75"
        advice = "薪资位于样本中上区间，仍需核对变动薪资和发放条件。"
    else:
        description = "高于市场 P75"
        advice = "薪资高于大部分同类样本，重点核对工时、绩效和合同承诺是否一致。"
    return {
        **payload,
        "description": description,
        "advice": advice,
        "offer_salary": salary,
    }


def generate_offer_report(
    offer: Offer,
    priorities: list[str] = None,
    market_insight: Optional[SalaryInsightResponse] = None,
) -> dict:
    """生成单份 Offer 分析报告。

    返回结构化数据，前端负责渲染。
    """
    city = offer.city or "杭州"
    salary = float(offer.monthly_salary or 0)
    job_title = offer.job_title or ""

    # 薪资计算
    salary_result = calculate_salary(salary, city)

    # 市场位置
    market = build_market_position(salary, market_insight) if job_title else None

    # 收入概览
    fixed_annual = float(offer.fixed_salary or salary) * int(offer.salary_months or 12)
    variable_annual = float(offer.variable_salary or 0) * int(offer.salary_months or 12)
    probation_loss = 0
    if offer.probation_months and offer.probation_salary_rate:
        rate = float(offer.probation_salary_rate)
        if rate < 1:
            probation_loss = salary * int(offer.probation_months) * (1 - rate)

    # 待确认事项（基于数据完整性判断）
    findings = []
    if offer.variable_salary and float(offer.variable_salary) > 0:
        findings.append({
            "severity": "warning",
            "title": "绩效工资占比需要确认",
            "explanation": f"绩效部分 {offer.variable_salary} 元/月，占总薪资 {float(offer.variable_salary)/salary*100:.0f}%。建议确认考核标准和发放条件。",
            "action": "问清楚绩效考核周期和发放标准",
        })
    if not offer.work_location or offer.work_location == city:
        findings.append({
            "severity": "info",
            "title": "工作地点待确认",
            "explanation": "合同中工作地点是否明确到具体城市？是否需要接受跨城市调动？",
            "action": "确认工作地点是否固定",
        })
    if offer.probation_months and int(offer.probation_months) > 3:
        findings.append({
            "severity": "warning",
            "title": "试用期偏长",
            "explanation": f"试用期 {offer.probation_months} 个月，超过 3 个月。确认试用期工资比例是否合理。",
            "action": "确认试用期工资不低于转正的 80%",
        })

    # 个人匹配分析
    match_analysis = []
    if priorities:
        if "income" in priorities:
            match_analysis.append(f"从收入角度看，月到手 {salary_result.take_home:.0f} 元，年储蓄约 {salary_result.annual_savings:.0f} 元。")
        if "growth" in priorities:
            match_analysis.append(f"岗位方向为 {job_title}，建议了解团队规模和晋升路径。")
        if "city_life" in priorities:
            cost = get_cost_breakdown(city)
            match_analysis.append(f"{city}生活成本约 {salary_result.monthly_living_cost} 元/月，月结余约 {salary_result.monthly_savings:.0f} 元。")

    return {
        "offer_id": offer.id,
        "company": offer.company_name,
        "job_title": job_title,
        "city": city,
        "summary": _build_summary(offer, salary_result, market, findings),
        "income": {
            "monthly_gross": salary,
            "monthly_take_home": round(salary_result.take_home),
            "annual_gross": fixed_annual + variable_annual,
            "annual_take_home": round(salary_result.annual_take_home),
            "fixed_annual": fixed_annual,
            "variable_annual": variable_annual,
            "probation_loss": round(probation_loss),
            "monthly_living_cost": round(salary_result.monthly_living_cost),
            "monthly_savings": round(salary_result.monthly_savings),
            "annual_savings": round(salary_result.annual_savings),
            "housing_fund_yearly": round(salary_result.annual_housing_fund_total),
        },
        "insurance_detail": {
            "pension": salary_result.pension,
            "medical": salary_result.medical,
            "unemployment": salary_result.unemployment,
            "housing_fund": salary_result.housing_fund,
            "total": salary_result.total_insurance,
            "income_tax": salary_result.income_tax,
        },
        "market": market,
        "findings": findings,
        "match_analysis": match_analysis,
    }


def _build_summary(offer, salary_result, market, findings) -> str:
    """生成一句话结论"""
    warnings = len([f for f in findings if f["severity"] == "warning"])
    if warnings > 0:
        return f"这份 Offer 可以继续考虑，但签之前建议问清楚 {warnings} 件事。"
    return "这份 Offer 整体条件不错，可以继续推进。"


def generate_hr_questions(offer: Offer, findings: list[dict]) -> list[dict]:
    """根据分析结果生成 HR 问题和沟通话术。"""
    questions = []

    if offer.variable_salary and float(offer.variable_salary) > 0:
        questions.append({
            "category": "薪资结构",
            "title": "绩效工资是否有明确考核标准",
            "why": f"绩效部分占月薪 {float(offer.variable_salary)/float(offer.monthly_salary or 1)*100:.0f}%，比例不低，需要确认发放条件。",
            "script": "想再确认一下，Offer 中绩效部分的考核周期和发放条件是什么？是否有书面制度可以提前了解？",
            "watch_for": "关注是否有'公司有权调整'等模糊表述",
        })

    if offer.bonus:
        questions.append({
            "category": "薪资结构",
            "title": "年终奖的发放条件",
            "why": f"Offer 提到 {offer.bonus}，但年终奖通常有条件限制。",
            "script": "想了解一下年终奖的具体发放条件，比如入职满多久可以参与分配？是否有绩效门槛？",
            "watch_for": "关注'根据公司经营状况'等不确定表述",
        })

    if offer.probation_months and int(offer.probation_months) > 0:
        questions.append({
            "category": "试用期",
            "title": "试用期考核标准",
            "why": f"试用期 {offer.probation_months} 个月，工资比例 {float(offer.probation_salary_rate or 0.8)*100:.0f}%。",
            "script": "请问试用期的考核标准是什么？转正评估的流程和时间节点是怎样的？",
            "watch_for": "关注是否有明确的转正条件，避免'表现良好'等模糊说法",
        })

    if not offer.work_location or (offer.work_location and "根据" in str(offer.work_location)):
        questions.append({
            "category": "工作地点",
            "title": "工作地点是否固定",
            "why": "工作地点的表述可能影响后续调动。",
            "script": "想确认一下，工作地点是否固定在 XX？是否存在跨城市调动的可能？",
            "watch_for": "关注'公司可根据经营需要调整'等弹性表述",
        })

    questions.append({
        "category": "社保和公积金",
        "title": "社保和公积金缴纳基数",
        "why": "缴纳基数直接影响到手工资和公积金账户。",
        "script": "请问社保和公积金的缴纳基数是按实际工资还是按最低基数？公积金比例是多少？",
        "watch_for": "按最低基数缴纳虽然到手多，但公积金账户会少很多",
    })

    return questions
