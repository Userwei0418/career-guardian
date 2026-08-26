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
GrowthWorkUpdateKind = Literal[
    "auto",
    "context",
    "progress",
    "blocker",
    "next_action",
    "result",
]
StoredGrowthWorkUpdateKind = Literal[
    "context",
    "progress",
    "blocker",
    "next_action",
    "result",
]
WorkNodeStatus = Literal["planned", "in_progress", "blocked", "completed", "cancelled"]
WorkNodeSource = Literal["intake", "manual", "work_update"]
GrowthMaterialType = Literal["meeting_minutes", "transcript", "note", "proposal", "plan", "other"]
GrowthMaterialStatementType = Literal[
    "confirmed_fact",
    "decision",
    "proposal",
    "open_question",
    "vendor_claim",
    "scope_change",
    "action",
    "conflict",
]
GrowthMaterialDecisionStatus = Literal["suggested", "confirmed", "dismissed"]
GrowthMaterialRelationType = Literal["derived_from", "same_event_version", "supersedes", "references"]
GrowthPriorityAxis = Literal["high", "low", "unknown"]
GrowthProgressHealth = Literal["healthy", "at_risk", "unknown"]
GrowthQuadrant = Literal["focus", "breakthrough", "maintain", "clarify", "unknown"]
GrowthOccurredAtPrecision = Literal["unknown", "date", "datetime"]
GrowthProgressImpact = Literal[
    "advanced",
    "setback",
    "redirected",
    "context",
    "no_change",
    "unknown",
]


class GrowthResourceLink(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    label: Optional[str] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_url(self):
        if not self.url.startswith(("https://", "http://")):
            raise ValueError("资料链接必须使用 http 或 https")
        return self


class GrowthWorkNodeCandidate(BaseModel):
    node_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    priority_order: int = Field(default=100, ge=1, le=1000)
    depends_on_node_keys: list[str] = Field(default_factory=list, max_length=50)
    time_hint: Optional[str] = Field(default=None, max_length=200)


class GrowthNodeSuggestion(BaseModel):
    action: Literal["create", "update"] = "create"
    title: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=500)
    node_id: Optional[int] = None
    proposed_status: Optional[WorkNodeStatus] = None


