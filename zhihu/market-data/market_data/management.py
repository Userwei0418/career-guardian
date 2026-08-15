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
from market_data.models.raw import CrawlTask, DataSource, RawRecord
from market_data.services.ingestion import IngestionService
from market_data.services.registry import definition_from_model, load_source_registry, upsert_sources


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
    last_task: CrawlTaskAdminView | None = None
    updated_at: datetime


class SourceAdminListResponse(BaseModel):
    sources: list[DataSourceAdminView]


class CrawlTaskAdminListResponse(BaseModel):
    tasks: list[CrawlTaskAdminView]
    total: int = Field(ge=0)


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
                blocked_reason = None
                if source.terms_review_status != "approved":
                    blocked_reason = "来源条款尚未人工审批"
                elif not source.enabled:
                    blocked_reason = "来源尚未启用"
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
            task = IngestionService(session).run_live(source.code, adapter)
            session.refresh(source)
            return self._task_view(task, source)


def build_management_runtime() -> tuple[MarketAdminRuntime | None, Engine | None]:
    database_url = os.getenv("MARKET_RAW_DATABASE_URL", "").strip()
    if not database_url:
        return None, None
    engine = make_engine(database_url)
    if database_url.startswith("sqlite"):
        RawBase.metadata.create_all(engine)
    runtime = MarketAdminRuntime(make_session_factory(engine))
    registry_path = os.getenv("MARKET_SOURCE_REGISTRY_PATH", str(ROOT / "sources" / "registry.json"))
    runtime.sync_registry(registry_path)
    return runtime, engine
