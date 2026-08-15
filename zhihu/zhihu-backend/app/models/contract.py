from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from app.db.session import Base


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    linked_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    employer = Column(String(200), nullable=True)
    contract_term = Column(String(100), nullable=True)
    probation = Column(String(100), nullable=True)
    salary_terms = Column(Text, nullable=True)
    work_location = Column(String(300), nullable=True)
    working_hours = Column(String(200), nullable=True)
    non_compete = Column(Text, nullable=True)
    penalty_terms = Column(Text, nullable=True)
    termination_terms = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
