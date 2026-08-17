from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from market_data.adapters import StructuredApiAdapter
from market_data.adapters.base import SourceAdapter
from market_data.db import CoreBase, RawBase
from market_data.errors import QualityGateError, SourcePolicyError
from market_data.models.core import Job, JobSource
from market_data.models.raw import (
    CollectionStrategyVersion,
    CrawlLogEntry,
    CrawlTask,
    DataSource,
    RawRecord,
    SourceOperationalState,
)
from market_data.schemas import (
    AdapterResult,
    CorePromotionInput,
    RawRecordInput,
    SourceDefinition,
    SourceSnapshot,
)
from market_data.services.core import promote_raw_candidate, promote_validated_job
from market_data.services.ingestion import IngestionService
from market_data.services.registry import load_source_registry, upsert_sources


ROOT = Path(__file__).resolve().parents[1]
FETCHED_AT = datetime.fromisoformat("2026-08-15T08:00:00+00:00")


class FailingAdapter(SourceAdapter):
    adapter_type = "api"

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        raise RuntimeError("synthetic fixture parse failure")

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        raise RuntimeError("not called")


class StrategyDiscoveryAdapter(SourceAdapter):
    adapter_type = "company_channel"

    def __init__(self) -> None:
        self.fetch_configs: list[dict] = []

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.fetch_configs.append(dict(source.config))
        return SourceSnapshot(
            source_url="https://jobs.example.invalid/campus",
            content_type="application/json",
            content={"records": [{"id": "job-1"}]},
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={
                "attempt": 1,
                "pagination_mode": "next_button",
                "pagination_action": "clicked:button.next-page",
                "pagination_stop_reason": "no_more_items",
                "parser_mode": "json_fixture",
                "matched_selector": "article.job-card",
                "records_discovered": 1,
                "batches_loaded": 2,
                "reported_total": 1,
                "detail_complete_count": 1,
                "detail_partial_count": 0,
                "detail_missing_count": 0,
                "detail_mode": "detail_page",
                "detail_selectors": ["section.job-detail"],
                "browser_mode": "visible",
                "browser_mode_source": "channel_default",
            },
        )

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        return AdapterResult(
            adapter_type="company_channel",
            adapter_version="test",
            source_code=source.code,
            records=[
                RawRecordInput(
                    external_id="job-1",
                    source_url="https://jobs.example.invalid/campus/job-1",
                    fetched_at=FETCHED_AT,
                    http_status=200,
                    content_type="application/json",
                    raw_payload={
                        "title": "后端开发实习生",
                        "responsibilities": "负责服务端功能开发、单元测试与运行质量跟踪。",
                        "requirements": "本科及以上学历，熟悉 Python 和 SQL。",
                    },
                )
            ],
        )


class StrategyFailureAdapter(SourceAdapter):
    adapter_type = "company_channel"

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        raise RuntimeError("synthetic selector drift")

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        raise AssertionError("parse must not run after fetch failure")


class PipelineIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.raw_engine = create_engine(f"sqlite:///{root / 'raw.sqlite3'}")
        self.core_engine = create_engine(f"sqlite:///{root / 'core.sqlite3'}")
        RawBase.metadata.create_all(self.raw_engine)
        CoreBase.metadata.create_all(self.core_engine)
        self.sources = load_source_registry(ROOT / "sources/registry.json")
        with Session(self.raw_engine) as session:
            upsert_sources(session, self.sources)

    def tearDown(self) -> None:
        self.raw_engine.dispose()
        self.core_engine.dispose()
        self.tempdir.cleanup()

    def api_snapshot(self) -> SourceSnapshot:
        content = json.loads(
            (ROOT / "tests/fixtures/structured_api.json").read_text(encoding="utf-8")
        )
        return SourceSnapshot(
            source_url="https://api.recruit.example.invalid/jobs",
            content_type="application/json",
            content=content,
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={"mode": "fixture", "synthetic": True},
        )

    def create_company_channel_source(self, session: Session) -> DataSource:
        source = DataSource(
            code="company-channel-strategy-test",
            name="测试企业·校园招聘",
            adapter_type="company_channel",
            base_url="https://jobs.example.invalid/campus",
            allowed_hosts=["jobs.example.invalid"],
            config={
                "browser_mode": "headless",
                "pagination": {"mode": "auto"},
                "strategy_failure_threshold": 2,
            },
            terms_review_status="approved",
            enabled=True,
            configuration_status="ready",
            channel_type="campus",
            source_kind="company_channel",
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        return source

    def test_repeat_snapshot_is_deduplicated_and_updates_task_metrics(self) -> None:
        with Session(self.raw_engine) as session:
            service = IngestionService(session)
            first = service.run_snapshot(
                "structured-api-fixture", StructuredApiAdapter(), self.api_snapshot()
            )
            second = service.run_snapshot(
                "structured-api-fixture", StructuredApiAdapter(), self.api_snapshot()
            )
            count = session.scalar(select(func.count()).select_from(RawRecord))
            self.assertEqual("succeeded", first.status)
            self.assertEqual(2, first.records_stored)
            self.assertEqual("succeeded", second.status)
            self.assertEqual(0, second.records_stored)
            self.assertEqual(2, second.duplicate_records)
            self.assertEqual(2, count)

    def test_collector_position_does_not_create_a_new_raw_version(self) -> None:
        with Session(self.raw_engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "structured-api-fixture")
            )
            self.assertIsNotNone(source)
            service = IngestionService(session)
            first_task = service._start_task(source, "test")
            base_record = RawRecordInput(
                external_id="stable-job-1",
                source_url="https://api.recruit.example.invalid/jobs/stable-job-1",
                fetched_at=FETCHED_AT,
                content_type="application/json",
                raw_payload={"title": "后端开发", "_record_index": 0},
            )
            service._store_record(source, first_task, base_record)
            session.commit()

            second_task = service._start_task(source, "test")
            moved_record = base_record.model_copy(
                update={"raw_payload": {"title": "后端开发", "_record_index": 17}}
            )
            service._store_record(source, second_task, moved_record)
            session.commit()

            self.assertEqual(1, session.scalar(select(func.count()).select_from(RawRecord)))
            self.assertEqual(0, second_task.records_stored)
            self.assertEqual(1, second_task.duplicate_records)

    def test_changed_job_payload_creates_a_new_raw_version(self) -> None:
        with Session(self.raw_engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "structured-api-fixture")
            )
            self.assertIsNotNone(source)
            service = IngestionService(session)
            first_task = service._start_task(source, "test")
            base_record = RawRecordInput(
                external_id="stable-job-2",
                source_url="https://api.recruit.example.invalid/jobs/stable-job-2",
                fetched_at=FETCHED_AT,
                content_type="application/json",
                raw_payload={"title": "后端开发", "requirements": "Java"},
            )
            service._store_record(source, first_task, base_record)
            session.commit()

            second_task = service._start_task(source, "test")
            changed_record = base_record.model_copy(
                update={
                    "raw_payload": {
                        "title": "后端开发",
                        "requirements": "Java、MySQL",
                    }
                }
            )
            service._store_record(source, second_task, changed_record)
            session.commit()

            self.assertEqual(2, session.scalar(select(func.count()).select_from(RawRecord)))
            self.assertEqual(1, second_task.records_stored)
            self.assertEqual(0, second_task.duplicate_records)

    def test_adapter_failure_isolated_from_raw_records_and_core(self) -> None:
        with Session(self.raw_engine) as raw_session:
            task = IngestionService(raw_session).run_snapshot(
                "structured-api-fixture", FailingAdapter(), self.api_snapshot()
            )
            raw_count = raw_session.scalar(select(func.count()).select_from(RawRecord))
            task_count = raw_session.scalar(select(func.count()).select_from(CrawlTask))
            log_codes = list(
                raw_session.scalars(
                    select(CrawlLogEntry.event_code)
                    .where(CrawlLogEntry.crawl_task_id == task.id)
                    .order_by(CrawlLogEntry.id)
                )
            )
        with Session(self.core_engine) as core_session:
            core_count = core_session.scalar(select(func.count()).select_from(Job))
        self.assertEqual("failed", task.status)
        self.assertEqual("RuntimeError", task.error_type)
        self.assertEqual(1, task_count)
        self.assertEqual(0, raw_count)
        self.assertEqual(0, core_count)
        self.assertEqual(
            ["task_started", "task_failed", "source_recovery_scheduled"],
            log_codes,
        )

    def test_explicit_core_promotion_always_creates_source_lineage(self) -> None:
        with Session(self.raw_engine) as raw_session:
            task = IngestionService(raw_session).run_snapshot(
                "structured-api-fixture", StructuredApiAdapter(), self.api_snapshot()
            )
            raw_record = raw_session.scalar(select(RawRecord).order_by(RawRecord.id))
            self.assertIsNotNone(raw_record)
            source_id = task.source_id
        assert raw_record is not None
        payload = CorePromotionInput(
            company_name="脱敏示例科技有限公司",
            title="数据分析培训生",
            normalized_title="数据分析师",
            location_text="上海",
            department="数据智能部",
            province="上海市",
            district="浦东新区",
            address="张江高科技园区",
            education_requirement="本科及以上",
            experience_requirement="应届毕业生",
            responsibilities="负责经营数据分析、经营报表建设、指标体系梳理、业务专题分析与跨部门协作，并持续跟踪数据质量和改进结果。",
            benefits="导师制、补充医疗",
            major_requirement="统计学、计算机相关专业",
            language_requirement="英语四级",
            certificate_requirement="CET-4",
            work_time="周一至周五",
            salary_payment="月薪",
            industry_requirement="科技互联网",
            job_level="校招培训生",
            apply_url="https://api.recruit.example.invalid/jobs/api-1001/apply",
            detail_url="https://api.recruit.example.invalid/jobs/api-1001",
            raw_record_id=raw_record.id,
            data_source_id=source_id,
            source_job_id=raw_record.external_id,
            source_url=raw_record.source_url,
            content_hash=raw_record.content_hash,
            fetched_at=raw_record.fetched_at,
            first_seen_at=raw_record.first_seen_at,
            last_seen_at=raw_record.last_seen_at,
        )
        with Session(self.raw_engine) as raw_session, Session(self.core_engine) as core_session:
            job = promote_raw_candidate(raw_session, core_session, payload)
            lineage = core_session.scalar(select(JobSource).where(JobSource.job_id == job.id))
            raw_status = raw_session.get(RawRecord, raw_record.id).validation_status
            self.assertIsNotNone(lineage)
            assert lineage is not None
            self.assertEqual(raw_record.id, lineage.raw_record_id)
            self.assertEqual(raw_record.source_url, lineage.source_url)
            self.assertEqual(raw_record.fetched_at, lineage.fetched_at)
            self.assertEqual("career-guardian-job-core-v1", job.gate_policy_version)
            self.assertEqual("open", job.status)
            self.assertEqual("数据智能部", job.department)
            self.assertEqual("本科及以上", job.education_requirement)
            self.assertEqual("应届毕业生", job.experience_requirement)
            self.assertIn("经营报表建设", job.responsibilities)
            self.assertEqual("统计学、计算机相关专业", job.major_requirement)
            self.assertEqual("https://api.recruit.example.invalid/jobs/api-1001/apply", job.apply_url)
            self.assertEqual("promoted", raw_status)

    def test_raw_to_core_cannot_bypass_quality_gate(self) -> None:
        payload = CorePromotionInput(
            company_name="脱敏示例科技有限公司",
            title="数据分析培训生",
            location_text="上海",
            raw_record_id=99,
            data_source_id=9,
            source_url="http://jobs.example.invalid/99",
            content_hash="a" * 64,
            fetched_at=FETCHED_AT,
            first_seen_at=FETCHED_AT,
            last_seen_at=FETCHED_AT,
        )
        with Session(self.core_engine) as core_session:
            with self.assertRaises(QualityGateError) as error:
                promote_validated_job(core_session, payload)
            count = core_session.scalar(select(func.count()).select_from(Job))
        self.assertIn("live_source_requires_https", error.exception.reason_codes)
        self.assertIn("live_job_content_missing", error.exception.reason_codes)
        self.assertEqual(0, count)

    def test_live_job_without_meaningful_details_is_quarantined(self) -> None:
        payload = CorePromotionInput(
            company_name="脱敏示例科技有限公司",
            title="空壳岗位",
            location_text="上海",
            raw_record_id=100,
            data_source_id=10,
            source_url="https://jobs.example.invalid/100",
            content_hash="b" * 64,
            fetched_at=FETCHED_AT,
            first_seen_at=FETCHED_AT,
            last_seen_at=FETCHED_AT,
        )
        with Session(self.core_engine) as core_session:
            with self.assertRaises(QualityGateError) as error:
                promote_validated_job(core_session, payload)
            count = core_session.scalar(select(func.count()).select_from(Job))
        self.assertIn("live_job_content_missing", error.exception.reason_codes)
        self.assertEqual(0, count)

    def test_discovered_collection_strategy_is_versioned_and_reused(self) -> None:
        with Session(self.raw_engine) as session:
            self.create_company_channel_source(session)
            service = IngestionService(session)
            adapter = StrategyDiscoveryAdapter()

            first = service.create_live_task("company-channel-strategy-test")
            self.assertIsNone(first.strategy_version)
            self.assertEqual("runtime_discovery", first.strategy_source)
            first = service.run_live_task(first.id, adapter, finalize_success=False)
            self.assertEqual("visible", first.browser_mode)
            reconciliation = session.scalar(
                select(CrawlLogEntry).where(
                    CrawlLogEntry.crawl_task_id == first.id,
                    CrawlLogEntry.event_code == "browser_mode_reconciled",
                )
            )
            self.assertIsNotNone(reconciliation)
            assert reconciliation is not None
            self.assertEqual("headless", reconciliation.context["planned_browser_mode"])
            self.assertEqual("visible", reconciliation.context["actual_browser_mode"])

            active = session.scalar(
                select(CollectionStrategyVersion).where(
                    CollectionStrategyVersion.source_id == first.source_id,
                    CollectionStrategyVersion.status == "active",
                )
            )
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(1, active.version)
            self.assertEqual("runtime_discovery", active.origin)
            self.assertEqual("next_button", active.strategy["pagination"]["mode"])
            self.assertEqual(
                ["button.next-page"], active.strategy["pagination"]["next_selectors"]
            )
            self.assertEqual("detail_page", active.strategy["detail_mode"])
            self.assertEqual(
                ["section.job-detail"], active.strategy["detail_selectors"]
            )

            second = service.create_live_task("company-channel-strategy-test")
            self.assertEqual(1, second.strategy_version)
            self.assertEqual("active_version", second.strategy_source)
            service.run_live_task(second.id, adapter, finalize_success=False)
            reused = adapter.fetch_configs[-1]["_collection_strategy"]
            self.assertEqual("next_button", reused["pagination"]["mode"])
            self.assertEqual("detail_page", reused["detail_mode"])
            self.assertEqual(["section.job-detail"], reused["detail_selectors"])
            versions = session.scalar(
                select(func.count()).select_from(CollectionStrategyVersion)
            )
            self.assertEqual(1, versions)

    def test_repeated_strategy_failures_invalidate_it_and_trigger_rediscovery(self) -> None:
        with Session(self.raw_engine) as session:
            self.create_company_channel_source(session)
            service = IngestionService(session)
            discovery = StrategyDiscoveryAdapter()
            initial = service.create_live_task("company-channel-strategy-test")
            service.run_live_task(initial.id, discovery, finalize_success=False)

            for expected_failures in (1, 2):
                task = service.create_live_task("company-channel-strategy-test")
                self.assertEqual(1, task.strategy_version)
                failed = service.run_live_task(task.id, StrategyFailureAdapter())
                self.assertEqual("failed", failed.status)
                strategy = session.scalar(
                    select(CollectionStrategyVersion).where(
                        CollectionStrategyVersion.source_id == task.source_id,
                        CollectionStrategyVersion.version == 1,
                    )
                )
                assert strategy is not None
                self.assertEqual(expected_failures, strategy.failure_count)
                operational_state = session.scalar(
                    select(SourceOperationalState).where(
                        SourceOperationalState.source_id == task.source_id
                    )
                )
                assert operational_state is not None
                operational_state.next_retry_at = None
                session.commit()

            self.assertEqual("invalidated", strategy.status)
            rediscovery = service.create_live_task("company-channel-strategy-test")
            self.assertIsNone(rediscovery.strategy_version)
            self.assertEqual("runtime_discovery", rediscovery.strategy_source)

    def test_collection_failure_creates_cooldown_and_recovery_guidance(self) -> None:
        with Session(self.raw_engine) as session:
            self.create_company_channel_source(session)
            service = IngestionService(session)
            task = service.create_live_task("company-channel-strategy-test")
            failed = service.run_live_task(task.id, StrategyFailureAdapter())

            self.assertEqual("failed", failed.status)
            state = session.scalar(
                select(SourceOperationalState).where(
                    SourceOperationalState.source_id == task.source_id
                )
            )
            assert state is not None
            self.assertEqual("degraded", state.health_status)
            self.assertEqual("selector_changed", state.last_failure_type)
            self.assertEqual("repair_strategy", state.recovery_action)
            self.assertEqual("open", state.alert_status)
            self.assertIsNotNone(state.next_retry_at)
            with self.assertRaises(SourcePolicyError):
                service.create_live_task("company-channel-strategy-test")


if __name__ == "__main__":
    unittest.main()
