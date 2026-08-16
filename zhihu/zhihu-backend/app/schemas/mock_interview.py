from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MockInterviewStartRequest(BaseModel):
    practice_type: Literal["full_interview", "self_introduction"] = "full_interview"
    interview_type: Literal["comprehensive", "technical", "project", "hr"] = "comprehensive"
    difficulty: Literal["supportive", "standard", "challenging"] = "standard"
    planned_duration_minutes: int = Field(default=15, ge=5, le=45)
    target_duration_seconds: Optional[int] = Field(default=None, ge=30, le=180)


class MockInterviewSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_target_id: int
    resume_version_id: Optional[int]
    status: Literal["preparing", "active", "reviewing", "completed", "cancelled", "failed"]
    practice_type: str
    rubric_version: str
    interview_type: str
    difficulty: str
    planned_duration_minutes: int
    target_duration_seconds: Optional[int]
    model: str
    voice_id: str
    agent_name: str
    summary: Optional[str]
    report: dict
    transcript: list[dict] = Field(default_factory=list)
    error_message: Optional[str]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    turn_count: int
    created_at: datetime
    updated_at: datetime
    job_snapshot: dict = Field(default_factory=dict)
    resume_display_name: Optional[str] = None


class MockInterviewStartResponse(BaseModel):
    session: MockInterviewSessionResponse
    realtime_ticket: str
    websocket_path: str
