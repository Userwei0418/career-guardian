from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from market_data.adapters import CompanyChannelAdapter, HtmlAdapter, PlaywrightAdapter, StructuredApiAdapter
from market_data.adapters.base import SourceAdapter
from market_data.db import RawBase, make_engine, make_session_factory
from market_data.errors import SourcePolicyError
from market_data.models.core import Job, JobSource
from market_data.models.raw import (
    CollectionStrategyVersion,
    CollectionTemplate,
    CrawlBatch,
    CrawlLogEntry,
    CrawlTask,
    DataSource,
    RawProcessingAttempt,
    RawRecord,
    RecruitmentCompany,
    SourceCollectionCheckpoint,
    SourceOperationalState,
    StrategyRepairCandidate,
)
from market_data.services.ingestion import IngestionService
from market_data.services.gate_policy import (
    gate_settings,
    preview_draft,
    publish_draft,
    save_draft,
)
from market_data.services.registry import definition_from_model, load_source_registry, upsert_sources
from market_data.services.raw_promotion import map_raw_record, promote_task_records
from market_data.services.raw_processing import BackendSemanticNormalizer, SemanticNormalizer
from market_data.services.resilience import (
    clear_source_recovery_after_repair,
    record_source_failure,
    record_source_success,
)
from market_data.services.network_access import validate_network_policy
from market_data.schemas import SourceDefinition


ROOT = Path(__file__).resolve().parents[1]


class CrawlTaskAdminView(BaseModel):
    id: int
    task_uid: str
    source_code: str
    source_name: str
    adapter_type: str
    trigger_type: str
    collection_mode: str = "full"
    checkpoint_version: int | None = None
    browser_mode: str = "headless"
    browser_mode_source: str = "channel_default"
    strategy_version: int | None = None
    strategy_source: str = "runtime_discovery"
    status: str
    attempt_count: int
    records_seen: int
    records_stored: int
    duplicate_records: int
    failed_records: int
    promoted_records: int
    quarantined_records: int
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    batch_id: int | None = None


class DataSourceAdminView(BaseModel):
    code: str
    name: str
    adapter_type: str
    base_url: str
    allowed_hosts: list[str]
    terms_review_status: str
    terms_reviewed_by: str | None = None
    terms_reviewed_at: datetime | None = None
    terms_review_note: str | None = None
    configuration_updated_by: str | None = None
    configuration_updated_at: datetime | None = None
    enabled: bool
    min_interval_seconds: int
    timeout_seconds: int
    max_retries: int
    configuration: dict = Field(default_factory=dict)
    mapped_fields: list[str] = Field(default_factory=list)
    can_run: bool
    blocked_reason: str | None = None
    raw_record_count: int = 0
    gate_status_counts: dict[str, int] = Field(default_factory=dict)
    last_task: CrawlTaskAdminView | None = None
    updated_at: datetime
    company_code: str | None = None
    company_name: str | None = None
    template_code: str | None = None
    template_name: str | None = None
    channel_type: str = "mixed"
    source_kind: str = "company_channel"
    configuration_status: str = "needs_review"
    collection_checkpoint: dict | None = None
    collection_strategy: dict | None = None
    operational_state: dict | None = None


class SourceAdminListResponse(BaseModel):
    sources: list[DataSourceAdminView]
    core_job_count: int = Field(default=0, ge=0)


class SourceGovernanceUpdate(BaseModel):
    terms_review_status: str = Field(pattern=r"^(pending|approved|rejected)$")
    enabled: bool
    review_note: str = Field(default="", max_length=1000)
    actor: str = Field(min_length=1, max_length=100)


class CompanyGovernanceUpdate(BaseModel):
    enabled: bool
    review_note: str = Field(default="", max_length=1000)
    actor: str = Field(min_length=1, max_length=100)


class CollectionRunOptions(BaseModel):
    browser_mode: str = Field(
        default="default", pattern=r"^(default|headless|visible)$"
    )


class CollectionCompanyView(BaseModel):
    code: str
    name: str
    website_url: str | None = None
    logo_url: str | None = None
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
    channels: list[DataSourceAdminView]


class CollectionCompanyListResponse(BaseModel):
    companies: list[CollectionCompanyView]
    total_companies: int
    total_channels: int
    runnable_channels: int
    raw_records: int
    promoted_records: int
    quarantined_records: int


class CrawlBatchAdminView(BaseModel):
    id: int
    batch_uid: str
    company_code: str | None = None
    company_name: str | None = None
    status: str
    requested_by: str
    requested_channels: int
    completed_channels: int
    failed_channels: int
    created_at: datetime
    completed_at: datetime | None = None
    tasks: list[CrawlTaskAdminView] = Field(default_factory=list)


class SourceTechnicalUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    adapter_type: str = Field(pattern=r"^(api|html|playwright|company_channel)$")
    base_url: str = Field(min_length=8, max_length=1000)
    allowed_hosts: list[str] = Field(min_length=1, max_length=20)
    min_interval_seconds: int = Field(ge=1, le=3600)
    timeout_seconds: int = Field(ge=1, le=120)
    max_retries: int = Field(ge=0, le=5)
    configuration: dict
    actor: str = Field(min_length=1, max_length=100)


class StrategyRepairCandidateCreate(BaseModel):
    proposed_strategy: dict
    actor: str = Field(min_length=1, max_length=100)
    origin: str = Field(default="admin", pattern=r"^(admin|ai)$")
    failure_task_id: int | None = None


class StrategyRepairReview(BaseModel):
    actor: str = Field(min_length=1, max_length=100)


class StrategyRepairCandidateView(BaseModel):
    id: int
    source_code: str
    source_name: str
    failure_task_id: int | None = None
    base_strategy_version: int | None = None
    status: str
    origin: str
    failure_signature: str | None = None
    proposed_strategy: dict
    replay_summary: dict = Field(default_factory=dict)
    canary_summary: dict = Field(default_factory=dict)
    created_by: str
    reviewed_by: str | None = None
    created_at: datetime
    replayed_at: datetime | None = None
    approved_at: datetime | None = None
    rolled_back_at: datetime | None = None


class StrategyRepairEvidenceView(BaseModel):
    source_code: str
    source_name: str
    adapter_type: str
    failure_signature: str | None = None
    evidence: dict = Field(default_factory=dict)


SENSITIVE_CONFIGURATION_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
}


