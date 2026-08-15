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
from app.models.finding import Finding


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


if __name__ == "__main__":
    unittest.main()
