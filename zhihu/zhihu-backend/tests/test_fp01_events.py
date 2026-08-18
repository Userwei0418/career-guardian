import json
import os
import unittest
from pathlib import Path

from mysql_test_support import mysql_test

os.environ["JWT_SECRET"] = "fp01-test-secret-only-not-for-production"

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app
from app.schemas.market import SalaryInsightResponse


@mysql_test
class FP01CareerEventTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("fp01-alice", "alice-secure-password")
        self.bob = self._register("fp01-bob", "bob-secure-password")

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

    def test_empty_guardian_state_contains_five_domains(self):
        response = self.client.get("/api/guardian/state", headers=self._headers(self.alice))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            [item["domain"] for item in body["domains"]],
            ["opportunity", "decision", "rights", "income", "growth"],
        )
        self.assertTrue(all(item["status"] == "empty" for item in body["domains"]))
        self.assertTrue(all(item["primary_action"] for item in body["domains"]))

    def test_event_supports_evidence_findings_actions_decisions_and_outcomes(self):
        headers = self._headers(self.alice)
        fixture_path = Path(__file__).parent / "fixtures" / "career_event_decision_case.json"
        fixture = json.loads(fixture_path.read_text())
        event_response = self.client.post(
            "/api/events/",
            headers=headers,
            json=fixture["event"],
        )
        self.assertEqual(event_response.status_code, 201, event_response.text)
        event_id = event_response.json()["id"]

        evidence_ids = []
        for payload in fixture["evidence"]:
            response = self.client.post(f"/api/events/{event_id}/evidence", headers=headers, json=payload)
            self.assertEqual(response.status_code, 201, response.text)
            evidence_ids.append(response.json()["id"])

        finding = self.client.post(
            f"/api/events/{event_id}/findings",
            headers=headers,
            json={"evidence_id": evidence_ids[0], **fixture["finding"]},
        )
        self.assertEqual(finding.status_code, 201, finding.text)

        action = self.client.post(
            f"/api/events/{event_id}/actions",
            headers=headers,
            json={"finding_id": finding.json()["id"], **fixture["action"]},
        )
        self.assertEqual(action.status_code, 201, action.text)

        decision = self.client.post(
            f"/api/events/{event_id}/decisions",
            headers=headers,
            json=fixture["decision"],
        )
        self.assertEqual(decision.status_code, 201, decision.text)

        outcome = self.client.post(
            f"/api/events/{event_id}/outcomes",
            headers=headers,
            json={"action_id": action.json()["id"], **fixture["outcome"]},
        )
        self.assertEqual(outcome.status_code, 201, outcome.text)

        detail = self.client.get(f"/api/events/{event_id}", headers=headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(len(body["evidence"]), 2)
        self.assertEqual(len(body["findings"]), 1)
        self.assertEqual(len(body["actions"]), 1)
        self.assertEqual(len(body["decisions"]), 1)
        self.assertEqual(len(body["outcomes"]), 1)
        self.assertEqual(body["findings"][0]["source_type"], "rule")

        guardian = self.client.get("/api/guardian/state", headers=headers).json()
        decision_state = next(item for item in guardian["domains"] if item["domain"] == "decision")
        self.assertEqual(decision_state["status"], "attention")
        self.assertEqual(decision_state["primary_action"], "向 HR 确认绩效发放条件")

    def test_event_and_nested_resources_are_owner_scoped(self):
        event = self.client.post(
            "/api/events/",
            headers=self._headers(self.alice),
            json={"event_type": "opportunity", "title": "目标岗位"},
        )
        event_id = event.json()["id"]

        foreign_get = self.client.get(f"/api/events/{event_id}", headers=self._headers(self.bob))
        self.assertEqual(foreign_get.status_code, 404, foreign_get.text)
        self.assertEqual(foreign_get.json()["error"]["code"], "not_found")

        foreign_write = self.client.post(
            f"/api/events/{event_id}/evidence",
            headers=self._headers(self.bob),
            json={
                "evidence_type": "job_posting",
                "source_type": "market_data",
                "title": "越权证据",
            },
        )
        self.assertEqual(foreign_write.status_code, 404, foreign_write.text)

    def test_validation_errors_use_unified_error_shape(self):
        response = self.client.post(
            "/api/events/",
            headers=self._headers(self.alice),
            json={"event_type": "unknown", "title": "错误事件"},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_high_risk_finding_takes_precedence_over_newer_warning(self):
        headers = self._headers(self.alice)
        event = self.client.post(
            "/api/events/",
            headers=headers,
            json={"event_type": "rights", "title": "签约前合同检查"},
        ).json()
        for severity, title in [
            ("high", "竞业范围和补偿未写明"),
            ("warning", "试用期发薪日需确认"),
        ]:
            response = self.client.post(
                f"/api/events/{event['id']}/findings",
                headers=headers,
                json={
                    "domain": "rights",
                    "severity": severity,
                    "title": title,
                    "source_type": "rule",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)

        guardian = self.client.get("/api/guardian/state", headers=headers).json()
        rights_state = next(item for item in guardian["domains"] if item["domain"] == "rights")
        self.assertEqual(rights_state["status"], "attention")
        self.assertEqual(rights_state["summary"], "竞业范围和补偿未写明")

    def test_clear_user_data_removes_career_event_graph(self):
        headers = self._headers(self.alice)
        event = self.client.post(
            "/api/events/",
            headers=headers,
            json={"event_type": "growth", "title": "开发能力成长计划"},
        ).json()
        evidence = self.client.post(
            f"/api/events/{event['id']}/evidence",
            headers=headers,
            json={"evidence_type": "skill_note", "source_type": "user_material", "title": "我的技能记录"},
        )
        self.assertEqual(evidence.status_code, 201, evidence.text)

        cleared = self.client.delete("/api/auth/data", headers=headers)
        self.assertEqual(cleared.status_code, 200, cleared.text)
        events = self.client.get("/api/events/", headers=headers)
        self.assertEqual(events.json(), [])
        guardian = self.client.get("/api/guardian/state", headers=headers).json()
        self.assertTrue(all(item["status"] == "empty" for item in guardian["domains"]))

    def test_user_can_confirm_actions_resolve_findings_and_complete_owned_event(self):
        headers = self._headers(self.alice)
        event = self.client.post(
            "/api/events/",
            headers=headers,
            json={"event_type": "growth", "title": "成长任务确认"},
        ).json()
        finding = self.client.post(
            f"/api/events/{event['id']}/findings",
            headers=headers,
            json={
                "domain": "growth",
                "severity": "warning",
                "title": "Python 项目经验待补充",
                "source_type": "calculation",
            },
        ).json()
        action = self.client.post(
            f"/api/events/{event['id']}/actions",
            headers=headers,
            json={
                "finding_id": finding["id"],
                "title": "完成一个 Python 小项目",
                "status": "draft",
                "requires_confirmation": True,
            },
        ).json()

        unconfirmed = self.client.patch(
            f"/api/events/{event['id']}/actions/{action['id']}",
            headers=headers,
            json={"status": "pending", "confirm": False},
        )
        self.assertEqual(409, unconfirmed.status_code, unconfirmed.text)
        premature_close = self.client.patch(
            f"/api/events/{event['id']}",
            headers=headers,
            json={"status": "completed"},
        )
        self.assertEqual(409, premature_close.status_code, premature_close.text)

        started = self.client.patch(
            f"/api/events/{event['id']}/actions/{action['id']}",
            headers=headers,
            json={"status": "pending", "confirm": True},
        )
        self.assertEqual(200, started.status_code, started.text)
        self.assertIsNotNone(started.json()["confirmed_at"])
        completed = self.client.patch(
            f"/api/events/{event['id']}/actions/{action['id']}",
            headers=headers,
            json={"status": "completed", "confirm": True},
        )
        self.assertIsNotNone(completed.json()["completed_at"])
        unresolved_close = self.client.patch(
            f"/api/events/{event['id']}",
            headers=headers,
            json={"status": "completed"},
        )
        self.assertEqual(409, unresolved_close.status_code, unresolved_close.text)
        resolved = self.client.patch(
            f"/api/events/{event['id']}/findings/{finding['id']}",
            headers=headers,
            json={"status": "resolved"},
        )
        self.assertEqual("resolved", resolved.json()["status"])
        event_done = self.client.patch(
            f"/api/events/{event['id']}",
            headers=headers,
            json={"status": "completed"},
        )
        self.assertEqual("completed", event_done.json()["status"])
        self.assertIsNotNone(event_done.json()["completed_at"])

        foreign = self.client.patch(
            f"/api/events/{event['id']}/actions/{action['id']}",
            headers=self._headers(self.bob),
            json={"status": "dismissed", "confirm": False},
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

    def test_market_fixture_matches_contract_without_pin_runtime(self):
        fixture_path = Path(__file__).parent / "fixtures" / "market_salary_available.json"
        insight = SalaryInsightResponse.model_validate(json.loads(fixture_path.read_text()))
        self.assertEqual(insight.availability, "available")
        self.assertEqual(insight.sample_size, 128)
        self.assertEqual(insight.methodology_version, "salary-v1")
        self.assertEqual(insight.sources[0].source_id, "fixture-source-1")


if __name__ == "__main__":
    unittest.main()
