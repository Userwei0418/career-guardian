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
    status: str
    attempt_count: int
    records_seen: int
    records_stored: int
    duplicate_records: int
    failed_records: int
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class MarketDataSource(BaseModel):
    code: str
    name: str
    adapter_type: str
    base_url: str
    allowed_hosts: list[str]
    terms_review_status: str
    enabled: bool
    can_run: bool
    blocked_reason: Optional[str] = None
    raw_record_count: int = 0
    gate_status_counts: dict[str, int] = Field(default_factory=dict)
    last_task: Optional[MarketCrawlTask] = None
    updated_at: datetime


class MarketDataSourceList(BaseModel):
    sources: list[MarketDataSource]


class MarketCrawlTaskList(BaseModel):
    tasks: list[MarketCrawlTask]
    total: int = Field(ge=0)


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