class GrowthWorkCandidate(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    account_name: Optional[str] = Field(default=None, max_length=200)
    objective: Optional[str] = Field(default=None, max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=30)
    strategy_summary: Optional[str] = Field(default=None, max_length=4000)
    key_constraints: list[str] = Field(default_factory=list, max_length=30)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = Field(default=14, ge=1, le=365)
    description: Optional[str] = Field(default=None, max_length=20000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: ImpactLevel = "unknown"
    energy_level: EnergyLevel = "unknown"
    priority_order: int = Field(default=100, ge=1, le=1000)
    selection_reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(default=0.5, ge=0, le=1)
    nodes: list[GrowthWorkNodeCandidate] = Field(default_factory=list, max_length=50)
    resource_links: list[GrowthResourceLink] = Field(default_factory=list, max_length=50)
    open_questions: list[str] = Field(default_factory=list, max_length=50)
    tracking_rule: Optional[str] = Field(default=None, max_length=500)


class GrowthEmotionCandidate(BaseModel):
    detected: bool = False
    summary: Optional[str] = Field(default=None, max_length=500)
    deidentified_fact: Optional[str] = Field(default=None, max_length=1000)


class GrowthAnalyzeRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    text: str = Field(min_length=1, max_length=20000)
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


class GrowthWorkInboxAnalyzeRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    content: str = Field(min_length=1, max_length=20000)
    kind: GrowthWorkUpdateKind = "auto"


class GrowthWorkInboxRoutingCandidate(BaseModel):
    work_item_id: int
    work_item_title: str
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_node_ids: list[int]


class GrowthWorkInboxAnalyzeResponse(BaseModel):
    request_id: str
    routing_candidates: list[GrowthWorkInboxRoutingCandidate]
    analysis_mode: Literal["rules"] = "rules"
    rule_version: str
    persisted: Literal[False] = False


class GrowthConfirmCandidate(BaseModel):
    candidate_key: str = Field(min_length=1, max_length=80)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    account_name: Optional[str] = Field(default=None, max_length=200)
    objective: Optional[str] = Field(default=None, max_length=4000)
    success_criteria: Optional[list[str]] = Field(default=None, max_length=30)
    strategy_summary: Optional[str] = Field(default=None, max_length=4000)
    key_constraints: Optional[list[str]] = Field(default=None, max_length=30)
    description: Optional[str] = Field(default=None, max_length=20000)
    fact_excerpt: Optional[str] = Field(default=None, max_length=500)
    impact_level: Optional[ImpactLevel] = None
    energy_level: Optional[EnergyLevel] = None
    due_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: Optional[int] = Field(default=None, ge=1, le=365)
    reportable: bool = False
    nodes: Optional[list[GrowthWorkNodeCandidate]] = Field(default=None, max_length=50)
    resource_links: Optional[list[GrowthResourceLink]] = Field(default=None, max_length=50)
    open_questions: Optional[list[str]] = Field(default=None, max_length=50)
    tracking_rule: Optional[str] = Field(default=None, max_length=500)


class GrowthConfirmIntakeRequest(BaseModel):
    selected: list[GrowthConfirmCandidate] = Field(min_length=1, max_length=50)
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
    account_name: Optional[str] = None
    objective: Optional[str] = None
    success_criteria: list[str] = Field(default_factory=list)
    strategy_summary: Optional[str] = None
    key_constraints: list[str] = Field(default_factory=list)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = 14
    description: Optional[str] = None
    fact_excerpt: Optional[str] = None
    impact_level: ImpactLevel
    energy_level: EnergyLevel
    priority_order: int
    selection_reason: Optional[str] = None
    resource_links: Optional[list[GrowthResourceLink]] = None
    open_questions: Optional[list[str]] = None
    tracking_rule: Optional[str] = None
    status: WorkItemStatus
    due_at: Optional[datetime] = None
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = 14
    progress_summary: Optional[str] = None
    blocker_note: Optional[str] = None
    next_action: Optional[str] = None
    result_summary: Optional[str] = None
    reportable: bool
    priority_axis: GrowthPriorityAxis = "unknown"
    progress_health: GrowthProgressHealth = "unknown"
    quadrant: GrowthQuadrant = "unknown"
    placement_rule_version: Optional[str] = None
    placement_updated_at: Optional[datetime] = None
    version: int
    confirmed_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkUpdateCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    content: str = Field(min_length=1, max_length=20000)
    kind: GrowthWorkUpdateKind = "auto"


class GrowthWorkUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    request_id: str
    content: str
    kind: StoredGrowthWorkUpdateKind
    assistant_summary: str
    suggestions: list[str]
    star_hints: list[str]
    node_suggestions: list[GrowthNodeSuggestion] = Field(default_factory=list)
    created_at: datetime


class GrowthWorkNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    node_key: str
    title: str
    status: WorkNodeStatus
    priority_order: int
    depends_on_node_keys: list[str]
    time_hint: Optional[str] = None
    version: int
    source: WorkNodeSource
    source_update_id: Optional[int] = None
    confirmed_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkNodeCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    title: str = Field(min_length=1, max_length=300)
    priority_order: int = Field(default=100, ge=1, le=1000)
    depends_on_node_keys: list[str] = Field(default_factory=list, max_length=50)
    time_hint: Optional[str] = Field(default=None, max_length=200)
    source_update_id: Optional[int] = None
    confirmed: Literal[True]


class GrowthWorkNodeUpdate(BaseModel):
    status: WorkNodeStatus
    expected_version: int = Field(ge=1)
    source_update_id: Optional[int] = None
    confirmed: Literal[True]


class GrowthWorkNodeEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: int
    work_update_id: int
    relation_kind: Literal["context", "progress", "blocker", "completion"]
    evidence_excerpt: str
    analysis_summary: str
    confidence: float
    status: Literal["suggested", "confirmed", "dismissed"]
    analysis_mode: Literal["rules", "ai"]
    rule_version: str
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime


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
    work_nodes: list[GrowthWorkNodeResponse] = Field(default_factory=list)
    emotion_retained: bool


class GrowthUpdateWorkItemRequest(BaseModel):
    status: WorkItemStatus
    expected_version: int = Field(ge=1)
    result_summary: Optional[str] = Field(default=None, max_length=4000)
    progress_summary: Optional[str] = Field(default=None, max_length=4000)
    blocker_note: Optional[str] = Field(default=None, max_length=4000)
    next_action: Optional[str] = Field(default=None, max_length=4000)
    reportable: Optional[bool] = None

    @model_validator(mode="after")
    def validate_blocker(self):
        if self.status == "blocked" and self.blocker_note is not None and not self.blocker_note.strip():
            raise ValueError("记录阻塞时请说明当前卡点")
        return self


class GrowthTaskCommunicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    audience: str
    scene: str
    goal: str
    generated_content: str
    edited_content: Optional[str] = None
    fact_questions: list[str]
    strategies: list[str]
    risk_notes: list[str]
    source_refs: list[dict]
    status: Literal["draft", "reviewed", "exported", "archived", "superseded"]
    created_at: datetime


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


class GrowthMaterialRelationInput(BaseModel):
    material_id: int = Field(ge=1)
    relation_type: GrowthMaterialRelationType
    reason: Optional[str] = Field(default=None, max_length=1000)


class GrowthWorkMaterialCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    material_type: GrowthMaterialType
    title: Optional[str] = Field(default=None, max_length=300)
    account_name: Optional[str] = Field(default=None, max_length=200)
    project_id: Optional[int] = Field(default=None, ge=1)
    content: str = Field(min_length=1, max_length=500000)
    occurred_at: Optional[datetime] = None
    occurred_at_precision: GrowthOccurredAtPrecision = "unknown"
    next_follow_up_at: Optional[datetime] = None
    source_document_id: Optional[str] = Field(default=None, max_length=500)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    related_materials: list[GrowthMaterialRelationInput] = Field(default_factory=list, max_length=50)
    candidate_work_item_ids: list[int] = Field(default_factory=list, max_length=50)
    candidate_node_ids: list[int] = Field(default_factory=list, max_length=100)
    # Retained for backward-compatible clients. Material analysis is an AI-led
    # product capability and the service always attempts the configured model;
    # the UI must not ask users to choose an implementation mode.
    use_ai: bool = True
    allow_external_processing: bool = True

    @model_validator(mode="after")
    def validate_material(self):
        if not self.content.strip():
            raise ValueError("材料原文不能为空")
        if self.occurred_at is None and self.occurred_at_precision != "unknown":
            raise ValueError("未提供真实发生时间时，时间精度必须为 unknown")
        if self.occurred_at is not None and self.occurred_at_precision == "unknown":
            raise ValueError("提供真实发生时间时，必须明确说明只知日期还是知道具体时间")
        if self.source_url and not self.source_url.startswith(("https://", "http://")):
            raise ValueError("来源链接必须使用 http 或 https")
        if len(set(self.candidate_work_item_ids)) != len(self.candidate_work_item_ids):
            raise ValueError("候选工作项不能重复")
        if len(set(self.candidate_node_ids)) != len(self.candidate_node_ids):
            raise ValueError("候选节点不能重复")
        relation_keys = [(item.material_id, item.relation_type) for item in self.related_materials]
        if len(set(relation_keys)) != len(relation_keys):
            raise ValueError("同一材料关系不能重复")
        return self


class GrowthMaterialEvidenceSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    excerpt: str
    statement_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.end < self.start:
            raise ValueError("证据范围结束位置不能早于开始位置")
        return self


class GrowthWorkMaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_type: GrowthMaterialType
    title: Optional[str] = None
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    content: str
    content_hash: str
    occurred_at: Optional[datetime] = None
    occurred_at_known: bool
    occurred_at_precision: GrowthOccurredAtPrecision
    next_follow_up_at: Optional[datetime] = None
    source_document_id: Optional[str] = None
    source_url: Optional[str] = None
    analysis_mode: Literal["rules", "ai"]
    analysis_rule_version: str
    ai_requested: bool
    external_processing_used: bool
    provider_name: Optional[str] = None
    model: Optional[str] = None
    fallback_reason: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime


class GrowthWorkMaterialSummaryResponse(BaseModel):
    id: int
    material_type: GrowthMaterialType
    title: Optional[str] = None
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    content_hash: str
    occurred_at: Optional[datetime] = None
    occurred_at_known: bool
    occurred_at_precision: GrowthOccurredAtPrecision
    next_follow_up_at: Optional[datetime] = None
    source_document_id: Optional[str] = None
    source_url: Optional[str] = None
    analysis_mode: Literal["rules", "ai"]
    fallback_reason: Optional[str] = None
    version: int
    created_at: datetime
    updated_at: datetime


class GrowthWorkMaterialListItem(GrowthWorkMaterialSummaryResponse):
    status: Literal["unassigned", "suggested", "confirmed", "dismissed", "mixed"]
    unassigned: bool
    suggested_link_count: int = Field(ge=0)
    confirmed_link_count: int = Field(ge=0)
    dismissed_link_count: int = Field(ge=0)


class GrowthWorkMaterialListResponse(BaseModel):
    items: list[GrowthWorkMaterialListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class GrowthBulkCleanupRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    confirmed: Literal[True]


class GrowthBulkCleanupSkippedItem(BaseModel):
    id: int = Field(ge=1)
    title: str
    reason: str


class GrowthBulkCleanupResponse(BaseModel):
    ok: bool = True
    deleted_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped: list[GrowthBulkCleanupSkippedItem] = Field(default_factory=list)


class GrowthWorkMaterialStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    statement_key: str
    statement_type: GrowthMaterialStatementType
    text: str
    # List/board/timeline payloads omit raw evidence. It is populated only by
    # the explicit material-detail endpoint after the user opens "查看依据".
    evidence_excerpt: Optional[str] = None
    confidence: float
    status: GrowthMaterialDecisionStatus
    analysis_mode: Literal["rules", "ai"]
    rule_version: str
    version: int
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkMaterialLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    target_type: Literal["work_item", "node"]
    target_id: int
    work_item_id: int
    work_item_title: str
    node_id: Optional[int] = None
    node_title: Optional[str] = None
    link_type: Literal[
        "confirmed_fact",
        "decision",
        "proposal",
        "open_question",
        "vendor_claim",
        "scope_change",
        "action",
        "conflict",
        "context",
    ]
    confidence: float
    reason: str
    evidence_spans: list[GrowthMaterialEvidenceSpan]
    proposed_node_status: Optional[WorkNodeStatus] = None
    status: GrowthMaterialDecisionStatus
    analysis_mode: Literal["rules", "ai"]
    rule_version: str
    version: int
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkMaterialRelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    related_material_id: int
    relation_type: GrowthMaterialRelationType
    reason: Optional[str] = None
    created_at: datetime


class GrowthWorkPlacementEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    work_item_title: str
    material_id: int
    priority_axis: GrowthPriorityAxis
    progress_health: GrowthProgressHealth
    quadrant: GrowthQuadrant
    confidence: float
    reason: str
    evidence_spans: list[GrowthMaterialEvidenceSpan]
    rule_version: str
    analysis_mode: Literal["rules", "ai"]
    base_work_item_version: int
    status: GrowthMaterialDecisionStatus
    version: int
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkProgressEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_item_id: int
    material_id: int
    # Event time always comes from the user-owned material occurrence.  It is
    # deliberately nullable: created_at is audit time and must never be shown
    # as if it were the meeting/progress time.
    occurred_at: Optional[datetime] = None
    occurred_at_precision: GrowthOccurredAtPrecision = "unknown"
    material_title: Optional[str] = None
    impact_kind: GrowthProgressImpact
    headline: str
    causal_reason: str
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    next_gap: Optional[str] = None
    evidence_spans: list[GrowthMaterialEvidenceSpan]
    confidence: float
    status: GrowthMaterialDecisionStatus
    analysis_mode: Literal["rules", "ai"]
    rule_version: str
    base_work_item_version: int
    reportable: bool
    version: int
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthWorkProgressEventReview(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    status: Literal["confirmed", "dismissed"]
    override_impact_kind: Optional[GrowthProgressImpact] = None
    override_headline: Optional[str] = Field(default=None, min_length=1, max_length=500)
    override_causal_reason: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    override_previous_state: Optional[str] = Field(default=None, max_length=4000)
    override_current_state: Optional[str] = Field(default=None, max_length=4000)
    override_next_gap: Optional[str] = Field(default=None, max_length=4000)
    reportable: bool = False
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_override(self):
        has_override = any(
            value is not None
            for value in (
                self.override_impact_kind,
                self.override_headline,
                self.override_causal_reason,
                self.override_previous_state,
                self.override_current_state,
                self.override_next_gap,
            )
        )
        if has_override and self.status != "confirmed":
            raise ValueError("只有确认进展判断时才能人工纠正内容")
        if has_override and not (self.reason or "").strip():
            raise ValueError("人工纠正进展判断时必须说明理由")
        if self.reportable and self.status != "confirmed":
            raise ValueError("只有已确认的进展才能进入正式汇报")
        return self


class GrowthProjectProfileUpsert(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    account_name: str = Field(min_length=1, max_length=200)
    project_name: str = Field(min_length=1, max_length=200)
    expected_version: Optional[int] = Field(default=None, ge=1)
    objective: str = Field(min_length=1, max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=30)
    strategy_summary: Optional[str] = Field(default=None, max_length=4000)
    key_constraints: list[str] = Field(default_factory=list, max_length=30)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = Field(default=14, ge=1, le=365)
    reason: str = Field(min_length=2, max_length=1000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_profile(self):
        self.account_name = self.account_name.strip()
        self.project_name = self.project_name.strip()
        self.objective = self.objective.strip()
        self.reason = self.reason.strip()
        self.success_criteria = [value.strip() for value in self.success_criteria if value.strip()]
        self.key_constraints = [value.strip() for value in self.key_constraints if value.strip()]
        self.strategy_summary = (self.strategy_summary or "").strip() or None
        return self


class GrowthProjectProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_name: str
    project_name: str
    objective: Optional[str] = None
    success_criteria: list[str] = Field(default_factory=list)
    strategy_summary: Optional[str] = None
    key_constraints: list[str] = Field(default_factory=list)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = 14
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthProjectProgressEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    material_id: int
    occurred_at: Optional[datetime] = None
    occurred_at_precision: GrowthOccurredAtPrecision = "unknown"
    material_title: Optional[str] = None
    impact_kind: GrowthProgressImpact
    headline: str
    causal_reason: str
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    next_gap: Optional[str] = None
    evidence_spans: list[GrowthMaterialEvidenceSpan]
    confidence: float
    status: GrowthMaterialDecisionStatus
    analysis_mode: Literal["rules", "ai"]
    rule_version: str
    base_project_version: int
    base_confirmed_event_id: Optional[int] = None
    reportable: bool
    version: int
    confirmed_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class GrowthProjectProgressEventReview(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    status: Literal["confirmed", "dismissed"]
    override_impact_kind: Optional[GrowthProgressImpact] = None
    override_headline: Optional[str] = Field(default=None, min_length=1, max_length=500)
    override_causal_reason: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    override_previous_state: Optional[str] = Field(default=None, max_length=4000)
    override_current_state: Optional[str] = Field(default=None, max_length=4000)
    override_next_gap: Optional[str] = Field(default=None, max_length=4000)
    reportable: bool = False
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_override(self):
        has_override = any(
            value is not None
            for value in (
                self.override_impact_kind,
                self.override_headline,
                self.override_causal_reason,
                self.override_previous_state,
                self.override_current_state,
                self.override_next_gap,
            )
        )
        if has_override and self.status != "confirmed":
            raise ValueError("只有确认项目进展判断时才能人工纠正内容")
        if has_override and not (self.reason or "").strip():
            raise ValueError("人工纠正项目进展判断时必须说明理由")
        if self.reportable and self.status != "confirmed":
            raise ValueError("只有已确认的项目进展才能进入正式汇报")
        return self


class GrowthWorkMaterialDetailResponse(BaseModel):
    material: GrowthWorkMaterialResponse
    statements: list[GrowthWorkMaterialStatementResponse]
    links: list[GrowthWorkMaterialLinkResponse]
    relations: list[GrowthWorkMaterialRelationResponse]
    placement_events: list[GrowthWorkPlacementEventResponse]
    progress_events: list[GrowthWorkProgressEventResponse] = Field(default_factory=list)
    project_progress_events: list[GrowthProjectProgressEventResponse] = Field(default_factory=list)
    workstream_proposals: list["GrowthWorkstreamProposalBatchResponse"] = Field(
        default_factory=list
    )


class GrowthWorkstreamProposalCandidateResponse(GrowthWorkCandidate):
    priority_axis: GrowthPriorityAxis = "unknown"
    progress_health: GrowthProgressHealth = "unknown"
    quadrant: GrowthQuadrant = "unknown"
    placement_reason: str
    evidence_excerpt: str
    resolution_status: Literal["pending", "confirmed", "dismissed"] = "pending"


class GrowthWorkstreamProposalBatchResponse(BaseModel):
    intake_id: int
    source_material_id: int
    status: Literal["draft", "confirmed", "cancelled"]
    parser_version: str
    selection_policy: Literal["unselected_candidates_dismissed_on_confirm"] = (
        "unselected_candidates_dismissed_on_confirm"
    )
    candidates: list[GrowthWorkstreamProposalCandidateResponse]


class GrowthWorkMaterialReanalyze(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)


class GrowthWorkMaterialMetadataUpdate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    title: Optional[str] = Field(default=None, max_length=300)
    account_name: Optional[str] = Field(default=None, max_length=200)
    # Omitted means "leave the current project unchanged"; an explicit null
    # detaches the material.  The service uses model_fields_set to preserve
    # that distinction and validates ownership before assigning an id.
    project_id: Optional[int] = Field(default=None, ge=1)
    occurred_at: Optional[datetime] = None
    occurred_at_precision: GrowthOccurredAtPrecision = "unknown"
    next_follow_up_at: Optional[datetime] = None
    source_document_id: Optional[str] = Field(default=None, max_length=500)
    source_url: Optional[str] = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_metadata(self):
        if self.occurred_at is None and self.occurred_at_precision != "unknown":
            raise ValueError("未提供真实发生时间时，时间精度必须为 unknown")
        if self.occurred_at is not None and self.occurred_at_precision == "unknown":
            raise ValueError("提供真实发生时间时，必须明确说明只知日期还是知道具体时间")
        if self.source_url and not self.source_url.startswith(("https://", "http://")):
            raise ValueError("来源链接必须使用 http 或 https")
        return self


class GrowthWorkTrackingProfileUpdate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    account_name: Optional[str] = Field(default=None, max_length=200)
    project_id: Optional[int] = Field(default=None, ge=1)
    objective: Optional[str] = Field(default=None, max_length=4000)
    success_criteria: list[str] = Field(default_factory=list, max_length=30)
    strategy_summary: Optional[str] = Field(default=None, max_length=4000)
    key_constraints: list[str] = Field(default_factory=list, max_length=30)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = Field(default=14, ge=1, le=365)
    reason: str = Field(min_length=2, max_length=1000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_profile(self):
        self.reason = self.reason.strip()
        self.success_criteria = [value.strip() for value in self.success_criteria if value.strip()]
        self.key_constraints = [value.strip() for value in self.key_constraints if value.strip()]
        return self


class GrowthWorkMaterialWorkstreamsConfirm(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_material_version: int = Field(ge=1)
    intake_id: int = Field(ge=1)
    selected: list[GrowthConfirmCandidate] = Field(min_length=1, max_length=30)


class GrowthMaterialStatusDecision(BaseModel):
    expected_version: int = Field(ge=1)
    status: Literal["confirmed", "dismissed"]


class GrowthMaterialStatementDecision(GrowthMaterialStatusDecision):
    statement_id: int = Field(ge=1)


class GrowthMaterialLinkDecision(GrowthMaterialStatusDecision):
    link_id: int = Field(ge=1)


class GrowthMaterialManualLink(BaseModel):
    target_type: Literal["work_item", "node"]
    target_id: int = Field(ge=1)
    link_type: Literal[
        "confirmed_fact",
        "decision",
        "proposal",
        "open_question",
        "vendor_claim",
        "scope_change",
        "action",
        "conflict",
        "context",
    ] = "context"
    reason: str = Field(min_length=1, max_length=1000)
    evidence_excerpt: Optional[str] = Field(default=None, max_length=2000)


class GrowthPlacementDecision(GrowthMaterialStatusDecision):
    placement_event_id: int = Field(ge=1)
    expected_work_item_version: Optional[int] = Field(default=None, ge=1)
    override_priority_axis: Optional[GrowthPriorityAxis] = None
    override_progress_health: Optional[GrowthProgressHealth] = None
    override_reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_work_item_version(self):
        if self.status == "confirmed" and self.expected_work_item_version is None:
            raise ValueError("确认象限建议时必须提供工作项当前版本")
        overrides = (self.override_priority_axis, self.override_progress_health)
        if any(value is not None for value in overrides):
            if self.status != "confirmed" or not all(value is not None for value in overrides):
                raise ValueError("人工调整象限时必须同时确认两个轴")
            if not (self.override_reason or "").strip():
                raise ValueError("人工调整象限时必须说明理由")
        elif self.override_reason is not None:
            raise ValueError("未调整象限轴时不能单独提交覆盖理由")
        return self


class GrowthWorkMaterialConfirm(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    statement_decisions: list[GrowthMaterialStatementDecision] = Field(default_factory=list, max_length=200)
    link_decisions: list[GrowthMaterialLinkDecision] = Field(default_factory=list, max_length=200)
    manual_links: list[GrowthMaterialManualLink] = Field(default_factory=list, max_length=50)
    placement_decisions: list[GrowthPlacementDecision] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_decisions(self):
        if not (
            self.statement_decisions
            or self.link_decisions
            or self.manual_links
            or self.placement_decisions
        ):
            raise ValueError("至少需要确认或驳回一条建议")
        for values, attribute in (
            (self.statement_decisions, "statement_id"),
            (self.link_decisions, "link_id"),
            (self.placement_decisions, "placement_event_id"),
        ):
            ids = [getattr(item, attribute) for item in values]
            if len(set(ids)) != len(ids):
                raise ValueError("同一建议不能在一次请求中重复决策")
        manual_keys = [
            (item.target_type, item.target_id, item.link_type)
            for item in self.manual_links
        ]
        if len(set(manual_keys)) != len(manual_keys):
            raise ValueError("同一人工归属不能重复")
        return self


class GrowthWorkPlacementCurrent(BaseModel):
    priority_axis: GrowthPriorityAxis
    progress_health: GrowthProgressHealth
    quadrant: GrowthQuadrant
    rule_version: Optional[str] = None
    updated_at: Optional[datetime] = None


class GrowthWorkTrackingProfile(BaseModel):
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    objective: Optional[str] = None
    success_criteria: list[str] = Field(default_factory=list)
    strategy_summary: Optional[str] = None
    key_constraints: list[str] = Field(default_factory=list)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = 14


class GrowthWorkTimelineEntry(BaseModel):
    material: GrowthWorkMaterialSummaryResponse
    statements: list[GrowthWorkMaterialStatementResponse]
    links: list[GrowthWorkMaterialLinkResponse]
    relations: list[GrowthWorkMaterialRelationResponse]
    placement_events: list[GrowthWorkPlacementEventResponse]
    progress_events: list[GrowthWorkProgressEventResponse] = Field(default_factory=list)
    progress_event: Optional[GrowthWorkProgressEventResponse] = None


class GrowthWorkTimelineResponse(BaseModel):
    work_item_id: int
    title: str
    profile: GrowthWorkTrackingProfile
    current_placement: GrowthWorkPlacementCurrent
    last_activity_at: Optional[datetime] = None
    last_advancement_at: Optional[datetime] = None
    days_since_advancement: Optional[int] = Field(default=None, ge=0)
    stale: bool = False
    stale_reason: Optional[str] = None
    follow_up_overdue: bool = False
    entries: list[GrowthWorkTimelineEntry]


class GrowthWorkBoardItem(BaseModel):
    work_item_id: int
    title: str
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    objective: Optional[str] = None
    success_criteria: list[str] = Field(default_factory=list)
    strategy_summary: Optional[str] = None
    key_constraints: list[str] = Field(default_factory=list)
    next_follow_up_at: Optional[datetime] = None
    stale_after_days: int = 14
    status: WorkItemStatus
    priority_axis: GrowthPriorityAxis
    progress_health: GrowthProgressHealth
    quadrant: GrowthQuadrant
    version: int
    placement_rule_version: Optional[str] = None
    placement_updated_at: Optional[datetime] = None
    latest_progress_event: Optional[GrowthWorkProgressEventResponse] = None
    last_activity_at: Optional[datetime] = None
    last_advancement_at: Optional[datetime] = None
    days_since_advancement: Optional[int] = Field(default=None, ge=0)
    stale: bool = False
    stale_reason: Optional[str] = None
    follow_up_overdue: bool = False


class GrowthWorkPlacementUpdate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_version: int = Field(ge=1)
    priority_axis: GrowthPriorityAxis
    progress_health: GrowthProgressHealth
    reason: str = Field(min_length=2, max_length=1000)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def normalize_reason(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("人工调整象限时必须说明理由")
        return self


class GrowthWorkBoardQuadrant(BaseModel):
    key: GrowthQuadrant
    label: str
    items: list[GrowthWorkBoardItem]


class GrowthWorkAccountGroup(BaseModel):
    project_id: Optional[int] = None
    account_name: str
    project_name: str
    item_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    overdue_count: int = Field(ge=0)
    project: Optional[GrowthProjectProfileResponse] = None
    latest_project_progress_event: Optional[GrowthProjectProgressEventResponse] = None
    last_project_advancement_at: Optional[datetime] = None
    project_stale: bool = False
    project_stale_reason: Optional[str] = None
    project_follow_up_overdue: bool = False
    items: list[GrowthWorkBoardItem]


class GrowthProjectTimelineResponse(BaseModel):
    project: GrowthProjectProfileResponse
    latest_confirmed_event: Optional[GrowthProjectProgressEventResponse] = None
    latest_suggested_event: Optional[GrowthProjectProgressEventResponse] = None
    events: list[GrowthProjectProgressEventResponse]


class GrowthWorkBoardResponse(BaseModel):
    rule_version: str
    axes: dict[str, dict[str, str]]
    mapping: dict[str, str]
    quadrants: list[GrowthWorkBoardQuadrant]
    account_groups: list[GrowthWorkAccountGroup] = Field(default_factory=list)


class GrowthProgressReviewWorkItem(BaseModel):
    work_item_id: int
    title: str
    account_name: Optional[str] = None
    project_id: Optional[int] = None
    objective: Optional[str] = None
    events: list[GrowthWorkProgressEventResponse]


class GrowthProgressReviewAccountGroup(BaseModel):
    project_id: Optional[int] = None
    account_name: str
    project_name: str
    project: Optional[GrowthProjectProfileResponse] = None
    project_events: list[GrowthProjectProgressEventResponse] = Field(default_factory=list)
    items: list[GrowthProgressReviewWorkItem]


class GrowthProgressReviewResponse(BaseModel):
    period: Literal["week", "month"]
    period_start: date
    period_end: date
    account_name: Optional[str] = None
    account_groups: list[GrowthProgressReviewAccountGroup]
    undated_count: int = Field(ge=0)


class GrowthWorkspaceResponse(BaseModel):
    active_items: list[GrowthWorkItemResponse]
    cancelled_items: list[GrowthWorkItemResponse]
    work_nodes: list[GrowthWorkNodeResponse]
    node_evidence: list[GrowthWorkNodeEvidenceResponse]
    task_updates: list[GrowthWorkUpdateResponse]
    recent_event_candidates: list[GrowthWorkEventResponse]
    confirmed_reportable_events: list[GrowthWorkEventResponse]
    recent_reports: list[GrowthWeeklyReportResponse]
    private_emotion_notes: list[GrowthEmotionNoteResponse]
    task_communications: list[GrowthTaskCommunicationResponse]
    summary: str
    attention_count: int
