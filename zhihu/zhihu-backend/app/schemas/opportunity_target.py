from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobTargetUpsertRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    status: Literal["saved", "target"]
    resume_version_id: Optional[int] = Field(default=None, gt=0)


class JobTargetUpdateRequest(BaseModel):
    status: Optional[Literal["saved", "target"]] = None
    resume_version_id: Optional[int] = Field(default=None, gt=0)


class JobTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    status: Literal["saved", "target"]
    resume_version_id: Optional[int]
    job_snapshot: dict
    learning_plan: dict
    plan_mode: Optional[str]
    plan_generated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class LearningPlanResponse(BaseModel):
    target_id: int
    mode: Literal["ai", "rules"]
    plan: dict
    generated_at: datetime


class TailoringDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_target_id: int
    source_resume_version_id: int
    confirmed_resume_version_id: Optional[int]
    status: Literal["draft", "confirmed", "discarded"]
    source_text: str = ""
    tailored_text: str
    changes: list[dict]
    warnings: list[str]
    generation_mode: Literal["ai", "rules"]
    created_at: datetime
    confirmed_at: Optional[datetime]
