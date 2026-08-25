from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


PortfolioType = Literal["github", "project", "link", "design", "article", "speech", "certificate", "feedback", "attachment", "other"]
PrivacyLevel = Literal["private", "shared", "public"]
EvidenceType = Literal["project_result", "collaboration", "leadership", "customer_feedback", "public_work", "certificate", "method", "other"]
SkillLayer = Literal["market_signal", "ai_candidate", "user_claimed", "evidence_confirmed"]


class PortfolioCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    item_type: PortfolioType
    title: str = Field(min_length=1, max_length=300)
    summary: Optional[str] = Field(default=None, max_length=5000)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    source_label: Optional[str] = Field(default=None, max_length=300)
    source_work_event_id: Optional[int] = Field(default=None, ge=1)
    source_attachment_id: Optional[int] = Field(default=None, ge=1)
    occurred_on: Optional[date] = None
    privacy_level: PrivacyLevel = "private"

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_url and not self.source_url.startswith("https://"):
            raise ValueError("作品链接必须使用 HTTPS")
        if self.item_type == "attachment" and self.source_attachment_id is None:
            raise ValueError("附件作品必须选择本人已有的附件版本")
        return self


class PortfolioUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    summary: Optional[str] = Field(default=None, max_length=5000)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    source_label: Optional[str] = Field(default=None, max_length=300)
    occurred_on: Optional[date] = None
    privacy_level: Optional[PrivacyLevel] = None
    status: Literal["draft", "active", "unavailable", "archived"]
    unavailable_reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_status(self):
        if self.source_url and not self.source_url.startswith("https://"):
            raise ValueError("作品链接必须使用 HTTPS")
        if self.status == "unavailable" and not (self.unavailable_reason or "").strip():
            raise ValueError("标记不可用时必须说明原因")
        return self


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: str
    source_work_event_id: Optional[int] = None
    source_attachment_id: Optional[int] = None
    item_type: PortfolioType
    title: str
    summary: Optional[str] = None
    source_url: Optional[str] = None
    source_label: Optional[str] = None
    occurred_on: Optional[date] = None
    privacy_level: PrivacyLevel
    status: Literal["draft", "active", "unavailable", "archived"]
    unavailable_reason: Optional[str] = None
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    portfolio_item_id: Optional[int] = Field(default=None, ge=1)
    work_event_id: Optional[int] = Field(default=None, ge=1)
    evidence_type: EvidenceType
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=5000)
    source_label: Optional[str] = Field(default=None, max_length=300)
    occurred_on: Optional[date] = None
    role: Optional[str] = Field(default=None, max_length=200)
    result_type: Optional[str] = Field(default=None, max_length=100)
    privacy_level: PrivacyLevel = "private"

    @model_validator(mode="after")
    def validate_traceable_source(self):
        if self.portfolio_item_id is None and self.work_event_id is None and not (self.source_label or "").strip():
            raise ValueError("成长证据必须关联作品、工作事件或明确来源")
        return self


class EvidenceUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    summary: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    source_label: Optional[str] = Field(default=None, max_length=300)
    occurred_on: Optional[date] = None
    role: Optional[str] = Field(default=None, max_length=200)
    result_type: Optional[str] = Field(default=None, max_length=100)
    privacy_level: Optional[PrivacyLevel] = None
    status: Literal["candidate", "confirmed", "unavailable", "archived"]
    unavailable_reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_status(self):
        if self.status == "unavailable" and not (self.unavailable_reason or "").strip():
            raise ValueError("标记不可用时必须说明原因")
        return self


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_id: str
    portfolio_item_id: Optional[int] = None
    work_event_id: Optional[int] = None
    evidence_type: EvidenceType
    title: str
    summary: str
    source_label: Optional[str] = None
    occurred_on: Optional[date] = None
    role: Optional[str] = None
    result_type: Optional[str] = None
    privacy_level: PrivacyLevel
    status: Literal["candidate", "confirmed", "unavailable", "archived"]
    unavailable_reason: Optional[str] = None
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SkillCandidateCreate(BaseModel):
    skill_name: str = Field(min_length=1, max_length=160)
    source_layer: Literal["ai_candidate", "user_claimed"]
    evidence_ids: list[int] = Field(default_factory=list, max_length=50)
    user_note: Optional[str] = Field(default=None, max_length=3000)


class SkillConfirmRequest(BaseModel):
    expected_version: int = Field(ge=1)
    evidence_ids: list[int] = Field(default_factory=list, max_length=50)
    user_note: Optional[str] = Field(default=None, max_length=3000)


class SkillAssessmentResponse(BaseModel):
    id: int
    skill_name: str
    version: int
    source_layer: SkillLayer
    status: Literal["candidate", "confirmed", "rejected", "superseded", "archived"]
    evidence_sufficiency: Literal["none", "partial", "supported"]
    evidence_ids: list[int]
    evidence_count: int
    latest_used_on: Optional[date] = None
    user_note: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime


class ReflectionCreate(BaseModel):
    work_event_id: int = Field(ge=1)


class ReflectionUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    answer: str = Field(min_length=1, max_length=5000)
    privacy_level: Literal["private", "shared"] = "private"
    confirm_as_method: bool = False


class ReflectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    work_event_id: Optional[int] = None
    evidence_id: Optional[int] = None
    question: str
    answer: Optional[str] = None
    privacy_level: Literal["private", "shared"]
    status: Literal["prompted", "answered", "confirmed", "archived"]
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CareerChip(BaseModel):
    chip_type: Literal["work_event", "portfolio", "evidence", "skill"]
    title: str
    source_id: int
    source_label: str
    occurred_on: Optional[date] = None
    evidence_count: int = 0
    privacy_level: Optional[PrivacyLevel] = None


class AssetWorkEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task: str
    result: Optional[str] = None
    role: Optional[str] = None
    occurred_on: date
    visibility: Literal["private", "reportable", "career_asset"]


class GrowthAssetsWorkspace(BaseModel):
    available_work_events: list[AssetWorkEvent]
    portfolios: list[PortfolioResponse]
    evidences: list[EvidenceResponse]
    skills: list[SkillAssessmentResponse]
    reflections: list[ReflectionResponse]
    career_chips: list[CareerChip]
    summary: dict[str, int]


class GrowthAssetsExport(BaseModel):
    generated_at: datetime
    scope: Literal["confirmed_growth_assets"] = "confirmed_growth_assets"
    portfolios: list[PortfolioResponse]
    evidences: list[EvidenceResponse]
    skills: list[SkillAssessmentResponse]
    reflections: list[ReflectionResponse]
    note: str
