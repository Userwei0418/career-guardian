from __future__ import annotations

import unittest
from datetime import date

try:
    from mysql_test_support import mysql_test
except ModuleNotFoundError:
    from tests.mysql_test_support import mysql_test

from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models.growth import (
    GrowthAuditEvent,
    GrowthCommunicationDraft,
    GrowthHandoff,
    GrowthInquiry,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
)


@mysql_test
class GrowthIntegrationApiMysqlTest(unittest.TestCase):
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
        self.alice = self._register("integration-alice", "integration-alice-password")
        self.bob = self._register("integration-bob", "integration-bob-password")
        with SessionLocal() as db:
            intake = GrowthWorkIntake(
                user_id=self.alice["user_id"],
                request_id="integration-intake-001",
                input_fingerprint="a" * 64,
                candidate_payload=[],
                parser_version="integration-test",
                analysis_mode="rules",
                status="confirmed",
            )
            db.add(intake)
            db.flush()
            work_item = GrowthWorkItem(
                user_id=self.alice["user_id"],
                intake_id=intake.id,
                candidate_key="integration-event",
                title="完成跨部门方案评审",
                status="completed",
                result_summary="方案按期通过评审",
                reportable=True,
            )
            db.add(work_item)
            db.flush()
            event = GrowthWorkEvent(
                user_id=self.alice["user_id"],
                work_item_id=work_item.id,
                task="完成跨部门方案评审",
                action="组织三方评审并关闭争议项",
                result="方案按期通过评审",
                role="负责人",
                occurred_on=date(2026, 8, 25),
                status="confirmed",
                visibility="career_asset",
                reportable=True,
            )
            db.add(event)
            db.commit()
            self.event_id = event.id

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def test_versioned_communication_handoff_revoke_and_full_export(self):
        communication_payload = {
            "request_id": "communication-request-001",
            "audience": "直属领导",
            "scene": "项目进度汇报",
            "goal": "确认下一阶段资源安排",
            "known_facts": ["方案已在 8 月 25 日通过三方评审", "下一阶段需要测试同事参与"],
            "tone": "专业、克制",
            "source_refs": [{"source_type": "work_event", "source_id": self.event_id}],
        }
        created = self.client.post("/api/growth/communication-drafts", headers=self._headers(self.alice), json=communication_payload)
        self.assertEqual(201, created.status_code, created.text)
        self.assertEqual("rules", created.json()["analysis_mode"])
        self.assertIn("已确认工作事件", created.json()["data_scope"])
        self.assertIn("不会自动发送", created.json()["risk_notes"][0])

        replay = self.client.post("/api/growth/communication-drafts", headers=self._headers(self.alice), json=communication_payload)
        self.assertEqual(created.json()["id"], replay.json()["id"])
        conflict = self.client.post("/api/growth/communication-drafts", headers=self._headers(self.alice), json={**communication_payload, "goal": "另一个目标"})
        self.assertEqual(409, conflict.status_code, conflict.text)

        foreign_revision = self.client.post(
            f"/api/growth/communication-drafts/{created.json()['id']}/revisions",
            headers=self._headers(self.bob),
            json={"request_id": "communication-revision-foreign", "expected_version": 1, "edited_content": "越权内容", "status": "reviewed"},
        )
        self.assertEqual(404, foreign_revision.status_code, foreign_revision.text)
        reviewed = self.client.post(
            f"/api/growth/communication-drafts/{created.json()['id']}/revisions",
            headers=self._headers(self.alice),
            json={"request_id": "communication-revision-001", "expected_version": 1, "edited_content": "结论先行：请确认下一阶段测试资源。", "status": "reviewed"},
        )
        self.assertEqual(201, reviewed.status_code, reviewed.text)
        self.assertEqual(2, reviewed.json()["version"])
        exported = self.client.post(
            f"/api/growth/communication-drafts/{reviewed.json()['id']}/revisions",
            headers=self._headers(self.alice),
            json={"request_id": "communication-revision-002", "expected_version": 2, "edited_content": reviewed.json()["edited_content"], "status": "exported"},
        )
        self.assertEqual(201, exported.status_code, exported.text)
        self.assertEqual("exported", exported.json()["status"])

        handoff_payload = {"request_id": "handoff-request-001", "target_domain": "opportunity", "source_type": "work_event", "source_id": self.event_id}
        proposal = self.client.post("/api/growth/handoffs", headers=self._headers(self.alice), json=handoff_payload)
        self.assertEqual(201, proposal.status_code, proposal.text)
        self.assertEqual("proposed", proposal.json()["status"])
        self.assertIn("不会自动修改", proposal.json()["impact_summary"])
        empty_inbox = self.client.get("/api/growth/handoffs/inbox/opportunity", headers=self._headers(self.alice))
        self.assertEqual([], empty_inbox.json())

        foreign_confirm = self.client.post(
            f"/api/growth/handoffs/{proposal.json()['id']}/confirm",
            headers=self._headers(self.bob),
            json={"expected_version": 1},
        )
        self.assertEqual(404, foreign_confirm.status_code, foreign_confirm.text)
        confirmed = self.client.post(
            f"/api/growth/handoffs/{proposal.json()['id']}/confirm",
            headers=self._headers(self.alice),
            json={"expected_version": 1},
        )
        self.assertEqual(200, confirmed.status_code, confirmed.text)
        self.assertEqual("confirmed", confirmed.json()["status"])
        inbox = self.client.get("/api/growth/handoffs/inbox/opportunity", headers=self._headers(self.alice))
        self.assertEqual([proposal.json()["id"]], [item["id"] for item in inbox.json()])

        full_export = self.client.get("/api/growth/export", headers=self._headers(self.alice))
        self.assertEqual(200, full_export.status_code, full_export.text)
        body = full_export.json()
        self.assertEqual("user_confirmed_growth_records", body["scope"])
        self.assertEqual(1, len(body["work"]["events"]))
        self.assertEqual(1, len(body["communication"]["drafts"]))
        self.assertTrue(any("原始情绪" in item for item in body["exclusions"]))
        self.assertNotIn("emotion", str(body["work"]).lower())

        inquiry_payload = {"request_id": "growth-inquiry-api-001", "question": "我现在有哪些已确认成果？", "data_scopes": ["current_work"], "use_ai": False, "allow_external_processing": False}
        inquiry = self.client.post("/api/growth/inquiries", headers=self._headers(self.alice), json=inquiry_payload)
        self.assertEqual(200, inquiry.status_code, inquiry.text)
        self.assertEqual("program", inquiry.json()["mode"])
        self.assertIn("[工作项 #", inquiry.json()["answer"])
        inquiry_replay = self.client.post("/api/growth/inquiries", headers=self._headers(self.alice), json=inquiry_payload)
        self.assertEqual(inquiry.json()["id"], inquiry_replay.json()["id"])
        inquiry_conflict = self.client.post("/api/growth/inquiries", headers=self._headers(self.alice), json={**inquiry_payload, "question": "另一个问题"})
        self.assertEqual(409, inquiry_conflict.status_code, inquiry_conflict.text)

        revoked = self.client.post(
            f"/api/growth/handoffs/{confirmed.json()['id']}/revoke",
            headers=self._headers(self.alice),
            json={"expected_version": 2},
        )
        self.assertEqual(200, revoked.status_code, revoked.text)
        self.assertEqual("revoked", revoked.json()["status"])
        self.assertEqual([], self.client.get("/api/growth/handoffs/inbox/opportunity", headers=self._headers(self.alice)).json())

        with SessionLocal() as db:
            self.assertEqual(3, db.query(GrowthCommunicationDraft).filter(GrowthCommunicationDraft.user_id == self.alice["user_id"]).count())
            actions = [row.action for row in db.query(GrowthAuditEvent).filter(GrowthAuditEvent.entity_type == "growth_handoff").order_by(GrowthAuditEvent.id).all()]
            self.assertEqual(["proposed", "confirmed", "revoked"], actions)

        cleared = self.client.delete("/api/auth/data", headers=self._headers(self.alice))
        self.assertEqual(200, cleared.status_code, cleared.text)
        with SessionLocal() as db:
            self.assertEqual(0, db.query(GrowthCommunicationDraft).filter(GrowthCommunicationDraft.user_id == self.alice["user_id"]).count())
            self.assertEqual(0, db.query(GrowthHandoff).filter(GrowthHandoff.user_id == self.alice["user_id"]).count())
            self.assertEqual(0, db.query(GrowthInquiry).filter(GrowthInquiry.user_id == self.alice["user_id"]).count())


if __name__ == "__main__":
    unittest.main()
