"""薪资计算引擎 — 五险一金 + 个税 + 年终奖 + 补贴 + 生活结余。

数据参考: engineering-contract-ai-review/frontend/src/views/SalaryCalculatorPage.vue
"""
from typing import Optional
from dataclasses import dataclass, field

# 10 城市五险一金个人缴纳比例 (%)
CITY_INSURANCE_DATA = {
    "北京": {"pension": 8, "medical": 2, "unemployment": 0.5, "housing": 12, "living_cost": 7000},
    "上海": {"pension": 8, "medical": 2, "unemployment": 0.5, "housing": 7, "living_cost": 6800},
    "广州": {"pension": 8, "medical": 2, "unemployment": 0.2, "housing": 12, "living_cost": 5500},
    "深圳": {"pension": 8, "medical": 2, "unemployment": 0.3, "housing": 5, "living_cost": 6000},
    "杭州": {"pension": 8, "medical": 2, "unemployment": 0.5, "housing": 12, "living_cost": 5500},
    "成都": {"pension": 8, "medical": 2, "unemployment": 0.4, "housing": 12, "living_cost": 4000},
    "武汉": {"pension": 8, "medical": 2, "unemployment": 0.3, "housing": 8, "living_cost": 3800},
    "南京": {"pension": 8, "medical": 2, "unemployment": 0.5, "housing": 10, "living_cost": 4500},
    "西安": {"pension": 8, "medical": 2, "unemployment": 0.3, "housing": 12, "living_cost": 3500},
    "长沙": {"pension": 8, "medical": 2, "unemployment": 0.3, "housing": 12, "living_cost": 3200},
}
DEFAULT_CITY = {"pension": 8, "medical": 2, "unemployment": 0.5, "housing": 12, "living_cost": 4000}

# 雇主缴纳比例 (%)
EMPLOYER_RATES = {"pension": 16, "medical": 9.8, "unemployment": 0.5, "injury": 0.4, "maternity": 0.8}

# 月度个税税率表（综合所得）
TAX_BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float("inf"), 0.45, 15160),
]

# 年度个税税率表（年终奖合并计税用）
ANNUAL_TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float("inf"), 0.45, 181920),
]

# 生活成本 8 项明细默认值
CITY_COST_BREAKDOWN = {
    "北京": {"rent": 3000, "food": 2500, "transport": 400, "utilities": 200, "communication": 150, "daily": 500, "entertainment": 500},
    "上海": {"rent": 2800, "food": 2500, "transport": 400, "utilities": 200, "communication": 150, "daily": 500, "entertainment": 500},
    "广州": {"rent": 2000, "food": 2000, "transport": 300, "utilities": 150, "communication": 120, "daily": 400, "entertainment": 400},
    "深圳": {"rent": 2500, "food": 2200, "transport": 300, "utilities": 180, "communication": 130, "daily": 450, "entertainment": 450},
    "杭州": {"rent": 2200, "food": 2200, "transport": 350, "utilities": 180, "communication": 130, "daily": 450, "entertainment": 450},
    "成都": {"rent": 1500, "food": 1800, "transport": 250, "utilities": 120, "communication": 100, "daily": 350, "entertainment": 350},
    "武汉": {"rent": 1400, "food": 1600, "transport": 200, "utilities": 120, "communication": 100, "daily": 300, "entertainment": 300},
    "南京": {"rent": 1800, "food": 2000, "transport": 300, "utilities": 150, "communication": 120, "daily": 400, "entertainment": 400},
    "西安": {"rent": 1300, "food": 1500, "transport": 200, "utilities": 100, "communication": 100, "daily": 300, "entertainment": 300},
    "长沙": {"rent": 1200, "food": 1500, "transport": 200, "utilities": 100, "communication": 100, "daily": 300, "entertainment": 300},
}
DEFAULT_COST = {"rent": 1500, "food": 2000, "transport": 300, "utilities": 150, "communication": 120, "daily": 400, "entertainment": 400}


