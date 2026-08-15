from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path

from market_data.adapters import HtmlAdapter, PlaywrightAdapter, StructuredApiAdapter
from market_data.errors import SourcePolicyError
from market_data.schemas import SourceSnapshot
from market_data.services.registry import load_source_registry


ROOT = Path(__file__).resolve().parents[1]
FETCHED_AT = datetime.fromisoformat("2026-08-15T08:00:00+00:00")


class AdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = {
            source.code: source for source in load_source_registry(ROOT / "sources/registry.json")
        }

    def snapshot(self, source_code: str, filename: str, content_type: str) -> SourceSnapshot:
        text = (ROOT / "tests/fixtures" / filename).read_text(encoding="utf-8")
        content = json.loads(text) if content_type == "application/json" else text
        return SourceSnapshot(
            source_url=self.sources[source_code].base_url,
            content_type=content_type,
            content=content,
            fetched_at=FETCHED_AT,
            http_status=200,
            transport_metadata={"mode": "fixture", "synthetic": True},
        )

    def test_three_source_shapes_and_playwright_snapshot_follow_contract(self) -> None:
        cases = [
            (
                "structured-api-fixture",
                StructuredApiAdapter(),
                "structured_api.json",
                "application/json",
                2,
            ),
            ("moka-feishu-fixture", HtmlAdapter(), "moka_feishu.html", "text/html", 2),
            ("hotjob-fixture", HtmlAdapter(), "hotjob.html", "text/html", 2),
            (
                "rendered-site-fixture",
                PlaywrightAdapter(),
                "rendered_site.html",
                "text/html",
                1,
            ),
        ]
        for source_code, adapter, filename, content_type, expected_count in cases:
            with self.subTest(source=source_code):
                source = self.sources[source_code]
                snapshot = self.snapshot(source_code, filename, content_type)
                first = adapter.parse(source, snapshot)
                second = adapter.parse(source, snapshot)
                self.assertEqual(expected_count, len(first.records))
                self.assertEqual(
                    first.model_dump(mode="json"), second.model_dump(mode="json")
                )
                self.assertEqual(source.adapter_type, first.adapter_type)
                self.assertTrue(all(record.source_url for record in first.records))

    def test_live_collection_requires_human_terms_approval_and_enablement(self) -> None:
        source = self.sources["structured-api-fixture"]
        with self.assertRaises(SourcePolicyError):
            StructuredApiAdapter().assert_live_collection_allowed(source)

    def test_http_live_source_must_be_https_and_allow_listed(self) -> None:
        source = self.sources["structured-api-fixture"].model_copy(
            update={
                "enabled": True,
                "terms_review_status": "approved",
                "base_url": "http://api.recruit.example.invalid/jobs",
            }
        )
        with self.assertRaises(SourcePolicyError):
            StructuredApiAdapter().assert_live_collection_allowed(source)


if __name__ == "__main__":
    unittest.main()
