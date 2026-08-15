"""市场数据服务 — 先用 mock 数据，后续对接职涯通 API。

参考: pin/backend/api/routers/salary.py 的薪资统计逻辑
"""
from typing import Optional

# Mock 市场薪资数据（月薪，单位：元）
MOCK_SALARY_DATA = {
    "前端开发工程师": {
        "北京": {"p25": 12000, "p50": 18000, "p75": 28000, "avg": 20000, "count": 342},
        "上海": {"p25": 13000, "p50": 19000, "p75": 30000, "avg": 21000, "count": 289},
        "杭州": {"p25": 10000, "p50": 15000, "p75": 24000, "avg": 17000, "count": 198},
        "广州": {"p25": 9000, "p50": 14000, "p75": 22000, "avg": 16000, "count": 156},
        "深圳": {"p25": 11000, "p50": 16000, "p75": 26000, "avg": 18000, "count": 234},
        "成都": {"p25": 7000, "p50": 11000, "p75": 18000, "avg": 13000, "count": 120},
        "武汉": {"p25": 6500, "p50": 10000, "p75": 16000, "avg": 12000, "count": 98},
        "南京": {"p25": 9000, "p50": 14000, "p75": 22000, "avg": 16000, "count": 110},
        "西安": {"p25": 6000, "p50": 9500, "p75": 15000, "avg": 11000, "count": 76},
        "长沙": {"p25": 6000, "p50": 9000, "p75": 14000, "avg": 10500, "count": 65},
    },
    "后端开发工程师": {
        "北京": {"p25": 13000, "p50": 20000, "p75": 30000, "avg": 22000, "count": 310},
        "上海": {"p25": 14000, "p50": 21000, "p75": 32000, "avg": 23000, "count": 265},
        "杭州": {"p25": 11000, "p50": 17000, "p75": 26000, "avg": 19000, "count": 180},
        "广州": {"p25": 10000, "p50": 15000, "p75": 24000, "avg": 17000, "count": 140},
        "深圳": {"p25": 12000, "p50": 18000, "p75": 28000, "avg": 20000, "count": 210},
        "成都": {"p25": 8000, "p50": 12000, "p75": 20000, "avg": 14000, "count": 105},
        "武汉": {"p25": 7000, "p50": 11000, "p75": 18000, "avg": 13000, "count": 85},
        "南京": {"p25": 10000, "p50": 15000, "p75": 24000, "avg": 17000, "count": 95},
        "西安": {"p25": 7000, "p50": 10000, "p75": 16000, "avg": 12000, "count": 68},
        "长沙": {"p25": 6500, "p50": 10000, "p75": 15000, "avg": 11500, "count": 55},
    },
    "产品经理": {
        "北京": {"p25": 12000, "p50": 18000, "p75": 28000, "avg": 20000, "count": 180},
        "上海": {"p25": 13000, "p50": 19000, "p75": 30000, "avg": 21000, "count": 160},
        "杭州": {"p25": 10000, "p50": 16000, "p75": 25000, "avg": 18000, "count": 120},
        "广州": {"p25": 9000, "p50": 14000, "p75": 22000, "avg": 16000, "count": 90},
        "深圳": {"p25": 11000, "p50": 17000, "p75": 26000, "avg": 19000, "count": 140},
    },
    "数据分析师": {
        "北京": {"p25": 11000, "p50": 17000, "p75": 26000, "avg": 19000, "count": 150},
        "上海": {"p25": 12000, "p50": 18000, "p75": 28000, "avg": 20000, "count": 130},
        "杭州": {"p25": 9000, "p50": 15000, "p75": 23000, "avg": 17000, "count": 95},
    },
}

DEFAULT_SALARY = {"p25": 8000, "p50": 12000, "p75": 20000, "avg": 14000, "count": 50}


def get_market_salary(job_title: str, city: str) -> dict:
    """获取岗位在目标城市的薪资市场数据"""
    role_data = MOCK_SALARY_DATA.get(job_title, {})
    city_data = role_data.get(city, DEFAULT_SALARY)

    # 计算 Offer 在市场中的位置
    return {
        "job_title": job_title,
        "city": city,
        "p25": city_data["p25"],
        "p50": city_data["p50"],
        "p75": city_data["p75"],
        "avg": city_data["avg"],
        "sample_count": city_data["count"],
        "data_source": "职护市场数据（模拟）",
        "note": "数据为模拟值，后续将对接职涯通真实招聘数据",
    }


def get_position_percentile(salary: float, job_title: str, city: str) -> dict:
    """计算 Offer 薪资在市场中的百分位"""
    market = get_market_salary(job_title, city)
    p25, p50, p75 = market["p25"], market["p50"], market["p75"]

    if salary <= p25:
        position = "低于25分位"
        advice = "这份 Offer 的薪资低于市场大部分同类岗位，建议了解是否有其他补偿（如股权、成长空间）"
    elif salary <= p50:
        position = "25-50分位"
        advice = "这份 Offer 的薪资处于市场中下水平，还有争取空间"
    elif salary <= p75:
        position = "50-75分位"
        advice = "这份 Offer 的薪资处于市场中上水平，比较有竞争力"
    else:
        position = "高于75分位"
        advice = "这份 Offer 的薪资非常有竞争力"

    return {**market, "offer_salary": salary, "position": position, "advice": advice}
