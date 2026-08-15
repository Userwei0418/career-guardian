from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.sql import func

from app.db.session import Base


class Payslip(Base):
    __tablename__ = "payslips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    linked_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    pay_month = Column(String(10), nullable=True)
    gross_salary = Column(Numeric(12, 2), nullable=True)
    base_salary = Column(Numeric(12, 2), nullable=True)
    performance = Column(Numeric(12, 2), nullable=True)
    allowance = Column(Numeric(12, 2), nullable=True)
    social_insurance = Column(Numeric(12, 2), nullable=True)
    housing_fund = Column(Numeric(12, 2), nullable=True)
    individual_tax = Column(Numeric(12, 2), nullable=True)
    other_deductions = Column(Numeric(12, 2), nullable=True)
    net_salary = Column(Numeric(12, 2), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
