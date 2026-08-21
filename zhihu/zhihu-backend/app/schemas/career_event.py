from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


CareerEventType = Literal["opportunity", "decision", "rights", "income", "growth"]
CareerEventStatus = Literal["active", "attention", "completed", "archived"]
SourceType = Literal["user_material", "market_data", "calculation", "rule", "ai_assistance"]


class CareerEventCreate(BaseModel):
    event_type: CareerEventType
    title: str = Field(min_length=1, max_length=200)
    status: CareerEventStatus = "active"
    stage: Optional[str] = Field(default=None, max_length=30)
    deadline: Optional[datetime] = None


class CareerEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    legacy_case_id: Optional[int] = None
    event_type: CareerEventType
    title: str
    status: CareerEventStatus
    stage: Optional[str] = None
    deadline: Optional[datetime] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class CareerEventUpdate(BaseModel):
    status: CareerEventStatus


class EvidenceCreate(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=40)
    source_type: SourceType
    title: str = Field(min_length=1, max_length=200)
    content_excerpt: Optional[str] = None
    source_ref: Optional[str] = Field(default=None, max_length=500)
    extra_data: Optional[dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class EvidenceResponse(EvidenceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    created_at: datetime


class GuardianFindingCreate(BaseModel):
    evidence_id: Optional[int] = None
    domain: CareerEventType
    category: Optional[str] = Field(default=None, max_length=50)
    severity: Literal["info", "warning", "high"] = "info"
    status: Literal["open", "confirmed", "resolved", "dismissed"] = "open"
    title: str = Field(min_length=1, max_length=300)
    explanation: Optional[str] = None
    source_type: SourceType
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class GuardianFindingResponse(GuardianFindingCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    created_at: datetime


class GuardianFindingUpdate(BaseModel):
    status: Literal["open", "confirmed", "resolved", "dismissed"]


class ActionItemCreate(BaseModel):
    finding_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    status: Literal["draft", "pending", "completed", "dismissed"] = "pending"
    priority: int = Field(default=100, ge=0, le=1000)
    due_at: Optional[datetime] = None
    requires_confirmation: bool = True


class ActionItemResponse(ActionItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class ActionItemUpdate(BaseModel):
    status: Literal["draft", "pending", "completed", "dismissed"]
    confirm: bool = False


class DecisionRecordCreate(BaseModel):
    decision_type: str = Field(min_length=1, max_length=50)
    choice: str = Field(min_length=1, max_length=300)
    rationale: Optional[str] = None


class DecisionRecordResponse(DecisionRecordCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    offer_revision_id: Optional[int] = None
    analysis_snapshot_id: Optional[int] = None
    preflight_snapshot: Optional[dict] = None
    acknowledged_unknowns: bool = False
    decided_at: datetime


class OutcomeCreate(BaseModel):
    action_id: Optional[int] = None
    outcome_type: str = Field(min_length=1, max_length=50)
    result: str = Field(min_length=1)


class OutcomeResponse(OutcomeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    recorded_at: datetime


class CareerEventDetail(CareerEventResponse):
    evidence: list[EvidenceResponse] = Field(default_factory=list)
    findings: list[GuardianFindingResponse] = Field(default_factory=list)
    actions: list[ActionItemResponse] = Field(default_factory=list)
    decisions: list[DecisionRecordResponse] = Field(default_factory=list)
    outcomes: list[OutcomeResponse] = Field(default_factory=list)
