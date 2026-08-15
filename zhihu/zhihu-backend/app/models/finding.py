from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Numeric
from sqlalchemy.sql import func

from app.db.session import Base


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    category = Column(String(50), nullable=True)
    severity = Column(String(20), default="info")
    title = Column(String(300), nullable=True)
    plain_explanation = Column(Text, nullable=True)
    evidence_text = Column(Text, nullable=True)
    evidence_source = Column(String(30), nullable=True)
    recommended_action = Column(Text, nullable=True)
    confidence = Column(Numeric(4, 3), default=1.0)
    created_at = Column(DateTime, server_default=func.now())
