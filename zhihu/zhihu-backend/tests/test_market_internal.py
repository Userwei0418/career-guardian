from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, derive_market_internal_token, settings
from app.main import app


class MarketInternalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_direct_backend_start_derives_the_same_internal_market_token(self) -> None:
        jwt_secret = "direct-uvicorn-test-secret"
        runtime_settings = Settings(
            DATABASE_URL=(
                "mysql+pymysql://test_disabled:test_disabled@127.0.0.1:3306/"
                "career_guardian_test_settings"
            ),
            JWT_SECRET=jwt_secret,
            MARKET_INTERNAL_TOKEN=None,
            _env_file=None,
        )
        self.assertEqual(derive_market_internal_token(jwt_secret), runtime_settings.MARKET_INTERNAL_TOKEN)
        self.assertNotEqual(jwt_secret, runtime_settings.MARKET_INTERNAL_TOKEN)

    def test_runtime_settings_reject_sqlite_database_url(self) -> None:
        with self.assertRaisesRegex(ValidationError, "只支持 MySQL/PyMySQL"):
            Settings(
                DATABASE_URL="sqlite:///./must-not-be-used-at-runtime.sqlite3",
                JWT_SECRET="runtime-database-guard-test-secret",
                _env_file=None,
            )

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
