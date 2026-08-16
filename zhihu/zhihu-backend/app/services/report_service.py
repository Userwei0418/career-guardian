"""Offer 分析报告生成 + HR 话术生成。"""
from typing import Optional

from app.services.calculator_service import calculate_salary, get_city_data
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
    profile=None,
    target=None,
    living_cost: Optional[float] = None,
    variable_realization: float = 0.7,
    extra_salary_months_realization: float = 1.0,
    confirmed_fact_keys: Optional[set[str]] = None,
    confirmation_count: int = 0,
) -> dict:
    """生成单份 Offer 分析报告。

    返回结构化数据，前端负责渲染。
    """
    city = offer.city or "杭州"
    salary = float(offer.monthly_salary or 0)
    job_title = offer.job_title or ""

    default_living_cost = float(get_city_data(city)["living_cost"])
    profile_budget = float(profile.monthly_budget) if profile and profile.monthly_budget else None
    assumed_living_cost = living_cost if living_cost is not None else profile_budget or default_living_cost

    fixed_monthly = float(offer.fixed_salary or 0)
    variable_monthly = float(offer.variable_salary or 0)
    allowance_monthly = float(offer.allowance or 0)
    if fixed_monthly <= 0:
        fixed_monthly = max(0, salary - variable_monthly) if variable_monthly else salary
    salary_months = max(12, int(offer.salary_months or 12))
    extra_salary_months = max(0, salary_months - 12)

    scenarios = [
        _build_income_scenario(
            "保守底线",
            fixed_monthly,
            variable_monthly,
            allowance_monthly,
            city,
            assumed_living_cost,
            variable_realization=0,
            extra_salary_months_realization=0,
            extra_salary_months=extra_salary_months,
        ),
        _build_income_scenario(
            "当前预期",
            fixed_monthly,
            variable_monthly,
            allowance_monthly,
            city,
            assumed_living_cost,
            variable_realization=variable_realization,
            extra_salary_months_realization=extra_salary_months_realization,
            extra_salary_months=extra_salary_months,
        ),
        _build_income_scenario(
            "条件兑现",
            fixed_monthly,
            variable_monthly,
            allowance_monthly,
            city,
            assumed_living_cost,
            variable_realization=1,
            extra_salary_months_realization=1,
            extra_salary_months=extra_salary_months,
        ),
    ]
    salary_result = calculate_salary(
        fixed_monthly,
        city,
        living_cost=assumed_living_cost,
        performance=variable_monthly * variable_realization,
        meal_subsidy=allowance_monthly,
        bonus_months=extra_salary_months * extra_salary_months_realization,
    )
    expected_scenario = scenarios[1]

    # 市场位置
    market = build_market_position(salary, market_insight) if job_title else None

    # 收入概览
    fixed_annual = fixed_monthly * salary_months
    variable_annual = variable_monthly * salary_months
    probation_loss = 0
    if offer.probation_months and offer.probation_salary_rate:
        rate = float(offer.probation_salary_rate)
        if rate < 1:
            probation_loss = salary * int(offer.probation_months) * (1 - rate)

    # 待确认事项（基于数据完整性判断）
    findings = []
    if offer.variable_salary and float(offer.variable_salary) > 0:
        variable_share = float(offer.variable_salary) / salary * 100 if salary > 0 else 0
        findings.append({
            "severity": "warning",
            "title": "绩效工资占比需要确认",
            "explanation": f"绩效部分 {offer.variable_salary} 元/月，占当前月薪口径 {variable_share:.0f}%。建议确认考核标准和发放条件。",
            "action": "问清楚绩效考核周期和发放标准",
        })
    if not offer.work_location:
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

    if not offer.working_hours:
        findings.append({
            "severity": "info",
            "title": "工作节奏待确认",
            "explanation": "Offer 尚未写明工时、加班频率或调休口径，无法判断实际时间成本。",
            "action": "向直属团队确认日常工时、加班频率与调休方式",
        })
    if not offer.response_deadline:
        findings.append({
            "severity": "info",
            "title": "回复期限待确认",
            "explanation": "没有明确最晚回复时间，容易错过比较和沟通窗口。",
            "action": "确认最晚回复时间，并为谈薪和核对合同预留至少一天",
        })

    # 个人匹配分析
    match_analysis = []
    if priorities:
        if "income" in priorities:
            match_analysis.append(f"按当前假设，月到手约 {salary_result.take_home:.0f} 元，年结余约 {expected_scenario['annual_savings']:.0f} 元。")
        if "growth" in priorities:
            match_analysis.append(f"岗位方向为 {job_title}，建议了解团队规模和晋升路径。")
        if "city_life" in priorities:
            match_analysis.append(f"按每月生活支出 {assumed_living_cost:.0f} 元估算，月结余约 {salary_result.monthly_savings:.0f} 元。")

    fact_ledger = _build_fact_ledger(offer, confirmed_fact_keys or set())
    target_snapshot = (target.job_snapshot or {}) if target else {}
    career_context = {
        "linked": bool(target),
        "target_id": target.id if target else None,
        "job_title": target_snapshot.get("title") if target else None,
        "company_name": target_snapshot.get("company_name") if target else None,
        "advice_summary": target.advice_summary if target else None,
        "plan_ready": bool(target and target.plan_status == "ready"),
    }
    decision_axes = _build_decision_axes(
        offer=offer,
        profile=profile,
        market=market,
        expected_scenario=expected_scenario,
        fact_ledger=fact_ledger,
        career_context=career_context,
    )
    stance = _build_stance(offer, expected_scenario, fact_ledger, findings)

    return {
        "offer_id": offer.id,
        "company": offer.company_name,
        "job_title": job_title,
        "city": city,
        "summary": stance["summary"],
        "stance": stance,
        "fact_ledger": fact_ledger,
        "assumptions": {
            "living_cost": round(assumed_living_cost),
            "living_cost_source": "本次调整" if living_cost is not None else "个人预算" if profile_budget else f"{city}普通生活估算",
            "variable_realization": round(variable_realization, 2),
            "extra_salary_months_realization": round(extra_salary_months_realization, 2),
            "social_insurance_basis": "暂按现金月收入估算",
        },
        "scenarios": scenarios,
        "income": {
            "monthly_gross": salary,
            "monthly_take_home": round(salary_result.take_home),
            "annual_gross": fixed_annual + variable_annual,
            "annual_take_home": round(expected_scenario["annual_take_home"]),
            "fixed_annual": fixed_annual,
            "variable_annual": variable_annual,
            "probation_loss": round(probation_loss),
            "monthly_living_cost": round(salary_result.monthly_living_cost),
            "monthly_savings": round(salary_result.monthly_savings),
            "annual_savings": round(expected_scenario["annual_savings"]),
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
        "decision_axes": decision_axes,
        "career_context": career_context,
        "confirmation_evidence": {
            "count": confirmation_count,
            "confirmed_fact_keys": sorted(confirmed_fact_keys or set()),
        },
    }


def _build_income_scenario(
    label: str,
    fixed_monthly: float,
    variable_monthly: float,
    allowance_monthly: float,
    city: str,
    living_cost: float,
    *,
    variable_realization: float,
    extra_salary_months_realization: float,
    extra_salary_months: int,
) -> dict:
    result = calculate_salary(
        fixed_monthly,
        city,
        living_cost=living_cost,
        performance=variable_monthly * variable_realization,
        meal_subsidy=allowance_monthly,
        bonus_months=extra_salary_months * extra_salary_months_realization,
    )
    annual_savings = result.annual_take_home - living_cost * 12
    return {
        "label": label,
        "monthly_take_home": round(result.take_home),
        "annual_gross": round(result.annual_gross),
        "annual_take_home": round(result.annual_take_home),
        "monthly_savings": round(result.monthly_savings),
        "annual_savings": round(annual_savings),
        "savings_rate": round(annual_savings / result.annual_take_home * 100) if result.annual_take_home > 0 else 0,
        "variable_realization": round(variable_realization, 2),
        "extra_salary_months_realization": round(extra_salary_months_realization, 2),
    }


def _build_fact_ledger(offer: Offer, confirmed_fact_keys: set[str]) -> dict:
    fields = [
        ("company_name", "公司", offer.company_name),
        ("job_title", "岗位", offer.job_title),
        ("city", "城市", offer.city),
        ("monthly_salary", "月薪", offer.monthly_salary),
        ("salary_months", "年薪月数", offer.salary_months),
        ("work_location", "工作地点", offer.work_location),
        ("working_hours", "工时制度", offer.working_hours),
        ("probation_terms", "试用期", offer.probation_months),
        ("response_deadline", "最晚回复时间", offer.response_deadline),
    ]
    confirmed = [label + ("（HR已答复）" if value in (None, "") else "") for key, label, value in fields if value not in (None, "") or key in confirmed_fact_keys]
    missing = [label for key, label, value in fields if value in (None, "") and key not in confirmed_fact_keys]
    return {
        "confirmed": confirmed,
        "missing": missing,
        "confirmed_count": len(confirmed),
        "total_count": len(fields),
        "source_kind": "书面 Offer" if offer.offer_kind == "written" else "口头意向",
        "facts_confirmed_at": offer.facts_confirmed_at,
    }


def _build_decision_axes(*, offer, profile, market, expected_scenario, fact_ledger, career_context) -> list[dict]:
    savings_goal = float(profile.savings_goal) if profile and profile.savings_goal else None
    annual_goal = savings_goal * 12 if savings_goal else None
    if not offer.monthly_salary:
        income = ("unknown", "收入结构不足", "先确认月薪、发薪月数和浮动部分。")
    elif annual_goal and expected_scenario["annual_savings"] < annual_goal:
        income = ("attention", "未达到储蓄目标", f"按当前假设，年结余比目标少约 {annual_goal - expected_scenario['annual_savings']:.0f} 元。")
    else:
        income = ("positive", "收入可继续比较", f"按当前假设，年到手约 {expected_scenario['annual_take_home']:.0f} 元。")

    if expected_scenario["monthly_savings"] < 0:
        life = ("attention", "生活现金流承压", "估算生活支出高于月到手，需要调整预算或重新谈条件。")
    elif savings_goal and expected_scenario["monthly_savings"] < savings_goal:
        life = ("attention", "月结余低于目标", f"当前月结余约 {expected_scenario['monthly_savings']:.0f} 元。")
    else:
        life = ("positive", "生活结余可控", f"当前月结余约 {expected_scenario['monthly_savings']:.0f} 元。")

    if market and market.get("availability") == "available":
        market_axis = ("neutral", market["description"], f"样本 {market.get('sample_size', 0)} 个；市场位置只作为谈判和比较参考。")
    else:
        market_axis = ("unknown", "市场位置暂不确定", "样本不足时不据此判断 Offer 好坏。")

    if career_context["linked"]:
        growth = ("neutral", "已接上目标岗位准备", career_context["advice_summary"] or "可结合目标岗位的能力路线继续判断成长价值。")
    else:
        growth = ("unknown", "成长判断缺少岗位上下文", "关联目标岗位后，才能结合 JD、简历差距和准备记录判断。")

    certainty = (
        "positive" if not fact_ledger["missing"] else "attention",
        "事实较完整" if not fact_ledger["missing"] else f"还有 {len(fact_ledger['missing'])} 项待确认",
        "已确认：" + "、".join(fact_ledger["confirmed"]) if fact_ledger["confirmed"] else "尚未确认关键 Offer 事实。",
    )
    rows = [
        ("收入", income),
        ("市场", market_axis),
        ("城市生活", life),
        ("职业成长", growth),
        ("信息确定性", certainty),
    ]
    return [{"key": key, "status": value[0], "title": value[1], "description": value[2]} for key, value in rows]


def _build_stance(offer, expected_scenario, fact_ledger, findings) -> dict:
    critical_missing = [item for item in fact_ledger["missing"] if item in {"公司", "岗位", "城市", "月薪"}]
    warnings = len([item for item in findings if item["severity"] == "warning"])
    if critical_missing:
        return {
            "level": "incomplete",
            "label": "先补齐关键信息",
            "summary": f"这份 Offer 还缺少 {'、'.join(critical_missing)}，现在不适合直接比较或作决定。",
        }
    if expected_scenario["monthly_savings"] < 0:
        return {
            "level": "attention",
            "label": "生活压力较大",
            "summary": "按当前生活支出估算，月度现金流为负；建议先重新核对预算或沟通收入条件。",
        }
    if warnings:
        return {
            "level": "conditional",
            "label": "有条件继续推进",
            "summary": f"确定收入和生活结余可以继续比较，但签之前还有 {warnings} 项重要条件需要问清楚。",
        }
    return {
        "level": "comparable",
        "label": "值得进入比较",
        "summary": "当前没有明显的阻断项；下一步应与其他机会、个人偏好和长期成长一起比较，而不是只看月薪。",
    }


def generate_hr_questions(offer: Offer, findings: list[dict]) -> list[dict]:
    """根据分析结果生成 HR 问题和沟通话术。"""
    questions = []

    if offer.variable_salary and float(offer.variable_salary) > 0:
        questions.append({
            "fact_key": "variable_salary_terms",
            "category": "薪资结构",
            "title": "绩效工资是否有明确考核标准",
            "why": f"绩效部分占月薪 {float(offer.variable_salary)/float(offer.monthly_salary or 1)*100:.0f}%，比例不低，需要确认发放条件。",
            "script": "想再确认一下，Offer 中绩效部分的考核周期和发放条件是什么？是否有书面制度可以提前了解？",
            "watch_for": "关注是否有'公司有权调整'等模糊表述",
        })

    if offer.bonus:
        questions.append({
            "fact_key": "bonus_terms",
            "category": "薪资结构",
            "title": "年终奖的发放条件",
            "why": f"Offer 提到 {offer.bonus}，但年终奖通常有条件限制。",
            "script": "想了解一下年终奖的具体发放条件，比如入职满多久可以参与分配？是否有绩效门槛？",
            "watch_for": "关注'根据公司经营状况'等不确定表述",
        })

    if offer.probation_months and int(offer.probation_months) > 0:
        questions.append({
            "fact_key": "probation_terms",
            "category": "试用期",
            "title": "试用期考核标准",
            "why": f"试用期 {offer.probation_months} 个月，工资比例 {float(offer.probation_salary_rate or 0.8)*100:.0f}%。",
            "script": "请问试用期的考核标准是什么？转正评估的流程和时间节点是怎样的？",
            "watch_for": "关注是否有明确的转正条件，避免'表现良好'等模糊说法",
        })

    if not offer.work_location or (offer.work_location and "根据" in str(offer.work_location)):
        questions.append({
            "fact_key": "work_location",
            "category": "工作地点",
            "title": "工作地点是否固定",
            "why": "工作地点的表述可能影响后续调动。",
            "script": "想确认一下，工作地点是否固定在 XX？是否存在跨城市调动的可能？",
            "watch_for": "关注'公司可根据经营需要调整'等弹性表述",
        })

    questions.append({
        "fact_key": "insurance_base",
        "category": "社保和公积金",
        "title": "社保和公积金缴纳基数",
        "why": "缴纳基数直接影响到手工资和公积金账户。",
        "script": "请问社保和公积金的缴纳基数是按实际工资还是按最低基数？公积金比例是多少？",
        "watch_for": "按最低基数缴纳虽然到手多，但公积金账户会少很多",
    })

    if not offer.working_hours:
        questions.append({
            "fact_key": "working_hours",
            "category": "工作节奏",
            "title": "日常工时、加班和调休口径",
            "why": "工时会显著影响真实时薪、生活安排和长期可持续性。",
            "script": "想了解一下团队通常几点上下班？最近三个月加班频率如何，周末加班是否可以调休？",
            "watch_for": "尽量询问团队真实情况，而不只看制度上的标准工时",
        })

    if not offer.response_deadline:
        questions.append({
            "fact_key": "response_deadline",
            "category": "决策时间",
            "title": "最晚回复时间",
            "why": "明确截止时间，才能安排比较、谈薪和合同核对。",
            "script": "感谢 Offer。想确认一下最晚需要在什么时间前正式回复？我会在期限内认真评估并明确答复。",
            "watch_for": "如果时间过紧，可以礼貌申请一到两个工作日完成核对",
        })

    return questions


def generate_negotiation_brief(offer: Offer, report: dict) -> dict:
    market = report.get("market") or {}
    anchors = []
    if offer.monthly_salary:
        anchors.append(f"当前月薪口径为 {float(offer.monthly_salary):,.0f} 元，年薪月数为 {int(offer.salary_months or 12)} 个月。")
    if market.get("availability") == "available":
        anchors.append(f"同类岗位市场位置：{market.get('description')}，参考样本 {market.get('sample_size', 0)} 个。")
    if offer.response_deadline:
        anchors.append(f"Offer 回复期限为 {offer.response_deadline:%Y-%m-%d %H:%M}。")

    requests = []
    if market.get("availability") == "available" and market.get("p50") and float(offer.monthly_salary or 0) < float(market["p50"]):
        requests.append({"title": "优先沟通固定月薪", "reason": "当前月薪低于市场中位样本，可用岗位职责和市场区间作为讨论依据。"})
    if offer.variable_salary and float(offer.variable_salary) > 0:
        requests.append({"title": "确认或提高固定收入占比", "reason": "浮动收入需要考核条件，固定部分更能代表可预期现金流。"})
    if offer.probation_months and float(offer.probation_salary_rate or 1) < 1:
        requests.append({"title": "争取试用期同薪", "reason": "试用期折扣会形成确定的收入损失，可作为替代谈判项。"})
    if not requests:
        requests.append({"title": "先确认完整条件，再决定是否谈金额", "reason": "当前没有足够证据支持具体加价，先补齐奖金、工时、社保和回复期限。"})

    company = offer.company_name or "贵公司"
    role = offer.job_title or "这个岗位"
    return {
        "offer_id": offer.id,
        "readiness": "ready" if len(report["fact_ledger"]["missing"]) <= 2 else "needs_facts",
        "summary": "先表达加入意愿，再用已经核实的职责、市场和收入结构讨论一到两个最重要的条件。",
        "anchors": anchors,
        "requests": requests,
        "opening_script": f"感谢 {company} 对我的认可，我对 {role} 的工作内容和团队方向很感兴趣。结合岗位职责、目前确认的薪资结构和市场情况，我想再沟通一下整体方案是否还有调整空间。",
        "fallback_script": "如果固定月薪暂时不能调整，想请问是否可以从试用期同薪、签字费、奖金保底或更明确的调薪评审时间中选择一项进一步沟通？",
        "cautions": ["只使用真实经历和已有 Offer 条件，不虚构其他公司报价。", "一次聚焦一到两个诉求，并请 HR 将最终结果落实为书面内容。"],
    }
