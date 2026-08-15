from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResumeVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    display_name: str
    original_filename: Optional[str] = None
    attachment_version_id: Optional[int] = None
    extracted_skills: list[str]
    parse_mode: str
    profile_parse_mode: str
    profile_parse_model: Optional[str] = None
    profile_parsed_at: Optional[datetime] = None
    profile_summary: str
    has_original_file: bool
    is_active: bool
    text_length: int
    created_at: datetime


class ResumeVersionDetailResponse(ResumeVersionResponse):
    content_text: str
    structured_profile: dict


class ResumePasteRequest(BaseModel):
    display_name: str = Field(default="粘贴简历", min_length=1, max_length=200)
    text: str = Field(min_length=50, max_length=100_000)


class OpportunityGuardRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    resume_version_id: int = Field(gt=0)
    force_refresh: bool = False


class OpportunityGuardResponse(BaseModel):
    event_id: int
    analysis_id: int
    analysis_mode: Literal["ai", "rules"]
    match_score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    strengths: list[str]
    risks: list[str]
    suggestions: list[str]
    summary: str
    reused: bool = False
