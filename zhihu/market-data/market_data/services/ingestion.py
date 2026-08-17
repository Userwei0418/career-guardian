from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from market_data.adapters.base import SourceAdapter
from market_data.errors import MarketDataError
from market_data.fingerprints import business_payload_hash
from market_data.models.raw import (
    CollectionStrategyVersion,
    CrawlLogEntry,
    CrawlTask,
    DataSource,
    RawRecord,
    SourceCollectionCheckpoint,
    StrategyRepairCandidate,
)
from market_data.schemas import RawRecordInput, SourceSnapshot
from market_data.services.registry import definition_from_model
from market_data.services.resilience import (
    assert_source_runnable,
    classify_failure,
    record_source_failure,
    record_source_success,
)


ACTIVE_REPAIR_STATUSES = {
    "ai_pending",
    "ai_generating",
    "ai_failed",
    "candidate",
    "replay_failed",
    "canary_passed",
}


def strategy_failure_signature(task: CrawlTask) -> str:
    """Build a stable, non-sensitive key for repeated parser failures."""

    category = classify_failure(task.error_type, task.error_message)
    error_type = re.sub(r"\s+", " ", str(task.error_type or "unknown").strip().lower())
    message = re.sub(r"https?://\S+", "<url>", str(task.error_message or "").lower())
    message = re.sub(r"\b\d+\b", "<n>", re.sub(r"\s+", " ", message)).strip()
    return f"{category}:{error_type}:{message}"[:160]


