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

    def test_market_gateway_proxies_pagination_and_job_detail(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/jobs":
                self.assertEqual("2", request.url.params["page"])
                self.assertEqual("1", request.url.params["page_size"])
                return httpx.Response(
                    200,
                    json={
                        "availability": "available",
                        "data_mode": "historical",
                        "total": 2,
                        "page": 2,
                        "page_size": 1,
                        "total_pages": 2,
                        "has_previous": True,
                        "has_next": False,
                        "generated_at": "2026-08-15T00:00:00Z",
                        "jobs": [
                            {
                                "job_id": "core:9",
                                "title": "数据分析师",
                                "company_name": "样例科技",
                                "city": "上海",
                                "data_mode": "historical",
                                "quality": {"grade": "B", "sample_size": 1, "methodology_version": "core-v2"},
                                "sources": [{"source_id": "core-source:9", "source_name": "职护市场数据", "source_url": "https://jobs.example.invalid/9", "observed_at": "2026-08-15T00:00:00Z"}],
                            }
                        ],
                    },
                )
            if request.url.path == "/api/jobs/core:9":
                return httpx.Response(
                    200,
                    json={
                        "availability": "available",
                        "data_mode": "historical",
                        "job": {
                            "job_id": "core:9",
                            "title": "数据分析师",
                            "company_name": "样例科技",
                            "city": "上海",
                            "skills": ["SQL"],
                            "data_mode": "historical",
                            "quality": {"grade": "B", "sample_size": 1, "methodology_version": "core-v2"},
                            "sources": [{"source_id": "core-source:9", "source_name": "职护市场数据", "source_url": "https://jobs.example.invalid/9", "observed_at": "2026-08-15T00:00:00Z"}],
                        },
                        "company": {"company_id": "core-company:3", "name": "样例科技"},
                        "description": "负责经营数据分析。",
                        "requirements": "熟悉 SQL。",
                        "first_seen_at": "2026-08-01T00:00:00Z",
                        "last_seen_at": "2026-08-15T00:00:00Z",
                        "quality_score": 80,
                        "quality_reasons": [],
                        "gate_policy_version": "career-guardian-job-core-v1",
                        "gate_evaluated_at": "2026-08-15T00:00:00Z",
                    },
                )
            return httpx.Response(404)

        upstream = httpx.Client(base_url="http://market.test", transport=httpx.MockTransport(handler))
        app.dependency_overrides[get_market_client] = lambda: MarketInsightClient("http://market.test", client=upstream)
        page = self.client.get("/api/market/jobs", params={"page": 2, "page_size": 1}, headers=self.headers)
        detail = self.client.get("/api/market/jobs/core:9", headers=self.headers)
        upstream.close()

        self.assertEqual(200, page.status_code, page.text)
        self.assertEqual(2, page.json()["page"])
        self.assertEqual(200, detail.status_code, detail.text)
        self.assertEqual("core:9", detail.json()["job"]["job_id"])
        self.assertEqual("负责经营数据分析。", detail.json()["description"])

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

    def test_offer_report_uses_traceable_market_insight_instead_of_mock(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/insights/salary":
                return httpx.Response(
                    200,
                    json={
                        "availability": "available",
                        "data_mode": "fixture",
                        "job_family": "数据分析师",
                        "city": "上海",
                        "currency": "CNY",
                        "period": "month",
                        "p25": 12500,
                        "p50": 15000,
                        "p75": 18500,
                        "sample_size": 86,
                        "calculated_at": "2026-08-15T00:00:00Z",
                        "methodology_version": "integrated-demo-salary-v1",
                        "quality_grade": "B",
                        "sources": [
                            {
                                "source_id": "fixture-market-salary-001",
                                "source_name": "脱敏市场样例",
                                "source_url": "https://market.example.invalid/salary/1",
                                "observed_at": "2026-08-15T00:00:00Z",
                            }
                        ],
                        "note": "不是实时市场数据",
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
        offer = self.client.post(
            "/api/offers/",
            headers=self.headers,
            json={
                "company_name": "海岳科技",
                "job_title": "数据分析师",
                "city": "上海",
                "monthly_salary": 16000,
            },
        )
        self.assertEqual(200, offer.status_code, offer.text)
        report = self.client.get(
            f"/api/reports/offer/{offer.json()['id']}",
            headers=self.headers,
        )
        upstream.close()

        self.assertEqual(200, report.status_code, report.text)
        market = report.json()["market"]
        self.assertEqual("fixture", market["data_mode"])
        self.assertEqual("B", market["quality_grade"])
        self.assertEqual(86, market["sample_size"])
        self.assertEqual("位于市场 P50–P75", market["description"])
        self.assertEqual("fixture-market-salary-001", market["sources"][0]["source_id"])
        self.assertNotIn("模拟", market["sources"][0]["source_name"])

    def test_growth_draft_separates_market_and_profile_evidence(self):
        profile = self.client.put(
            "/api/profiles/",
            headers=self.headers,
            json={
                "career_stage": "fresh_graduate",
                "target_roles": ["数据分析师"],
                "skills": ["Excel", "SQL 基础"],
            },
        )
        self.assertEqual(200, profile.status_code, profile.text)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/insights/skills":
                return httpx.Response(
                    200,
                    json={
                        "availability": "available",
                        "data_mode": "fixture",
                        "job_family": "数据分析师",
                        "sample_size": 120,
                        "calculated_at": "2026-08-15T00:00:00Z",
                        "methodology_version": "integrated-demo-skill-v1",
                        "quality_grade": "B",
                        "skills": [
                            {"name": "SQL", "count": 92, "share": 0.76},
                            {"name": "Excel", "count": 81, "share": 0.67},
                            {"name": "Python", "count": 68, "share": 0.56},
                        ],
                        "sources": [
                            {
                                "source_id": "fixture-market-skill-001",
                                "source_name": "脱敏技能样本",
                                "source_url": "https://market.example.invalid/skills/1",
                                "observed_at": "2026-08-15T00:00:00Z",
                            }
                        ],
                        "note": "脱敏演示技能信号",
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
        response = self.client.post(
            "/api/guardian/growth-draft",
            headers=self.headers,
            json={"job_family": "数据分析师", "limit": 8},
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(["SQL", "Excel"], body["matched_skills"])
        self.assertEqual(["Python"], body["gaps"])
        self.assertEqual("fixture", body["data_mode"])
        self.assertEqual(1, len(body["draft_actions"]))

        event = self.client.get(
            f"/api/events/{body['event_id']}", headers=self.headers
        ).json()
        market_evidence = next(item for item in event["evidence"] if item["source_type"] == "market_data")
        profile_evidence = next(item for item in event["evidence"] if item["source_type"] == "user_material")
        self.assertTrue(market_evidence["extra_data"]["public_market_fact"])
        self.assertNotIn("confirmed_user_skills", market_evidence["extra_data"])
        self.assertTrue(profile_evidence["extra_data"]["private_user_material"])
        self.assertTrue(all(item["requires_confirmation"] for item in event["actions"]))
        self.assertTrue(all(item["status"] == "draft" for item in event["actions"]))
        upstream.close()


if __name__ == "__main__":
    unittest.main()
