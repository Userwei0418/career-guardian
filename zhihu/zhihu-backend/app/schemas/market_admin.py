from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    run_options: dict = Field(default_factory=dict)
    progress_snapshot: dict = Field(default_factory=dict)
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


class MarketTaskCancelRequest(BaseModel):
    reason: str = Field(default="管理员手动终止", max_length=500)


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
    raw_text_available: bool = False
    raw_text_characters: int = 0
    raw_text_bytes: int = 0
    detail_text_characters: int = 0
    detail_capture_mode: Optional[str] = None
    detail_strategy: Optional[str] = None
    detail_selector: Optional[str] = None
    detail_warning: Optional[str] = None


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


class MarketRawRecordEvidence(BaseModel):
    id: int
    crawl_task_id: int
    source_url: str
    content_type: str
    schema_version: str
    raw_text: str
    raw_text_characters: int
    raw_text_bytes: int
    detail_text: Optional[str] = None
    detail_capture_mode: Optional[str] = None
    detail_strategy: Optional[str] = None
    detail_selector: Optional[str] = None
    detail_warning: Optional[str] = None
    transport_metadata: dict = Field(default_factory=dict)


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
    terms_review_status: Optional[str] = Field(
        default=None, pattern=r"^(pending|approved|rejected)$"
    )
    review_note: str = Field(default="", max_length=1000)


class MarketCollectionRunRequest(BaseModel):
    browser_mode: str = Field(
        default="default", pattern=r"^(default|headless|visible)$"
    )
    collection_mode: str = Field(
        default="default", pattern=r"^(default|full|incremental)$"
    )
    max_pages: Optional[int] = Field(default=None, ge=1, le=200)
    max_records: Optional[int] = Field(default=None, ge=1, le=2000)
    detail_delay_min_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    detail_delay_max_seconds: Optional[int] = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def validate_delay_range(self) -> "MarketCollectionRunRequest":
        if (
            self.detail_delay_min_seconds is not None
            and self.detail_delay_max_seconds is not None
            and self.detail_delay_max_seconds < self.detail_delay_min_seconds
        ):
            raise ValueError("最大随机等待不能小于最小随机等待")
        return self


class MarketCoreCompany(BaseModel):
    id: int
    name: str
    alias_name: Optional[str] = None
    short_name: Optional[str] = None
    website_url: Optional[str] = None
    career_page_url: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[str] = None
    size_range: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    tags: list = Field(default_factory=list)
    status: str
    job_count: int = 0
    created_at: datetime
    updated_at: datetime


class MarketCoreCompanyList(BaseModel):
    items: list[MarketCoreCompany]
    total: int
    page: int
    page_size: int
    total_pages: int
    sort_by: str


class MarketCoreCompanyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    alias_name: Optional[str] = Field(default=None, max_length=255)
    short_name: Optional[str] = Field(default=None, max_length=100)
    website_url: Optional[str] = Field(default=None, max_length=1000)
    career_page_url: Optional[str] = Field(default=None, max_length=1000)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[str] = Field(default=None, max_length=100)
    size_range: Optional[str] = Field(default=None, max_length=100)
    headquarters: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")


class MarketCoreCompanyUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    alias_name: Optional[str] = Field(default=None, max_length=255)
    short_name: Optional[str] = Field(default=None, max_length=100)
    website_url: Optional[str] = Field(default=None, max_length=1000)
    career_page_url: Optional[str] = Field(default=None, max_length=1000)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_type: Optional[str] = Field(default=None, max_length=100)
    size_range: Optional[str] = Field(default=None, max_length=100)
    headquarters: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    logo_url: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[list[str]] = Field(default=None, max_length=30)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|deleted)$")


class MarketSchool(BaseModel):
    id: int
    code: str
    name: str
    employment_center_name: str
    short_name: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    website_url: Optional[str] = None
    description: Optional[str] = None
    origin: str
    status: str
    source_count: int = 0
    enabled_source_count: int = 0
    raw_record_count: int = 0
    created_at: datetime
    updated_at: datetime


class MarketSchoolList(BaseModel):
    items: list[MarketSchool]
    total: int
    page: int
    page_size: int
    total_pages: int
    sort_by: str


class MarketSchoolCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    employment_center_name: str = Field(min_length=2, max_length=255)
    short_name: Optional[str] = Field(default=None, max_length=100)
    province: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    website_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")


class MarketSchoolUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    employment_center_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    short_name: Optional[str] = Field(default=None, max_length=100)
    province: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    website_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|deleted)$")


class MarketSchoolAuditLog(BaseModel):
    id: int
    school_id: Optional[int] = None
    entity_id: str
    action: str
    actor: str
    before_payload: Optional[dict] = None
    after_payload: Optional[dict] = None
    created_at: datetime


class MarketSchoolAuditLogList(BaseModel):
    items: list[MarketSchoolAuditLog]
    total: int


class MarketCoreJob(BaseModel):
    id: int
    company_id: int
    company_name: str
    title: str
    location_text: Optional[str] = None
    department: Optional[str] = None
    job_category: Optional[str] = None
    employment_type: Optional[str] = None
    education_requirement: Optional[str] = None
    experience_requirement: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    salary_text: Optional[str] = None
    apply_url: Optional[str] = None
    detail_url: Optional[str] = None
    published_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: str
    quality_score: int
    quality_grade: str
    created_at: datetime
    updated_at: datetime


class MarketCoreJobList(BaseModel):
    items: list[MarketCoreJob]
    total: int
    page: int
    page_size: int
    total_pages: int
    sort_by: str


class MarketCoreJobCreateRequest(BaseModel):
    company_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=255)
    location_text: Optional[str] = Field(default=None, max_length=500)
    department: Optional[str] = Field(default=None, max_length=255)
    job_category: Optional[str] = Field(default=None, max_length=255)
    employment_type: Optional[str] = Field(default=None, max_length=100)
    education_requirement: Optional[str] = Field(default=None, max_length=255)
    experience_requirement: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    salary_text: Optional[str] = Field(default=None, max_length=255)
    apply_url: Optional[str] = Field(default=None, max_length=2000)
    detail_url: Optional[str] = Field(default=None, max_length=2000)
    published_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: str = Field(default="draft", pattern=r"^(draft|open|closed|expired)$")


class MarketCoreJobUpdateRequest(BaseModel):
    company_id: Optional[int] = Field(default=None, gt=0)
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    location_text: Optional[str] = Field(default=None, max_length=500)
    department: Optional[str] = Field(default=None, max_length=255)
    job_category: Optional[str] = Field(default=None, max_length=255)
    employment_type: Optional[str] = Field(default=None, max_length=100)
    education_requirement: Optional[str] = Field(default=None, max_length=255)
    experience_requirement: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    salary_text: Optional[str] = Field(default=None, max_length=255)
    apply_url: Optional[str] = Field(default=None, max_length=2000)
    detail_url: Optional[str] = Field(default=None, max_length=2000)
    published_at: Optional[datetime] = None
    deadline_at: Optional[datetime] = None
    status: Optional[str] = Field(default=None, pattern=r"^(draft|open|closed|expired|deleted)$")


class MarketCoreAuditLog(BaseModel):
    id: int
    entity_type: Literal["company", "job"]
    entity_id: str
    action: str
    actor: str
    before_payload: Optional[dict] = None
    after_payload: Optional[dict] = None
    created_at: datetime


class MarketCoreAuditLogList(BaseModel):
    items: list[MarketCoreAuditLog]
    total: int


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


class MarketStrategyRepairBackfillResult(BaseModel):
    inspected_failures: int = 0
    created_candidates: int = 0
    reused_candidates: int = 0


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
