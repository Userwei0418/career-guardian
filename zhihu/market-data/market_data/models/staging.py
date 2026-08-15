from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from market_data.db import StagingBase


class LegacyImportBatch(StagingBase):
    __tablename__ = "legacy_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dump_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_basename: Mapped[str] = mapped_column(String(255), nullable=False)
    import_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="fixture")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    table_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class LegacyTableStat(StagingBase):
    __tablename__ = "legacy_table_stats"
    __table_args__ = (UniqueConstraint("batch_id", "table_name", name="uq_legacy_batch_table"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("legacy_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_name: Mapped[str] = mapped_column(String(100), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    null_rates: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duplicate_rates: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observed_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LegacyJobRecord(StagingBase):
    __tablename__ = "legacy_job_records"
    __table_args__ = (UniqueConstraint("batch_id", "legacy_job_id", name="uq_legacy_batch_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("legacy_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    legacy_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_site: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    legacy_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
