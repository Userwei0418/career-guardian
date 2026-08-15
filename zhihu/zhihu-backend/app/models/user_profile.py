from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.session import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    career_stage = Column(String(30), nullable=True)
    graduation_date = Column(String(20), nullable=True)
    years_of_experience = Column(Integer, default=0)
    current_city = Column(String(50), nullable=True)
    target_cities = Column(JSON, nullable=True)
    target_roles = Column(JSON, nullable=True)
    skills = Column(JSON, nullable=True)
    priorities = Column(JSON, nullable=True)
    monthly_budget = Column(Integer, nullable=True)
    savings_goal = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
