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
from market_data.errors import QualityGateError
from market_data.models.core import Job, JobSource
from market_data.models.raw import CrawlLogEntry, CrawlTask, RawRecord
from market_data.schemas import AdapterResult, CorePromotionInput, SourceDefinition, SourceSnapshot
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
        self.assertEqual(["task_started", "task_failed"], log_codes)

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
        self.assertEqual(0, count)


if __name__ == "__main__":
    unittest.main()
