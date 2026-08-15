"""财务规划计算引擎 — 养老金估算 + 医保退休待遇 + 公积金账户。"""
from dataclasses import dataclass
from typing import Optional

# 10 城市社平工资（月，元）— 2024 年参考值
CITY_AVERAGE_SALARY = {
    "北京": 13000, "上海": 12500, "广州": 10500, "深圳": 12000,
    "杭州": 11000, "成都": 9000, "武汉": 9500, "南京": 10500,
    "西安": 8500, "长沙": 8500,
}
DEFAULT_AVG_SALARY = 9000

# 计发月数（退休年龄 → 月数）
PAYMENT_MONTHS_MAP = {
    40: 233, 41: 230, 42: 226, 43: 223, 44: 220,
    45: 216, 46: 212, 47: 208, 48: 204, 49: 199,
    50: 195, 51: 190, 52: 185, 53: 180, 54: 175,
    55: 170, 56: 164, 57: 158, 58: 152, 59: 145,
    60: 139, 61: 132, 62: 125, 63: 117, 64: 109,
    65: 101, 66: 93, 67: 84, 68: 75, 69: 65, 70: 56,
}

# 10 城市医保最低缴费年限（男/女）
CITY_MEDICAL_MIN_YEARS = {
    "北京": {"male": 25, "female": 20},
    "上海": {"male": 15, "female": 15},
    "广州": {"male": 30, "female": 25},
    "深圳": {"male": 25, "female": 20},
    "杭州": {"male": 20, "female": 20},
    "成都": {"male": 15, "female": 15},
    "武汉": {"male": 30, "female": 25},
    "南京": {"male": 25, "female": 20},
    "西安": {"male": 25, "female": 20},
    "长沙": {"male": 25, "female": 20},
}

# 10 城市退休后医保报销比例
CITY_RETIREMENT_REIMBURSEMENT = {
    "北京": 0.90, "上海": 0.92, "广州": 0.85, "深圳": 0.90,
    "杭州": 0.88, "成都": 0.85, "武汉": 0.85, "南京": 0.88,
    "西安": 0.85, "长沙": 0.85,
}

# 10 城市退休后医保个人账户月入账（元）
CITY_RETIREMENT_MEDICAL_MONTHLY = {
    "北京": 100, "上海": 110, "广州": 80, "深圳": 90,
    "杭州": 85, "成都": 70, "武汉": 75, "南京": 80,
    "西安": 65, "长沙": 65,
}

# 养老金个人账户记账利率（年化）
PENSION_INTEREST_RATE = 0.03

# 公积金年利率（一年期定期存款基准利率）
HOUSING_FUND_INTEREST_RATE = 0.015

# 法定退休年龄
DEFAULT_RETIREMENT_AGE = {
    "male": {"management": 60, "worker": 60},
    "female": {"management": 55, "worker": 50},
}


def get_default_retire_age(gender: str = "male", worker_type: str = "management") -> int:
    """获取默认退休年龄。"""
    g = DEFAULT_RETIREMENT_AGE.get(gender, DEFAULT_RETIREMENT_AGE["male"])
    return g.get(worker_type, 60)

