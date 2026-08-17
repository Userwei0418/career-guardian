from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from market_data.db import RawBase


class CollectionTemplate(RawBase):
    __tablename__ = "collection_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    platform_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    adapter_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    default_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RecruitmentCompany(RawBase):
    __tablename__ = "recruitment_companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    website_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    origin: Mapped[str] = mapped_column(String(30), nullable=False, default="native")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CrawlBatch(RawBase):
    __tablename__ = "crawl_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_uid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("recruitment_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_channels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_channels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_channels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataSource(RawBase):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("recruitment_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    allowed_hosts: Mapped[list] = mapped_column(JSON, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    terms_review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    terms_reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    terms_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terms_review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    configuration_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    channel_type: Mapped[str] = mapped_column(String(30), nullable=False, default="mixed", index=True)
    source_kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default="company_channel", index=True
    )
    legacy_company_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    configuration_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="needs_review", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CollectionStrategyVersion(RawBase):
    """A validated, reusable loading/parser strategy for one channel.

    Strategy documents are deliberately declarative.  They may contain the
    supported pagination mode and selectors, but never executable code.  AI or
    administrators can propose richer candidates later without bypassing the
    replay/canary activation path.
    """

    __tablename__ = "collection_strategy_versions"
    __table_args__ = (
        UniqueConstraint("source_id", "version", name="uq_collection_strategy_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate", index=True)
    origin: Mapped[str] = mapped_column(String(30), nullable=False, default="runtime_discovery")
    strategy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CrawlTask(RawBase):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_uid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("crawl_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    adapter_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default="fixture")
    collection_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="full", index=True
    )
    checkpoint_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    browser_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="headless"
    )
    browser_mode_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="channel_default"
    )
    strategy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="runtime_discovery"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promoted_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SourceCollectionCheckpoint(RawBase):
    """Successful collection boundary for one recruitment channel.

    The cursor is intentionally data based instead of a page number. Page
    numbers move whenever an upstream inserts new jobs, while stable source job
    identifiers can safely form an overlap window.
    """

    __tablename__ = "source_collection_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cursor_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    successful_incremental_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_successful_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"), nullable=True
    )
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_full_crawl_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RawRecord(RawBase):
    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("source_id", "content_hash", name="uq_raw_source_content"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    crawl_task_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    normalized_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="raw-v1")
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_gate"
    )
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class RawProcessingAttempt(RawBase):
    """Auditable processing lineage without storing prompts or copied source text."""

    __tablename__ = "raw_processing_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_record_id: Mapped[int] = mapped_column(
        ForeignKey("raw_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    crawl_task_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    processor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CrawlLogEntry(RawBase):
    __tablename__ = "crawl_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crawl_task_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    event_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
