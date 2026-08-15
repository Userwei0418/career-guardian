from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from market_data.adapters import HtmlAdapter, PlaywrightAdapter, StructuredApiAdapter
from market_data.adapters.base import SourceAdapter
from market_data.db import RawBase, make_engine, make_session_factory
from market_data.errors import SourcePolicyError
from market_data.models.raw import CrawlTask, DataSource, RawRecord
from market_data.services.ingestion import IngestionService
from market_data.services.gate_policy import (
    gate_settings,
    preview_draft,
    publish_draft,
    save_draft,
)
from market_data.services.registry import definition_from_model, load_source_registry, upsert_sources
from market_data.services.raw_promotion import promote_task_records


ROOT = Path(__file__).resolve().parents[1]


class CrawlTaskAdminView(BaseModel):
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
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class DataSourceAdminView(BaseModel):
    code: str
    name: str
    adapter_type: str
    base_url: str
    allowed_hosts: list[str]
    terms_review_status: str
    enabled: bool
    can_run: bool
    blocked_reason: str | None = None
    raw_record_count: int = 0
    gate_status_counts: dict[str, int] = Field(default_factory=dict)
    last_task: CrawlTaskAdminView | None = None
    updated_at: datetime


class SourceAdminListResponse(BaseModel):
    sources: list[DataSourceAdminView]


class CrawlTaskAdminListResponse(BaseModel):
    tasks: list[CrawlTaskAdminView]
    total: int = Field(ge=0)


class GatePolicyConfigurationView(BaseModel):
    policy_version: str
    minimum_core_score: int
    minimum_description_chars: int
    live_freshness_days: int
    maximum_future_hours: int
    maximum_salary: int
    required_facts: list[str]
    score_weights: dict[str, int]


class GatePreviewReasonView(BaseModel):
    code: str
    count: int


class GatePreviewSummaryView(BaseModel):
    sample_size: int
    accepted: int
    quarantined: int
    acceptance_rate: float
    top_reasons: list[GatePreviewReasonView]


class GatePolicyAdminView(BaseModel):
    id: int
    policy_version: str
    status: str
    configuration: GatePolicyConfigurationView
    change_note: str | None = None
    created_by: str
    published_by: str | None = None
    preview_summary: GatePreviewSummaryView | None = None
    previewed_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    certified_jobs: int = 0


class GateSettingsAdminView(BaseModel):
    active: GatePolicyAdminView
    draft: GatePolicyAdminView | None = None
    certified_job_counts: dict[str, int]
    supported_required_facts: list[str]
    immutable_required_facts: list[str]
    score_dimensions: list[str]
    publish_scope: str


class GateDraftUpdate(BaseModel):
    configuration: dict
    change_note: str = ""
    actor: str


class GatePublishRequest(BaseModel):
    actor: str


def default_adapter_factory(adapter_type: str) -> SourceAdapter:
    adapters: dict[str, type[SourceAdapter]] = {
        "api": StructuredApiAdapter,
        "html": HtmlAdapter,
        "playwright": PlaywrightAdapter,
    }
    adapter_class = adapters.get(adapter_type)
    if adapter_class is None:
        raise ValueError(f"unsupported adapter type: {adapter_type}")
    return adapter_class()


