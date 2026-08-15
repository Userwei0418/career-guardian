from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text, JSON
from sqlalchemy.sql import func

from app.db.session import Base


class SalaryCalculation(Base):
    __tablename__ = "salary_calculations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=True)  # 用户自定义名称，如"杭州15K方案"

    # 输入参数
    city = Column(String(50), nullable=True)
    monthly_salary = Column(Numeric(12, 2), nullable=True)
    performance = Column(Numeric(12, 2), default=0)
    subsidies = Column(JSON, nullable=True)  # {meal, transport, housing, communication}
    housing_ratio = Column(Numeric(4, 2), default=12)
    supplementary_housing_ratio = Column(Numeric(4, 2), default=0)
    supplementary_medical = Column(Numeric(8, 2), default=0)
    special_deduction = Column(Numeric(10, 2), default=0)
    social_insurance_base = Column(Numeric(12, 2), nullable=True)
    bonus_months = Column(Numeric(4, 2), default=0)
    living_cost = Column(Numeric(10, 2), nullable=True)

    # 计算结果（冗余存储，避免重新计算）
    result_take_home = Column(Numeric(12, 2), nullable=True)
    result_annual_take_home = Column(Numeric(12, 2), nullable=True)
    result_savings_rate = Column(Numeric(5, 2), nullable=True)
    result_json = Column(JSON, nullable=True)  # 完整计算结果

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