def content_hash(record: RawRecordInput) -> str:
    if record.raw_payload is not None:
        return business_payload_hash(record.raw_payload)
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
        assert_source_runnable(self.session, source)
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
            record_source_success(self.session, source)
            self._log(task, "info", "task_succeeded", "collection task completed")
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            task = self.session.get(CrawlTask, task.id)
            assert task is not None
            source = self.session.get(DataSource, task.source_id)
            assert source is not None
            task.status = "failed"
            task.error_type = exc.code if isinstance(exc, MarketDataError) else type(exc).__name__
            task.error_message = str(exc)[:2000]
            task.completed_at = datetime.now(timezone.utc)
            state = record_source_failure(self.session, source, task.error_type, task.error_message)
            if state.recovery_action == "repair_strategy":
                self._queue_strategy_repair(source, task)
            self._log(task, "error", "task_failed", "collection task failed")
            self._log(
                task,
                "warning",
                "source_recovery_scheduled",
                "source health updated after collection failure",
                context={
                    "failure_type": state.last_failure_type,
                    "health_status": state.health_status,
                    "next_retry_at": state.next_retry_at.isoformat() if state.next_retry_at else None,
                    "recovery_action": state.recovery_action,
                },
            )
            self.session.commit()
        self.session.refresh(task)
        return task

    def run_live(self, source_code: str, adapter: SourceAdapter) -> CrawlTask:
        task = self.create_live_task(source_code)
        return self.run_live_task(task.id, adapter)

    def create_live_task(
        self, source_code: str, *, browser_mode: str | None = None
    ) -> CrawlTask:
        source = self._get_source(source_code)
        assert_source_runnable(self.session, source)
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
        configured_pagination = source.config.get("pagination") or {}
        configured_mode = str(
            configured_pagination.get("mode")
            if isinstance(configured_pagination, dict)
            else ""
        ).strip()
        active_strategy = None
        if source.adapter_type == "company_channel" and configured_mode in {"", "auto"}:
            active_strategy = self.session.scalar(
                select(CollectionStrategyVersion)
                .where(
                    CollectionStrategyVersion.source_id == source.id,
                    CollectionStrategyVersion.status == "active",
                )
                .order_by(CollectionStrategyVersion.version.desc())
                .limit(1)
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
            strategy_version=active_strategy.version if active_strategy else None,
            strategy_source=(
                "active_version"
                if active_strategy
                else "channel_config"
                if configured_mode not in {"", "auto"}
                else "runtime_discovery"
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
                "strategy_version": task.strategy_version,
                "strategy_source": task.strategy_source,
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
            actual_browser_mode = str(
                snapshot.transport_metadata.get("browser_mode") or ""
            ).strip().lower()
            if (
                actual_browser_mode in {"headless", "visible"}
                and actual_browser_mode != task.browser_mode
            ):
                planned_browser_mode = task.browser_mode
                task.browser_mode = actual_browser_mode
                self._log(
                    task,
                    "warning",
                    "browser_mode_reconciled",
                    "task browser mode reconciled with the execution snapshot",
                    context={
                        "planned_browser_mode": planned_browser_mode,
                        "actual_browser_mode": actual_browser_mode,
                        "browser_mode_source": task.browser_mode_source,
                    },
                )
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
            self._record_strategy_success(source, task, snapshot.transport_metadata)
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
                record_source_success(self.session, source)
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
            source = self.session.get(DataSource, task.source_id)
            assert source is not None
            task.status = "failed"
            task.error_type = exc.code if isinstance(exc, MarketDataError) else type(exc).__name__
            task.error_message = str(exc)[:2000]
            task.completed_at = datetime.now(timezone.utc)
            self._record_strategy_failure(source, task, task.error_type)
            state = record_source_failure(self.session, source, task.error_type, task.error_message)
            if state.recovery_action == "repair_strategy":
                self._queue_strategy_repair(source, task)
            self._log(task, "error", "task_failed", "live collection task failed")
            self._log(
                task,
                "warning",
                "source_recovery_scheduled",
                "source health updated after collection failure",
                context={
                    "failure_type": state.last_failure_type,
                    "health_status": state.health_status,
                    "next_retry_at": state.next_retry_at.isoformat() if state.next_retry_at else None,
                    "recovery_action": state.recovery_action,
                },
            )
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
            "known_content_hashes": (
                dict(cursor.get("recent_content_hashes") or {})
                if task.collection_mode == "incremental"
                else {}
            ),
            "known_batch_streak": max(
                1,
                min(
                    int(
                        incremental.get(
                            "known_batch_streak",
                            incremental.get("known_batch_threshold", 2),
                        )
                    ),
                    10,
                ),
            ),
            "published_high_watermark": (
                cursor.get("published_high_watermark")
                if task.collection_mode == "incremental"
                else None
            ),
            "published_overlap_days": max(
                0, min(int(incremental.get("published_overlap_days", 7)), 90)
            ),
            "published_boundary_streak": max(
                1,
                min(
                    int(
                        incremental.get(
                            "published_boundary_streak",
                            incremental.get(
                                "known_batch_streak",
                                incremental.get("known_batch_threshold", 2),
                            ),
                        )
                    ),
                    10,
                ),
            ),
        }
        config["_runtime"] = {
            "browser_mode": task.browser_mode,
            "browser_mode_source": task.browser_mode_source,
            "task_uid": task.task_uid,
            "strategy_version": task.strategy_version,
            "strategy_source": task.strategy_source,
        }
        if task.strategy_version is not None:
            strategy = self.session.scalar(
                select(CollectionStrategyVersion).where(
                    CollectionStrategyVersion.source_id == source.id,
                    CollectionStrategyVersion.version == task.strategy_version,
                    CollectionStrategyVersion.status == "active",
                )
            )
            if strategy is not None:
                config["_collection_strategy"] = dict(strategy.strategy or {})
        return definition.model_copy(update={"config": config})

    @staticmethod
    def _strategy_document(metadata: dict) -> dict | None:
        mode = str(metadata.get("pagination_mode") or "").strip()
        if mode not in {
            "single_page",
            "infinite_scroll",
            "load_more",
            "next_button",
        }:
            return None
        pagination: dict[str, object] = {"mode": mode}
        action = str(metadata.get("pagination_action") or "")
        if action.startswith("clicked:"):
            selector = action.split(":", 1)[1].strip()
            if selector:
                key = "load_more_selectors" if mode == "load_more" else "next_selectors"
                pagination[key] = [selector]
        detail_mode = str(metadata.get("detail_mode") or "").strip()
        detail_selectors = [
            str(selector).strip()
            for selector in (metadata.get("detail_selectors") or [])
            if str(selector or "").strip()
        ][:20]
        document = {
            "schema_version": "collection-strategy-v1",
            "pagination": pagination,
            "parser_mode": metadata.get("parser_mode"),
            "matched_selector": metadata.get("matched_selector"),
        }
        if detail_mode in {"embedded_panel", "expanded_panel", "detail_page"}:
            document["detail_mode"] = detail_mode
        if detail_selectors:
            document["detail_selectors"] = detail_selectors
        return document

    def _record_strategy_success(
        self, source: DataSource, task: CrawlTask, metadata: dict
    ) -> None:
        if source.adapter_type != "company_channel":
            return
        strategy_document = self._strategy_document(metadata)
        if strategy_document is None:
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        evidence = {
            "task_uid": task.task_uid,
            "records_discovered": metadata.get("records_discovered"),
            "batches_loaded": metadata.get("batches_loaded"),
            "reported_total": metadata.get("reported_total"),
            "pagination_stop_reason": metadata.get("pagination_stop_reason"),
            "detail_complete_count": metadata.get("detail_complete_count"),
            "detail_partial_count": metadata.get("detail_partial_count"),
            "detail_missing_count": metadata.get("detail_missing_count"),
            "detail_mode": metadata.get("detail_mode"),
            "detail_selectors": metadata.get("detail_selectors"),
        }
        active = self.session.scalar(
            select(CollectionStrategyVersion)
            .where(
                CollectionStrategyVersion.source_id == source.id,
                CollectionStrategyVersion.status == "active",
            )
            .order_by(CollectionStrategyVersion.version.desc())
            .limit(1)
        )
        if active is not None and active.strategy == strategy_document:
            active.failure_count = 0
            active.last_validated_at = now
            active.evidence = evidence
            active.validation_summary = {
                "last_status": "succeeded",
                "last_task_uid": task.task_uid,
            }
            task.strategy_version = active.version
            task.strategy_source = "active_version"
            self._log(
                task,
                "info",
                "collection_strategy_revalidated",
                "active collection strategy revalidated",
                context={"strategy_version": active.version, **evidence},
            )
            return
        latest_version = self.session.scalar(
            select(CollectionStrategyVersion.version)
            .where(CollectionStrategyVersion.source_id == source.id)
            .order_by(CollectionStrategyVersion.version.desc())
            .limit(1)
        ) or 0
        if active is not None:
            active.status = "superseded"
        origin = (
            "channel_config"
            if task.strategy_source == "channel_config"
            else "runtime_discovery"
        )
        created = CollectionStrategyVersion(
            source_id=source.id,
            version=int(latest_version) + 1,
            status="active",
            origin=origin,
            strategy=strategy_document,
            evidence=evidence,
            validation_summary={
                "last_status": "succeeded",
                "last_task_uid": task.task_uid,
            },
            failure_count=0,
            created_by="system",
            activated_at=now,
            last_validated_at=now,
        )
        self.session.add(created)
        self.session.flush()
        task.strategy_version = created.version
        task.strategy_source = origin
        self._log(
            task,
            "info",
            "collection_strategy_activated",
            "validated collection strategy activated",
            context={"strategy_version": created.version, "strategy": strategy_document, **evidence},
        )

    def _record_strategy_failure(
        self, source: DataSource, task: CrawlTask, error_type: str | None
    ) -> None:
        if task.strategy_version is None:
            return
        strategy = self.session.scalar(
            select(CollectionStrategyVersion).where(
                CollectionStrategyVersion.source_id == source.id,
                CollectionStrategyVersion.version == task.strategy_version,
                CollectionStrategyVersion.status == "active",
            )
        )
        if strategy is None:
            return
        strategy.failure_count += 1
        threshold = max(
            1, min(int((source.config or {}).get("strategy_failure_threshold", 2)), 5)
        )
        strategy.validation_summary = {
            "last_status": "failed",
            "last_task_uid": task.task_uid,
            "error_type": error_type,
            "consecutive_failures": strategy.failure_count,
        }
        if strategy.failure_count >= threshold:
            strategy.status = "invalidated"
            strategy.invalidated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self._log(
                task,
                "warning",
                "collection_strategy_invalidated",
                "active collection strategy invalidated; next run will rediscover",
                context={
                    "strategy_version": strategy.version,
                    "failure_count": strategy.failure_count,
                    "threshold": threshold,
                },
            )
        else:
            self._log(
                task,
                "warning",
                "collection_strategy_failed",
                "active collection strategy failed and remains under observation",
                context={
                    "strategy_version": strategy.version,
                    "failure_count": strategy.failure_count,
                    "threshold": threshold,
                },
            )

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
        promoted_records = list(
            self.session.scalars(
                select(RawRecord)
                .where(
                    RawRecord.source_id == source.id,
                    RawRecord.external_id.in_(observed),
                    RawRecord.validation_status == "promoted",
                )
                .order_by(RawRecord.last_seen_at.desc(), RawRecord.id.desc())
            )
        ) if observed else []
        promoted_by_id: dict[str, RawRecord] = {}
        for record in promoted_records:
            if record.external_id and record.external_id not in promoted_by_id:
                promoted_by_id[record.external_id] = record
        promoted_ids = set(promoted_by_id)
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
        prior_hashes = dict(
            (checkpoint.cursor_payload or {}).get("recent_content_hashes") or {}
        )
        incremental = source.config.get("incremental") or {}
        recent_id_window = max(
            20, min(int(incremental.get("recent_id_window", 500)), 5_000)
        )
        merged = list(dict.fromkeys([*accepted, *prior]))[:recent_id_window]
        merged_hashes = {
            external_id: (
                business_payload_hash(promoted_by_id[external_id].raw_payload)
                if external_id in promoted_by_id
                else prior_hashes.get(external_id)
            )
            for external_id in merged
            if external_id in promoted_by_id or prior_hashes.get(external_id)
        }
        published_candidates = [
            record.source_published_at
            for record in promoted_by_id.values()
            if record.source_published_at is not None
        ]
        prior_watermark = (checkpoint.cursor_payload or {}).get("published_high_watermark")
        current_watermark = max(published_candidates).isoformat() if published_candidates else None
        published_high_watermark = max(
            [value for value in [prior_watermark, current_watermark] if value],
            default=None,
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        checkpoint.version += 1
        checkpoint.cursor_payload = {
            "recent_external_ids": merged,
            "recent_content_hashes": merged_hashes,
            "published_high_watermark": published_high_watermark,
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
                "recent_content_hash_count": len(merged_hashes),
                "published_high_watermark": published_high_watermark,
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
        latest_external_record = None
        if record.external_id:
            latest_external_record = self.session.scalar(
                select(RawRecord)
                .where(
                    RawRecord.source_id == source.id,
                    RawRecord.external_id == record.external_id,
                )
                .order_by(RawRecord.last_seen_at.desc(), RawRecord.id.desc())
                .limit(1)
            )
        if (
            latest_external_record is not None
            and record.raw_payload is not None
            and latest_external_record.raw_payload is not None
            and business_payload_hash(latest_external_record.raw_payload) == digest
        ):
            latest_external_record.last_seen_at = max(
                latest_external_record.last_seen_at,
                storage_time(record.fetched_at),
            )
            task.duplicate_records += 1
            return
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

    def _queue_strategy_repair(
        self, source: DataSource, task: CrawlTask
    ) -> StrategyRepairCandidate:
        """Persist an AI repair request without activating unverified selectors."""
        signature = strategy_failure_signature(task)
        existing = self.session.scalar(
            select(StrategyRepairCandidate)
            .where(
                StrategyRepairCandidate.source_id == source.id,
                or_(
                    StrategyRepairCandidate.failure_task_id == task.id,
                    StrategyRepairCandidate.failure_signature == signature,
                ),
                StrategyRepairCandidate.status.in_(ACTIVE_REPAIR_STATUSES),
            )
            .order_by(StrategyRepairCandidate.id.desc())
            .limit(1)
        )
        if existing is not None:
            summary = dict(existing.replay_summary or {})
            latest_failure_task_id = int(summary.get("latest_failure_task_id") or 0)
            if existing.failure_task_id == task.id or latest_failure_task_id == task.id:
                return existing
            summary["failure_occurrences"] = int(summary.get("failure_occurrences") or 1) + 1
            summary["latest_failure_task_id"] = task.id
            summary["latest_failure_at"] = (
                task.completed_at or datetime.now(timezone.utc)
            ).isoformat()
            existing.replay_summary = summary
            if existing.status in {"ai_pending", "ai_failed"}:
                existing.failure_task_id = task.id
            self._log(
                task,
                "info",
                "strategy_repair_ai_deduplicated",
                "reused existing AI parser repair candidate",
                context={
                    "candidate_id": existing.id,
                    "candidate_status": existing.status,
                    "failure_signature": signature,
                    "requires_replay_and_approval": True,
                },
            )
            return existing
        active = self.session.scalar(
            select(CollectionStrategyVersion)
            .where(
                CollectionStrategyVersion.source_id == source.id,
                CollectionStrategyVersion.status == "active",
            )
            .order_by(CollectionStrategyVersion.version.desc())
            .limit(1)
        )
        candidate = StrategyRepairCandidate(
            source_id=source.id,
            failure_task_id=task.id,
            base_strategy_version=active.version if active else None,
            status="ai_pending",
            origin="ai",
            failure_signature=signature,
            proposed_strategy={},
            replay_summary={
                "generation_stage": "queued",
                "generation_attempts": 0,
                "failure_occurrences": 1,
                "latest_failure_task_id": task.id,
            },
            created_by="system",
        )
        self.session.add(candidate)
        self.session.flush()
        self._log(
            task,
            "info",
            "strategy_repair_ai_queued",
            "AI parser repair candidate queued",
            context={
                "candidate_id": candidate.id,
                "candidate_status": candidate.status,
                "requires_replay_and_approval": True,
            },
        )
        return candidate