def _contains_sensitive_configuration(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in SENSITIVE_CONFIGURATION_KEYS:
                return True
            if _contains_sensitive_configuration(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_configuration(child) for child in value)
    return False


DECLARATIVE_STRATEGY_KEYS = {
    "schema_version",
    "pagination",
    "parser_mode",
    "matched_selector",
    "item_selectors",
    "detail_selectors",
    "detail_mode",
}
DECLARATIVE_PAGINATION_KEYS = {
    "mode",
    "max_records",
    "max_rounds",
    "stable_rounds",
    "load_more_selectors",
    "next_selectors",
    "scroll_pause_ms",
}


def validate_strategy_document(document: dict) -> dict:
    if not isinstance(document, dict):
        raise ValueError("修复候选必须是声明式策略对象")
    unknown = sorted(set(document) - DECLARATIVE_STRATEGY_KEYS)
    if unknown:
        raise ValueError(f"修复候选包含不允许的字段: {', '.join(unknown)}")
    if _contains_sensitive_configuration(document):
        raise ValueError("修复候选不能包含 Cookie、Token、密钥或密码")
    pagination = document.get("pagination")
    if not isinstance(pagination, dict):
        raise ValueError("修复候选必须声明 pagination")
    unknown_pagination = sorted(set(pagination) - DECLARATIVE_PAGINATION_KEYS)
    if unknown_pagination:
        raise ValueError(
            f"pagination 包含不允许的字段: {', '.join(unknown_pagination)}"
        )
    mode = str(pagination.get("mode") or "").strip()
    if mode not in {"single_page", "infinite_scroll", "load_more", "next_button"}:
        raise ValueError("分页模式必须是 single_page/infinite_scroll/load_more/next_button")
    parser_mode = str(document.get("parser_mode") or "declarative_dom").strip()
    if parser_mode not in {"declarative_dom", "generic"}:
        raise ValueError("parser_mode 只能是 declarative_dom 或 generic")
    detail_mode = str(document.get("detail_mode") or "").strip()
    if detail_mode and detail_mode not in {
        "embedded_panel",
        "expanded_panel",
        "detail_page",
    }:
        raise ValueError(
            "detail_mode 只能是 embedded_panel/expanded_panel/detail_page"
        )
    matched_selector = str(document.get("matched_selector") or "").strip()
    if len(matched_selector) > 300:
        raise ValueError("matched_selector 超过 300 字符")
    for key in ("item_selectors", "detail_selectors"):
        selectors = document.get(key, [])
        if not isinstance(selectors, list) or len(selectors) > 20:
            raise ValueError(f"{key} 必须是不超过 20 项的选择器列表")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 300 for value in selectors):
            raise ValueError(f"{key} 包含无效选择器")
    for key in ("load_more_selectors", "next_selectors"):
        selectors = pagination.get(key, [])
        if not isinstance(selectors, list) or len(selectors) > 20:
            raise ValueError(f"pagination.{key} 必须是不超过 20 项的列表")
        if any(not isinstance(value, str) or not value.strip() or len(value) > 300 for value in selectors):
            raise ValueError(f"pagination.{key} 包含无效选择器")
    numeric_limits = {
        "max_records": (1, 2_000, 500),
        "max_rounds": (1, 200, 30),
        "stable_rounds": (1, 5, 2),
        "scroll_pause_ms": (200, 5_000, 650),
    }
    normalized_pagination = dict(pagination)
    for key, (minimum, maximum, default) in numeric_limits.items():
        value = pagination.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"pagination.{key} 必须是整数")
        if value < minimum or value > maximum:
            raise ValueError(
                f"pagination.{key} 必须在 {minimum} 到 {maximum} 之间"
            )
        normalized_pagination[key] = value
    normalized = dict(document)
    normalized["schema_version"] = "collection-strategy-v1"
    normalized["parser_mode"] = parser_mode
    normalized["matched_selector"] = matched_selector
    normalized["detail_mode"] = detail_mode
    normalized["item_selectors"] = list(document.get("item_selectors") or [])
    normalized["detail_selectors"] = list(document.get("detail_selectors") or [])
    normalized["pagination"] = normalized_pagination
    return normalized


def _sanitized_configuration(value: object) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in SENSITIVE_CONFIGURATION_KEYS:
                continue
            result[str(key)] = _sanitized_configuration(child)
        return result
    if isinstance(value, list):
        return [_sanitized_configuration(child) for child in value]
    return value


def _collection_strategy_summary(
    strategy: CollectionStrategyVersion | None,
) -> dict | None:
    if strategy is None:
        return None
    document = strategy.strategy or {}
    pagination = document.get("pagination") if isinstance(document, dict) else {}
    return {
        "version": strategy.version,
        "status": strategy.status,
        "origin": strategy.origin,
        "pagination_mode": (
            pagination.get("mode") if isinstance(pagination, dict) else None
        ),
        "failure_count": strategy.failure_count,
        "last_validated_at": strategy.last_validated_at,
        "activated_at": strategy.activated_at,
        "validation_summary": _sanitized_configuration(
            strategy.validation_summary or {}
        ),
    }


def _collection_checkpoint_summary(
    source: DataSource, checkpoint: SourceCollectionCheckpoint | None
) -> dict | None:
    if checkpoint is None:
        return None
    cursor = checkpoint.cursor_payload or {}
    incremental = (source.config or {}).get("incremental") or {}
    full_refresh_every = max(
        1, min(int(incremental.get("full_refresh_every_runs", 10)), 100)
    )
    return {
        "version": checkpoint.version,
        "recent_external_id_count": len(cursor.get("recent_external_ids", [])),
        "recent_content_hash_count": len(cursor.get("recent_content_hashes", {})),
        "published_high_watermark": cursor.get("published_high_watermark"),
        "successful_incremental_runs": checkpoint.successful_incremental_runs,
        "full_refresh_every_runs": full_refresh_every,
        "full_refresh_due_in_runs": max(
            0, full_refresh_every - checkpoint.successful_incremental_runs
        ),
        "last_successful_at": checkpoint.last_successful_at,
        "last_full_crawl_at": checkpoint.last_full_crawl_at,
        "last_stop_reason": cursor.get("last_stop_reason"),
    }


def _operational_state_summary(state: SourceOperationalState | None) -> dict | None:
    if state is None:
        return {
            "health_status": "healthy",
            "consecutive_failures": 0,
            "alert_status": "closed",
        }
    return {
        "health_status": state.health_status,
        "consecutive_failures": state.consecutive_failures,
        "last_failure_type": state.last_failure_type,
        "last_failure_message": state.last_failure_message,
        "last_failure_at": state.last_failure_at,
        "last_success_at": state.last_success_at,
        "next_retry_at": state.next_retry_at,
        "recovery_action": state.recovery_action,
        "recovery_recommendation": state.recovery_recommendation,
        "alert_status": state.alert_status,
        "alert_count": state.alert_count,
        "last_alert_at": state.last_alert_at,
    }


def _preview_text(value: object, limit: int = 240) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= limit else f"{text[:limit]}…"


def _preview_value(value: object, depth: int = 0) -> object:
    if depth >= 2:
        return _preview_text(value, 160)
    if isinstance(value, dict):
        return {
            str(key): _preview_value(child, depth + 1)
            for key, child in list(value.items())[:16]
        }
    if isinstance(value, list):
        return [_preview_value(child, depth + 1) for child in value[:8]]
    if isinstance(value, str):
        return _preview_text(value, 320)
    return value


def _payload_preview(value: object) -> dict:
    preview = _preview_value(value)
    if isinstance(preview, dict):
        return preview
    if isinstance(preview, list):
        return {"items": preview}
    return {"value": preview} if preview is not None else {}


def _record_has_meaningful_detail(record: object) -> bool:
    payload = getattr(record, "raw_payload", None)
    if not isinstance(payload, dict):
        return bool(str(getattr(record, "raw_text", "") or "").strip())
    detail_keys = (
        "responsibilities",
        "requirements",
        "description",
        "job_description",
        "job_detail",
        "content",
    )
    return any(len(str(payload.get(key) or "").strip()) >= 30 for key in detail_keys)


