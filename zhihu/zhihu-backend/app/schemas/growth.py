from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


ImpactLevel = Literal["high", "medium", "low", "unknown"]
EnergyLevel = Literal["high", "medium", "low", "unknown"]
WorkItemStatus = Literal[
    "captured",
    "planned",
    "in_progress",
    "blocked",
    "completed",
    "deferred",
    "cancelled",
]
WorkEventStatus = Literal[
    "captured",
    "structured",
    "confirmed",
    "needs_more_evidence",
    "discarded",
    "archived",
]


class GrowthWorkCandidate(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: ImpactLevel = "unknown"
    energy_level: EnergyLevel = "unknown"
    priority_order: int = Field(default=100, ge=1, le=1000)
    selection_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)


class GrowthEmotionCandidate(BaseModel):
    detected: bool = False
    summary: Optional[str] = Field(default=None, max_length=500)
    deidentified_fact: Optional[str] = Field(default=None, max_length=1000)


class GrowthAnalyzeRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    text: str = Field(min_length=5, max_length=4000)
    use_ai: bool = False
    allow_external_processing: bool = False

    @model_validator(mode="after")
    def validate_external_processing(self):
        if self.use_ai and not self.allow_external_processing:
            raise ValueError("使用 AI 整理前必须明确允许发送脱敏后的最小文本")
        return self


class GrowthAnalyzeResponse(BaseModel):
    intake_id: int
    request_id: str
    status: Literal["draft", "confirmed", "cancelled"]
    analysis_mode: Literal["rules", "ai"]
    parser_version: str
    provider_name: Optional[str] = None
    model: Optional[str] = None
    candidates: list[GrowthWorkCandidate]
    emotion: GrowthEmotionCandidate
    original_text_persisted: bool = False
    privacy_notice: str


class GrowthConfirmCandidate(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=80)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: Optional[ImpactLevel] = None
    energy_level: Optional[EnergyLevel] = None
    due_at: Optional[datetime] = None
    reportable: bool = False


class GrowthConfirmIntakeRequest(BaseModel):
    selected: list[GrowthConfirmCandidate] = Field(min_length=1, max_length=3)
    retain_emotion: bool = False
    emotion_text: Optional[str] = Field(default=None, max_length=2000)
    deidentified_fact: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_selection(self):
        keys = [item.candidate_key for item in self.selected]
        if len(set(keys)) != len(keys):
            raise ValueError("同一个候选不能重复确认")
        if self.retain_emotion and not (self.emotion_text or "").strip():
            raise ValueError("选择保留情绪记录时必须提供要保留的原始内容")
        if not self.retain_emotion and self.emotion_text is not None:
            raise ValueError("未选择保留情绪时不能提交原始情绪内容")
        return self


class GrowthWorkItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intake_id: int
    career_event_id: Optional[int] = None
    candidate_key: str
    title: str
    description: Optional[str] = None
    fact_excerpt: Optional[str] = None
    impact_level: ImpactLevel
    energy_level: EnergyLevel
    priority_order: int
    selection_reason: Optional[str] = None
    status: WorkItemStatus
    due_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    reportable: bool
    version: int
    confirmed_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    situation: Optional[str] = None
    task: str
    action: Optional[str] = None
    result: Optional[str] = None
    role: Optional[str] = None
    occurred_on: date
    status: WorkEventStatus
    visibility: Literal["private", "reportable", "career_asset"]
    reportable: bool
    evidence_gaps: list[str]
    version: int
    confirmed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthConfirmIntakeResponse(BaseModel):
    intake_id: int
    status: Literal["confirmed"]
    work_items: list[GrowthWorkItemResponse]
    emotion_retained: bool


class GrowthUpdateWorkItemRequest(BaseModel):
    status: WorkItemStatus
    expected_version: int = Field(ge=1)
    result_summary: Optional[str] = Field(default=None, max_length=4000)
    reportable: Optional[bool] = None

    @model_validator(mode="after")
    def validate_completion(self):
        if self.status == "completed" and not (self.result_summary or "").strip():
            raise ValueError("完成工作项时必须记录结果")
        return self


class GrowthUpdateWorkItemResponse(BaseModel):
    work_item: GrowthWorkItemResponse
    event_candidate: Optional[GrowthWorkEventResponse] = None


class GrowthUpdateWorkEventRequest(BaseModel):
    status: Literal["confirmed", "needs_more_evidence", "discarded", "archived"]
    expected_version: int = Field(ge=1)
    situation: Optional[str] = Field(default=None, max_length=4000)
    task: Optional[str] = Field(default=None, max_length=4000)
    action: Optional[str] = Field(default=None, max_length=4000)
    result: Optional[str] = Field(default=None, max_length=4000)
    role: Optional[str] = Field(default=None, max_length=200)
    visibility: Optional[Literal["private", "reportable", "career_asset"]] = None
    reportable: Optional[bool] = None


class GrowthWeeklyReportCreate(BaseModel):
    week_start: date
    event_ids: list[int] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_week_start(self):
        if self.week_start.weekday() != 0:
            raise ValueError("周报开始日期必须是星期一")
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError("周报不能重复引用同一事件")
        return self


class GrowthWeeklyReportUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["draft", "reviewed", "exported", "archived"]
    edited_content: Optional[str] = Field(default=None, max_length=20000)


class GrowthWeeklyReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_start: date
    version: int
    status: Literal["draft", "reviewed", "exported", "archived"]
    included_event_ids: list[int]
    generated_content: str
    edited_content: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    exported_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthEmotionNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deidentified_fact: Optional[str] = None
    privacy_level: Literal["private", "private_deidentified"]
    created_at: datetime


class GrowthWorkspaceResponse(BaseModel):
    active_items: list[GrowthWorkItemResponse]
    recent_event_candidates: list[GrowthWorkEventResponse]
    confirmed_reportable_events: list[GrowthWorkEventResponse]
    recent_reports: list[GrowthWeeklyReportResponse]
    private_emotion_notes: list[GrowthEmotionNoteResponse]
    summary: str
    attention_count: int
