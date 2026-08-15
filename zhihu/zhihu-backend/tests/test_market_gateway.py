import os
import tempfile
import unittest
from pathlib import Path

import httpx


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "market-gateway-test-secret-not-for-production"

from fastapi.testclient import TestClient

from app.api.routes.market import get_market_client
from app.db.session import Base, engine
from app.main import app
from app.services.market_insight_client import MarketInsightClient


class MarketGatewayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_market_client, None)
        cls.client.close()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        response = self.client.post(
            "/api/auth/register",
            json={"username": "market-user", "password": "market-secure-password"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def tearDown(self):
        app.dependency_overrides.pop(get_market_client, None)

    def test_market_gateway_requires_login(self):
        response = self.client.get("/api/market/jobs")
        self.assertEqual(401, response.status_code, response.text)

    def test_market_gateway_preserves_source_quality_and_data_mode(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/jobs":
                return httpx.Response(
                    200,
                    json={
                        "availability": "available",
                        "data_mode": "fixture",
                        "keyword": "数据",
                        "city": "上海",
                        "total": 1,
                        "generated_at": "2026-08-15T00:00:00Z",
                        "jobs": [
                            {
                                "job_id": "fixture-job-1",
                                "title": "数据分析师",
                                "company_name": "浦江科技",
                                "city": "上海",
                                "recruitment_type": "campus",
                                "salary_min": 10000,
                                "salary_max": 14000,
                                "salary_period": "month",
                                "skills": ["SQL"],
                                "status": "open",
                                "data_mode": "fixture",
                                "quality": {
                                    "grade": "B",
                                    "sample_size": 1,
                                    "methodology_version": "fixture-v1",
                                },
                                "sources": [
                                    {
                                        "source_id": "fixture-source-1",
                                        "source_name": "脱敏集成样例",
                                        "source_url": "https://jobs.example.invalid/1",
                                        "observed_at": "2026-08-15T00:00:00Z",
                                    }
                                ],
                            }
                        ],
                        "note": "不是实时招聘数据",
                    },
                )
            return httpx.Response(404)

        upstream = httpx.Client(
            base_url="http://market.test",
            transport=httpx.MockTransport(handler),
        )
        app.dependency_overrides[get_market_client] = lambda: MarketInsightClient(
            "http://market.test", client=upstream
        )
        response = self.client.get(
            "/api/market/jobs",
            params={"keyword": "数据", "city": "上海"},
            headers=self.headers,
        )
        upstream.close()

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("fixture", body["data_mode"])
        self.assertEqual("B", body["jobs"][0]["quality"]["grade"])
        self.assertEqual("fixture-source-1", body["jobs"][0]["sources"][0]["source_id"])

    def test_market_gateway_degrades_without_fabricating_data(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        upstream = httpx.Client(
            base_url="http://market.test",
            transport=httpx.MockTransport(handler),
        )
        app.dependency_overrides[get_market_client] = lambda: MarketInsightClient(
            "http://market.test", client=upstream
        )
        response = self.client.get(
            "/api/market/insights/salary",
            params={"job_family": "数据分析师", "city": "上海"},
            headers=self.headers,
        )
        upstream.close()

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("unavailable", body["availability"])
        self.assertEqual("unknown", body["data_mode"])
        self.assertEqual(0, body["sample_size"])
        self.assertEqual([], body["sources"])


if __name__ == "__main__":
    unittest.main()
