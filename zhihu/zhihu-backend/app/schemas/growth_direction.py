from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FutureTargetCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    target_type: Literal["role", "job_family", "level", "transition", "other"]
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    source_label: Optional[str] = Field(default=None, max_length=300)
    target_date: Optional[date] = None


class FutureTargetConfirm(BaseModel):
    expected_version: int = Field(ge=1)


class FutureTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supersedes_target_id: Optional[int] = None
    request_id: str
    target_type: str
    title: str
    description: Optional[str] = None
    source_label: Optional[str] = None
    target_date: Optional[date] = None
    status: Literal["draft", "active", "paused", "completed", "superseded"]
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime


class MarketSignalRefresh(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    target_id: int = Field(ge=1)
    limit: int = Field(default=8, ge=1, le=20)


class MarketSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    target_id: int
    skill_name: str
    occurrence_count: int
    share: Optional[float] = None
    direction: Literal["rising", "stable", "declining", "unknown"]
    availability: Literal["available", "insufficient_sample", "stale", "unavailable"]
    data_mode: str
    quality_grade: Literal["A", "B", "C", "insufficient"]
    sample_size: int
    methodology_version: str
    sources: list[dict[str, Any]]
    calculated_at: datetime
    limitation: Optional[str] = None
    status: Literal["active", "weak", "expired", "rejected"]


class MarketRefreshResponse(BaseModel):
    availability: Literal["available", "insufficient_sample", "stale", "unavailable"]
    data_mode: str
    sample_size: int
    quality_grade: Literal["A", "B", "C", "insufficient"]
    calculated_at: datetime
    signals: list[MarketSignalResponse]
    note: Optional[str] = None


class GapSnapshotCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    target_id: int = Field(ge=1)


class GapSnapshotConfirm(BaseModel):
    expected_version: int = Field(ge=1)


class GapSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    target_id: int
    request_id: str
    version: int
    market_signal_ids: list[int]
    career_chip_refs: list[dict[str, Any]]
    matched_items: list[str]
    gap_items: list[str]
    unknown_items: list[str]
    quality: Literal["strong", "limited", "insufficient", "stale"]
    confidence: float
    limitation: Optional[str] = None
    status: Literal["candidate", "confirmed", "superseded"]
    confirmed_at: Optional[datetime] = None
    created_at: datetime


class MilestoneCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    target_id: int = Field(ge=1)
    gap_snapshot_id: Optional[int] = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=300)
    success_criteria: str = Field(min_length=1, max_length=5000)
    timeframe: Literal["30d", "60d", "90d", "quarter", "custom"] = "custom"
    due_on: Optional[date] = None

    @model_validator(mode="after")
    def validate_custom_due(self):
        if self.timeframe == "custom" and self.due_on is None:
            raise ValueError("自定义里程碑需要截止日期")
        return self


class MilestoneUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["confirmed", "in_progress", "completed", "cancelled"]


class MilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supersedes_milestone_id: Optional[int] = None
    target_id: int
    gap_snapshot_id: Optional[int] = None
    request_id: str
    title: str
    success_criteria: str
    timeframe: Literal["30d", "60d", "90d", "quarter", "custom"]
    due_on: Optional[date] = None
    status: Literal["proposed", "confirmed", "in_progress", "completed", "cancelled", "superseded"]
    version: int
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DirectionWorkspace(BaseModel):
    targets: list[FutureTargetResponse]
    current_target: Optional[FutureTargetResponse] = None
    market_signals: list[MarketSignalResponse]
    gap_snapshots: list[GapSnapshotResponse]
    milestones: list[MilestoneResponse]
    confirmed_skill_names: list[str]
    career_chip_count: int
    summary: dict[str, int]


class MilestoneActionProposal(BaseModel):
    milestone_id: int
    intake_id: int
    candidate_key: str
    title: str
    status: Literal["draft"] = "draft"
    note: str
