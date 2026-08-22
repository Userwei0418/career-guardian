from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


class Payslip(Base):
    __tablename__ = "payslips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    linked_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    pay_month = Column(String(10), nullable=True)
    pay_date = Column(Date, nullable=True)
    employer_name = Column(String(255), nullable=True)
    gross_salary = Column(Numeric(12, 2), nullable=True)
    base_salary = Column(Numeric(12, 2), nullable=True)
    performance = Column(Numeric(12, 2), nullable=True)
    bonus = Column(Numeric(12, 2), nullable=True)
    overtime_pay = Column(Numeric(12, 2), nullable=True)
    allowance = Column(Numeric(12, 2), nullable=True)
    social_insurance = Column(Numeric(12, 2), nullable=True)
    housing_fund = Column(Numeric(12, 2), nullable=True)
    individual_tax = Column(Numeric(12, 2), nullable=True)
    attendance_deductions = Column(Numeric(12, 2), nullable=True)
    meal_deductions = Column(Numeric(12, 2), nullable=True)
    other_deductions = Column(Numeric(12, 2), nullable=True)
    net_salary = Column(Numeric(12, 2), nullable=True)
    custom_items = Column(JSON, nullable=True)
    source_type = Column(String(30), nullable=False, default="manual", server_default="manual")
    recognition_confidence = Column(Numeric(5, 4), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
