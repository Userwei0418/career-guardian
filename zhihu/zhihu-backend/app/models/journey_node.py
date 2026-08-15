from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.db.session import Base


class JourneyNode(Base):
    __tablename__ = "journey_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")
    sort_order = Column(Integer, default=0)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    remind_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
