from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.session import Base


class ReviewRule(Base):
    __tablename__ = "review_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    rule_code = Column(String(64), nullable=False, unique=True, index=True)
    risk_type = Column(String(100), nullable=False)
    condition_type = Column(String(32), nullable=False, index=True)
    condition_value = Column(Text, nullable=False)
    risk_level = Column(String(16), nullable=False, index=True)
    suggestion = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, default=100, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
