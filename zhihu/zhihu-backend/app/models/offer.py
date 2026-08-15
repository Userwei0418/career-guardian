from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.sql import func

from app.db.session import Base


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    name = Column(String(200), nullable=True)  # 用户自定义名称，如"字节终面"、"Offer A"
    company_name = Column(String(200), nullable=True)
    job_title = Column(String(200), nullable=True)
    city = Column(String(50), nullable=True)
    monthly_salary = Column(Numeric(12, 2), nullable=True)
    salary_months = Column(Integer, default=12)
    fixed_salary = Column(Numeric(12, 2), nullable=True)
    variable_salary = Column(Numeric(12, 2), nullable=True)
    bonus = Column(String(100), nullable=True)
    allowance = Column(Numeric(12, 2), nullable=True)
    probation_months = Column(Integer, default=0)
    probation_salary_rate = Column(Numeric(4, 2), default=0.80)
    work_location = Column(String(300), nullable=True)
    working_hours = Column(String(200), nullable=True)
    start_date = Column(String(50), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    extraction_confidence = Column(Numeric(4, 3), default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
