from __future__ import annotations

import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from market_data.adapters import HtmlAdapter, PlaywrightAdapter, StructuredApiAdapter
from market_data.errors import AdapterTimeoutError, SourcePolicyError
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

    def test_real_candidate_is_registered_but_cannot_run_before_approval(self) -> None:
        source = self.sources["picc-campus-public-api"]
        self.assertFalse(source.enabled)
        self.assertEqual("pending", source.terms_review_status)
        self.assertEqual(100, source.config["json_body"]["PageSize"])
        self.assertEqual(20, source.config["pagination"]["max_pages"])
        self.assertEqual("Data", source.config["items_path"])
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

    def test_api_live_fetch_rate_limits_and_retries_after_timeout(self) -> None:
        source = self.sources["structured-api-fixture"].model_copy(
            update={"enabled": True, "terms_review_status": "approved", "max_retries": 1}
        )
        response = MagicMock()
        response.url = str(source.base_url)
        response.status_code = 200
        response.headers = {"content-type": "application/json"}
        response.json.return_value = {"data": {"jobs": []}}
        response.raise_for_status.return_value = None

        client = MagicMock()
        client.request.side_effect = [httpx.TimeoutException("fixture timeout"), response]
        client_context = MagicMock()
        client_context.__enter__.return_value = client
        with patch("market_data.adapters.api.httpx.Client", return_value=client_context), patch.object(
            StructuredApiAdapter, "throttle"
        ) as throttle, patch("market_data.adapters.api.time.sleep") as retry_sleep:
            snapshot = StructuredApiAdapter().fetch(source)

        self.assertEqual(200, snapshot.http_status)
        self.assertEqual(2, snapshot.transport_metadata["attempt"])
        self.assertEqual(2, client.request.call_count)
        throttle.assert_called_once_with(source)
        retry_sleep.assert_called_once_with(source.min_interval_seconds)

    def test_api_live_fetch_classifies_exhausted_timeouts(self) -> None:
        source = self.sources["structured-api-fixture"].model_copy(
            update={"enabled": True, "terms_review_status": "approved", "max_retries": 1}
        )
        client = MagicMock()
        client.request.side_effect = httpx.TimeoutException("fixture timeout")
        client_context = MagicMock()
        client_context.__enter__.return_value = client
        with patch("market_data.adapters.api.httpx.Client", return_value=client_context), patch.object(
            StructuredApiAdapter, "throttle"
        ), patch("market_data.adapters.api.time.sleep"):
            with self.assertRaises(AdapterTimeoutError):
                StructuredApiAdapter().fetch(source)
        self.assertEqual(2, client.request.call_count)

    def test_paginated_api_aggregates_pages_with_rate_limit(self) -> None:
        source = self.sources["picc-campus-public-api"].model_copy(
            update={"enabled": True, "terms_review_status": "approved", "max_retries": 0}
        )
        responses = []
        for payload in [
            {"Code": 200, "Count": 3, "Data": [{"JobAdId": "1"}, {"JobAdId": "2"}]},
            {"Code": 200, "Count": 3, "Data": [{"JobAdId": "3"}]},
        ]:
            response = MagicMock()
            response.url = str(source.base_url)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response.json.return_value = payload
            response.raise_for_status.return_value = None
            responses.append(response)
        client = MagicMock()
        client.request.side_effect = responses
        client_context = MagicMock()
        client_context.__enter__.return_value = client
        source = source.model_copy(
            update={
                "config": {
                    **source.config,
                    "pagination": {**source.config["pagination"], "page_size": 2},
                }
            }
        )
        with patch("market_data.adapters.api.httpx.Client", return_value=client_context), patch(
            "market_data.adapters.api.time.sleep"
        ) as page_sleep:
            snapshot = StructuredApiAdapter().fetch(source)
        result = StructuredApiAdapter().parse(source, snapshot)
        self.assertEqual(["1", "2", "3"], [row.external_id for row in result.records])
        self.assertEqual(2, snapshot.transport_metadata["pages"])
        self.assertEqual(3, snapshot.transport_metadata["records"])
        self.assertEqual([0, 1], [call.kwargs["json"]["PageIndex"] for call in client.request.call_args_list])
        page_sleep.assert_called_once_with(source.min_interval_seconds)

    def test_paginated_api_stops_on_incremental_known_id_boundary(self) -> None:
        source = self.sources["picc-campus-public-api"].model_copy(
            update={"enabled": True, "terms_review_status": "approved", "max_retries": 0}
        )
        responses = []
        for payload in [
            {"Code": 200, "Count": 99, "Data": [{"JobAdId": "new-1"}]},
            {"Code": 200, "Count": 99, "Data": [{"JobAdId": "known-1"}]},
            {"Code": 200, "Count": 99, "Data": [{"JobAdId": "must-not-read"}]},
        ]:
            response = MagicMock()
            response.url = str(source.base_url)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response.json.return_value = payload
            response.raise_for_status.return_value = None
            responses.append(response)
        client = MagicMock()
        client.request.side_effect = responses
        client_context = MagicMock()
        client_context.__enter__.return_value = client
        source = source.model_copy(
            update={
                "config": {
                    **source.config,
                    "pagination": {**source.config["pagination"], "page_size": 1},
                    "_collection": {
                        "mode": "incremental",
                        "known_external_ids": ["known-1"],
                    },
                }
            }
        )
        with patch("market_data.adapters.api.httpx.Client", return_value=client_context), patch(
            "market_data.adapters.api.time.sleep"
        ):
            snapshot = StructuredApiAdapter().fetch(source)
        result = StructuredApiAdapter().parse(source, snapshot)
        self.assertEqual(["new-1", "known-1"], [row.external_id for row in result.records])
        self.assertEqual(2, client.request.call_count)
        self.assertEqual("incremental_boundary_reached", snapshot.transport_metadata["pagination_stop_reason"])


if __name__ == "__main__":
    unittest.main()
