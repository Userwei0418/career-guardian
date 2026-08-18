from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.api import StructuredApiAdapter
from market_data.adapters.base import SourceAdapter
from market_data.app import create_app
from market_data.db import CoreBase, RawBase, make_engine, make_session_factory
from market_data.management import MarketAdminRuntime
from market_data.models.core import Job, QualityGatePolicy
from market_data.models.raw import (
    CollectionStrategyVersion,
    CrawlLogEntry,
    CrawlTask,
    DataSource,
    RawRecord,
    SourceCollectionCheckpoint,
    StrategyRepairCandidate,
)
from market_data.providers import CoreMarketProvider, FixtureMarketProvider
from market_data.schemas import (
    AdapterResult,
    RawRecordInput,
    SourceDefinition,
    SourceSnapshot,
)


ROOT = Path(__file__).resolve().parents[1]
FETCHED_AT = datetime.fromisoformat("2026-08-15T08:00:00+00:00")


class FixedSnapshotAdapter(StructuredApiAdapter):
    def __init__(self, snapshot: SourceSnapshot):
        self.snapshot = snapshot

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        return self.snapshot


class RepairCanaryAdapter(SourceAdapter):
    adapter_type = "company_channel"

    def capture_repair_evidence(self, source: SourceDefinition) -> dict[str, object]:
        return {
            "page_title": "校园招聘",
            "final_url": str(source.base_url),
            "http_status": 200,
            "repeated_elements": [
                {
                    "tag": "article",
                    "classes": ["job-card"],
                    "count": 12,
                    "sample_text": "后端开发工程师",
                }
            ],
            "interactive_controls": [
                {"tag": "button", "text": "下一页", "aria_label": "", "classes": ["next"]}
            ],
        }

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        return SourceSnapshot(
            source_url=source.base_url,
            content_type="application/json",
            content={"records": [{"id": "repair-job-1"}]},
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={
                "pagination_mode": "next_button",
                "pagination_stop_reason": "canary_limit",
            },
        )

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        return AdapterResult(
            adapter_type="company_channel",
            adapter_version="repair-canary-v1",
            source_code=source.code,
            records=[
                RawRecordInput(
                    external_id="repair-job-1",
                    source_url=snapshot.source_url,
                    fetched_at=snapshot.fetched_at,
                    http_status=200,
                    content_type="application/json",
                    raw_payload={
                        "title": "后端开发工程师",
                        "responsibilities": "负责核心系统的设计、开发、测试与性能优化，参与技术方案评审。",
                        "requirements": "熟悉 Python 和 SQL，具备良好的工程实践、沟通与问题分析能力。",
                    },
                )
            ],
        )


class MarketManagementApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        database_path = Path(self.tempdir.name) / "market_raw.sqlite3"
        core_database_path = Path(self.tempdir.name) / "market_core.sqlite3"
        self.engine = make_engine(f"sqlite:///{database_path}")
        self.core_engine = make_engine(f"sqlite:///{core_database_path}")
        RawBase.metadata.create_all(self.engine)
        CoreBase.metadata.create_all(self.core_engine)
        self.runtime = MarketAdminRuntime(
            make_session_factory(self.engine),
            core_session_factory=make_session_factory(self.core_engine),
        )
        self.runtime.sync_registry(ROOT / "sources" / "registry.json")
        provider = FixtureMarketProvider(ROOT / "fixtures" / "integrated_graduate_case.json")
        self.client = TestClient(
            create_app(provider=provider, management_runtime=self.runtime, admin_token="test-admin-token")
        )
        self.headers = {"X-Market-Admin-Token": "test-admin-token"}

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()
        self.core_engine.dispose()
        self.tempdir.cleanup()

    def wait_for_task(self, task_id: int) -> dict:
        for _ in range(200):
            tasks = self.client.get("/internal/admin/tasks", headers=self.headers).json()["tasks"]
            task = next(item for item in tasks if item["id"] == task_id)
            if task["status"] not in {"pending", "running"}:
                return task
            time.sleep(0.01)
        self.fail(f"crawl task {task_id} did not finish")

    def test_management_endpoints_require_internal_token_and_hide_raw_content(self) -> None:
        self.assertEqual(403, self.client.get("/internal/admin/sources").status_code)
        self.assertEqual(
            403,
            self.client.get(
                "/internal/admin/sources",
                headers={"X-Market-Admin-Token": "wrong"},
            ).status_code,
        )

        response = self.client.get("/internal/admin/sources", headers=self.headers)
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(0, response.json()["core_job_count"])
        sources = response.json()["sources"]
        self.assertGreaterEqual(len(sources), 5)
        self.assertTrue(all("config" not in source for source in sources))
        self.assertTrue(all("raw_payload" not in source for source in sources))
        self.assertTrue(all(not source["can_run"] for source in sources))

    def test_blocked_source_cannot_start_and_creates_no_task(self) -> None:
        response = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        self.assertEqual(409, response.status_code, response.text)
        tasks = self.client.get("/internal/admin/tasks", headers=self.headers).json()
        self.assertEqual(0, tasks["total"])

    def test_admin_approval_is_audited_and_survives_registry_sync(self) -> None:
        approved = self.client.put(
            "/internal/admin/sources/picc-campus-public-api",
            headers=self.headers,
            json={
                "terms_review_status": "approved",
                "enabled": True,
                "review_note": "reviewed for controlled test",
                "actor": "admin-test",
            },
        )
        self.assertEqual(200, approved.status_code, approved.text)
        self.assertTrue(approved.json()["enabled"])
        self.assertEqual("admin-test", approved.json()["terms_reviewed_by"])
        self.runtime.sync_registry(ROOT / "sources" / "registry.json")
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        source = next(item for item in sources if item["code"] == "picc-campus-public-api")
        self.assertTrue(source["enabled"])
        self.assertEqual("approved", source["terms_review_status"])

    def test_company_channel_view_groups_channels_and_supports_company_governance(self) -> None:
        response = self.client.get("/internal/admin/collection/companies", headers=self.headers)
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual(1, payload["total_companies"])
        self.assertEqual(3, payload["total_channels"])
        company = payload["companies"][0]
        self.assertEqual("picc", company["code"])
        self.assertEqual(3, company["channel_count"])
        self.assertEqual(0, company["runnable_channel_count"])

        approved = self.client.put(
            "/internal/admin/collection/companies/picc/governance",
            headers=self.headers,
            json={
                "enabled": True,
                "review_note": "company channels reviewed together",
                "actor": "admin-company-test",
            },
        )
        self.assertEqual(200, approved.status_code, approved.text)
        self.assertEqual(3, approved.json()["approved_channel_count"])
        self.assertEqual(3, approved.json()["runnable_channel_count"])
        self.assertTrue(all(item["can_run"] for item in approved.json()["channels"]))

    def test_source_cannot_be_enabled_without_approval(self) -> None:
        response = self.client.put(
            "/internal/admin/sources/picc-campus-public-api",
            headers=self.headers,
            json={
                "terms_review_status": "pending",
                "enabled": True,
                "review_note": "invalid",
                "actor": "admin-test",
            },
        )
        self.assertEqual(422, response.status_code, response.text)

    def test_source_configuration_is_safe_audited_and_survives_registry_sync(self) -> None:
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        current = next(item for item in sources if item["code"] == "picc-campus-public-api")
        payload = {
            "name": current["name"],
            "adapter_type": current["adapter_type"],
            "base_url": current["base_url"],
            "allowed_hosts": current["allowed_hosts"],
            "min_interval_seconds": 7,
            "timeout_seconds": 35,
            "max_retries": 3,
            "configuration": current["configuration"],
            "actor": "admin-config-test",
        }
        updated = self.client.put(
            "/internal/admin/sources/picc-campus-public-api/configuration",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual(7, updated.json()["min_interval_seconds"])
        self.assertEqual("admin-config-test", updated.json()["configuration_updated_by"])
        self.assertGreater(len(updated.json()["mapped_fields"]), 10)

        self.runtime.sync_registry(ROOT / "sources" / "registry.json")
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        persisted = next(item for item in sources if item["code"] == "picc-campus-public-api")
        self.assertEqual(7, persisted["min_interval_seconds"])

        rejected = self.client.put(
            "/internal/admin/sources/picc-campus-public-api/configuration",
            headers=self.headers,
            json={
                **payload,
                "configuration": {**payload["configuration"], "api_key": "must-not-persist"},
            },
        )
        self.assertEqual(422, rejected.status_code, rejected.text)
        self.assertIn("不能保存", rejected.text)

    def test_source_configuration_accepts_only_opaque_network_references(self) -> None:
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        current = next(item for item in sources if item["code"] == "picc-campus-public-api")
        payload = {
            "name": current["name"],
            "adapter_type": current["adapter_type"],
            "base_url": current["base_url"],
            "allowed_hosts": current["allowed_hosts"],
            "min_interval_seconds": current["min_interval_seconds"],
            "timeout_seconds": current["timeout_seconds"],
            "max_retries": current["max_retries"],
            "configuration": {
                **current["configuration"],
                "network_policy": {
                    "mode": "proxy_and_session",
                    "proxy_pool_id": "campus-cn-east",
                    "session_profile_id": "moka.public",
                },
            },
            "actor": "network-admin",
        }
        updated = self.client.put(
            "/internal/admin/sources/picc-campus-public-api/configuration",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual(
            payload["configuration"]["network_policy"],
            updated.json()["configuration"]["network_policy"],
        )

        for unsafe_policy in (
            {"mode": "proxy", "proxy_url": "http://user:pass@example.test:8080"},
            {"mode": "session", "cookie": "secret=value"},
        ):
            response = self.client.put(
                "/internal/admin/sources/picc-campus-public-api/configuration",
                headers=self.headers,
                json={
                    **payload,
                    "configuration": {
                        **payload["configuration"],
                        "network_policy": unsafe_policy,
                    },
                },
            )
            self.assertEqual(422, response.status_code, response.text)

    def test_approved_source_without_product_mapping_still_cannot_run(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(select(DataSource).where(DataSource.code == "hotjob-fixture"))
            assert source is not None
            source.enabled = True
            source.terms_review_status = "approved"
            session.commit()
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        source_view = next(item for item in sources if item["code"] == "hotjob-fixture")
        self.assertFalse(source_view["can_run"])
        self.assertEqual("来源尚未配置产品字段映射", source_view["blocked_reason"])
        response = self.client.post(
            "/internal/admin/sources/hotjob-fixture/runs", headers=self.headers
        )
        self.assertEqual(409, response.status_code, response.text)

    def test_approved_source_run_is_audited_and_deduplicated(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "structured-api-fixture")
            )
            assert source is not None
            source.enabled = True
            source.terms_review_status = "approved"
            source.config = {
                **source.config,
                "incremental": {
                    "enabled": True,
                    "ordering": "newest_first",
                    "recent_id_window": 100,
                    "full_refresh_every_runs": 10,
                },
            }
            session.commit()

        snapshot = SourceSnapshot(
            source_url="https://api.recruit.example.invalid/jobs",
            content_type="application/json",
            content=json.loads(
                (ROOT / "tests" / "fixtures" / "structured_api.json").read_text(encoding="utf-8")
            ),
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={"mode": "controlled-test"},
        )
        self.runtime.adapter_factory = lambda _adapter_type: FixedSnapshotAdapter(snapshot)

        first = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        first_task = self.wait_for_task(first.json()["id"])
        second = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        second_task = self.wait_for_task(second.json()["id"])
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual("pending", first.json()["status"])
        self.assertEqual(2, first_task["records_stored"])
        self.assertEqual(2, first_task["promoted_records"])
        self.assertEqual(0, first_task["quarantined_records"])
        self.assertEqual(200, second.status_code, second.text)
        self.assertEqual(0, second_task["records_stored"])
        self.assertEqual(2, second_task["duplicate_records"])
        self.assertEqual("full", first_task["collection_mode"])
        self.assertEqual("incremental", second_task["collection_mode"])
        with Session(self.engine) as session:
            checkpoint = session.scalar(select(SourceCollectionCheckpoint))
            assert checkpoint is not None
            self.assertEqual(second_task["id"], checkpoint.last_successful_task_id)
            self.assertEqual(1, checkpoint.successful_incremental_runs)
            self.assertEqual(2, len(checkpoint.cursor_payload["recent_external_ids"]))
            self.assertEqual(2, len(checkpoint.cursor_payload["recent_content_hashes"]))
            self.assertTrue(checkpoint.cursor_payload["published_high_watermark"])
            checkpoint.successful_incremental_runs = 10
            session.commit()

        third = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        third_task = self.wait_for_task(third.json()["id"])
        self.assertEqual(200, third.status_code, third.text)
        self.assertEqual("full", third_task["collection_mode"])
        with Session(self.engine) as session:
            checkpoint = session.scalar(select(SourceCollectionCheckpoint))
            assert checkpoint is not None
            self.assertEqual(third_task["id"], checkpoint.last_successful_task_id)
            self.assertEqual(0, checkpoint.successful_incremental_runs)

        detail_html = "<html><main>岗位职责：负责数据分析。任职要求：本科及以上。</main></html>"
        with Session(self.engine) as session:
            raw_evidence = session.scalar(
                select(RawRecord)
                .where(RawRecord.crawl_task_id == first_task["id"])
                .order_by(RawRecord.id)
            )
            assert raw_evidence is not None
            raw_evidence.raw_text = detail_html
            raw_evidence.raw_payload = {
                **dict(raw_evidence.raw_payload or {}),
                "_detail_text": "岗位职责：负责数据分析。任职要求：本科及以上。",
                "_detail_capture_mode": "configured_selector",
                "_detail_strategy": "detail_page",
                "_detail_selector": "main",
            }
            raw_evidence_id = raw_evidence.id
            session.commit()

        detail = self.client.get(
            f"/internal/admin/tasks/{first_task['id']}", headers=self.headers
        )
        self.assertEqual(200, detail.status_code, detail.text)
        detail_body = detail.json()
        self.assertEqual(2, detail_body["record_total"])
        self.assertEqual(2, len(detail_body["records"]))
        self.assertTrue(all(item["core_job_id"] for item in detail_body["records"]))
        self.assertTrue(all(item["title"] for item in detail_body["records"]))
        self.assertTrue(all(item["payload_preview"] for item in detail_body["records"]))
        evidence_summary = next(
            item for item in detail_body["records"] if item["id"] == raw_evidence_id
        )
        self.assertTrue(evidence_summary["raw_text_available"])
        self.assertEqual(len(detail_html), evidence_summary["raw_text_characters"])
        self.assertEqual("main", evidence_summary["detail_selector"])
        self.assertNotIn("raw_text", evidence_summary)
        self.assertIn(
            "quality_gate_completed",
            [item["event_code"] for item in detail_body["logs"]],
        )

        self.assertEqual(
            403,
            self.client.get(
                f"/internal/admin/raw-records/{raw_evidence_id}/evidence"
            ).status_code,
        )
        evidence = self.client.get(
            f"/internal/admin/raw-records/{raw_evidence_id}/evidence",
            headers=self.headers,
        )
        self.assertEqual(200, evidence.status_code, evidence.text)
        self.assertEqual(detail_html, evidence.json()["raw_text"])
        self.assertEqual("detail_page", evidence.json()["detail_strategy"])
        self.assertEqual("main", evidence.json()["detail_selector"])

        duplicate_detail = self.client.get(
            f"/internal/admin/tasks/{second_task['id']}", headers=self.headers
        ).json()
        self.assertEqual(0, duplicate_detail["record_total"])
        self.assertEqual([], duplicate_detail["records"])

        tasks = self.client.get("/internal/admin/tasks", headers=self.headers).json()
        self.assertEqual(3, tasks["total"])
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        source = next(item for item in sources if item["code"] == "structured-api-fixture")
        self.assertTrue(source["can_run"])
        self.assertEqual(2, source["raw_record_count"])
        self.assertEqual(2, source["gate_status_counts"]["promoted"])
        self.assertEqual("succeeded", source["last_task"]["status"])
        with Session(self.core_engine) as session:
            core_jobs = list(session.scalars(select(Job).order_by(Job.id)))
            self.assertEqual(2, len(core_jobs))
            core_jobs[0].quality_score = 99
            core_jobs[0].last_seen_at = datetime(2026, 8, 14, 8)
            core_jobs[0].published_at = datetime(2026, 8, 10, 8)
            core_jobs[1].quality_score = 50
            core_jobs[1].last_seen_at = datetime(2026, 8, 16, 8)
            core_jobs[1].published_at = datetime(2026, 8, 12, 8)
            session.commit()
            first_id, second_id = core_jobs[0].id, core_jobs[1].id
        core_provider = CoreMarketProvider(str(self.core_engine.url))
        newest_observed = core_provider.search_jobs(
            None, None, 10, sort_by="observed_desc"
        )
        earliest_published = core_provider.search_jobs(
            None, None, 10, sort_by="published_asc"
        )
        self.assertEqual(f"core:{second_id}", newest_observed.jobs[0].job_id)
        self.assertEqual("observed_desc", newest_observed.sort_by)
        self.assertEqual(f"core:{first_id}", earliest_published.jobs[0].job_id)
        self.assertEqual("published_asc", earliest_published.sort_by)
        core_provider.engine.dispose()
        source_summary = self.client.get(
            "/internal/admin/sources", headers=self.headers
        ).json()
        self.assertEqual(2, source_summary["core_job_count"])
        with Session(self.engine) as session:
            gate_logs = list(
                session.scalars(
                    select(CrawlLogEntry).where(
                        CrawlLogEntry.event_code == "quality_gate_completed"
                    )
                )
            )
            self.assertEqual(1, len(gate_logs))
            self.assertEqual(
                {
                    "promoted": 2,
                    "quarantined": 0,
                    "semantic_stage_attempts": 2,
                    "semantic_stage_status_counts": {"skipped": 2},
                    "semantic_llm_called": 0,
                },
                gate_logs[0].context,
            )

    def test_run_browser_mode_override_is_persisted_and_exposed(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "structured-api-fixture")
            )
            assert source is not None
            source.enabled = True
            source.terms_review_status = "approved"
            session.commit()

        snapshot = SourceSnapshot(
            source_url="https://api.recruit.example.invalid/jobs",
            content_type="application/json",
            content=json.loads(
                (ROOT / "tests" / "fixtures" / "structured_api.json").read_text(
                    encoding="utf-8"
                )
            ),
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={"mode": "controlled-test"},
        )
        self.runtime.adapter_factory = lambda _adapter_type: FixedSnapshotAdapter(snapshot)

        queued = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
            json={"browser_mode": "visible"},
        )
        self.assertEqual(200, queued.status_code, queued.text)
        self.assertEqual("visible", queued.json()["browser_mode"])
        self.assertEqual("run_override", queued.json()["browser_mode_source"])
        completed = self.wait_for_task(queued.json()["id"])
        self.assertEqual("visible", completed["browser_mode"])
        self.assertEqual("run_override", completed["browser_mode_source"])

        invalid = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
            json={"browser_mode": "unsupported"},
        )
        self.assertEqual(422, invalid.status_code, invalid.text)

    def test_new_records_with_invalid_product_mapping_are_quarantined(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "structured-api-fixture")
            )
            assert source is not None
            source.enabled = True
            source.terms_review_status = "approved"
            source.config = {
                **source.config,
                "promotion_mapping": {
                    **source.config["promotion_mapping"],
                    "title": {"path": "fieldThatDoesNotExist"},
                },
            }
            session.commit()

        snapshot = SourceSnapshot(
            source_url="https://api.recruit.example.invalid/jobs",
            content_type="application/json",
            content=json.loads(
                (ROOT / "tests" / "fixtures" / "structured_api.json").read_text(
                    encoding="utf-8"
                )
            ),
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={"mode": "controlled-test"},
        )
        self.runtime.adapter_factory = lambda _adapter_type: FixedSnapshotAdapter(snapshot)

        response = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        self.assertEqual(200, response.status_code, response.text)
        task = self.wait_for_task(response.json()["id"])
        self.assertEqual(0, task["promoted_records"])
        self.assertEqual(2, task["quarantined_records"])
        with Session(self.core_engine) as session:
            self.assertEqual(0, len(list(session.scalars(select(Job)))))
        with Session(self.engine) as session:
            records = list(session.scalars(select(RawRecord).order_by(RawRecord.id)))
            self.assertEqual(["quarantined", "quarantined"], [row.validation_status for row in records])
            self.assertTrue(
                all("candidate_mapping_invalid" in (row.validation_error or "") for row in records)
            )
            gate_log = session.scalar(
                select(CrawlLogEntry).where(
                    CrawlLogEntry.event_code == "quality_gate_completed"
                )
            )
            assert gate_log is not None
            self.assertEqual(
                {
                    "promoted": 0,
                    "quarantined": 2,
                    "semantic_stage_attempts": 2,
                    "semantic_stage_status_counts": {"skipped": 2},
                    "semantic_llm_called": 0,
                },
                gate_log.context,
            )
            self.assertIsNone(session.scalar(select(SourceCollectionCheckpoint)))
            checkpoint_log = session.scalar(
                select(CrawlLogEntry).where(
                    CrawlLogEntry.event_code == "collection_checkpoint_not_advanced"
                )
            )
            assert checkpoint_log is not None
            self.assertEqual(2, checkpoint_log.context["observed_external_id_count"])

    def test_quality_gate_draft_requires_preview_before_publish(self) -> None:
        current = self.client.get("/internal/admin/gate", headers=self.headers)
        self.assertEqual(200, current.status_code, current.text)
        active = current.json()["active"]
        self.assertEqual("career-guardian-job-core-v1", active["policy_version"])

        configuration = dict(active["configuration"])
        configuration["minimum_core_score"] = 60
        configuration["required_facts"] = [*configuration["required_facts"], "city"]
        draft = self.client.put(
            "/internal/admin/gate/draft",
            headers=self.headers,
            json={
                "configuration": configuration,
                "change_note": "提高岗位最低准入分",
                "actor": "admin-test",
            },
        )
        self.assertEqual(200, draft.status_code, draft.text)
        self.assertEqual("career-guardian-job-core-v2", draft.json()["draft"]["policy_version"])
        self.assertIn("city", draft.json()["draft"]["configuration"]["required_facts"])
        self.assertIsNone(draft.json()["draft"]["preview_summary"])

        blocked = self.client.post(
            "/internal/admin/gate/draft/publish",
            headers=self.headers,
            json={"actor": "admin-test"},
        )
        self.assertEqual(409, blocked.status_code, blocked.text)

        preview = self.client.post(
            "/internal/admin/gate/draft/preview", headers=self.headers
        )
        self.assertEqual(200, preview.status_code, preview.text)
        self.assertEqual(0, preview.json()["draft"]["preview_summary"]["sample_size"])

        published = self.client.post(
            "/internal/admin/gate/draft/publish",
            headers=self.headers,
            json={"actor": "admin-test"},
        )
        self.assertEqual(200, published.status_code, published.text)
        self.assertEqual("career-guardian-job-core-v2", published.json()["active"]["policy_version"])
        with Session(self.core_engine) as session:
            policies = list(session.scalars(select(QualityGatePolicy).order_by(QualityGatePolicy.id)))
            self.assertEqual(["archived", "active"], [policy.status for policy in policies])

    def test_quality_gate_rejects_invalid_weight_total(self) -> None:
        current = self.client.get("/internal/admin/gate", headers=self.headers).json()
        configuration = dict(current["active"]["configuration"])
        configuration["score_weights"] = {
            **configuration["score_weights"],
            "salary": 11,
        }
        response = self.client.put(
            "/internal/admin/gate/draft",
            headers=self.headers,
            json={"configuration": configuration, "change_note": "invalid", "actor": "admin-test"},
        )
        self.assertEqual(422, response.status_code, response.text)

    def test_strategy_repair_requires_declarative_canary_and_supports_rollback(self) -> None:
        source_code = "picc-campus-public-api"
        with Session(self.engine) as session:
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            assert source is not None
            source.adapter_type = "company_channel"
            source.terms_review_status = "approved"
            source.enabled = True
            session.commit()
        self.runtime.adapter_factory = lambda _adapter_type: RepairCanaryAdapter()
        evidence = self.client.get(
            f"/internal/admin/sources/{source_code}/strategy-repair-evidence",
            headers=self.headers,
        )
        self.assertEqual(200, evidence.status_code, evidence.text)
        self.assertEqual(12, evidence.json()["evidence"]["repeated_elements"][0]["count"])
        created = self.client.post(
            f"/internal/admin/sources/{source_code}/strategy-repairs",
            headers=self.headers,
            json={
                "proposed_strategy": {
                    "pagination": {
                        "mode": "next_button",
                        "next_selectors": ["button.next"],
                        "max_rounds": 8,
                        "max_records": 200,
                    },
                    "item_selectors": ["article.job-card"],
                    "detail_selectors": ["section.job-detail"],
                },
                "actor": "repair-admin",
                "origin": "ai",
            },
        )
        self.assertEqual(200, created.status_code, created.text)
        candidate_id = created.json()["id"]
        blocked = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/approve",
            headers=self.headers,
            json={"actor": "repair-admin"},
        )
        self.assertEqual(409, blocked.status_code, blocked.text)

        replayed = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/replay",
            headers=self.headers,
        )
        self.assertEqual(200, replayed.status_code, replayed.text)
        self.assertEqual("canary_passed", replayed.json()["status"])
        self.assertEqual(1, replayed.json()["replay_summary"]["record_count"])
        criteria = replayed.json()["canary_summary"]["criteria"]
        self.assertEqual(0.8, criteria["minimum_detail_completeness"])

        approved = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/approve",
            headers=self.headers,
            json={"actor": "repair-reviewer"},
        )
        self.assertEqual(200, approved.status_code, approved.text)
        self.assertEqual("approved", approved.json()["status"])
        with Session(self.engine) as session:
            active = session.scalar(
                select(CollectionStrategyVersion).where(
                    CollectionStrategyVersion.status == "active"
                )
            )
            candidate = session.get(StrategyRepairCandidate, candidate_id)
            self.assertIsNotNone(active)
            assert active is not None and candidate is not None
            self.assertEqual("repair_candidate", active.origin)
            self.assertEqual("approved", candidate.status)

        rolled_back = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/rollback",
            headers=self.headers,
            json={"actor": "repair-reviewer"},
        )
        self.assertEqual(200, rolled_back.status_code, rolled_back.text)
        self.assertEqual("rolled_back", rolled_back.json()["status"])

        unsafe = self.client.post(
            f"/internal/admin/sources/{source_code}/strategy-repairs",
            headers=self.headers,
            json={
                "proposed_strategy": {
                    "pagination": {"mode": "single_page"},
                    "javascript": "document.body.innerHTML",
                },
                "actor": "repair-admin",
            },
        )
        self.assertEqual(422, unsafe.status_code, unsafe.text)

        invalid_limits = self.client.post(
            f"/internal/admin/sources/{source_code}/strategy-repairs",
            headers=self.headers,
            json={
                "proposed_strategy": {
                    "pagination": {"mode": "single_page", "max_records": 100_000},
                },
                "actor": "repair-admin",
            },
        )
        self.assertEqual(422, invalid_limits.status_code, invalid_limits.text)

        unsafe_selector = self.client.post(
            f"/internal/admin/sources/{source_code}/strategy-repairs",
            headers=self.headers,
            json={
                "proposed_strategy": {
                    "pagination": {"mode": "single_page"},
                    "item_selectors": ["document.cookie"],
                },
                "actor": "repair-admin",
            },
        )
        self.assertEqual(422, unsafe_selector.status_code, unsafe_selector.text)

    def test_ai_repair_claim_lease_retry_and_worker_ownership(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "picc-campus-public-api")
            )
            assert source is not None
            candidate = StrategyRepairCandidate(
                source_id=source.id,
                status="ai_pending",
                origin="ai",
                failure_signature="selector_changed:runtimeerror:selector missing",
                proposed_strategy={},
                replay_summary={"generation_stage": "queued", "generation_attempts": 0},
                canary_summary={},
                created_by="system",
            )
            session.add(candidate)
            session.commit()
            session.refresh(candidate)
            candidate_id = candidate.id

        claimed = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/claim",
            headers=self.headers,
            json={"actor": "worker-a", "lease_seconds": 30, "max_attempts": 3},
        )
        self.assertEqual(200, claimed.status_code, claimed.text)
        self.assertEqual("ai_generating", claimed.json()["status"])
        self.assertEqual(1, claimed.json()["replay_summary"]["generation_attempts"])

        competing = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/claim",
            headers=self.headers,
            json={"actor": "worker-b", "lease_seconds": 30, "max_attempts": 3},
        )
        self.assertEqual(409, competing.status_code, competing.text)

        failed = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/fail",
            headers=self.headers,
            json={
                "actor": "worker-a",
                "error_message": "provider timeout",
                "retry_delay_seconds": 30,
                "max_attempts": 3,
            },
        )
        self.assertEqual(200, failed.status_code, failed.text)
        self.assertTrue(failed.json()["replay_summary"]["generation_retryable"])
        self.assertEqual(409, self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/claim",
            headers=self.headers,
            json={"actor": "worker-b", "lease_seconds": 30, "max_attempts": 3},
        ).status_code)

        with Session(self.engine) as session:
            candidate = session.get(StrategyRepairCandidate, candidate_id)
            assert candidate is not None
            summary = dict(candidate.replay_summary)
            summary["generation_next_retry_at"] = (
                datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
            ).isoformat()
            candidate.replay_summary = summary
            session.commit()

        reclaimed = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/claim",
            headers=self.headers,
            json={"actor": "worker-b", "lease_seconds": 30, "max_attempts": 3},
        )
        self.assertEqual(200, reclaimed.status_code, reclaimed.text)
        self.assertEqual(2, reclaimed.json()["replay_summary"]["generation_attempts"])
        strategy = {
            "pagination": {"mode": "single_page"},
            "item_selectors": ["article.job-card"],
            "detail_selectors": ["section.job-detail"],
        }
        stale_completion = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/complete",
            headers=self.headers,
            json={"actor": "worker-a", "proposed_strategy": strategy},
        )
        self.assertEqual(422, stale_completion.status_code, stale_completion.text)
        completed = self.client.post(
            f"/internal/admin/strategy-repairs/{candidate_id}/complete",
            headers=self.headers,
            json={"actor": "worker-b", "proposed_strategy": strategy},
        )
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual("candidate", completed.json()["status"])
        self.assertNotIn("generation_error", completed.json()["replay_summary"])
        self.assertNotIn("generation_failed_at", completed.json()["replay_summary"])
        self.assertNotIn("generation_retryable", completed.json()["replay_summary"])

    def test_strategy_repair_backfill_is_idempotent_for_old_failure(self) -> None:
        with Session(self.engine) as session:
            source = session.scalar(
                select(DataSource).where(DataSource.code == "picc-campus-public-api")
            )
            assert source is not None
            source.adapter_type = "company_channel"
            task = CrawlTask(
                task_uid="old-selector-failure",
                source_id=source.id,
                adapter_type="company_channel",
                trigger_type="manual",
                status="failed",
                error_type="RuntimeError",
                error_message="未命中岗位列表 selector",
                completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(task)
            session.commit()

        first = self.client.post(
            "/internal/admin/strategy-repairs/backfill?limit=20", headers=self.headers
        )
        second = self.client.post(
            "/internal/admin/strategy-repairs/backfill?limit=20", headers=self.headers
        )
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(1, first.json()["created_candidates"])
        self.assertEqual(200, second.status_code, second.text)
        with Session(self.engine) as session:
            candidates = list(session.scalars(select(StrategyRepairCandidate)))
            self.assertEqual(1, len(candidates))
            self.assertEqual(1, candidates[0].replay_summary["failure_occurrences"])
            repair_events = list(
                session.scalars(
                    select(CrawlLogEntry).where(
                        CrawlLogEntry.crawl_task_id == candidates[0].failure_task_id,
                        CrawlLogEntry.event_code.in_(
                            {
                                "strategy_repair_ai_queued",
                                "strategy_repair_ai_deduplicated",
                            }
                        ),
                    )
                )
            )
            self.assertEqual(1, len(repair_events))


if __name__ == "__main__":
    unittest.main()
