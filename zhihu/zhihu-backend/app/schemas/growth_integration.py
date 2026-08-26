from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceType = Literal["work_event", "portfolio", "evidence", "skill", "target", "gap", "milestone"]
CommunicationSourceType = Literal["work_item", "work_event", "portfolio", "evidence", "skill", "target", "gap", "milestone"]
TargetDomain = Literal["opportunity", "decision", "rights", "income", "resume"]


class GrowthSourceRef(BaseModel):
    source_type: CommunicationSourceType
    source_id: int = Field(ge=1)


class CommunicationDraftCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    audience: str = Field(min_length=1, max_length=200)
    scene: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=500)
    known_facts: list[str] = Field(min_length=1, max_length=30)
    tone: str = Field(default="专业、克制", min_length=1, max_length=100)
    source_refs: list[GrowthSourceRef] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_facts(self):
        if any(not item.strip() for item in self.known_facts):
            raise ValueError("已知事实不能包含空项")
        unique_refs = {(item.source_type, item.source_id) for item in self.source_refs}
        if len(unique_refs) != len(self.source_refs):
            raise ValueError("同一来源不能重复引用")
        return self


class CommunicationDraftRevise(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    expected_version: int = Field(ge=1)
    edited_content: str = Field(min_length=1, max_length=20000)
    status: Literal["draft", "reviewed", "exported", "archived"] = "draft"


class CommunicationDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supersedes_draft_id: Optional[int] = None
    request_id: str
    version: int
    audience: str
    scene: str
    goal: str
    known_facts: list[str]
    tone: str
    fact_questions: list[str]
    strategies: list[str]
    risk_notes: list[str]
    source_refs: list[dict[str, Any]]
    data_scope: list[str]
    generated_content: str
    edited_content: Optional[str] = None
    analysis_mode: Literal["rules", "ai"]
    provider_name: Optional[str] = None
    model: Optional[str] = None
    status: Literal["draft", "reviewed", "exported", "archived", "superseded"]
    reviewed_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    created_at: datetime


class HandoffCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    target_domain: TargetDomain
    source_type: SourceType
    source_id: int = Field(ge=1)


class HandoffTransition(BaseModel):
    expected_version: int = Field(ge=1)


class HandoffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    target_domain: TargetDomain
    source_type: SourceType
    source_id: int
    title: str
    content_summary: str
    evidence_refs: list[dict[str, Any]]
    impact_summary: str
    status: Literal["proposed", "confirmed", "revoked"]
    version: int
    confirmed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class HandoffSourceOption(BaseModel):
    source_type: SourceType
    source_id: int
    title: str
    source_label: str


class GrowthIntegrationWorkspace(BaseModel):
    communication_drafts: list[CommunicationDraftResponse]
    handoff_sources: list[HandoffSourceOption]
    handoff_proposals: list[HandoffResponse]
    handoff_inbox: list[HandoffResponse]
    summary: dict[str, int]
    safety_note: str


class GrowthFullExport(BaseModel):
    generated_at: datetime
    scope: Literal["user_confirmed_growth_records"] = "user_confirmed_growth_records"
    work: dict[str, list[dict[str, Any]]]
    materials: dict[str, list[dict[str, Any]]]
    assets: dict[str, list[dict[str, Any]]]
    direction: dict[str, list[dict[str, Any]]]
    communication: dict[str, list[dict[str, Any]]]
    handoffs: list[dict[str, Any]]
    exclusions: list[str]


class GrowthInquiryRequest(BaseModel):
    request_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,79}$")
    question: str = Field(min_length=1, max_length=500)
    data_scopes: list[Literal["current_work", "past_assets", "future_direction", "market_signals"]] = Field(min_length=1, max_length=4)
    use_ai: bool = False
    allow_external_processing: bool = False

    @model_validator(mode="after")
    def validate_external_processing(self):
        if len(set(self.data_scopes)) != len(self.data_scopes):
            raise ValueError("同一数据域不能重复选择")
        if self.use_ai and not self.allow_external_processing:
            raise ValueError("使用 AI 问询前必须明确允许发送脱敏后的最小上下文")
        if not self.use_ai and self.allow_external_processing:
            raise ValueError("未使用 AI 时无需授权外部处理")
        self.question = self.question.strip()
        return self


class GrowthInquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    question: str
    answer: str
    mode: Literal["program", "ai"]
    data_scopes: list[str]
    evidence_refs: list[dict[str, Any]]
    follow_up_questions: list[str]
    provider_name: Optional[str] = None
    model: Optional[str] = None
    status: Literal["completed", "failed"]
    created_at: datetime
