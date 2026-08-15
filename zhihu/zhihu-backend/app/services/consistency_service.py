"""Offer 与合同一致性检查服务。"""


def check_consistency(offer_data: dict, contract_data: dict) -> list[dict]:
    """逐项对比 Offer 和合同的关键字段，返回差异列表。

    Args:
        offer_data: Offer 字段字典（来自前端确认后的数据）
        contract_data: 合同字段字典（来自合同解析或手动填写）
    """
    diffs = []

    # 薪资对比
    offer_salary = offer_data.get("monthly_salary")
    contract_salary = contract_data.get("salary_terms")
    if offer_salary and contract_salary:
        try:
            offer_num = float(offer_salary)
            # 简单检查合同中是否包含 Offer 薪资数字
            if str(int(offer_num)) not in str(contract_salary):
                diffs.append({
                    "field": "月薪",
                    "offer_value": f"¥{offer_num:,.0f}",
                    "contract_value": str(contract_salary)[:100],
                    "status": "mismatch",
                    "suggestion": "薪资表述不一致，建议向 HR 确认合同中的薪资结构",
                })
            else:
                diffs.append({
                    "field": "月薪",
                    "offer_value": f"¥{offer_num:,.0f}",
                    "contract_value": str(contract_salary)[:100],
                    "status": "consistent",
                    "suggestion": "",
                })
        except (ValueError, TypeError):
            pass

    # 工作地点对比
    offer_city = offer_data.get("city", "")
    contract_location = contract_data.get("work_location", "")
    if offer_city and contract_location:
        if offer_city in contract_location:
            diffs.append({
                "field": "工作地点",
                "offer_value": offer_city,
                "contract_value": contract_location,
                "status": "consistent",
                "suggestion": "",
            })
        elif "根据" in contract_location or "安排" in contract_location:
            diffs.append({
                "field": "工作地点",
                "offer_value": offer_city,
                "contract_value": contract_location,
                "status": "vague",
                "suggestion": "合同中工作地点表述模糊，可能允许跨城市调动",
            })
        else:
            diffs.append({
                "field": "工作地点",
                "offer_value": offer_city,
                "contract_value": contract_location,
                "status": "mismatch",
                "suggestion": "工作地点与 Offer 不一致，签之前一定要问清楚",
            })

    # 试用期对比
    offer_probation = offer_data.get("probation_months")
    contract_probation = contract_data.get("probation", "")
    if offer_probation and contract_probation:
        offer_p = str(int(offer_probation))
        if offer_p in str(contract_probation):
            diffs.append({
                "field": "试用期",
                "offer_value": f"{offer_p} 个月",
                "contract_value": str(contract_probation)[:50],
                "status": "consistent",
                "suggestion": "",
            })
        else:
            diffs.append({
                "field": "试用期",
                "offer_value": f"{offer_p} 个月",
                "contract_value": str(contract_probation)[:50],
                "status": "mismatch",
                "suggestion": "试用期与 Offer 不一致，需要确认",
            })

    # 年终奖对比
    offer_bonus = offer_data.get("bonus", "")
    if offer_bonus:
        contract_text = str(contract_data.get("salary_terms", ""))
        if "年终" in contract_text or "奖金" in contract_text:
            diffs.append({
                "field": "年终奖",
                "offer_value": str(offer_bonus),
                "contract_value": "合同中有提及",
                "status": "consistent",
                "suggestion": "",
            })
        else:
            diffs.append({
                "field": "年终奖",
                "offer_value": str(offer_bonus),
                "contract_value": "合同中未写入",
                "status": "missing",
                "suggestion": "Offer 提到的年终奖在合同中未写入，建议确认",
            })

    return diffs
