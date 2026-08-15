from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.api import StructuredApiAdapter
from market_data.app import create_app
from market_data.db import CoreBase, RawBase, make_engine, make_session_factory
from market_data.management import MarketAdminRuntime
from market_data.models.core import QualityGatePolicy
from market_data.models.raw import DataSource
from market_data.providers import FixtureMarketProvider
from market_data.schemas import SourceDefinition, SourceSnapshot


ROOT = Path(__file__).resolve().parents[1]
FETCHED_AT = datetime.fromisoformat("2026-08-15T08:00:00+00:00")


class FixedSnapshotAdapter(StructuredApiAdapter):
    def __init__(self, snapshot: SourceSnapshot):
        self.snapshot = snapshot

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        return self.snapshot


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

    def test_approved_source_run_is_audited_and_deduplicated(self) -> None:
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
        second = self.client.post(
            "/internal/admin/sources/structured-api-fixture/runs",
            headers=self.headers,
        )
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(2, first.json()["records_stored"])
        self.assertEqual(200, second.status_code, second.text)
        self.assertEqual(0, second.json()["records_stored"])
        self.assertEqual(2, second.json()["duplicate_records"])

        tasks = self.client.get("/internal/admin/tasks", headers=self.headers).json()
        self.assertEqual(2, tasks["total"])
        sources = self.client.get("/internal/admin/sources", headers=self.headers).json()["sources"]
        source = next(item for item in sources if item["code"] == "structured-api-fixture")
        self.assertTrue(source["can_run"])
        self.assertEqual(2, source["raw_record_count"])
        self.assertEqual(2, source["gate_status_counts"]["pending_gate"])
        self.assertEqual("succeeded", source["last_task"]["status"])

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


if __name__ == "__main__":
    unittest.main()