@dataclass
class MarketAdminRuntime:
    session_factory: sessionmaker[Session]
    core_session_factory: sessionmaker[Session] | None = None
    adapter_factory: Callable[[str], SourceAdapter] = default_adapter_factory

    def sync_registry(self, registry_path: str | Path) -> None:
        with self.session_factory() as session:
            upsert_sources(session, load_source_registry(registry_path))

    @staticmethod
    def _task_view(task: CrawlTask, source: DataSource) -> CrawlTaskAdminView:
        return CrawlTaskAdminView(
            id=task.id,
            task_uid=task.task_uid,
            source_code=source.code,
            source_name=source.name,
            adapter_type=task.adapter_type,
            trigger_type=task.trigger_type,
            status=task.status,
            attempt_count=task.attempt_count,
            records_seen=task.records_seen,
            records_stored=task.records_stored,
            duplicate_records=task.duplicate_records,
            failed_records=task.failed_records,
            error_type=task.error_type,
            error_message=task.error_message,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
        )

    def list_sources(self) -> SourceAdminListResponse:
        with self.session_factory() as session:
            sources = list(session.scalars(select(DataSource).order_by(DataSource.id.asc())))
            result: list[DataSourceAdminView] = []
            for source in sources:
                latest_task = session.scalar(
                    select(CrawlTask)
                    .where(CrawlTask.source_id == source.id)
                    .order_by(CrawlTask.id.desc())
                    .limit(1)
                )
                raw_record_count = int(
                    session.scalar(
                        select(func.count()).select_from(RawRecord).where(RawRecord.source_id == source.id)
                    )
                    or 0
                )
                gate_status_counts = {
                    status: int(count)
                    for status, count in session.execute(
                        select(RawRecord.validation_status, func.count(RawRecord.id))
                        .where(RawRecord.source_id == source.id)
                        .group_by(RawRecord.validation_status)
                    )
                }
                blocked_reason = None
                if source.terms_review_status != "approved":
                    blocked_reason = "来源条款尚未人工审批"
                elif not source.enabled:
                    blocked_reason = "来源尚未启用"
                elif not isinstance((source.config or {}).get("promotion_mapping"), dict):
                    blocked_reason = "来源尚未配置产品字段映射"
                elif self.core_session_factory is None:
                    blocked_reason = "产品市场事实库尚未配置"
                result.append(
                    DataSourceAdminView(
                        code=source.code,
                        name=source.name,
                        adapter_type=source.adapter_type,
                        base_url=source.base_url,
                        allowed_hosts=[str(item) for item in source.allowed_hosts],
                        terms_review_status=source.terms_review_status,
                        enabled=source.enabled,
                        can_run=blocked_reason is None,
                        blocked_reason=blocked_reason,
                        raw_record_count=raw_record_count,
                        gate_status_counts=gate_status_counts,
                        last_task=self._task_view(latest_task, source) if latest_task else None,
                        updated_at=source.updated_at,
                    )
                )
            return SourceAdminListResponse(sources=result)

    def list_tasks(self, limit: int = 50) -> CrawlTaskAdminListResponse:
        with self.session_factory() as session:
            rows = session.execute(
                select(CrawlTask, DataSource)
                .join(DataSource, DataSource.id == CrawlTask.source_id)
                .order_by(CrawlTask.id.desc())
                .limit(limit)
            ).all()
            total = int(session.scalar(select(func.count()).select_from(CrawlTask)) or 0)
            return CrawlTaskAdminListResponse(
                tasks=[self._task_view(task, source) for task, source in rows],
                total=total,
            )

    def run_source(self, source_code: str) -> CrawlTaskAdminView:
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            adapter = self.adapter_factory(source.adapter_type)
            adapter.assert_live_collection_allowed(definition_from_model(source))
            if not isinstance((source.config or {}).get("promotion_mapping"), dict):
                raise SourcePolicyError(f"source {source.code} has no promotion mapping")
            core_factory = self._require_core_session_factory()
            task = IngestionService(session).run_live(source.code, adapter)
            if task.status == "succeeded" and task.records_stored:
                with core_factory() as core_session:
                    promote_task_records(session, core_session, source, task.id)
            session.refresh(source)
            return self._task_view(task, source)

    def _require_core_session_factory(self) -> sessionmaker[Session]:
        if self.core_session_factory is None:
            raise RuntimeError("市场 Core 数据库尚未配置")
        return self.core_session_factory

    def get_gate_settings(self) -> GateSettingsAdminView:
        with self._require_core_session_factory()() as session:
            return GateSettingsAdminView.model_validate(gate_settings(session))

    def save_gate_draft(self, request: GateDraftUpdate) -> GateSettingsAdminView:
        with self._require_core_session_factory()() as session:
            return GateSettingsAdminView.model_validate(
                save_draft(
                    session,
                    request.configuration,
                    request.change_note,
                    request.actor,
                )
            )

    def preview_gate_draft(self) -> GateSettingsAdminView:
        with self._require_core_session_factory()() as session:
            return GateSettingsAdminView.model_validate(preview_draft(session))

    def publish_gate_draft(self, request: GatePublishRequest) -> GateSettingsAdminView:
        with self._require_core_session_factory()() as session:
            return GateSettingsAdminView.model_validate(
                publish_draft(session, request.actor)
            )


def build_management_runtime() -> tuple[MarketAdminRuntime | None, list[Engine]]:
    raw_database_url = os.getenv("MARKET_RAW_DATABASE_URL", "").strip()
    core_database_url = os.getenv("MARKET_CORE_DATABASE_URL", "").strip()
    if not raw_database_url:
        return None, []
    raw_engine = make_engine(raw_database_url)
    if raw_database_url.startswith("sqlite"):
        RawBase.metadata.create_all(raw_engine)
    engines = [raw_engine]
    core_session_factory = None
    if core_database_url:
        core_engine = make_engine(core_database_url)
        engines.append(core_engine)
        core_session_factory = make_session_factory(core_engine)
    runtime = MarketAdminRuntime(
        make_session_factory(raw_engine),
        core_session_factory=core_session_factory,
    )
    registry_path = os.getenv("MARKET_SOURCE_REGISTRY_PATH", str(ROOT / "sources" / "registry.json"))
    runtime.sync_registry(registry_path)
    return runtime, engines