class CrawlTaskAdminListResponse(BaseModel):
    tasks: list[CrawlTaskAdminView]
    total: int = Field(ge=0)


class CrawlTaskRecordAdminView(BaseModel):
    id: int
    external_id: str | None = None
    source_url: str
    title: str | None = None
    company_name: str | None = None
    city: str | None = None
    summary: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    validation_status: str
    validation_error: str | None = None
    processing_status: str = "pending"
    processing_version: str | None = None
    processing_attempts: int = 0
    processing_trace: list[dict] = Field(default_factory=list)
    core_job_id: int | None = None
    core_job_title: str | None = None
    payload_preview: dict = Field(default_factory=dict)
    normalized_payload_preview: dict = Field(default_factory=dict)


class CrawlTaskLogAdminView(BaseModel):
    id: int
    level: str
    event_code: str
    message: str
    context: dict = Field(default_factory=dict)
    created_at: datetime


class CrawlTaskDetailAdminView(BaseModel):
    task: CrawlTaskAdminView
    record_total: int = Field(ge=0)
    records: list[CrawlTaskRecordAdminView]
    logs: list[CrawlTaskLogAdminView]


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
        "company_channel": CompanyChannelAdapter,
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
    semantic_normalizer: SemanticNormalizer | None = None

    def sync_registry(self, registry_path: str | Path) -> None:
        with self.session_factory() as session:
            upsert_sources(session, load_source_registry(registry_path))
            self._organize_bootstrap_sources(session)

    @staticmethod
    def _organize_bootstrap_sources(session: Session) -> None:
        template = session.scalar(select(CollectionTemplate).where(CollectionTemplate.code == "structured-api"))
        if template is None:
            template = CollectionTemplate(
                code="structured-api",
                name="结构化招聘 API",
                platform_type="api",
                adapter_type="api",
                description="官方招聘 API 渠道",
                capabilities={"list": True, "detail": True, "pagination": True},
                default_config={},
            )
            session.add(template)
            session.flush()
        picc = session.scalar(select(RecruitmentCompany).where(RecruitmentCompany.code == "picc"))
        if picc is None:
            picc = RecruitmentCompany(
                code="picc",
                name="中国人民保险集团",
                website_url="https://picc.zhiye.com",
                origin="native",
            )
            session.add(picc)
            session.flush()
        for source in session.scalars(select(DataSource)):
            if source.code.endswith("-fixture"):
                source.source_kind = "development_fixture"
                source.configuration_status = "needs_review"
            elif source.code.startswith("picc-"):
                source.company_id = picc.id
                source.template_id = template.id
                source.source_kind = "company_channel"
                source.configuration_status = "ready"
                if "campus" in source.code:
                    source.channel_type = "campus"
                elif "internship" in source.code:
                    source.channel_type = "internship"
                elif "social" in source.code:
                    source.channel_type = "social"
        session.commit()

    @staticmethod
    def _task_view(task: CrawlTask, source: DataSource) -> CrawlTaskAdminView:
        return CrawlTaskAdminView(
            id=task.id,
            task_uid=task.task_uid,
            source_code=source.code,
            source_name=source.name,
            adapter_type=task.adapter_type,
            trigger_type=task.trigger_type,
            collection_mode=task.collection_mode,
            checkpoint_version=task.checkpoint_version,
            browser_mode=task.browser_mode,
            browser_mode_source=task.browser_mode_source,
            strategy_version=task.strategy_version,
            strategy_source=task.strategy_source,
            status=task.status,
            attempt_count=task.attempt_count,
            records_seen=task.records_seen,
            records_stored=task.records_stored,
            duplicate_records=task.duplicate_records,
            failed_records=task.failed_records,
            promoted_records=task.promoted_records,
            quarantined_records=task.quarantined_records,
            error_type=task.error_type,
            error_message=task.error_message,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            batch_id=task.batch_id,
        )

    @staticmethod
    def _repair_candidate_view(
        candidate: StrategyRepairCandidate, source: DataSource
    ) -> StrategyRepairCandidateView:
        return StrategyRepairCandidateView(
            id=candidate.id,
            source_code=source.code,
            source_name=source.name,
            failure_task_id=candidate.failure_task_id,
            base_strategy_version=candidate.base_strategy_version,
            status=candidate.status,
            origin=candidate.origin,
            failure_signature=candidate.failure_signature,
            proposed_strategy=_sanitized_configuration(candidate.proposed_strategy),
            replay_summary=_sanitized_configuration(candidate.replay_summary),
            canary_summary=_sanitized_configuration(candidate.canary_summary),
            created_by=candidate.created_by,
            reviewed_by=candidate.reviewed_by,
            created_at=candidate.created_at,
            replayed_at=candidate.replayed_at,
            approved_at=candidate.approved_at,
            rolled_back_at=candidate.rolled_back_at,
        )

    def list_sources(self) -> SourceAdminListResponse:
        core_job_count = 0
        if self.core_session_factory is not None:
            with self.core_session_factory() as core_session:
                core_job_count = int(
                    core_session.scalar(select(func.count()).select_from(Job)) or 0
                )
        with self.session_factory() as session:
            sources = list(session.scalars(select(DataSource).order_by(DataSource.id.asc())))
            source_ids = [item.id for item in sources]
            active_strategies: dict[int, CollectionStrategyVersion] = {}
            operational_states = {
                item.source_id: item
                for item in session.scalars(
                    select(SourceOperationalState).where(
                        SourceOperationalState.source_id.in_(source_ids)
                    )
                )
            } if source_ids else {}
            if source_ids:
                for strategy in session.scalars(
                    select(CollectionStrategyVersion)
                    .where(
                        CollectionStrategyVersion.source_id.in_(source_ids),
                        CollectionStrategyVersion.status == "active",
                    )
                    .order_by(
                        CollectionStrategyVersion.source_id,
                        CollectionStrategyVersion.version.desc(),
                    )
                ):
                    active_strategies.setdefault(strategy.source_id, strategy)
            result: list[DataSourceAdminView] = []
            for source in sources:
                checkpoint = session.scalar(
                    select(SourceCollectionCheckpoint).where(
                        SourceCollectionCheckpoint.source_id == source.id
                    )
                )
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
                if source.source_kind != "development_fixture" and source.configuration_status != "ready":
                    blocked_reason = "渠道配置尚未通过校验"
                elif source.terms_review_status != "approved":
                    blocked_reason = "来源条款尚未人工审批"
                elif not source.enabled:
                    blocked_reason = "来源尚未启用"
                elif latest_task is not None and latest_task.status in {"pending", "running"}:
                    blocked_reason = "该来源已有采集任务正在执行"
                elif not isinstance((source.config or {}).get("promotion_mapping"), dict):
                    blocked_reason = "来源尚未配置产品字段映射"
                elif self.core_session_factory is None:
                    blocked_reason = "产品市场事实库尚未配置"
                else:
                    operational = operational_states.get(source.id)
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    if operational and operational.health_status == "blocked":
                        blocked_reason = operational.recovery_recommendation or "渠道已阻断"
                    elif operational and operational.next_retry_at and operational.next_retry_at > now:
                        blocked_reason = f"渠道冷却至 {operational.next_retry_at:%Y/%m/%d %H:%M}"
                company = session.get(RecruitmentCompany, source.company_id) if source.company_id else None
                template = session.get(CollectionTemplate, source.template_id) if source.template_id else None
                result.append(
                    DataSourceAdminView(
                        code=source.code,
                        name=source.name,
                        adapter_type=source.adapter_type,
                        base_url=source.base_url,
                        allowed_hosts=[str(item) for item in source.allowed_hosts],
                        terms_review_status=source.terms_review_status,
                        terms_reviewed_by=source.terms_reviewed_by,
                        terms_reviewed_at=source.terms_reviewed_at,
                        terms_review_note=source.terms_review_note,
                        configuration_updated_by=source.configuration_updated_by,
                        configuration_updated_at=source.configuration_updated_at,
                        enabled=source.enabled,
                        min_interval_seconds=source.min_interval_seconds,
                        timeout_seconds=source.timeout_seconds,
                        max_retries=source.max_retries,
                        configuration=_sanitized_configuration(source.config),
                        mapped_fields=sorted(
                            str(key)
                            for key in ((source.config or {}).get("promotion_mapping") or {})
                        ),
                        can_run=blocked_reason is None,
                        blocked_reason=blocked_reason,
                        raw_record_count=raw_record_count,
                        gate_status_counts=gate_status_counts,
                        last_task=self._task_view(latest_task, source) if latest_task else None,
                        updated_at=source.updated_at,
                        company_code=company.code if company else None,
                        company_name=company.name if company else None,
                        template_code=template.code if template else None,
                        template_name=template.name if template else None,
                        channel_type=source.channel_type,
                        source_kind=source.source_kind,
                        configuration_status=source.configuration_status,
                        collection_checkpoint=_collection_checkpoint_summary(
                            source, checkpoint
                        ),
                        collection_strategy=_collection_strategy_summary(
                            active_strategies.get(source.id)
                        ),
                        operational_state=_operational_state_summary(
                            operational_states.get(source.id)
                        ),
                    )
                )
            return SourceAdminListResponse(
                sources=result,
                core_job_count=core_job_count,
            )

    def list_collection_companies(self, query: str | None = None) -> CollectionCompanyListResponse:
        with self.session_factory() as session:
            company_statement = select(RecruitmentCompany).order_by(RecruitmentCompany.name)
            normalized_query = (query or "").strip().lower()
            if normalized_query:
                company_statement = company_statement.where(
                    func.lower(RecruitmentCompany.name).contains(normalized_query)
                )
            companies = list(session.scalars(company_statement))
            company_ids = [item.id for item in companies]
            if not company_ids:
                return CollectionCompanyListResponse(
                    companies=[],
                    total_companies=0,
                    total_channels=0,
                    runnable_channels=0,
                    raw_records=0,
                    promoted_records=0,
                    quarantined_records=0,
                )

            sources = list(
                session.scalars(
                    select(DataSource)
                    .where(
                        DataSource.company_id.in_(company_ids),
                        DataSource.source_kind == "company_channel",
                    )
                    .order_by(DataSource.company_id, DataSource.channel_type, DataSource.id)
                )
            )
            source_ids = [item.id for item in sources]
            template_ids = {item.template_id for item in sources if item.template_id is not None}
            templates = {
                item.id: item
                for item in session.scalars(
                    select(CollectionTemplate).where(CollectionTemplate.id.in_(template_ids))
                )
            } if template_ids else {}

            latest_tasks: dict[int, CrawlTask] = {}
            if source_ids:
                for task in session.scalars(
                    select(CrawlTask)
                    .where(CrawlTask.source_id.in_(source_ids))
                    .order_by(CrawlTask.id.desc())
                ):
                    latest_tasks.setdefault(task.source_id, task)
            checkpoints = {
                item.source_id: item
                for item in session.scalars(
                    select(SourceCollectionCheckpoint).where(
                        SourceCollectionCheckpoint.source_id.in_(source_ids)
                    )
                )
            } if source_ids else {}
            active_strategies: dict[int, CollectionStrategyVersion] = {}
            operational_states = {
                item.source_id: item
                for item in session.scalars(
                    select(SourceOperationalState).where(
                        SourceOperationalState.source_id.in_(source_ids)
                    )
                )
            } if source_ids else {}
            if source_ids:
                for strategy in session.scalars(
                    select(CollectionStrategyVersion)
                    .where(
                        CollectionStrategyVersion.source_id.in_(source_ids),
                        CollectionStrategyVersion.status == "active",
                    )
                    .order_by(
                        CollectionStrategyVersion.source_id,
                        CollectionStrategyVersion.version.desc(),
                    )
                ):
                    active_strategies.setdefault(strategy.source_id, strategy)
            raw_counts = {
                source_id: int(count)
                for source_id, count in session.execute(
                    select(RawRecord.source_id, func.count(RawRecord.id))
                    .where(RawRecord.source_id.in_(source_ids))
                    .group_by(RawRecord.source_id)
                )
            } if source_ids else {}
            gate_counts: dict[int, dict[str, int]] = {}
            if source_ids:
                for source_id, status, count in session.execute(
                    select(RawRecord.source_id, RawRecord.validation_status, func.count(RawRecord.id))
                    .where(RawRecord.source_id.in_(source_ids))
                    .group_by(RawRecord.source_id, RawRecord.validation_status)
                ):
                    gate_counts.setdefault(source_id, {})[status] = int(count)

            company_by_id = {item.id: item for item in companies}
            grouped: dict[int, list[DataSourceAdminView]] = {}
            for source in sources:
                company = company_by_id[source.company_id]
                template = templates.get(source.template_id)
                latest_task = latest_tasks.get(source.id)
                checkpoint = checkpoints.get(source.id)
                blocked_reason = None
                if source.configuration_status != "ready":
                    blocked_reason = "渠道配置尚未通过校验"
                elif source.terms_review_status != "approved":
                    blocked_reason = "来源条款尚未人工审批"
                elif not source.enabled or not company.enabled:
                    blocked_reason = "公司或渠道尚未启用"
                elif latest_task is not None and latest_task.status in {"pending", "running"}:
                    blocked_reason = "该来源已有采集任务正在执行"
                elif not isinstance((source.config or {}).get("promotion_mapping"), dict):
                    blocked_reason = "来源尚未配置产品字段映射"
                elif self.core_session_factory is None:
                    blocked_reason = "产品市场事实库尚未配置"
                else:
                    operational = operational_states.get(source.id)
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    if operational and operational.health_status == "blocked":
                        blocked_reason = operational.recovery_recommendation or "渠道已阻断"
                    elif operational and operational.next_retry_at and operational.next_retry_at > now:
                        blocked_reason = f"渠道冷却至 {operational.next_retry_at:%Y/%m/%d %H:%M}"
                grouped.setdefault(source.company_id, []).append(
                    DataSourceAdminView(
                        code=source.code,
                        name=source.name,
                        adapter_type=source.adapter_type,
                        base_url=source.base_url,
                        allowed_hosts=[str(item) for item in source.allowed_hosts],
                        terms_review_status=source.terms_review_status,
                        terms_reviewed_by=source.terms_reviewed_by,
                        terms_reviewed_at=source.terms_reviewed_at,
                        terms_review_note=source.terms_review_note,
                        configuration_updated_by=source.configuration_updated_by,
                        configuration_updated_at=source.configuration_updated_at,
                        enabled=source.enabled,
                        min_interval_seconds=source.min_interval_seconds,
                        timeout_seconds=source.timeout_seconds,
                        max_retries=source.max_retries,
                        configuration=_sanitized_configuration(source.config),
                        mapped_fields=sorted(
                            str(key) for key in ((source.config or {}).get("promotion_mapping") or {})
                        ),
                        can_run=blocked_reason is None,
                        blocked_reason=blocked_reason,
                        raw_record_count=raw_counts.get(source.id, 0),
                        gate_status_counts=gate_counts.get(source.id, {}),
                        last_task=self._task_view(latest_task, source) if latest_task else None,
                        updated_at=source.updated_at,
                        company_code=company.code,
                        company_name=company.name,
                        template_code=template.code if template else None,
                        template_name=template.name if template else None,
                        channel_type=source.channel_type,
                        source_kind=source.source_kind,
                        configuration_status=source.configuration_status,
                        collection_checkpoint=_collection_checkpoint_summary(
                            source, checkpoint
                        ),
                        collection_strategy=_collection_strategy_summary(
                            active_strategies.get(source.id)
                        ),
                        operational_state=_operational_state_summary(
                            operational_states.get(source.id)
                        ),
                    )
                )

            result: list[CollectionCompanyView] = []
            for company in companies:
                channels = grouped.get(company.id, [])
                if not channels:
                    continue
                result.append(
                    CollectionCompanyView(
                        code=company.code,
                        name=company.name,
                        website_url=company.website_url,
                        logo_url=company.logo_url,
                        origin=company.origin,
                        enabled=company.enabled,
                        channel_count=len(channels),
                        ready_channel_count=sum(item.configuration_status == "ready" for item in channels),
                        runnable_channel_count=sum(item.can_run for item in channels),
                        approved_channel_count=sum(item.terms_review_status == "approved" for item in channels),
                        invalid_channel_count=sum(item.configuration_status == "invalid" for item in channels),
                        raw_record_count=sum(item.raw_record_count for item in channels),
                        promoted_record_count=sum(item.gate_status_counts.get("promoted", 0) for item in channels),
                        quarantined_record_count=sum(item.gate_status_counts.get("quarantined", 0) for item in channels),
                        channels=channels,
                    )
                )
        return CollectionCompanyListResponse(
            companies=result,
            total_companies=len(result),
            total_channels=sum(item.channel_count for item in result),
            runnable_channels=sum(item.runnable_channel_count for item in result),
            raw_records=sum(item.raw_record_count for item in result),
            promoted_records=sum(item.promoted_record_count for item in result),
            quarantined_records=sum(item.quarantined_record_count for item in result),
        )

    def update_company_governance(
        self, company_code: str, request: CompanyGovernanceUpdate
    ) -> CollectionCompanyView:
        with self.session_factory() as session:
            company = session.scalar(select(RecruitmentCompany).where(RecruitmentCompany.code == company_code))
            if company is None:
                raise LookupError(f"unknown recruitment company: {company_code}")
            channels = list(session.scalars(select(DataSource).where(DataSource.company_id == company.id)))
            ready = [item for item in channels if item.configuration_status == "ready"]
            if request.enabled and not ready:
                raise ValueError("该公司没有通过配置校验的招聘渠道")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            company.enabled = request.enabled
            for source in ready:
                source.terms_review_status = "approved" if request.enabled else "pending"
                source.enabled = request.enabled
                source.terms_reviewed_by = request.actor
                source.terms_reviewed_at = now
                source.terms_review_note = request.review_note.strip() or None
            session.commit()
        return next(item for item in self.list_collection_companies().companies if item.code == company_code)

    def queue_company(
        self, company_code: str, actor: str, *, browser_mode: str = "default"
    ) -> CrawlBatchAdminView:
        with self.session_factory() as session:
            company = session.scalar(select(RecruitmentCompany).where(RecruitmentCompany.code == company_code))
            if company is None:
                raise LookupError(f"unknown recruitment company: {company_code}")
            sources = list(
                session.scalars(
                    select(DataSource).where(
                        DataSource.company_id == company.id,
                        DataSource.configuration_status == "ready",
                        DataSource.terms_review_status == "approved",
                        DataSource.enabled.is_(True),
                    )
                )
            )
            if not sources:
                raise ValueError("该公司没有已审批并启用的可运行渠道")
            import uuid

            batch = CrawlBatch(
                batch_uid=str(uuid.uuid4()),
                company_id=company.id,
                requested_by=actor,
                requested_channels=len(sources),
            )
            session.add(batch)
            session.flush()
            tasks: list[CrawlTaskAdminView] = []
            for source in sources:
                active = session.scalar(
                    select(CrawlTask).where(
                        CrawlTask.source_id == source.id,
                        CrawlTask.status.in_(["pending", "running"]),
                    )
                )
                if active is not None:
                    continue
                task = IngestionService(session).create_live_task(
                    source.code, browser_mode=browser_mode
                )
                task.batch_id = batch.id
                session.commit()
                session.refresh(task)
                tasks.append(self._task_view(task, source))
            batch.requested_channels = len(tasks)
            if not tasks:
                session.delete(batch)
                session.commit()
                raise ValueError("所有渠道已有任务在执行")
            session.commit()
            session.refresh(batch)
            return self._batch_view(batch, company, tasks)

    @staticmethod
    def _batch_view(
        batch: CrawlBatch,
        company: RecruitmentCompany | None,
        tasks: list[CrawlTaskAdminView],
    ) -> CrawlBatchAdminView:
        return CrawlBatchAdminView(
            id=batch.id,
            batch_uid=batch.batch_uid,
            company_code=company.code if company else None,
            company_name=company.name if company else None,
            status=batch.status,
            requested_by=batch.requested_by,
            requested_channels=batch.requested_channels,
            completed_channels=batch.completed_channels,
            failed_channels=batch.failed_channels,
            created_at=batch.created_at,
            completed_at=batch.completed_at,
            tasks=tasks,
        )

    def update_source_governance(
        self, source_code: str, request: SourceGovernanceUpdate
    ) -> DataSourceAdminView:
        if request.enabled and request.terms_review_status != "approved":
            raise ValueError("只有条款已审批的来源才能启用")
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            source.terms_review_status = request.terms_review_status
            source.enabled = request.enabled
            source.terms_reviewed_by = request.actor
            source.terms_reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            source.terms_review_note = request.review_note.strip() or None
            session.commit()
        return next(item for item in self.list_sources().sources if item.code == source_code)

    def update_source_configuration(
        self, source_code: str, request: SourceTechnicalUpdate
    ) -> DataSourceAdminView:
        if _contains_sensitive_configuration(request.configuration):
            raise ValueError("来源配置不能保存 Cookie、Token、密钥或密码")
        parsed = urlparse(request.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("采集入口必须使用有效的 HTTPS 地址")
        allowed_hosts = sorted(
            {host.strip().lower() for host in request.allowed_hosts if host.strip()}
        )
        if parsed.hostname.lower() not in allowed_hosts:
            raise ValueError("采集入口域名必须包含在 HTTPS 白名单中")
        if not isinstance(request.configuration.get("promotion_mapping"), dict):
            raise ValueError("必须配置进入产品岗位库的字段映射")
        browser_mode = str(request.configuration.get("browser_mode") or "headless")
        if browser_mode not in {"headless", "visible"}:
            raise ValueError("默认浏览器模式只能是 headless 或 visible")
        normalized_configuration = dict(request.configuration)
        normalized_configuration["network_policy"] = validate_network_policy(
            request.configuration.get("network_policy")
        )
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            active = session.scalar(
                select(CrawlTask).where(
                    CrawlTask.source_id == source.id,
                    CrawlTask.status.in_(["pending", "running"]),
                )
            )
            if active is not None:
                raise ValueError("采集任务执行期间不能修改来源配置")
            # Validate the complete persisted definition through the same schema used by adapters.
            definition = SourceDefinition(
                code=source.code,
                name=request.name.strip(),
                adapter_type=request.adapter_type,
                base_url=request.base_url,
                allowed_hosts=allowed_hosts,
                config=normalized_configuration,
                terms_review_status=source.terms_review_status,
                enabled=source.enabled,
                min_interval_seconds=request.min_interval_seconds,
                timeout_seconds=request.timeout_seconds,
                max_retries=request.max_retries,
            )
            if definition.adapter_type == "company_channel":
                CompanyChannelAdapter().validate_configuration(definition)
            source.name = definition.name
            source.adapter_type = definition.adapter_type
            source.base_url = str(definition.base_url)
            source.allowed_hosts = definition.allowed_hosts
            source.config = definition.config
            source.min_interval_seconds = definition.min_interval_seconds
            source.timeout_seconds = definition.timeout_seconds
            source.max_retries = definition.max_retries
            source.configuration_status = "ready"
            source.configuration_updated_by = request.actor
            source.configuration_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            company = session.get(RecruitmentCompany, source.company_id) if source.company_id else None
            company_name = company.name if company else None
            session.commit()
        if company_name:
            return next(
                channel
                for company_view in self.list_collection_companies(company_name).companies
                for channel in company_view.channels
                if channel.code == source_code
            )
        return next(item for item in self.list_sources().sources if item.code == source_code)

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

    def get_task_detail(self, task_id: int, limit: int = 100) -> CrawlTaskDetailAdminView:
        with self.session_factory() as session:
            task = session.get(CrawlTask, task_id)
            if task is None:
                raise LookupError(f"unknown crawl task: {task_id}")
            source = session.get(DataSource, task.source_id)
            if source is None:
                raise LookupError(f"unknown data source id: {task.source_id}")
            record_total = int(
                session.scalar(
                    select(func.count()).select_from(RawRecord).where(
                        RawRecord.crawl_task_id == task_id
                    )
                )
                or 0
            )
            raw_records = list(
                session.scalars(
                    select(RawRecord)
                    .where(RawRecord.crawl_task_id == task_id)
                    .order_by(RawRecord.id)
                    .limit(limit)
                )
            )
            logs = list(
                session.scalars(
                    select(CrawlLogEntry)
                    .where(CrawlLogEntry.crawl_task_id == task_id)
                    .order_by(CrawlLogEntry.id)
                )
            )
            raw_ids = [record.id for record in raw_records]
            attempts_by_raw: dict[int, list[dict]] = {record_id: [] for record_id in raw_ids}
            if raw_ids:
                attempts = list(
                    session.scalars(
                        select(RawProcessingAttempt)
                        .where(RawProcessingAttempt.raw_record_id.in_(raw_ids))
                        .order_by(RawProcessingAttempt.raw_record_id, RawProcessingAttempt.attempt_no)
                    )
                )
                for attempt in attempts:
                    attempts_by_raw.setdefault(attempt.raw_record_id, []).append(
                        {
                            "stage": attempt.stage,
                            "status": attempt.status,
                            "attempt_no": attempt.attempt_no,
                            "processor_type": attempt.processor_type,
                            "provider": attempt.provider,
                            "model": attempt.model,
                            "prompt_version": attempt.prompt_version,
                            "reason_codes": attempt.reason_codes or [],
                            "metrics": attempt.metrics or {},
                            "started_at": attempt.started_at,
                            "completed_at": attempt.completed_at,
                        }
                    )

            mapped_records: dict[int, dict[str, object | None]] = {}
            for raw in raw_records:
                try:
                    candidate = map_raw_record(source, raw)
                    summary = candidate.description or candidate.requirements or candidate.responsibilities
                    mapped_records[raw.id] = {
                        "title": candidate.title,
                        "company_name": candidate.company_name,
                        "city": candidate.city or candidate.location_text,
                        "summary": _preview_text(summary, 600),
                        "published_at": candidate.published_at,
                    }
                except (TypeError, ValueError):
                    mapped_records[raw.id] = {}

        core_jobs: dict[int, tuple[int, str]] = {}
        if raw_ids and self.core_session_factory is not None:
            with self.core_session_factory() as core_session:
                for raw_record_id, job_id, job_title in core_session.execute(
                    select(JobSource.raw_record_id, Job.id, Job.title)
                    .join(Job, Job.id == JobSource.job_id)
                    .where(JobSource.raw_record_id.in_(raw_ids))
                ):
                    if raw_record_id is not None:
                        core_jobs[int(raw_record_id)] = (int(job_id), str(job_title))

        record_views = []
        for raw in raw_records:
            mapped = mapped_records.get(raw.id, {})
            core_job = core_jobs.get(raw.id)
            record_views.append(
                CrawlTaskRecordAdminView(
                    id=raw.id,
                    external_id=raw.external_id,
                    source_url=raw.source_url,
                    title=mapped.get("title"),
                    company_name=mapped.get("company_name"),
                    city=mapped.get("city"),
                    summary=mapped.get("summary"),
                    published_at=mapped.get("published_at") or raw.source_published_at,
                    fetched_at=raw.fetched_at,
                    validation_status=raw.validation_status,
                    validation_error=raw.validation_error,
                    processing_status=raw.processing_status,
                    processing_version=raw.processing_version,
                    processing_attempts=raw.processing_attempts,
                    processing_trace=attempts_by_raw.get(raw.id, []),
                    core_job_id=core_job[0] if core_job else None,
                    core_job_title=core_job[1] if core_job else None,
                    payload_preview=_payload_preview(raw.raw_payload),
                    normalized_payload_preview=_payload_preview(raw.normalized_payload),
                )
            )
        return CrawlTaskDetailAdminView(
            task=self._task_view(task, source),
            record_total=record_total,
            records=record_views,
            logs=[
                CrawlTaskLogAdminView(
                    id=log.id,
                    level=log.level,
                    event_code=log.event_code,
                    message=log.message,
                    context=log.context or {},
                    created_at=log.created_at,
                )
                for log in logs
            ],
        )

    def run_source(
        self, source_code: str, *, browser_mode: str = "default"
    ) -> CrawlTaskAdminView:
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            adapter = self.adapter_factory(source.adapter_type)
            adapter.assert_live_collection_allowed(definition_from_model(source))
            if not isinstance((source.config or {}).get("promotion_mapping"), dict):
                raise SourcePolicyError(f"source {source.code} has no promotion mapping")
            core_factory = self._require_core_session_factory()
            ingestion = IngestionService(session)
            task = ingestion.create_live_task(source.code, browser_mode=browser_mode)
            task = ingestion.run_live_task(task.id, adapter, finalize_success=False)
            if task.status == "running" and task.records_stored:
                with core_factory() as core_session:
                    promote_task_records(
                        session,
                        core_session,
                        source,
                        task.id,
                        semantic_normalizer=self.semantic_normalizer,
                    )
            if task.status == "running":
                task.status = "succeeded"
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                ingestion.advance_checkpoint(task.id)
                record_source_success(session, source)
                session.add(
                    CrawlLogEntry(
                        crawl_task_id=task.id,
                        level="info",
                        event_code="task_succeeded",
                        message="collection and quality gate completed",
                    )
                )
                session.commit()
            session.refresh(source)
            return self._task_view(task, source)

    def queue_source(
        self, source_code: str, *, browser_mode: str = "default"
    ) -> CrawlTaskAdminView:
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            adapter = self.adapter_factory(source.adapter_type)
            adapter.assert_live_collection_allowed(definition_from_model(source))
            if not isinstance((source.config or {}).get("promotion_mapping"), dict):
                raise SourcePolicyError(f"source {source.code} has no promotion mapping")
            self._require_core_session_factory()
            active = session.scalar(
                select(CrawlTask).where(
                    CrawlTask.source_id == source.id,
                    CrawlTask.status.in_(["pending", "running"]),
                )
            )
            if active is not None:
                raise ValueError("该来源已有采集任务正在执行")
            task = IngestionService(session).create_live_task(
                source.code, browser_mode=browser_mode
            )
            return self._task_view(task, source)

    def execute_task(self, task_id: int) -> None:
        with self.session_factory() as session:
            task = session.get(CrawlTask, task_id)
            if task is None:
                return
            source = session.get(DataSource, task.source_id)
            if source is None:
                return
            adapter = self.adapter_factory(source.adapter_type)
            task = IngestionService(session).run_live_task(
                task_id, adapter, finalize_success=False
            )
            if task.status == "running" and task.records_stored:
                try:
                    with self._require_core_session_factory()() as core_session:
                        promote_task_records(
                            session,
                            core_session,
                            source,
                            task.id,
                            semantic_normalizer=self.semantic_normalizer,
                        )
                except Exception as exc:
                    task.status = "failed"
                    task.error_type = "promotion_failed"
                    task.error_message = f"质量门处理失败：{type(exc).__name__}"
                    task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    state = record_source_failure(
                        session, source, task.error_type, task.error_message
                    )
                    session.add(
                        CrawlLogEntry(
                            crawl_task_id=task.id,
                            level="warning",
                            event_code="source_recovery_scheduled",
                            message="source health updated after quality pipeline failure",
                            context={
                                "failure_type": state.last_failure_type,
                                "health_status": state.health_status,
                                "next_retry_at": (
                                    state.next_retry_at.isoformat()
                                    if state.next_retry_at
                                    else None
                                ),
                                "recovery_action": state.recovery_action,
                            },
                        )
                    )
                    session.commit()
                    raise
            if task.status == "running":
                task.status = "succeeded"
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                IngestionService(session).advance_checkpoint(task.id)
                record_source_success(session, source)
                session.add(
                    CrawlLogEntry(
                        crawl_task_id=task.id,
                        level="info",
                        event_code="task_succeeded",
                        message="collection and quality gate completed",
                    )
                )
                session.commit()
            if task.batch_id:
                batch = session.get(CrawlBatch, task.batch_id)
                if batch is not None:
                    rows = list(session.scalars(select(CrawlTask).where(CrawlTask.batch_id == batch.id)))
                    batch.completed_channels = sum(item.status not in {"pending", "running"} for item in rows)
                    batch.failed_channels = sum(item.status == "failed" for item in rows)
                    if batch.completed_channels >= batch.requested_channels:
                        batch.status = "failed" if batch.failed_channels else "succeeded"
                        batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    else:
                        batch.status = "running"
                    session.commit()

    def list_strategy_repair_candidates(
        self, source_code: str | None = None, limit: int = 50
    ) -> list[StrategyRepairCandidateView]:
        with self.session_factory() as session:
            statement = (
                select(StrategyRepairCandidate, DataSource)
                .join(DataSource, DataSource.id == StrategyRepairCandidate.source_id)
                .order_by(StrategyRepairCandidate.id.desc())
                .limit(limit)
            )
            if source_code:
                statement = statement.where(DataSource.code == source_code)
            return [
                self._repair_candidate_view(candidate, source)
                for candidate, source in session.execute(statement).all()
            ]

    def get_strategy_repair_evidence(
        self, source_code: str
    ) -> StrategyRepairEvidenceView:
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            if source.adapter_type != "company_channel":
                raise ValueError("当前只支持为公司招聘渠道生成声明式修复证据")
            adapter = self.adapter_factory(source.adapter_type)
            if not callable(getattr(adapter, "capture_repair_evidence", None)):
                raise ValueError("当前渠道没有可用的公司渠道采集器")
            failed_task = session.scalar(
                select(CrawlTask)
                .where(CrawlTask.source_id == source.id, CrawlTask.status == "failed")
                .order_by(CrawlTask.id.desc())
                .limit(1)
            )
            definition = definition_from_model(source)
        evidence = adapter.capture_repair_evidence(definition)
        return StrategyRepairEvidenceView(
            source_code=source.code,
            source_name=source.name,
            adapter_type=source.adapter_type,
            failure_signature=(
                f"{failed_task.error_type}: {failed_task.error_message}"[:300]
                if failed_task
                else None
            ),
            evidence=_sanitized_configuration(evidence),
        )

    def create_strategy_repair_candidate(
        self, source_code: str, request: StrategyRepairCandidateCreate
    ) -> StrategyRepairCandidateView:
        strategy = validate_strategy_document(request.proposed_strategy)
        with self.session_factory() as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            if source is None:
                raise LookupError(f"unknown data source: {source_code}")
            if source.adapter_type != "company_channel":
                raise ValueError("当前仅支持为公司招聘渠道创建声明式修复候选")
            failure_task = None
            if request.failure_task_id is not None:
                failure_task = session.get(CrawlTask, request.failure_task_id)
                if failure_task is None or failure_task.source_id != source.id:
                    raise ValueError("失败任务不属于当前渠道")
            if failure_task is None:
                failure_task = session.scalar(
                    select(CrawlTask)
                    .where(CrawlTask.source_id == source.id, CrawlTask.status == "failed")
                    .order_by(CrawlTask.id.desc())
                    .limit(1)
                )
            active = session.scalar(
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
                failure_task_id=failure_task.id if failure_task else None,
                base_strategy_version=active.version if active else None,
                status="candidate",
                origin=request.origin,
                failure_signature=(
                    f"{failure_task.error_type}: {failure_task.error_message}"[:160]
                    if failure_task
                    else None
                ),
                proposed_strategy=strategy,
                created_by=request.actor,
            )
            session.add(candidate)
            session.commit()
            session.refresh(candidate)
            return self._repair_candidate_view(candidate, source)

    def replay_strategy_repair_candidate(
        self, candidate_id: int
    ) -> StrategyRepairCandidateView:
        with self.session_factory() as session:
            candidate = session.get(StrategyRepairCandidate, candidate_id)
            if candidate is None:
                raise LookupError(f"unknown repair candidate: {candidate_id}")
            if candidate.status not in {"candidate", "replay_failed", "canary_passed"}:
                raise ValueError("当前修复候选状态不允许回放")
            source = session.get(DataSource, candidate.source_id)
            if source is None:
                raise LookupError(f"unknown data source id: {candidate.source_id}")
            adapter = self.adapter_factory(source.adapter_type)
            definition = definition_from_model(source)
            adapter.assert_live_collection_allowed(definition)
            config = dict(definition.config)
            proposed = dict(candidate.proposed_strategy)
            pagination = dict(proposed.get("pagination") or {})
            pagination["max_records"] = min(int(pagination.get("max_records", 20)), 20)
            pagination["max_rounds"] = min(int(pagination.get("max_rounds", 3)), 3)
            proposed["pagination"] = pagination
            config["_collection_strategy"] = proposed
            config["_runtime"] = {
                "browser_mode": "headless",
                "browser_mode_source": "repair_canary",
                "strategy_source": "repair_candidate",
                "repair_candidate_id": candidate.id,
            }
            replay_definition = definition.model_copy(update={"config": config})
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                snapshot = adapter.fetch(replay_definition)
                result = adapter.parse(replay_definition, snapshot)
                record_count = len(result.records)
                complete_count = sum(
                    _record_has_meaningful_detail(record) for record in result.records
                )
                completeness = complete_count / record_count if record_count else 0.0
                passed = record_count > 0 and completeness >= 0.8
                candidate.replay_summary = {
                    "record_count": record_count,
                    "detail_complete_count": complete_count,
                    "detail_completeness": round(completeness, 4),
                    "transport": _sanitized_configuration(snapshot.transport_metadata),
                    "warnings": result.warnings[:20],
                }
                candidate.canary_summary = {
                    "passed": passed,
                    "criteria": {
                        "minimum_records": 1,
                        "minimum_detail_completeness": 0.8,
                        "maximum_records": 20,
                        "maximum_rounds": 3,
                    },
                }
                candidate.status = "canary_passed" if passed else "replay_failed"
            except Exception as exc:
                candidate.status = "replay_failed"
                candidate.replay_summary = {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                }
                candidate.canary_summary = {"passed": False}
            candidate.replayed_at = now
            session.commit()
            session.refresh(candidate)
            return self._repair_candidate_view(candidate, source)

    def approve_strategy_repair_candidate(
        self, candidate_id: int, request: StrategyRepairReview
    ) -> StrategyRepairCandidateView:
        with self.session_factory() as session:
            candidate = session.get(StrategyRepairCandidate, candidate_id)
            if candidate is None:
                raise LookupError(f"unknown repair candidate: {candidate_id}")
            if candidate.status != "canary_passed":
                raise ValueError("只有通过回放 Canary 的候选才能批准")
            source = session.get(DataSource, candidate.source_id)
            if source is None:
                raise LookupError(f"unknown data source id: {candidate.source_id}")
            active_versions = list(
                session.scalars(
                    select(CollectionStrategyVersion).where(
                        CollectionStrategyVersion.source_id == source.id,
                        CollectionStrategyVersion.status == "active",
                    )
                )
            )
            for active in active_versions:
                active.status = "superseded"
            current_max = int(
                session.scalar(
                    select(func.max(CollectionStrategyVersion.version)).where(
                        CollectionStrategyVersion.source_id == source.id
                    )
                )
                or 0
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(
                CollectionStrategyVersion(
                    source_id=source.id,
                    version=current_max + 1,
                    status="active",
                    origin="repair_candidate",
                    strategy=candidate.proposed_strategy,
                    evidence={"repair_candidate_id": candidate.id},
                    validation_summary=candidate.replay_summary,
                    created_by=request.actor,
                    activated_at=now,
                    last_validated_at=now,
                )
            )
            candidate.status = "approved"
            candidate.reviewed_by = request.actor
            candidate.approved_at = now
            clear_source_recovery_after_repair(session, source)
            session.commit()
            session.refresh(candidate)
            return self._repair_candidate_view(candidate, source)

    def rollback_strategy_repair_candidate(
        self, candidate_id: int, request: StrategyRepairReview
    ) -> StrategyRepairCandidateView:
        with self.session_factory() as session:
            candidate = session.get(StrategyRepairCandidate, candidate_id)
            if candidate is None:
                raise LookupError(f"unknown repair candidate: {candidate_id}")
            if candidate.status != "approved":
                raise ValueError("只有已批准的修复候选可以回滚")
            source = session.get(DataSource, candidate.source_id)
            assert source is not None
            versions = list(
                session.scalars(
                    select(CollectionStrategyVersion)
                    .where(CollectionStrategyVersion.source_id == source.id)
                    .order_by(CollectionStrategyVersion.version.desc())
                )
            )
            repaired = next(
                (
                    version
                    for version in versions
                    if (version.evidence or {}).get("repair_candidate_id") == candidate.id
                    and version.status == "active"
                ),
                None,
            )
            if repaired is None:
                raise ValueError("当前修复版本已不是激活版本，无法回滚")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            repaired.status = "invalidated"
            repaired.invalidated_at = now
            previous = next(
                (
                    version
                    for version in versions
                    if version.version < repaired.version
                    and version.status in {"superseded", "invalidated"}
                ),
                None,
            )
            if previous is not None:
                previous.status = "active"
                previous.activated_at = now
            candidate.status = "rolled_back"
            candidate.reviewed_by = request.actor
            candidate.rolled_back_at = now
            state = record_source_failure(
                session, source, "selector_changed", "已回滚采集策略，需要重新验证渠道"
            )
            state.next_retry_at = None
            session.commit()
            session.refresh(candidate)
            return self._repair_candidate_view(candidate, source)

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
    semantic_normalizer = None
    semantic_enabled = os.getenv("MARKET_SEMANTIC_NORMALIZATION_ENABLED", "true").strip().lower()
    internal_token = os.getenv("MARKET_INTERNAL_TOKEN", "").strip()
    if semantic_enabled in {"1", "true", "yes", "on"} and internal_token:
        semantic_normalizer = BackendSemanticNormalizer(
            os.getenv(
                "MARKET_SEMANTIC_NORMALIZATION_URL",
                "http://127.0.0.1:8000/api/internal/market/semantic-normalize",
            ).strip(),
            internal_token,
        )
    runtime = MarketAdminRuntime(
        make_session_factory(raw_engine),
        core_session_factory=core_session_factory,
        semantic_normalizer=semantic_normalizer,
    )
    registry_path = os.getenv("MARKET_SOURCE_REGISTRY_PATH", str(ROOT / "sources" / "registry.json"))
    runtime.sync_registry(registry_path)
    return runtime, engines
