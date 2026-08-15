from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.session import Base


class CareerCase(Base):
    __tablename__ = "career_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(30), nullable=False)
    title = Column(String(200), nullable=True)
    status = Column(String(20), default="in_progress")
    current_step = Column(Integer, default=1)
    started_at = Column(DateTime, server_default=func.now())
    deadline = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
