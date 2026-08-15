from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.base import SourceAdapter
from market_data.errors import MarketDataError
from market_data.models.raw import CrawlLogEntry, CrawlTask, DataSource, RawRecord
from market_data.schemas import RawRecordInput, SourceSnapshot
from market_data.services.registry import definition_from_model


def content_hash(record: RawRecordInput) -> str:
    if record.raw_payload is not None:
        content = json.dumps(
            record.raw_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    else:
        content = (record.raw_text or "").replace("\r\n", "\n").strip().encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def storage_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class IngestionService:
    """Writes only Market Raw. It does not accept a Core session or Core models."""

    def __init__(self, raw_session: Session):
        self.session = raw_session

    def run_snapshot(
        self,
        source_code: str,
        adapter: SourceAdapter,
        snapshot: SourceSnapshot,
        *,
        trigger_type: str = "fixture",
    ) -> CrawlTask:
        source = self._get_source(source_code)
        task = self._start_task(source, trigger_type)
        try:
            result = adapter.parse(definition_from_model(source), snapshot)
            if result.source_code != source.code or result.adapter_type != source.adapter_type:
                raise ValueError("adapter result does not match registered source")
            task.records_seen = len(result.records)
            for record in result.records:
                self._store_record(source, task, record)
            task.status = "succeeded"
            task.completed_at = datetime.now(timezone.utc)
            self._log(task, "info", "task_succeeded", "collection task completed")
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            task = self.session.get(CrawlTask, task.id)
            assert task is not None
            task.status = "failed"
            task.error_type = exc.code if isinstance(exc, MarketDataError) else type(exc).__name__
            task.error_message = str(exc)[:2000]
            task.completed_at = datetime.now(timezone.utc)
            self._log(task, "error", "task_failed", "collection task failed")
            self.session.commit()
        self.session.refresh(task)
        return task

    def run_live(self, source_code: str, adapter: SourceAdapter) -> CrawlTask:
        source = self._get_source(source_code)
        task = self._start_task(source, "live")
        try:
            definition = definition_from_model(source)
            snapshot = adapter.fetch(definition)
            result = adapter.parse(definition, snapshot)
            if result.source_code != source.code or result.adapter_type != source.adapter_type:
                raise ValueError("adapter result does not match registered source")
            task.attempt_count = int(snapshot.transport_metadata.get("attempt", 1))
            task.records_seen = len(result.records)
            for record in result.records:
                self._store_record(source, task, record)
            task.status = "succeeded"
            task.completed_at = datetime.now(timezone.utc)
            self._log(task, "info", "task_succeeded", "live collection task completed")
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            task = self.session.get(CrawlTask, task.id)
            assert task is not None
            task.status = "failed"
            task.error_type = exc.code if isinstance(exc, MarketDataError) else type(exc).__name__
            task.error_message = str(exc)[:2000]
            task.completed_at = datetime.now(timezone.utc)
            self._log(task, "error", "task_failed", "live collection task failed")
            self.session.commit()
        self.session.refresh(task)
        return task

    def _get_source(self, source_code: str) -> DataSource:
        source = self.session.scalar(select(DataSource).where(DataSource.code == source_code))
        if source is None:
            raise LookupError(f"unknown data source: {source_code}")
        return source

    def _start_task(self, source: DataSource, trigger_type: str) -> CrawlTask:
        now = datetime.now(timezone.utc)
        task = CrawlTask(
            task_uid=str(uuid4()),
            source_id=source.id,
            adapter_type=source.adapter_type,
            trigger_type=trigger_type,
            status="running",
            attempt_count=1,
            started_at=now,
        )
        self.session.add(task)
        self.session.flush()
        self._log(task, "info", "task_started", "collection task started")
        self.session.commit()
        return task

    def _store_record(self, source: DataSource, task: CrawlTask, record: RawRecordInput) -> None:
        digest = content_hash(record)
        existing = self.session.scalar(
            select(RawRecord).where(
                RawRecord.source_id == source.id,
                RawRecord.content_hash == digest,
            )
        )
        if existing is not None:
            existing.last_seen_at = max(existing.last_seen_at, storage_time(record.fetched_at))
            task.duplicate_records += 1
            return
        self.session.add(
            RawRecord(
                source_id=source.id,
                crawl_task_id=task.id,
                external_id=record.external_id,
                source_url=str(record.source_url),
                source_published_at=(
                    storage_time(record.source_published_at) if record.source_published_at else None
                ),
                fetched_at=storage_time(record.fetched_at),
                http_status=record.http_status,
                content_type=record.content_type,
                raw_payload=record.raw_payload,
                raw_text=record.raw_text,
                transport_metadata=record.transport_metadata,
                content_hash=digest,
                schema_version=record.schema_version,
                validation_status="pending_gate",
                first_seen_at=storage_time(record.fetched_at),
                last_seen_at=storage_time(record.fetched_at),
            )
        )
        task.records_stored += 1

    def _log(
        self, task: CrawlTask, level: str, event_code: str, message: str, context: dict | None = None
    ) -> None:
        self.session.add(
            CrawlLogEntry(
                crawl_task_id=task.id,
                level=level,
                event_code=event_code,
                message=message,
                context=context,
            )
        )
