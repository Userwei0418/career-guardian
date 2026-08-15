from pydantic import BaseModel
from typing import Optional


class ProfileUpdateRequest(BaseModel):
    career_stage: Optional[str] = None
    graduation_date: Optional[str] = None
    years_of_experience: Optional[int] = None
    current_city: Optional[str] = None
    target_cities: Optional[list[str]] = None
    target_roles: Optional[list[str]] = None
    skills: Optional[list[str]] = None
    priorities: Optional[list[str]] = None
    monthly_budget: Optional[int] = None
    savings_goal: Optional[int] = None


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    career_stage: Optional[str] = None
    graduation_date: Optional[str] = None
    years_of_experience: int = 0
    current_city: Optional[str] = None
    target_cities: Optional[list] = None
    target_roles: Optional[list] = None
    skills: Optional[list] = None
    priorities: Optional[list] = None
    monthly_budget: Optional[int] = None
    savings_goal: Optional[int] = None

    class Config:
        from_attributes = True