# 最低缴费年限政策（2030 起每年增加 6 个月，上限 20 年）
def get_min_pension_years(retire_year: int) -> int:
    """获取退休年份对应的最低缴费年限。"""
    if retire_year < 2030:
        return 15
    years_after = retire_year - 2030
    return min(15 + (years_after + 1) // 2, 20)


# ========== 养老金估算 ==========

@dataclass
class PensionResult:
    current_age: int
    retire_age: int
    contribution_years: int
    min_required_years: int
    is_enough: bool

    # 个人账户
    monthly_contribution: float  # 每月个人缴纳（8%）
    account_balance: float  # 退休时个人账户累计额（含利息）

    # 养老金
    basic_pension: float  # 基础养老金
    personal_pension: float  # 个人账户养老金
    monthly_pension: float  # 每月养老金总额

    # 分析
    replacement_rate: float  # 替代率 %
    payback_years: float  # 回本周期（年）
    total_personal_paid: float  # 个人累计缴纳总额
    avg_salary_at_retire: float  # 退休时社平工资


def estimate_pension(
    current_age: int = 25,
    retire_age: int = 60,
    current_salary: float = 15000,
    city: str = "杭州",
    salary_growth_rate: float = 0.05,
    gender: str = "male",
) -> PensionResult:
    """养老金估算。

    Args:
        current_age: 当前年龄
        retire_age: 预期退休年龄
        current_salary: 当前税前月薪
        city: 城市
        salary_growth_rate: 年工资增长率
        gender: 性别（影响医保年限，此处仅传递）
    """
    contribution_years = retire_age - current_age
    if contribution_years <= 0:
        contribution_years = 1

    retire_year = 2026 + contribution_years
    min_required = get_min_pension_years(retire_year)
    avg_salary = CITY_AVERAGE_SALARY.get(city, DEFAULT_AVG_SALARY)

    # 模拟逐年计算
    salary = current_salary
    account_balance = 0.0
    total_paid = 0.0
    salary_index_sum = 0.0

    for year in range(contribution_years):
        # 当年社平工资（按 3% 增长）
        avg_salary_year = avg_salary * ((1.03) ** year)
        # 缴费指数 = 本人工资 / 社平工资（上限 3，下限 0.6）
        if avg_salary_year > 0:
            index = min(max(salary / avg_salary_year, 0.6), 3.0)
        else:
            index = 1.0
        salary_index_sum += index

        # 个人缴纳 8%/月
        monthly_contrib = salary * 0.08
        annual_contrib = monthly_contrib * 12
        account_balance += annual_contrib
        # 记账利息（简化：按年初余额计息）
        account_balance *= (1 + PENSION_INTEREST_RATE)
        total_paid += annual_contrib

        # 工资年增长
        salary *= (1 + salary_growth_rate)

    # 退休时社平工资
    avg_salary_at_retire = avg_salary * (1.03 ** contribution_years)
    # 平均缴费指数
    avg_index = salary_index_sum / contribution_years if contribution_years > 0 else 1.0

    # 基础养老金 = 社平工资 × (1 + 平均指数) / 2 × 年限 × 1%
    basic_pension = avg_salary_at_retire * (1 + avg_index) / 2 * contribution_years * 0.01

    # 个人账户养老金 = 累计额 / 计发月数
    payment_months = PAYMENT_MONTHS_MAP.get(retire_age, 139)
    personal_pension = account_balance / payment_months if payment_months > 0 else 0

    monthly_pension = basic_pension + personal_pension

    # 退休前最后一年工资
    final_salary = current_salary * ((1 + salary_growth_rate) ** (contribution_years - 1))
    replacement_rate = round(monthly_pension / final_salary * 100) if final_salary > 0 else 0

    # 回本周期 = 个人缴纳总额 / (月养老金 × 12)
    annual_pension = monthly_pension * 12
    payback_years = round(total_paid / annual_pension, 1) if annual_pension > 0 else 0

    return PensionResult(
        current_age=current_age,
        retire_age=retire_age,
        contribution_years=contribution_years,
        min_required_years=min_required,
        is_enough=contribution_years >= min_required,
        monthly_contribution=round(current_salary * 0.08),
        account_balance=round(account_balance),
        basic_pension=round(basic_pension),
        personal_pension=round(personal_pension),
        monthly_pension=round(monthly_pension),
        replacement_rate=replacement_rate,
        payback_years=payback_years,
        total_personal_paid=round(total_paid),
        avg_salary_at_retire=round(avg_salary_at_retire),
    )


# ========== 医保退休待遇 ==========

@dataclass
class MedicalRetirementResult:
    city: str
    gender: str
    min_years: int
    current_age: int
    retire_age: int
    contribution_years: int
    remaining_years: int
    is_enough: bool

    # 退休后待遇
    reimbursement_rate: float  # 报销比例
    monthly_account: float  # 月个人账户入账
    account_balance: float  # 累计账户余额
    in_service_reimbursement: float  # 在职报销比例


def estimate_medical_retirement(
    current_age: int = 25,
    retire_age: int = 60,
    city: str = "杭州",
    gender: str = "male",
    current_salary: float = 15000,
) -> MedicalRetirementResult:
    """医保退休待遇估算。"""
    contribution_years = max(retire_age - current_age, 1)

    city_min = CITY_MEDICAL_MIN_YEARS.get(city, {"male": 25, "female": 20})
    min_years = city_min.get(gender, 25)
    remaining = max(min_years - contribution_years, 0)

    reimbursement = CITY_RETIREMENT_REIMBURSEMENT.get(city, 0.85)
    monthly_account = CITY_RETIREMENT_MEDICAL_MONTHLY.get(city, 70)

    # 在职报销比例（一般比退休低 5~15%）
    in_service = max(reimbursement - 0.10, 0.70)

    # 累计账户余额（退休后每月入账 × 预期领取年数 20 年）
    account_balance = monthly_account * 12 * 20

    return MedicalRetirementResult(
        city=city,
        gender=gender,
        min_years=min_years,
        current_age=current_age,
        retire_age=retire_age,
        contribution_years=contribution_years,
        remaining_years=remaining,
        is_enough=contribution_years >= min_years,
        reimbursement_rate=reimbursement,
        monthly_account=monthly_account,
        account_balance=account_balance,
        in_service_reimbursement=in_service,
    )


# ========== 公积金账户 ==========

@dataclass
class HousingFundResult:
    monthly_contribution: float  # 月缴额（双边）
    months_paid: int  # 已缴月数
    current_balance: float  # 当前余额（含利息）
    balance_1y: float  # 1 年后
    balance_3y: float  # 3 年后
    balance_5y: float  # 5 年后
    balance_10y: float  # 10 年后
    withdrawal_rules: list  # 提取场景说明


def estimate_housing_fund(
    monthly_contribution: float = 3600,
    months_paid: int = 24,
    interest_rate: float = HOUSING_FUND_INTEREST_RATE,
) -> HousingFundResult:
    """公积金账户估算。

    Args:
        monthly_contribution: 月缴额（个人+公司双边）
        months_paid: 已缴月数
        interest_rate: 年利率
    """
    monthly_rate = interest_rate / 12

    # 当前余额（每月存入 + 复利）
    balance = 0
    for m in range(months_paid):
        balance += monthly_contribution
        balance *= (1 + monthly_rate)
    current_balance = round(balance)

    def project_balance(from_balance: float, extra_months: int) -> float:
        b = from_balance
        for _ in range(extra_months):
            b += monthly_contribution
            b *= (1 + monthly_rate)
        return round(b)

    withdrawal_rules = [
        {"scene": "租房", "condition": "连续缴存 3 个月以上", "amount": "每月可提取不超过月缴存额，且不超过当地月租金上限"},
        {"scene": "购房", "condition": "购房合同或房产证", "amount": "可一次性提取账户全部余额"},
        {"scene": "偿还房贷", "condition": "有住房贷款", "amount": "每年可提取一次，不超过当年还款额"},
        {"scene": "离职", "condition": "与单位解除劳动关系且未再就业满半年", "amount": "可一次性提取全部余额"},
        {"scene": "退休", "condition": "达到法定退休年龄", "amount": "可一次性提取全部余额并销户"},
    ]

    return HousingFundResult(
        monthly_contribution=monthly_contribution,
        months_paid=months_paid,
        current_balance=current_balance,
        balance_1y=project_balance(current_balance, 12),
        balance_3y=project_balance(current_balance, 36),
        balance_5y=project_balance(current_balance, 60),
        balance_10y=project_balance(current_balance, 120),
        withdrawal_rules=withdrawal_rules,
    )
