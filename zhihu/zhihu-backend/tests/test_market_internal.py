from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


class MarketInternalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_semantic_normalizer_requires_internal_token(self) -> None:
        with patch.object(settings, "MARKET_INTERNAL_TOKEN", "test-market-token"):
            response = self.client.post(
                "/api/internal/market/semantic-normalize",
                json={"text": "熟悉 Java", "source_code": "test"},
            )
        self.assertEqual(403, response.status_code)

    def test_semantic_normalizer_returns_structured_evidence_candidates(self) -> None:
        with (
            patch.object(settings, "MARKET_INTERNAL_TOKEN", "test-market-token"),
            patch(
                "app.api.routes.market_internal._call_llm",
                return_value='{"responsibilities":["负责后端开发"],"requirements":["熟悉 Java"],"skill_tags":["Java"]}',
            ),
            patch("app.api.routes.market_internal.effective_ai_configuration", return_value=None),
        ):
            response = self.client.post(
                "/api/internal/market/semantic-normalize",
                headers={"X-Market-Admin-Token": "test-market-token"},
                json={"text": "负责后端开发，需要熟悉 Java", "source_code": "test"},
            )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(["负责后端开发"], response.json()["responsibilities"])
        self.assertEqual(["Java"], response.json()["skill_tags"])


if __name__ == "__main__":
    unittest.main()
