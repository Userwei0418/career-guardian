import os
import tempfile
import unittest
from pathlib import Path


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "integrated-demo-test-secret-not-for-production"

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app


class IntegratedDemoJourneyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        response = self.client.post(
            "/api/auth/register",
            json={"username": "journey-user", "password": "journey-secure-password"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_fixture_builds_five_domain_journey_and_is_idempotent(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers)
        self.assertEqual(201, created.status_code, created.text)
        body = created.json()
        self.assertTrue(body["created"])
        self.assertEqual("fixture", body["data_mode"])
        self.assertEqual(
            {"opportunity", "decision", "rights", "income", "growth"},
            set(body["event_ids"]),
        )
        self.assertIsNotNone(body["offer_id"])
        self.assertIsNotNone(body["contract_id"])
        self.assertIsNotNone(body["payslip_id"])

        repeated = self.client.post("/api/guardian/demo-journey", headers=self.headers)
        self.assertEqual(201, repeated.status_code, repeated.text)
        self.assertFalse(repeated.json()["created"])
        self.assertEqual(body["event_ids"], repeated.json()["event_ids"])

        events = self.client.get("/api/events/", headers=self.headers).json()
        self.assertEqual(5, len(events))

    def test_fixture_separates_public_market_and_private_material_evidence(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers).json()
        opportunity = self.client.get(
            f"/api/events/{created['event_ids']['opportunity']}", headers=self.headers
        ).json()
        decision = self.client.get(
            f"/api/events/{created['event_ids']['decision']}", headers=self.headers
        ).json()
        income = self.client.get(
            f"/api/events/{created['event_ids']['income']}", headers=self.headers
        ).json()

        market_evidence = opportunity["evidence"][0]
        self.assertEqual("market_data", market_evidence["source_type"])
        self.assertTrue(market_evidence["extra_data"]["public_market_fact"])
        self.assertEqual("fixture", market_evidence["extra_data"]["data_mode"])
        self.assertTrue(all(item["source_type"] == "user_material" for item in decision["evidence"]))
        self.assertTrue(all(item["extra_data"]["private_user_material"] for item in decision["evidence"]))
        self.assertTrue(income["evidence"][0]["extra_data"]["private_user_material"])

    def test_income_difference_is_primary_action_and_journey_contains_event_graph(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers).json()
        guardian = self.client.get("/api/guardian/state", headers=self.headers).json()
        self.assertEqual("income", guardian["primary_domain"])
        income = next(item for item in guardian["domains"] if item["domain"] == "income")
        self.assertEqual("attention", income["status"])
        self.assertIn("1200", income["summary"])
        self.assertIn("1200", income["primary_action"])

        journey = self.client.get("/api/journey/", headers=self.headers)
        self.assertEqual(200, journey.status_code, journey.text)
        career_events = journey.json()["career_events"]
        self.assertEqual(5, len(career_events))
        income_event = next(item for item in career_events if item["event_type"] == "income")
        self.assertEqual(created["event_ids"]["income"], income_event["id"])
        self.assertEqual("high", income_event["latest_finding"]["severity"])
        self.assertEqual("pending", income_event["next_action"]["status"])

    def test_hr_reply_is_persisted_as_private_evidence_and_optional_action(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers).json()
        response = self.client.post(
            f"/api/reports/offer/{created['offer_id']}/hr-confirmations",
            headers=self.headers,
            json={
                "question_title": "绩效发放条件",
                "question_script": "请问绩效如何计算？",
                "reply": "HR 回复按季度考核，详细制度入职后查看。",
                "conclusion": "绩效口径仍需书面制度佐证",
                "follow_up_action": "签约前索取绩效制度截图",
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("follow_up", body["status"])
        self.assertIsNotNone(body["action_id"])

        decision = self.client.get(
            f"/api/events/{created['event_ids']['decision']}", headers=self.headers
        ).json()
        saved = next(item for item in decision["evidence"] if item["id"] == body["evidence_id"])
        self.assertEqual("hr_reply", saved["evidence_type"])
        self.assertTrue(saved["extra_data"]["private_user_material"])
        action = next(item for item in decision["actions"] if item["id"] == body["action_id"])
        self.assertTrue(action["requires_confirmation"])

    def test_contract_review_consistency_and_checklist_sync_without_duplicates(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers).json()
        contract_id = created["contract_id"]
        first_review = self.client.post(
            f"/api/contracts/{contract_id}/review", headers=self.headers
        )
        self.assertEqual(200, first_review.status_code, first_review.text)
        self.assertGreaterEqual(first_review.json()["synced_finding_count"], 1)
        second_review = self.client.post(
            f"/api/contracts/{contract_id}/review", headers=self.headers
        )
        self.assertEqual(0, second_review.json()["synced_finding_count"])
        self.assertEqual(0, second_review.json()["synced_action_count"])

        consistency = self.client.post(
            f"/api/contracts/{contract_id}/consistency", headers=self.headers
        )
        self.assertEqual(200, consistency.status_code, consistency.text)
        self.assertGreaterEqual(consistency.json()["issue_count"], 1)
        self.assertGreaterEqual(consistency.json()["synced_finding_count"], 1)

        checklist = self.client.post(
            f"/api/contracts/{contract_id}/checklist", headers=self.headers
        )
        self.assertEqual(200, checklist.status_code, checklist.text)
        self.assertGreaterEqual(checklist.json()["synced_action_count"], 1)
        repeated_checklist = self.client.post(
            f"/api/contracts/{contract_id}/checklist", headers=self.headers
        )
        self.assertEqual(0, repeated_checklist.json()["synced_action_count"])

        rights = self.client.get(
            f"/api/events/{created['event_ids']['rights']}", headers=self.headers
        ).json()
        rule_findings = [
            item for item in rights["findings"] if item["category"].startswith("contract_rule:")
        ]
        self.assertEqual(len({item["category"] for item in rule_findings}), len(rule_findings))
        self.assertTrue(all(item["requires_confirmation"] for item in rights["actions"]))

    def test_saved_payslip_compares_offer_gross_and_creates_income_action(self):
        created = self.client.post("/api/guardian/demo-journey", headers=self.headers).json()
        response = self.client.post(
            "/api/payslips/",
            headers=self.headers,
            json={
                "linked_offer_id": created["offer_id"],
                "pay_month": "2026-08",
                "gross_salary": 14500,
                "base_salary": 13000,
                "performance": 1000,
                "allowance": 500,
                "social_insurance": 1435,
                "housing_fund": 1050,
                "individual_tax": 400,
                "net_salary": 11615,
                "raw_text": "脱敏工资条记录",
                "expected_salary": 99999,
                "city": "杭州"
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual(-500, body["difference_from_offer_gross"])
        self.assertIsNotNone(body["action_id"])
        self.assertEqual(created["offer_id"], body["payslip"]["linked_offer_id"])

        event = self.client.get(
            f"/api/events/{body['payslip']['career_event_id']}", headers=self.headers
        ).json()
        self.assertEqual("income", event["event_type"])
        self.assertEqual("high", event["findings"][0]["severity"])
        self.assertTrue(event["evidence"][0]["extra_data"]["private_user_material"])
        self.assertEqual(15000, event["evidence"][0]["extra_data"]["offer_monthly_salary"])

        listed = self.client.get("/api/payslips/", headers=self.headers)
        self.assertEqual(200, listed.status_code, listed.text)
        self.assertEqual(2, len(listed.json()))


if __name__ == "__main__":
    unittest.main()
