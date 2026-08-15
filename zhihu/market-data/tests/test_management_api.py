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
from market_data.db import RawBase, make_engine, make_session_factory
from market_data.management import MarketAdminRuntime
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
        self.engine = make_engine(f"sqlite:///{database_path}")
        RawBase.metadata.create_all(self.engine)
        self.runtime = MarketAdminRuntime(make_session_factory(self.engine))
        self.runtime.sync_registry(ROOT / "sources" / "registry.json")
        provider = FixtureMarketProvider(ROOT / "fixtures" / "integrated_graduate_case.json")
        self.client = TestClient(
            create_app(provider=provider, management_runtime=self.runtime, admin_token="test-admin-token")
        )
        self.headers = {"X-Market-Admin-Token": "test-admin-token"}

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()
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
        self.assertEqual("succeeded", source["last_task"]["status"])


if __name__ == "__main__":
    unittest.main()
