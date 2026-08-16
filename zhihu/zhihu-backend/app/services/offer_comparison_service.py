from datetime import datetime


PRIORITY_LABELS = {
    "income": "收入",
    "growth": "职业成长",
    "stability": "稳定",
    "workload": "工作强度",
    "city_life": "城市和生活",
    "major_match": "专业匹配",
    "platform": "公司平台",
    "commute": "通勤距离",
}


def _offer_name(snapshot: dict) -> str:
    return snapshot.get("name") or " · ".join(
        value for value in (snapshot.get("company_name"), snapshot.get("job_title")) if value
    ) or "未命名 Offer"


def build_offer_snapshot(offer) -> dict:
    return {
        "id": offer.id,
        "name": offer.name,
        "company_name": offer.company_name,
        "job_title": offer.job_title,
        "city": offer.city,
        "monthly_salary": float(offer.monthly_salary or 0),
        "salary_months": int(offer.salary_months or 12),
        "offer_kind": offer.offer_kind,
        "decision_status": offer.decision_status,
        "response_deadline": offer.response_deadline.isoformat() if offer.response_deadline else None,
        "job_target_id": offer.job_target_id,
        "facts_confirmed_at": offer.facts_confirmed_at.isoformat() if offer.facts_confirmed_at else None,
        "offer_updated_at": offer.updated_at.isoformat() if offer.updated_at else None,
    }


def build_comparison_result(report_a: dict, report_b: dict, snapshots: dict, priorities: list[str]) -> dict:
    reports = {"a": report_a, "b": report_b}
    expected = {key: value["scenarios"][1] for key, value in reports.items()}
    missing = {key: len(value["fact_ledger"]["missing"]) for key, value in reports.items()}
    names = {key: _offer_name(snapshots[key]) for key in ("a", "b")}

    rows = [
        {
            "key": "annual_take_home",
            "label": "预估年到手",
            "format": "currency",
            "a": expected["a"]["annual_take_home"],
            "b": expected["b"]["annual_take_home"],
        },
        {
            "key": "annual_savings",
            "label": "预估年结余",
            "format": "currency",
            "a": expected["a"]["annual_savings"],
            "b": expected["b"]["annual_savings"],
        },
        {
            "key": "market",
            "label": "市场位置",
            "format": "text",
            "a": (report_a.get("market") or {}).get("description") or "暂不确定",
            "b": (report_b.get("market") or {}).get("description") or "暂不确定",
        },
        {
            "key": "career",
            "label": "目标方向",
            "format": "text",
            "a": "已关联目标岗位" if report_a["career_context"]["linked"] else "尚未关联目标岗位",
            "b": "已关联目标岗位" if report_b["career_context"]["linked"] else "尚未关联目标岗位",
        },
        {
            "key": "certainty",
            "label": "待确认事实",
            "format": "count",
            "a": missing["a"],
            "b": missing["b"],
        },
        {
            "key": "deadline",
            "label": "回复期限",
            "format": "date",
            "a": snapshots["a"].get("response_deadline"),
            "b": snapshots["b"].get("response_deadline"),
        },
    ]

    conditions = []
    saving_delta = expected["a"]["annual_savings"] - expected["b"]["annual_savings"]
    if abs(saving_delta) >= 1000:
        winner = "a" if saving_delta > 0 else "b"
        conditions.append({
            "priority": "income",
            "title": "如果你优先短期现金流",
            "better_offer": winner,
            "summary": f"{names[winner]} 的预估年结余高约 {abs(saving_delta):,.0f} 元。",
        })
    else:
        conditions.append({
            "priority": "income",
            "title": "如果你优先短期现金流",
            "better_offer": None,
            "summary": "两份 Offer 的预估年结余接近，现金收入不足以单独决定。",
        })

    career_linked = {key: reports[key]["career_context"]["linked"] for key in ("a", "b")}
    if career_linked["a"] != career_linked["b"]:
        winner = "a" if career_linked["a"] else "b"
        conditions.append({
            "priority": "growth",
            "title": "如果你优先长期方向",
            "better_offer": winner,
            "summary": f"{names[winner]} 已关联目标岗位，可沿用能力差距、路线和模拟面试记录继续判断。",
        })
    else:
        conditions.append({
            "priority": "growth",
            "title": "如果你优先长期方向",
            "better_offer": None,
            "summary": "请结合两份岗位的职责、晋升路径和目标岗位准备记录判断，系统暂不凭公司名称猜测成长价值。",
        })

    if missing["a"] != missing["b"]:
        winner = "a" if missing["a"] < missing["b"] else "b"
        conditions.append({
            "priority": "stability",
            "title": "如果你优先确定性",
            "better_offer": winner,
            "summary": f"{names[winner]} 的关键事实更完整，当前少 {abs(missing['a'] - missing['b'])} 项待确认。",
        })
    else:
        conditions.append({
            "priority": "stability",
            "title": "如果你优先确定性",
            "better_offer": None,
            "summary": "两份 Offer 的信息完整度接近，继续比较前应先确认会改变结论的条件。",
        })

    unknowns = []
    for key in ("a", "b"):
        if reports[key]["fact_ledger"]["missing"]:
            unknowns.append({
                "offer": key,
                "name": names[key],
                "missing": reports[key]["fact_ledger"]["missing"],
            })

    ordered_conditions = sorted(
        conditions,
        key=lambda item: priorities.index(item["priority"]) if item["priority"] in priorities else 99,
    )
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": "没有脱离条件的唯一答案；先看你最在意的交换关系，再补齐会改变结论的事实。",
        "rows": rows,
        "conditions": ordered_conditions,
        "unknowns": unknowns,
        "reports": reports,
    }
