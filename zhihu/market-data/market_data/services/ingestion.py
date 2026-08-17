from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.base import SourceAdapter
from market_data.errors import MarketDataError
from market_data.models.raw import (
    CrawlLogEntry,
    CrawlTask,
    DataSource,
    RawRecord,
    SourceCollectionCheckpoint,
)
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
        task = self.create_live_task(source_code)
        return self.run_live_task(task.id, adapter)

    def create_live_task(
        self, source_code: str, *, browser_mode: str | None = None
    ) -> CrawlTask:
        source = self._get_source(source_code)
        requested_browser_mode = str(browser_mode or "default").strip().lower()
        if requested_browser_mode not in {"default", "headless", "visible"}:
            raise ValueError("browser_mode must be default, headless, or visible")
        configured_browser_mode = str(
            (source.config or {}).get("browser_mode") or ""
        ).strip().lower()
        if configured_browser_mode not in {"headless", "visible"}:
            configured_browser_mode = (
                "visible" if (source.config or {}).get("headless") is False else "headless"
            )
        effective_browser_mode = (
            configured_browser_mode
            if requested_browser_mode == "default"
            else requested_browser_mode
        )
        checkpoint = self.session.scalar(
            select(SourceCollectionCheckpoint).where(
                SourceCollectionCheckpoint.source_id == source.id
            )
        )
        incremental = source.config.get("incremental") or {}
        incremental_enabled = bool(incremental.get("enabled", False))
        ordering_is_safe = str(incremental.get("ordering") or "").strip() == "newest_first"
        full_refresh_every = max(
            1, min(int(incremental.get("full_refresh_every_runs", 10)), 100)
        )
        due_for_full_refresh = bool(
            checkpoint
            and checkpoint.successful_incremental_runs >= full_refresh_every
        )
        collection_mode = (
            "incremental"
            if checkpoint is not None
            and incremental_enabled
            and ordering_is_safe
            and not due_for_full_refresh
            else "full"
        )
        task = CrawlTask(
            task_uid=str(uuid4()),
            source_id=source.id,
            adapter_type=source.adapter_type,
            trigger_type="live",
            status="pending",
            attempt_count=0,
            collection_mode=collection_mode,
            checkpoint_version=checkpoint.version if checkpoint else None,
            browser_mode=effective_browser_mode,
            browser_mode_source=(
                "channel_default"
                if requested_browser_mode == "default"
                else "run_override"
            ),
        )
        self.session.add(task)
        self.session.flush()
        self._log(
            task,
            "info",
            "task_queued",
            "collection task queued",
            context={
                "collection_mode": collection_mode,
                "checkpoint_version": checkpoint.version if checkpoint else None,
                "periodic_full_refresh": due_for_full_refresh,
                "browser_mode": effective_browser_mode,
                "browser_mode_source": task.browser_mode_source,
            },
        )
        self.session.commit()
        self.session.refresh(task)
        return task

    def run_live_task(
        self, task_id: int, adapter: SourceAdapter, *, finalize_success: bool = True
    ) -> CrawlTask:
        task = self.session.get(CrawlTask, task_id)
        if task is None:
            raise LookupError(f"unknown crawl task: {task_id}")
        source = self.session.get(DataSource, task.source_id)
        if source is None:
            raise LookupError(f"unknown data source id: {task.source_id}")
        if task.status != "pending":
            return task
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        task.attempt_count = 1
        self._log(task, "info", "task_started", "collection task started")
        self.session.commit()
        try:
            definition = self._definition_for_task(source, task)
            snapshot = adapter.fetch(definition)
            self._log(
                task,
                "info",
                "collection_snapshot",
                "browser collection snapshot captured",
                context=snapshot.transport_metadata,
            )
            result = adapter.parse(definition, snapshot)
            if result.source_code != source.code or result.adapter_type != source.adapter_type:
                raise ValueError("adapter result does not match registered source")
            task.attempt_count = int(snapshot.transport_metadata.get("attempt", 1))
            task.records_seen = len(result.records)
            observed_external_ids = list(
                dict.fromkeys(
                    str(record.external_id).strip()
                    for record in result.records
                    if record.external_id and str(record.external_id).strip()
                )
            )
            incremental = source.config.get("incremental") or {}
            recent_id_window = max(
                20, min(int(incremental.get("recent_id_window", 500)), 5_000)
            )
            self._log(
                task,
                "info",
                "collection_boundary_observed",
                "stable source job identifiers observed",
                context={
                    "external_ids": observed_external_ids[:recent_id_window],
                    "collection_mode": task.collection_mode,
                    "pagination_mode": snapshot.transport_metadata.get("pagination_mode"),
                    "pagination_stop_reason": snapshot.transport_metadata.get(
                        "pagination_stop_reason"
                    ),
                },
            )
            for record in result.records:
                self._store_record(source, task, record)
            if finalize_success:
                task.status = "succeeded"
                task.completed_at = datetime.now(timezone.utc)
                self._log(task, "info", "task_succeeded", "live collection task completed")
                self.advance_checkpoint(task.id)
            else:
                self._log(
                    task,
                    "info",
                    "collection_completed",
                    "live collection completed; quality gate is next",
                )
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

    def _definition_for_task(self, source: DataSource, task: CrawlTask):
        definition = definition_from_model(source)
        checkpoint = self.session.scalar(
            select(SourceCollectionCheckpoint).where(
                SourceCollectionCheckpoint.source_id == source.id
            )
        )
        cursor = checkpoint.cursor_payload if checkpoint else {}
        incremental = source.config.get("incremental") or {}
        config = dict(definition.config)
        config["_collection"] = {
            "mode": task.collection_mode,
            "known_external_ids": (
                list(cursor.get("recent_external_ids") or [])
                if task.collection_mode == "incremental"
                else []
            ),
            "known_batch_threshold": max(
                1, min(int(incremental.get("known_batch_threshold", 1)), 10)
            ),
        }
        config["_runtime"] = {
            "browser_mode": task.browser_mode,
            "browser_mode_source": task.browser_mode_source,
            "task_uid": task.task_uid,
        }
        return definition.model_copy(update={"config": config})

    def advance_checkpoint(self, task_id: int) -> SourceCollectionCheckpoint | None:
        """Advance a source boundary only for records accepted by the quality gate.

        A collected identifier is not automatically a safe checkpoint.  If the
        corresponding raw record was quarantined, keeping it out of the cursor
        guarantees that a later run will revisit the upstream item after the
        parser or mapping has been repaired.
        """

        task = self.session.get(CrawlTask, task_id)
        if task is None:
            raise LookupError(f"unknown crawl task: {task_id}")
        source = self.session.get(DataSource, task.source_id)
        if source is None:
            raise LookupError(f"unknown data source id: {task.source_id}")
        boundary_log = self.session.scalar(
            select(CrawlLogEntry)
            .where(
                CrawlLogEntry.crawl_task_id == task.id,
                CrawlLogEntry.event_code == "collection_boundary_observed",
            )
            .order_by(CrawlLogEntry.id.desc())
            .limit(1)
        )
        observed = list(
            dict.fromkeys(
                str(item).strip()
                for item in ((boundary_log.context or {}).get("external_ids", []) if boundary_log else [])
                if str(item).strip()
            )
        )
        promoted_ids = set(
            self.session.scalars(
                select(RawRecord.external_id).where(
                    RawRecord.source_id == source.id,
                    RawRecord.external_id.in_(observed),
                    RawRecord.validation_status == "promoted",
                )
            )
        ) if observed else set()
        accepted = [external_id for external_id in observed if external_id in promoted_ids]
        if not accepted:
            self._log(
                task,
                "warning",
                "collection_checkpoint_not_advanced",
                "no quality-approved source identifiers were available for the checkpoint",
                context={
                    "observed_external_id_count": len(observed),
                    "quarantined_records": task.quarantined_records,
                    "collection_mode": task.collection_mode,
                },
            )
            return None

        checkpoint = self.session.scalar(
            select(SourceCollectionCheckpoint).where(
                SourceCollectionCheckpoint.source_id == source.id
            )
        )
        if checkpoint is None:
            checkpoint = SourceCollectionCheckpoint(
                source_id=source.id,
                version=0,
                cursor_payload={},
            )
            self.session.add(checkpoint)
            self.session.flush()
        prior = list((checkpoint.cursor_payload or {}).get("recent_external_ids") or [])
        incremental = source.config.get("incremental") or {}
        recent_id_window = max(
            20, min(int(incremental.get("recent_id_window", 500)), 5_000)
        )
        merged = list(dict.fromkeys([*accepted, *prior]))[:recent_id_window]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        checkpoint.version += 1
        checkpoint.cursor_payload = {
            "recent_external_ids": merged,
            "last_pagination_mode": (
                (boundary_log.context or {}).get("pagination_mode") if boundary_log else None
            ),
            "last_stop_reason": (
                (boundary_log.context or {}).get("pagination_stop_reason")
                if boundary_log
                else None
            ),
            "last_records_seen": task.records_seen,
            "last_task_uid": task.task_uid,
        }
        checkpoint.last_successful_task_id = task.id
        checkpoint.last_successful_at = now
        if task.collection_mode == "full":
            checkpoint.successful_incremental_runs = 0
            checkpoint.last_full_crawl_at = now
        else:
            checkpoint.successful_incremental_runs += 1
        self._log(
            task,
            "info",
            "collection_checkpoint_advanced",
            "incremental collection boundary advanced",
            context={
                "checkpoint_version": checkpoint.version,
                "recent_external_id_count": len(merged),
                "collection_mode": task.collection_mode,
                "successful_incremental_runs": checkpoint.successful_incremental_runs,
            },
        )
        return checkpoint

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
