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
    GrowthEvidenceItem,
    GrowthPortfolioItem,
    GrowthReflection,
    GrowthSkillAssessment,
    GrowthSkillEvidenceLink,
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

    def test_past_assets_require_confirmation_and_preserve_evidence_history(self):
        analyzed = self._analyze(request_id="growth-assets-work-001", text="完成客户复盘")
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={"selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}]},
        )
        item = confirmed.json()["work_items"][0]
        completed = self.client.patch(
            f"/api/growth/work-items/{item['id']}",
            headers=self._headers(self.alice),
            json={"status": "completed", "expected_version": item["version"], "result_summary": "客户确认复盘结论"},
        )
        event = completed.json()["event_candidate"]

        premature = self.client.post(
            "/api/growth/assets/portfolio",
            headers=self._headers(self.alice),
            json={"request_id": "portfolio-request-001", "item_type": "project", "title": "客户复盘", "source_work_event_id": event["id"]},
        )
        self.assertEqual(422, premature.status_code, premature.text)
        foreign = self.client.post(
            "/api/growth/assets/portfolio",
            headers=self._headers(self.bob),
            json={"request_id": "portfolio-request-foreign", "item_type": "project", "title": "不属于我的项目", "source_work_event_id": event["id"]},
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

        event_confirmed = self.client.patch(
            f"/api/growth/work-events/{event['id']}",
            headers=self._headers(self.alice),
            json={"status": "confirmed", "expected_version": event["version"], "action": "汇总反馈并形成复盘方法", "visibility": "career_asset"},
        )
        self.assertEqual(200, event_confirmed.status_code, event_confirmed.text)

        untraceable = self.client.post(
            "/api/growth/assets/portfolio",
            headers=self._headers(self.alice),
            json={"request_id": "portfolio-no-source-001", "item_type": "project", "title": "没有来源的草稿"},
        )
        self.assertEqual(201, untraceable.status_code, untraceable.text)
        rejected_activation = self.client.patch(
            f"/api/growth/assets/portfolio/{untraceable.json()['id']}",
            headers=self._headers(self.alice),
            json={"expected_version": 1, "status": "active"},
        )
        self.assertEqual(422, rejected_activation.status_code, rejected_activation.text)

        portfolio_payload = {
            "request_id": "portfolio-request-001",
            "item_type": "project",
            "title": "客户复盘",
            "summary": "可追溯到已确认工作事件",
            "source_work_event_id": event["id"],
            "privacy_level": "shared",
        }
        portfolio = self.client.post("/api/growth/assets/portfolio", headers=self._headers(self.alice), json=portfolio_payload)
        self.assertEqual(201, portfolio.status_code, portfolio.text)
        replay = self.client.post("/api/growth/assets/portfolio", headers=self._headers(self.alice), json=portfolio_payload)
        self.assertEqual(portfolio.json()["id"], replay.json()["id"])
        conflict_payload = {**portfolio_payload, "title": "不同内容"}
        conflict = self.client.post("/api/growth/assets/portfolio", headers=self._headers(self.alice), json=conflict_payload)
        self.assertEqual(409, conflict.status_code, conflict.text)
        active = self.client.patch(
            f"/api/growth/assets/portfolio/{portfolio.json()['id']}",
            headers=self._headers(self.alice),
            json={"expected_version": 1, "status": "active"},
        )
        self.assertEqual(200, active.status_code, active.text)

        evidence = self.client.post(
            "/api/growth/assets/evidence",
            headers=self._headers(self.alice),
            json={
                "request_id": "evidence-request-001",
                "portfolio_item_id": active.json()["id"],
                "work_event_id": event["id"],
                "evidence_type": "project_result",
                "title": "客户确认结论",
                "summary": "客户在评审中确认关键结论",
                "privacy_level": "shared",
            },
        )
        self.assertEqual(201, evidence.status_code, evidence.text)
        evidence_confirmed = self.client.patch(
            f"/api/growth/assets/evidence/{evidence.json()['id']}",
            headers=self._headers(self.alice),
            json={"expected_version": 1, "status": "confirmed"},
        )
        self.assertEqual(200, evidence_confirmed.status_code, evidence_confirmed.text)

        candidate = self.client.post(
            "/api/growth/assets/skills",
            headers=self._headers(self.alice),
            json={"skill_name": "客户复盘", "source_layer": "ai_candidate", "evidence_ids": [evidence.json()["id"]]},
        )
        self.assertEqual(201, candidate.status_code, candidate.text)
        self.assertEqual("candidate", candidate.json()["status"])
        skill = self.client.post(
            f"/api/growth/assets/skills/{candidate.json()['id']}/confirm",
            headers=self._headers(self.alice),
            json={"expected_version": 1, "evidence_ids": [evidence.json()["id"]]},
        )
        self.assertEqual(200, skill.status_code, skill.text)
        self.assertEqual("evidence_confirmed", skill.json()["source_layer"])
        self.assertEqual(2, skill.json()["version"])

        reflection = self.client.post(
            "/api/growth/assets/reflections",
            headers=self._headers(self.alice),
            json={"work_event_id": event["id"]},
        )
        self.assertEqual(201, reflection.status_code, reflection.text)
        reflected = self.client.patch(
            f"/api/growth/assets/reflections/{reflection.json()['id']}",
            headers=self._headers(self.alice),
            json={"expected_version": 1, "answer": "先核对客户原话，再归纳可复用方法", "privacy_level": "private", "confirm_as_method": True},
        )
        self.assertEqual(200, reflected.status_code, reflected.text)

        workspace = self.client.get("/api/growth/assets/workspace", headers=self._headers(self.alice))
        self.assertEqual(200, workspace.status_code, workspace.text)
        self.assertEqual(1, workspace.json()["summary"]["active_portfolios"])
        self.assertGreaterEqual(workspace.json()["summary"]["confirmed_evidences"], 2)
        self.assertFalse(any("score" in key.lower() for key in workspace.json()))
        exported = self.client.get("/api/growth/assets/export", headers=self._headers(self.alice))
        self.assertEqual(200, exported.status_code, exported.text)
        self.assertEqual([], exported.json()["reflections"])

        protected = self.client.delete(
            f"/api/growth/assets/evidence/{evidence.json()['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(409, protected.status_code, protected.text)
        detached = self.client.delete(
            f"/api/growth/assets/evidence/{evidence.json()['id']}?detach_skills=true",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, detached.status_code, detached.text)

        cleared = self.client.delete("/api/auth/data", headers=self._headers(self.alice))
        self.assertEqual(200, cleared.status_code, cleared.text)
        with SessionLocal() as db:
            for model in (GrowthReflection, GrowthSkillEvidenceLink, GrowthSkillAssessment, GrowthEvidenceItem, GrowthPortfolioItem):
                self.assertEqual(0, db.query(model).filter(model.user_id == self.alice["user_id"]).count())

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
