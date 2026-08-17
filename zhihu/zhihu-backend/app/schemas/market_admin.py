from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MarketCrawlTask(BaseModel):
    id: int
    task_uid: str
    source_code: str
    source_name: str
    adapter_type: str
    trigger_type: str
    collection_mode: str = "full"
    checkpoint_version: Optional[int] = None
    browser_mode: str = "headless"
    browser_mode_source: str = "channel_default"
    strategy_version: Optional[int] = None
    strategy_source: str = "runtime_discovery"
    status: str
    attempt_count: int
    records_seen: int
    records_stored: int
    duplicate_records: int
    failed_records: int
    promoted_records: int
    quarantined_records: int
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    batch_id: Optional[int] = None


class MarketDataSource(BaseModel):
    code: str
    name: str
    adapter_type: str
    base_url: str
    allowed_hosts: list[str]
    terms_review_status: str
    terms_reviewed_by: Optional[str] = None
    terms_reviewed_at: Optional[datetime] = None
    terms_review_note: Optional[str] = None
    configuration_updated_by: Optional[str] = None
    configuration_updated_at: Optional[datetime] = None
    enabled: bool
    min_interval_seconds: int
    timeout_seconds: int
    max_retries: int
    configuration: dict = Field(default_factory=dict)
    mapped_fields: list[str] = Field(default_factory=list)
    can_run: bool
    blocked_reason: Optional[str] = None
    raw_record_count: int = 0
    gate_status_counts: dict[str, int] = Field(default_factory=dict)
    last_task: Optional[MarketCrawlTask] = None
    updated_at: datetime
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    template_code: Optional[str] = None
    template_name: Optional[str] = None
    channel_type: str = "mixed"
    source_kind: str = "company_channel"
    configuration_status: str = "needs_review"
    collection_checkpoint: Optional[dict] = None
    collection_strategy: Optional[dict] = None
    operational_state: Optional[dict] = None


class MarketDataSourceList(BaseModel):
    sources: list[MarketDataSource]
    core_job_count: int = Field(default=0, ge=0)


class MarketSourceGovernanceRequest(BaseModel):
    terms_review_status: str = Field(pattern=r"^(pending|approved|rejected)$")
    enabled: bool
    review_note: str = Field(default="", max_length=1000)


class MarketSourceConfigurationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    adapter_type: str = Field(pattern=r"^(api|html|playwright|company_channel)$")
    base_url: str = Field(min_length=8, max_length=1000)
    allowed_hosts: list[str] = Field(min_length=1, max_length=20)
    min_interval_seconds: int = Field(ge=1, le=3600)
    timeout_seconds: int = Field(ge=1, le=120)
    max_retries: int = Field(ge=0, le=5)
    configuration: dict


class MarketCrawlTaskList(BaseModel):
    tasks: list[MarketCrawlTask]
    total: int = Field(ge=0)


class MarketCrawlTaskRecord(BaseModel):
    id: int
    external_id: Optional[str] = None
    source_url: str
    title: Optional[str] = None
    company_name: Optional[str] = None
    city: Optional[str] = None
    summary: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime
    validation_status: str
    validation_error: Optional[str] = None
    processing_status: str = "pending"
    processing_version: Optional[str] = None
    processing_attempts: int = 0
    processing_trace: list[dict] = Field(default_factory=list)
    core_job_id: Optional[int] = None
    core_job_title: Optional[str] = None
    payload_preview: dict = Field(default_factory=dict)
    normalized_payload_preview: dict = Field(default_factory=dict)


class MarketCrawlTaskLog(BaseModel):
    id: int
    level: str
    event_code: str
    message: str
    context: dict = Field(default_factory=dict)
    created_at: datetime


class MarketCrawlTaskDetail(BaseModel):
    task: MarketCrawlTask
    record_total: int = Field(ge=0)
    records: list[MarketCrawlTaskRecord]
    logs: list[MarketCrawlTaskLog]


class MarketCollectionCompany(BaseModel):
    code: str
    name: str
    website_url: Optional[str] = None
    logo_url: Optional[str] = None
    origin: str
    enabled: bool
    channel_count: int
    ready_channel_count: int
    runnable_channel_count: int
    approved_channel_count: int
    invalid_channel_count: int
    raw_record_count: int
    promoted_record_count: int
    quarantined_record_count: int
    channels: list[MarketDataSource]


class MarketCollectionCompanyList(BaseModel):
    companies: list[MarketCollectionCompany]
    total_companies: int
    total_channels: int
    runnable_channels: int
    raw_records: int
    promoted_records: int
    quarantined_records: int


class MarketCompanyGovernanceRequest(BaseModel):
    enabled: bool
    review_note: str = Field(default="", max_length=1000)


class MarketCollectionRunRequest(BaseModel):
    browser_mode: str = Field(
        default="default", pattern=r"^(default|headless|visible)$"
    )


class MarketStrategyRepairCandidate(BaseModel):
    id: int
    source_code: str
    source_name: str
    failure_task_id: Optional[int] = None
    base_strategy_version: Optional[int] = None
    status: str
    origin: str
    failure_signature: Optional[str] = None
    proposed_strategy: dict = Field(default_factory=dict)
    replay_summary: dict = Field(default_factory=dict)
    canary_summary: dict = Field(default_factory=dict)
    created_by: str
    reviewed_by: Optional[str] = None
    created_at: datetime
    replayed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None


class MarketStrategyRepairCreateRequest(BaseModel):
    proposed_strategy: dict
    origin: str = Field(default="admin", pattern=r"^(admin|ai)$")
    failure_task_id: Optional[int] = None


class MarketStrategyRepairEvidence(BaseModel):
    source_code: str
    source_name: str
    adapter_type: str
    failure_signature: Optional[str] = None
    evidence: dict = Field(default_factory=dict)


class MarketCrawlBatch(BaseModel):
    id: int
    batch_uid: str
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    status: str
    requested_by: str
    requested_channels: int
    completed_channels: int
    failed_channels: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    tasks: list[MarketCrawlTask] = Field(default_factory=list)


class MarketGateConfiguration(BaseModel):
    policy_version: str
    minimum_core_score: int
    minimum_description_chars: int
    live_freshness_days: int
    maximum_future_hours: int
    maximum_salary: int
    required_facts: list[str]
    score_weights: dict[str, int]


class MarketGatePreviewReason(BaseModel):
    code: str
    count: int


class MarketGatePreview(BaseModel):
    sample_size: int
    accepted: int
    quarantined: int
    acceptance_rate: float
    top_reasons: list[MarketGatePreviewReason]


class MarketGatePolicy(BaseModel):
    id: int
    policy_version: str
    status: str
    configuration: MarketGateConfiguration
    change_note: Optional[str] = None
    created_by: str
    published_by: Optional[str] = None
    preview_summary: Optional[MarketGatePreview] = None
    previewed_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    certified_jobs: int = 0


class MarketGateSettings(BaseModel):
    active: MarketGatePolicy
    draft: Optional[MarketGatePolicy] = None
    certified_job_counts: dict[str, int]
    supported_required_facts: list[str]
    immutable_required_facts: list[str]
    score_dimensions: list[str]
    publish_scope: str


class MarketGateDraftRequest(BaseModel):
    configuration: dict
    change_note: str = Field(default="", max_length=1000)
