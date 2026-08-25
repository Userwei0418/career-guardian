from __future__ import annotations

import unittest
from datetime import date, timedelta

try:
    from mysql_test_support import mysql_test
except ModuleNotFoundError:
    from tests.mysql_test_support import mysql_test

# The guard module must configure the isolated URL before application imports.
from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models.growth import (
    GrowthAuditEvent,
    GrowthEmotionNote,
    GrowthWeeklyReport,
    GrowthWorkEvent,
    GrowthWorkIntake,
    GrowthWorkItem,
)


@mysql_test
class GrowthApiMysqlTest(unittest.TestCase):
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
        self.alice = self._register("growth-alice", "growth-alice-password")
        self.bob = self._register("growth-bob", "growth-bob-password")

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _analyze(self, *, request_id: str, text: str):
        return self.client.post(
            "/api/growth/intakes/analyze",
            headers=self._headers(self.alice),
            json={
                "request_id": request_id,
                "text": text,
                "use_ai": False,
                "allow_external_processing": False,
            },
        )

    def test_confirm_complete_event_report_and_clear_data_loop(self):
        original = "我很焦虑；今天完成客户汇报；整理项目文档"
        analyzed = self._analyze(request_id="growth-loop-001", text=original)
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        self.assertFalse(intake["original_text_persisted"])
        self.assertEqual(2, len(intake["candidates"]))
        self.assertNotIn("焦虑", str(intake["candidates"]))

        replay = self._analyze(request_id="growth-loop-001", text=original)
        self.assertEqual(201, replay.status_code, replay.text)
        self.assertEqual(intake["intake_id"], replay.json()["intake_id"])

        conflict = self._analyze(request_id="growth-loop-001", text="处理另一项工作")
        self.assertEqual(409, conflict.status_code, conflict.text)

        foreign = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.bob),
            json={"selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}]},
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "selected": [
                    {
                        "candidate_key": intake["candidates"][0]["candidate_key"],
                        "title": "完成客户汇报",
                        "reportable": True,
                    }
                ],
                "retain_emotion": False,
            },
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        item = confirmed.json()["work_items"][0]
        self.assertFalse(confirmed.json()["emotion_retained"])

        completed = self.client.patch(
            f"/api/growth/work-items/{item['id']}",
            headers=self._headers(self.alice),
            json={
                "status": "completed",
                "expected_version": item["version"],
                "result_summary": "客户确认了汇报结论",
                "reportable": True,
            },
        )
        self.assertEqual(200, completed.status_code, completed.text)
        event = completed.json()["event_candidate"]
        self.assertEqual("structured", event["status"])
        self.assertIn("action", event["evidence_gaps"])

        stale = self.client.patch(
            f"/api/growth/work-items/{item['id']}",
            headers=self._headers(self.alice),
            json={
                "status": "completed",
                "expected_version": item["version"],
                "result_summary": "重复提交",
            },
        )
        self.assertEqual(409, stale.status_code, stale.text)

        event_confirmed = self.client.patch(
            f"/api/growth/work-events/{event['id']}",
            headers=self._headers(self.alice),
            json={
                "status": "confirmed",
                "expected_version": event["version"],
                "action": "整合数据并在评审会上解释关键差异",
                "role": "汇报负责人",
                "visibility": "reportable",
                "reportable": True,
            },
        )
        self.assertEqual(200, event_confirmed.status_code, event_confirmed.text)
        confirmed_event = event_confirmed.json()

        occurred_on = date.fromisoformat(confirmed_event["occurred_on"])
        week_start = occurred_on - timedelta(days=occurred_on.weekday())
        report = self.client.post(
            "/api/growth/weekly-reports",
            headers=self._headers(self.alice),
            json={"week_start": week_start.isoformat(), "event_ids": [event["id"]]},
        )
        self.assertEqual(201, report.status_code, report.text)
        self.assertIn("客户确认了汇报结论", report.json()["generated_content"])
        self.assertNotIn("焦虑", report.json()["generated_content"])

        state = self.client.get(
            "/api/guardian/state",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, state.status_code, state.text)
        growth_state = next(item for item in state.json()["domains"] if item["domain"] == "growth")
        self.assertNotIn("完成客户汇报", str(growth_state))
        self.assertNotIn("客户确认", str(growth_state))

        cleared = self.client.delete(
            "/api/auth/data",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, cleared.status_code, cleared.text)
        with SessionLocal() as db:
            for model in (
                GrowthAuditEvent,
                GrowthWeeklyReport,
                GrowthWorkEvent,
                GrowthEmotionNote,
                GrowthWorkItem,
                GrowthWorkIntake,
            ):
                self.assertEqual(0, db.query(model).filter(model.user_id == self.alice["user_id"]).count())

    def test_explicit_emotion_retention_is_encrypted_and_never_returned(self):
        emotion_text = "这周客户压力让我很焦虑"
        analyzed = self._analyze(
            request_id="growth-emotion-001",
            text="整理客户复盘材料",
        )
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}],
                "retain_emotion": True,
                "emotion_text": emotion_text,
                "deidentified_fact": "客户沟通带来压力",
            },
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        self.assertTrue(confirmed.json()["emotion_retained"])

        workspace = self.client.get(
            "/api/growth/workspace",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, workspace.status_code, workspace.text)
        self.assertNotIn(emotion_text, workspace.text)
        notes = workspace.json()["private_emotion_notes"]
        self.assertEqual(1, len(notes))

        with SessionLocal() as db:
            note = db.query(GrowthEmotionNote).filter(
                GrowthEmotionNote.user_id == self.alice["user_id"]
            ).one()
            self.assertNotEqual(emotion_text, note.encrypted_content)
            self.assertNotIn(emotion_text, note.encrypted_content)

        deleted = self.client.delete(
            f"/api/growth/emotion-notes/{notes[0]['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertEqual({"ok": True}, deleted.json())
        with SessionLocal() as db:
            note = db.query(GrowthEmotionNote).filter(GrowthEmotionNote.id == notes[0]["id"]).one()
            self.assertIsNotNone(note.deleted_at)
            self.assertIsNone(note.deidentified_fact)
            self.assertNotIn(emotion_text, note.encrypted_content)


if __name__ == "__main__":
    unittest.main()
