from __future__ import annotations

import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from market_data.app import create_app
from market_data.providers import FixtureMarketProvider, PinMarketProvider


ROOT = Path(__file__).resolve().parents[1]


class MarketInsightApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        provider = FixtureMarketProvider(ROOT / "fixtures/integrated_graduate_case.json")
        cls.client = TestClient(create_app(provider))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_health_identifies_fixture_provider(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual("fixture", response.json()["data_mode"])

    def test_job_search_returns_traceable_fixture_facts(self) -> None:
        response = self.client.get("/api/jobs", params={"keyword": "数据", "city": "上海"})
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("available", body["availability"])
        self.assertEqual("fixture", body["data_mode"])
        self.assertEqual(1, len(body["jobs"]))
        self.assertTrue(body["jobs"][0]["sources"][0]["source_url"])
        self.assertIn("不是实时", body["note"])

    def test_job_search_supports_independent_business_filters(self) -> None:
        response = self.client.get(
            "/api/jobs",
            params={
                "company": "海岳",
                "job_title": "数据分析",
                "city": "上海",
                "major": "SQL",
                "recruitment_type": "campus",
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(1, body["total"])
        self.assertEqual("海岳", body["company"])
        self.assertEqual("数据分析", body["job_title"])
        self.assertEqual("SQL", body["major"])
        self.assertEqual("campus", body["recruitment_type"])
        self.assertEqual("海岳科技（脱敏示例）", body["jobs"][0]["company_name"])

        no_match = self.client.get(
            "/api/jobs", params={"company": "海岳", "recruitment_type": "internship"}
        )
        self.assertEqual(200, no_match.status_code, no_match.text)
        self.assertEqual(0, no_match.json()["total"])

    def test_job_search_uses_database_style_pagination_contract(self) -> None:
        first = self.client.get("/api/jobs", params={"page": 1, "page_size": 1})
        second = self.client.get("/api/jobs", params={"page": 2, "page_size": 1})
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual(200, second.status_code, second.text)
        first_body = first.json()
        second_body = second.json()
        self.assertEqual(2, first_body["total"])
        self.assertEqual(2, first_body["total_pages"])
        self.assertFalse(first_body["has_previous"])
        self.assertTrue(first_body["has_next"])
        self.assertTrue(second_body["has_previous"])
        self.assertFalse(second_body["has_next"])
        self.assertNotEqual(first_body["jobs"][0]["job_id"], second_body["jobs"][0]["job_id"])

    def test_job_detail_returns_traceability_and_rejects_unknown_job(self) -> None:
        response = self.client.get("/api/jobs/fixture:job:data-analyst-001")
        encoded = self.client.get("/api/jobs/fixture%253Ajob%253Adata-analyst-001")
        missing = self.client.get("/api/jobs/fixture:job:missing")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("fixture:job:data-analyst-001", body["job"]["job_id"])
        self.assertEqual("海岳科技（脱敏示例）", body["company"]["name"])
        self.assertEqual("integrated-demo-v1", body["gate_policy_version"])
        self.assertTrue(body["job"]["sources"])
        self.assertEqual(200, encoded.status_code, encoded.text)
        self.assertEqual("fixture:job:data-analyst-001", encoded.json()["job"]["job_id"])
        self.assertEqual(404, missing.status_code, missing.text)

    def test_salary_and_skill_contracts_include_quality_and_sample(self) -> None:
        salary = self.client.get(
            "/api/insights/salary", params={"job_family": "数据分析师", "city": "上海"}
        )
        skills = self.client.get(
            "/api/insights/skills", params={"job_family": "数据分析师", "limit": 3}
        )
        self.assertEqual(200, salary.status_code, salary.text)
        self.assertEqual(86, salary.json()["sample_size"])
        self.assertEqual("B", salary.json()["quality_grade"])
        self.assertEqual(200, skills.status_code, skills.text)
        self.assertEqual(3, len(skills.json()["skills"]))
        self.assertEqual("fixture", skills.json()["data_mode"])

    def test_unavailable_provider_returns_truthful_degraded_contract(self) -> None:
        class UnavailableProvider:
            name = "unavailable-test-provider"
            data_mode = "historical"

            def search_jobs(self, *_args, **_kwargs):
                raise httpx.ConnectError("offline")

            def salary_insight(self, *_args):
                raise httpx.ConnectError("offline")

            def skill_insight(self, *_args):
                raise httpx.ConnectError("offline")

        with TestClient(create_app(UnavailableProvider())) as client:
            jobs = client.get("/api/jobs")
            salary = client.get(
                "/api/insights/salary", params={"job_family": "数据分析师", "city": "上海"}
            )
            skills = client.get(
                "/api/insights/skills", params={"job_family": "数据分析师"}
            )
        for response in (jobs, salary, skills):
            self.assertEqual(200, response.status_code, response.text)
            self.assertEqual("unavailable", response.json()["availability"])
            self.assertIn("暂时不可用", response.json()["note"])


class PinMarketProviderTests(unittest.TestCase):
    def test_pin_api_is_mapped_to_v2_market_contract(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/jobs":
                return httpx.Response(
                    200,
                    json={
                        "total": 1,
                        "jobs": [
                            {
                                "id": 7,
                                "title": "数据分析师",
                                "company_name": "样例科技",
                                "city": "上海",
                            }
                        ],
                    },
                )
            if request.url.path == "/api/jobs/7":
                return httpx.Response(
                    200,
                    json={
                        "id": 7,
                        "title": "数据分析师",
                        "normalized_title": "数据分析师",
                        "company_name": "样例科技",
                        "city": "上海",
                        "salary_min": 10000,
                        "salary_max": 15000,
                        "salary_unit": "月",
                        "skill_tags": '["SQL", "Python"]',
                        "published_at": "2026-08-01T00:00:00Z",
                        "first_seen_at": "2026-08-01T00:00:00Z",
                        "last_seen_at": "2026-08-15T00:00:00Z",
                        "status": "open",
                        "quality_score": 82,
                        "source_site": "Pin 演示源",
                        "detail_url": "https://jobs.example.invalid/7",
                        "is_campus": True,
                        "is_intern": False,
                    },
                )
            if request.url.path == "/api/jobs/7/sources":
                return httpx.Response(
                    200,
                    json={
                        "sources": [
                            {
                                "id": 3,
                                "source_site": "Pin 演示源",
                                "source_url": "https://jobs.example.invalid/7",
                                "last_seen_at": "2026-08-15T00:00:00Z",
                            }
                        ]
                    },
                )
            if request.url.path == "/api/analysis/salary/city-comparison":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "city": "上海",
                            "salaryP25": 9500,
                            "salaryMedian": 12500,
                            "salaryP75": 16000,
                            "sampleSize": 64,
                        }
                    ],
                )
            if request.url.path == "/api/analysis/skills/top-skills":
                return httpx.Response(
                    200,
                    json=[{"skill": "SQL", "count": 50}, {"skill": "Python", "count": 38}],
                )
            return httpx.Response(404)

        client = httpx.Client(
            base_url="http://pin.test",
            transport=httpx.MockTransport(handler),
        )
        provider = PinMarketProvider("http://pin.test", client=client)
        jobs = provider.search_jobs("数据", "上海", 10)
        detail = provider.get_job("pin:7")
        salary = provider.salary_insight("数据分析师", "上海")
        skills = provider.skill_insight("数据分析师", 2)
        client.close()

        self.assertEqual("historical", jobs.data_mode)
        self.assertEqual("pin:7", jobs.jobs[0].job_id)
        self.assertEqual("campus", jobs.jobs[0].recruitment_type)
        self.assertEqual(["SQL", "Python"], jobs.jobs[0].skills)
        self.assertEqual("B", jobs.jobs[0].quality.grade)
        self.assertIsNotNone(detail)
        self.assertEqual("pin:7", detail.job.job_id)
        self.assertEqual(64, salary.sample_size)
        self.assertEqual("SQL", skills.skills[0].name)


if __name__ == "__main__":
    unittest.main()
