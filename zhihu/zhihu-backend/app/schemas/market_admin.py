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
    last_task: Optional[MarketCrawlTask] = None
    updated_at: datetime


class MarketDataSourceList(BaseModel):
    sources: list[MarketDataSource]


class MarketCrawlTaskList(BaseModel):
    tasks: list[MarketCrawlTask]
    total: int = Field(ge=0)
