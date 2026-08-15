import os
import tempfile
import unittest
from pathlib import Path


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "fp00-test-secret-only-not-for-production"

from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.api.routes.market_admin import get_market_admin_client
from app.models.finding import Finding
from app.models.knowledge_article import KnowledgeArticle
from app.models.user import User


class FP00SecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()
        TEST_DATABASE_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("alice", "alice-secure-password")
        self.bob = self._register("bob", "bob-secure-password")

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _create_offer(self) -> tuple[int, int]:
        case_response = self.client.post(
            "/api/cases/",
            headers=self._headers(self.alice),
            json={"type": "offer_analysis", "title": "Alice Offer"},
        )
        self.assertEqual(case_response.status_code, 200, case_response.text)
        case_id = case_response.json()["id"]
        offer_response = self.client.post(
            "/api/offers/",
            headers=self._headers(self.alice),
            json={
                "case_id": case_id,
                "company_name": "示例科技",
                "job_title": "产品经理",
                "city": "杭州",
                "monthly_salary": 15000,
            },
        )
        self.assertEqual(offer_response.status_code, 200, offer_response.text)
        self.assertIsNotNone(offer_response.json()["career_event_id"])
        return case_id, offer_response.json()["id"]

    def test_health_reports_version_and_database_status(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["version"], "0.2.0")
        self.assertEqual(body["dependencies"]["database"], "ok")

        ready = self.client.get("/api/health/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "ready")

    def test_knowledge_api_reads_published_articles_from_database(self):
        with SessionLocal() as db:
            db.add(
                KnowledgeArticle(
                    slug="database-backed-article",
                    title="数据库文章",
                    category="新手必知",
                    tags=["MySQL"],
                    keywords=["数据库"],
                    summary="数据库读取验证",
                    content="正文",
                    sort_order=1,
                )
            )
            db.commit()
        response = self.client.get(
            "/api/knowledge/", headers=self._headers(self.alice)
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("database-backed-article", response.json()[0]["slug"])

    def test_finance_contract_preserves_structured_housing_withdrawal_rules(self):
        headers = self._headers(self.alice)
        response = self.client.get(
            "/api/finance/housing-fund?monthly_contribution=3600&months_paid=24",
            headers=headers,
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertGreater(body["current_balance"], 0)
        self.assertEqual(
            {"scene", "condition", "amount"},
            set(body["withdrawal_rules"][0]),
        )

    def test_offer_details_updates_and_reports_are_owner_scoped(self):
        _, offer_id = self._create_offer()
        alice_headers = self._headers(self.alice)
        bob_headers = self._headers(self.bob)

        self.assertEqual(self.client.get(f"/api/offers/{offer_id}", headers=alice_headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/reports/offer/{offer_id}", headers=alice_headers).status_code, 200)

        forbidden_requests = [
            self.client.get(f"/api/offers/{offer_id}", headers=bob_headers),
            self.client.put(
                f"/api/offers/{offer_id}",
                headers=bob_headers,
                json={"company_name": "越权修改"},
            ),
            self.client.get(f"/api/reports/offer/{offer_id}", headers=bob_headers),
            self.client.get(f"/api/reports/offer/{offer_id}/hr-questions", headers=bob_headers),
        ]
        for response in forbidden_requests:
            self.assertEqual(response.status_code, 404, response.text)

        owned_offer = self.client.get(f"/api/offers/{offer_id}", headers=alice_headers).json()
        self.assertEqual(owned_offer["company_name"], "示例科技")

    def test_contract_creation_validates_case_and_offer_ownership(self):
        case_id, offer_id = self._create_offer()
        bob_headers = self._headers(self.bob)

        foreign_case = self.client.post(
            "/api/contracts/",
            headers=bob_headers,
            json={"case_id": case_id, "employer": "越权合同"},
        )
        self.assertEqual(foreign_case.status_code, 404, foreign_case.text)

        foreign_offer = self.client.post(
            "/api/contracts/",
            headers=bob_headers,
            json={"linked_offer_id": offer_id, "employer": "越权合同"},
        )
        self.assertEqual(foreign_offer.status_code, 404, foreign_offer.text)

        owned_contract = self.client.post(
            "/api/contracts/",
            headers=self._headers(self.alice),
            json={
                "linked_offer_id": offer_id,
                "employer": "示例科技",
                "raw_text": "劳动合同期限三年，试用期三个月，月薪人民币 15000 元。",
            },
        )
        self.assertEqual(owned_contract.status_code, 200, owned_contract.text)
        self.assertEqual(owned_contract.json()["case_id"], case_id)
        self.assertIsNotNone(owned_contract.json()["career_event_id"])

    def test_contract_detail_actions_are_owner_scoped(self):
        _, offer_id = self._create_offer()
        contract_response = self.client.post(
            "/api/contracts/",
            headers=self._headers(self.alice),
            json={
                "linked_offer_id": offer_id,
                "employer": "示例科技",
                "salary_terms": "月薪 15000 元",
                "raw_text": "劳动合同期限三年，试用期三个月，月薪人民币 15000 元。",
            },
        )
        self.assertEqual(contract_response.status_code, 200, contract_response.text)
        contract_id = contract_response.json()["id"]
        bob_headers = self._headers(self.bob)

        requests = [
            self.client.get(f"/api/contracts/{contract_id}", headers=bob_headers),
            self.client.post(f"/api/contracts/{contract_id}/review", headers=bob_headers),
            self.client.post(f"/api/contracts/{contract_id}/consistency", headers=bob_headers),
            self.client.post(f"/api/contracts/{contract_id}/checklist", headers=bob_headers),
        ]
        for response in requests:
            self.assertEqual(response.status_code, 404, response.text)

    def test_findings_require_owned_case(self):
        case_id, _ = self._create_offer()
        with SessionLocal() as db:
            db.add(
                Finding(
                    case_id=case_id,
                    category="offer",
                    severity="warning",
                    title="需要确认绩效条件",
                )
            )
            db.commit()

        owned = self.client.get(
            "/api/findings/",
            params={"case_id": case_id},
            headers=self._headers(self.alice),
        )
        self.assertEqual(owned.status_code, 200, owned.text)
        self.assertEqual(len(owned.json()), 1)

        foreign = self.client.get(
            "/api/findings/",
            params={"case_id": case_id},
            headers=self._headers(self.bob),
        )
        self.assertEqual(foreign.status_code, 404, foreign.text)

    def test_market_collection_management_is_admin_only(self):
        class FakeMarketAdminClient:
            @staticmethod
            def list_sources():
                return {
                    "sources": [
                        {
                            "code": "official-api",
                            "name": "官方招聘 API",
                            "adapter_type": "api",
                            "base_url": "https://jobs.example.com/api",
                            "allowed_hosts": ["jobs.example.com"],
                            "terms_review_status": "approved",
                            "enabled": True,
                            "can_run": True,
                            "raw_record_count": 12,
                            "updated_at": "2026-08-15T08:00:00",
                        }
                    ]
                }

            @staticmethod
            def list_tasks(limit: int = 50):
                return {"tasks": [], "total": 0}

            @staticmethod
            def run_source(source_code: str):
                return {
                    "id": 1,
                    "task_uid": "00000000-0000-0000-0000-000000000001",
                    "source_code": source_code,
                    "source_name": "官方招聘 API",
                    "adapter_type": "api",
                    "trigger_type": "live",
                    "status": "succeeded",
                    "attempt_count": 1,
                    "records_seen": 2,
                    "records_stored": 2,
                    "duplicate_records": 0,
                    "failed_records": 0,
                    "started_at": "2026-08-15T08:00:00",
                    "completed_at": "2026-08-15T08:00:01",
                    "created_at": "2026-08-15T08:00:00",
                }

            @staticmethod
            def get_gate_settings():
                configuration = {
                    "policy_version": "career-guardian-job-core-v1",
                    "minimum_core_score": 55,
                    "minimum_description_chars": 50,
                    "live_freshness_days": 14,
                    "maximum_future_hours": 48,
                    "maximum_salary": 1000000,
                    "required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "score_weights": {
                        "identity": 30,
                        "source_url": 15,
                        "content_hash": 5,
                        "description": 15,
                        "city": 10,
                        "published_at": 5,
                        "observed_at": 5,
                        "skills": 5,
                        "salary": 10,
                    },
                }
                return {
                    "active": {
                        "id": 1,
                        "policy_version": configuration["policy_version"],
                        "status": "active",
                        "configuration": configuration,
                        "change_note": "initial",
                        "created_by": "system",
                        "published_by": "system",
                        "created_at": "2026-08-15T08:00:00",
                        "updated_at": "2026-08-15T08:00:00",
                        "published_at": "2026-08-15T08:00:00",
                        "certified_jobs": 12,
                    },
                    "draft": None,
                    "certified_job_counts": {configuration["policy_version"]: 12},
                    "supported_required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "immutable_required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "score_dimensions": list(configuration["score_weights"]),
                    "publish_scope": "future_ingestion",
                }

        with SessionLocal() as db:
            admin = db.query(User).filter(User.id == self.alice["user_id"]).one()
            admin.is_admin = True
            db.commit()

        app.dependency_overrides[get_market_admin_client] = lambda: FakeMarketAdminClient()
        try:
            ordinary = self.client.get(
                "/api/admin/market/sources",
                headers=self._headers(self.bob),
            )
            self.assertEqual(403, ordinary.status_code, ordinary.text)

            sources = self.client.get(
                "/api/admin/market/sources",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, sources.status_code, sources.text)
            self.assertEqual("official-api", sources.json()["sources"][0]["code"])

            gate = self.client.get(
                "/api/admin/market/gate",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, gate.status_code, gate.text)
            self.assertEqual("career-guardian-job-core-v1", gate.json()["active"]["policy_version"])

            run = self.client.post(
                "/api/admin/market/sources/official-api/runs",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, run.status_code, run.text)
            self.assertEqual("succeeded", run.json()["status"])
        finally:
            app.dependency_overrides.pop(get_market_admin_client, None)


if __name__ == "__main__":
    unittest.main()