@dataclass
class SalaryResult:
    # 收入
    gross_salary: float
    performance: float
    subsidies: float  # 4 项补贴合计
    total_income: float  # gross + performance + subsidies

    # 五险一金（个人）
    pension: float
    medical: float
    unemployment: float
    housing_fund: float
    supplementary_housing: float  # 补充公积金
    supplementary_medical: float  # 补充医疗保险（月扣金额）
    total_insurance: float

    # 个税
    special_deduction: float  # 专项附加扣除
    taxable_income: float
    income_tax: float

    # 到手
    take_home: float

    # 雇主成本
    employer_insurance: float
    employer_housing: float
    employer_cost: float  # 薪资 + 雇主五险一金

    # 年终奖
    bonus_months: float
    bonus_amount: float
    bonus_tax_separate: float  # 单独计税
    bonus_tax_combined: float  # 合并计税
    bonus_tax: float  # 推荐方案的税额
    bonus_after_tax: float  # 年终奖到手

    # 年度汇总
    annual_gross: float
    annual_take_home: float  # 月薪到手×12 + 年终奖到手
    annual_tax: float
    annual_housing_fund_total: float  # 个人+公司双边×12

    # 结余
    monthly_living_cost: float
    monthly_savings: float
    annual_savings: float
    savings_rate: float  # 储蓄率 %

    # 真实年包（含公积金双边隐藏资产）
    real_annual_package: float


def get_city_data(city: str) -> dict:
    return CITY_INSURANCE_DATA.get(city, DEFAULT_CITY)


def get_cost_breakdown(city: str) -> dict:
    return CITY_COST_BREAKDOWN.get(city, DEFAULT_COST)


def calc_monthly_tax(taxable_income: float) -> float:
    """计算月度个税（简化为单月计算，非累计）"""
    if taxable_income <= 0:
        return 0
    for upper, rate, deduction in TAX_BRACKETS:
        if taxable_income <= upper:
            return round(taxable_income * rate - deduction)
    return round(taxable_income * 0.45 - 15160)


def calc_annual_tax(taxable_income: float) -> float:
    """计算年度个税"""
    if taxable_income <= 0:
        return 0
    for upper, rate, deduction in ANNUAL_TAX_BRACKETS:
        if taxable_income <= upper:
            return round(taxable_income * rate - deduction)
    return round(taxable_income * 0.45 - 181920)


def calc_bonus_tax_separate(bonus: float) -> float:
    """年终奖单独计税：bonus/12 找月度税率，对全额计算"""
    if bonus <= 0:
        return 0
    monthly = bonus / 12
    for upper, rate, deduction in TAX_BRACKETS:
        if monthly <= upper:
            return round(bonus * rate - deduction)
    return round(bonus * 0.45 - 15160)


