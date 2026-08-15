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
    plan_status: Literal["idle", "queued", "running", "ready", "failed"]
    plan_error: Optional[str]
    plan_started_at: Optional[datetime]
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
    status: Literal["generating", "draft", "confirmed", "discarded", "failed"]
    source_text: str = ""
    tailored_text: str
    changes: list[dict]
    warnings: list[str]
    generation_mode: Literal["pending", "ai", "rules"]
    error_message: Optional[str]
    generation_started_at: Optional[datetime]
    generation_completed_at: Optional[datetime]
    created_at: datetime
    confirmed_at: Optional[datetime]