def calculate_salary(
    monthly_salary: float,
    city: str = "杭州",
    housing_ratio: Optional[float] = None,
    special_deduction: float = 0,
    living_cost: Optional[float] = None,
    performance: float = 0,
    meal_subsidy: float = 0,
    transport_subsidy: float = 0,
    housing_subsidy: float = 0,
    communication_subsidy: float = 0,
    supplementary_housing_ratio: float = 0,
    supplementary_medical: float = 0,
    social_insurance_base: Optional[float] = None,
    bonus_months: float = 0,
) -> SalaryResult:
    """完整薪资计算。

    Args:
        monthly_salary: 基本月薪
        city: 城市名
        housing_ratio: 公积金比例（覆盖城市默认值）
        special_deduction: 专项附加扣除（租房/赡养/子女教育等）
        living_cost: 自定义生活成本（覆盖城市默认值）
        performance: 绩效工资
        meal_subsidy: 餐补
        transport_subsidy: 交通补贴
        housing_subsidy: 住房补贴
        communication_subsidy: 通讯补贴
        supplementary_housing_ratio: 补充公积金比例（0=不缴，1~5）
        supplementary_medical: 补充医疗保险月扣金额（元）
        social_insurance_base: 社保缴费基数（默认=月薪+绩效+补贴）
        bonus_months: 年终奖月数（0~12）
    """
    city_data = get_city_data(city)
    housing_pct = housing_ratio if housing_ratio is not None else city_data["housing"]

    # 收入汇总
    subsidies = meal_subsidy + transport_subsidy + housing_subsidy + communication_subsidy
    total_income = monthly_salary + performance + subsidies

    # 社保基数（默认 = 总现金收入）
    base = social_insurance_base if social_insurance_base is not None else total_income

    # 五险一金（个人部分）
    pension = round(base * city_data["pension"] / 100)
    medical = round(base * city_data["medical"] / 100)
    unemployment = round(base * city_data["unemployment"] / 100)
    housing_fund = round(base * housing_pct / 100)
    supplementary_housing = round(base * supplementary_housing_ratio / 100) if supplementary_housing_ratio > 0 else 0
    total_insurance = pension + medical + unemployment + housing_fund + supplementary_housing + supplementary_medical

    # 个税
    taxable_income = max(0, total_income - total_insurance - 5000 - special_deduction)
    income_tax = calc_monthly_tax(taxable_income)

    # 月到手
    take_home = total_income - total_insurance - income_tax

    # 年终奖
    bonus_amount = monthly_salary * bonus_months
    bonus_tax_sep = calc_bonus_tax_separate(bonus_amount)

    # 合并计税：年终奖并入综合所得
    annual_income = total_income * 12
    annual_insurance = total_insurance * 12
    annual_standard_deduction = 60000
    annual_special = special_deduction * 12
    annual_taxable_combined = max(0, annual_income + bonus_amount - annual_insurance - annual_standard_deduction - annual_special)
    annual_tax_combined = calc_annual_tax(annual_taxable_combined)
    monthly_tax_total = income_tax * 12
    bonus_tax_comb = max(0, annual_tax_combined - monthly_tax_total)

    # 推荐更省税的方案
    if bonus_amount > 0:
        if bonus_tax_sep <= bonus_tax_comb:
            bonus_tax = bonus_tax_sep
        else:
            bonus_tax = bonus_tax_comb
    else:
        bonus_tax = 0
    bonus_after_tax = bonus_amount - bonus_tax

    # 雇主成本
    employer_insurance = round(base * sum(
        EMPLOYER_RATES.get(k, 0) for k in ["pension", "medical", "unemployment", "injury", "maternity"]
    ) / 100)
    employer_housing = housing_fund + supplementary_housing
    employer_cost = total_income + employer_insurance + employer_housing

    # 生活成本
    cost = living_cost if living_cost is not None else city_data["living_cost"]
    monthly_savings = take_home - cost
    savings_rate = round(monthly_savings / take_home * 100) if take_home > 0 else 0

    # 年度汇总
    annual_gross = total_income * 12 + bonus_amount
    annual_take_home = take_home * 12 + bonus_after_tax
    annual_tax = income_tax * 12 + bonus_tax
    annual_housing_fund_total = (housing_fund + supplementary_housing + employer_housing) * 12

    # 真实年包 = 年到手 + 公积金双边年入（隐藏资产）
    real_annual_package = annual_take_home + annual_housing_fund_total

    return SalaryResult(
        gross_salary=monthly_salary,
        performance=performance,
        subsidies=subsidies,
        total_income=total_income,
        pension=pension,
        medical=medical,
        unemployment=unemployment,
        housing_fund=housing_fund,
        supplementary_housing=supplementary_housing,
        supplementary_medical=supplementary_medical,
        total_insurance=total_insurance,
        special_deduction=special_deduction,
        taxable_income=taxable_income,
        income_tax=income_tax,
        take_home=take_home,
        employer_insurance=employer_insurance,
        employer_housing=employer_housing,
        employer_cost=employer_cost,
        bonus_months=bonus_months,
        bonus_amount=bonus_amount,
        bonus_tax_separate=bonus_tax_sep,
        bonus_tax_combined=bonus_tax_comb,
        bonus_tax=bonus_tax,
        bonus_after_tax=bonus_after_tax,
        annual_gross=annual_gross,
        annual_take_home=annual_take_home,
        annual_tax=annual_tax,
        annual_housing_fund_total=annual_housing_fund_total,
        monthly_living_cost=cost,
        monthly_savings=monthly_savings,
        annual_savings=monthly_savings * 12,
        savings_rate=savings_rate,
        real_annual_package=real_annual_package,
    )
