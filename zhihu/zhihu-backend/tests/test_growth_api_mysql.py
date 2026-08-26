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
    GrowthWorkMaterial,
    GrowthWorkMaterialLink,
    GrowthWorkMaterialRelation,
    GrowthWorkMaterialRequest,
    GrowthWorkMaterialStatement,
    GrowthWorkNode,
    GrowthWorkNodeEvidence,
    GrowthWorkPlacementEvent,
    GrowthWorkUpdate,
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
                GrowthWorkNodeEvidence,
                GrowthWorkNode,
                GrowthWorkUpdate,
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
            note = db.query(GrowthEmotionNote).filter(
                GrowthEmotionNote.id == notes[0]["id"]
            ).one()
            self.assertIsNotNone(note.deleted_at)
            self.assertIsNone(note.deidentified_fact)
            self.assertNotIn(emotion_text, note.encrypted_content)

    def test_append_work_update_api_is_idempotent_and_owner_scoped(self):
        analyzed = self._analyze(
            request_id="growth-update-api-intake-001",
            text="推进产品上线",
        )
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={"selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}]},
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        item = confirmed.json()["work_items"][0]
        payload = {
            "request_id": "growth-update-api-001",
            "content": "目前还缺测试环境，等待运维确认",
            "kind": "auto",
        }

        foreign = self.client.post(
            f"/api/growth/work-items/{item['id']}/updates",
            headers=self._headers(self.bob),
            json={**payload, "request_id": "growth-update-api-foreign"},
        )
        self.assertEqual(404, foreign.status_code, foreign.text)
        created = self.client.post(
            f"/api/growth/work-items/{item['id']}/updates",
            headers=self._headers(self.alice),
            json=payload,
        )
        self.assertEqual(201, created.status_code, created.text)
        self.assertEqual("blocker", created.json()["kind"])
        replay = self.client.post(
            f"/api/growth/work-items/{item['id']}/updates",
            headers=self._headers(self.alice),
            json=payload,
        )
        self.assertEqual(created.json()["id"], replay.json()["id"])
        conflict = self.client.post(
            f"/api/growth/work-items/{item['id']}/updates",
            headers=self._headers(self.alice),
            json={**payload, "content": "不同的更新内容"},
        )
        self.assertEqual(409, conflict.status_code, conflict.text)
        workspace = self.client.get("/api/growth/workspace", headers=self._headers(self.alice))
        self.assertEqual(created.json()["id"], workspace.json()["task_updates"][0]["id"])

    def test_node_evidence_and_work_inbox_require_explicit_confirmation(self):
        analyzed = self._analyze(
            request_id="growth-node-api-intake-001",
            text="推进硬件方案",
        )
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={"selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}]},
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        item = confirmed.json()["work_items"][0]
        node = confirmed.json()["work_nodes"][0]

        with SessionLocal() as db:
            before_updates = db.query(GrowthWorkUpdate).count()
        routed = self.client.post(
            "/api/growth/work-inbox/analyze",
            headers=self._headers(self.alice),
            json={
                "request_id": "growth-node-inbox-api-001",
                "content": "硬件方案正在推进",
                "kind": "auto",
            },
        )
        self.assertEqual(200, routed.status_code, routed.text)
        self.assertFalse(routed.json()["persisted"])
        self.assertEqual(item["id"], routed.json()["routing_candidates"][0]["work_item_id"])
        with SessionLocal() as db:
            self.assertEqual(before_updates, db.query(GrowthWorkUpdate).count())

        update = self.client.post(
            f"/api/growth/work-items/{item['id']}/updates",
            headers=self._headers(self.alice),
            json={
                "request_id": "growth-node-update-api-001",
                "content": "硬件方案已经完成",
                "kind": "auto",
            },
        )
        self.assertEqual(201, update.status_code, update.text)
        suggestion = update.json()["node_suggestions"][0]
        self.assertEqual("update", suggestion["action"])
        self.assertEqual("completed", suggestion["proposed_status"])
        with SessionLocal() as db:
            self.assertEqual("planned", db.get(GrowthWorkNode, node["id"]).status)

        missing_gate = self.client.patch(
            f"/api/growth/work-items/{item['id']}/nodes/{node['id']}",
            headers=self._headers(self.alice),
            json={
                "status": "completed",
                "expected_version": node["version"],
                "source_update_id": update.json()["id"],
            },
        )
        self.assertEqual(422, missing_gate.status_code, missing_gate.text)
        accepted = self.client.patch(
            f"/api/growth/work-items/{item['id']}/nodes/{node['id']}",
            headers=self._headers(self.alice),
            json={
                "status": "completed",
                "expected_version": node["version"],
                "source_update_id": update.json()["id"],
                "confirmed": True,
            },
        )
        self.assertEqual(200, accepted.status_code, accepted.text)
        workspace = self.client.get("/api/growth/workspace", headers=self._headers(self.alice))
        evidence = next(
            row
            for row in workspace.json()["node_evidence"]
            if row["work_update_id"] == update.json()["id"] and row["node_id"] == node["id"]
        )
        self.assertEqual("confirmed", evidence["status"])

    def test_work_material_api_routes_confirmed_placement_and_timeline(self):
        analyzed = self._analyze(
            request_id="growth-material-api-intake-001",
            text="推进脱敏语音试点",
        )
        self.assertEqual(201, analyzed.status_code, analyzed.text)
        intake = analyzed.json()
        confirmed = self.client.post(
            f"/api/growth/intakes/{intake['intake_id']}/confirm",
            headers=self._headers(self.alice),
            json={"selected": [{"candidate_key": intake["candidates"][0]["candidate_key"]}]},
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        item = confirmed.json()["work_items"][0]
        material_payload = {
            "request_id": "growth-material-api-create-001",
            "material_type": "note",
            "title": "脱敏进展记录",
            "content": "推进脱敏语音试点为最高优先级，当前卡住，还缺线路资料。",
            "occurred_at": "2026-08-05T09:31:00",
            "occurred_at_precision": "datetime",
            "candidate_work_item_ids": [item["id"]],
            "use_ai": False,
            "allow_external_processing": False,
        }
        created = self.client.post(
            "/api/growth/work-materials",
            headers=self._headers(self.alice),
            json=material_payload,
        )
        self.assertEqual(201, created.status_code, created.text)
        material = created.json()
        self.assertTrue(material["material"]["occurred_at_known"])
        self.assertEqual("suggested", material["links"][0]["status"])
        self.assertEqual(item["title"], material["links"][0]["work_item_title"])
        self.assertEqual("focus", material["placement_events"][0]["quadrant"])

        unassigned = self.client.get(
            "/api/growth/work-materials?unassigned_only=true&limit=10&offset=0",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, unassigned.status_code, unassigned.text)
        self.assertEqual(1, unassigned.json()["total"])
        self.assertEqual("suggested", unassigned.json()["items"][0]["status"])
        self.assertEqual("datetime", unassigned.json()["items"][0]["occurred_at_precision"])
        foreign_list = self.client.get(
            "/api/growth/work-materials?unassigned_only=true",
            headers=self._headers(self.bob),
        )
        self.assertEqual(200, foreign_list.status_code, foreign_list.text)
        self.assertEqual(0, foreign_list.json()["total"])

        replay = self.client.post(
            "/api/growth/work-materials",
            headers=self._headers(self.alice),
            json=material_payload,
        )
        self.assertEqual(201, replay.status_code, replay.text)
        self.assertEqual(material["material"]["id"], replay.json()["material"]["id"])
        foreign = self.client.get(
            f"/api/growth/work-materials/{material['material']['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

        link = next(row for row in material["links"] if row["target_type"] == "work_item")
        placement = material["placement_events"][0]
        decision_payload = {
            "request_id": "growth-material-api-confirm-001",
            "expected_version": material["material"]["version"],
            "link_decisions": [
                {
                    "link_id": link["id"],
                    "status": "confirmed",
                    "expected_version": link["version"],
                }
            ],
            "placement_decisions": [
                {
                    "placement_event_id": placement["id"],
                    "status": "confirmed",
                    "expected_version": placement["version"],
                    "expected_work_item_version": item["version"],
                }
            ],
        }
        decision = self.client.post(
            f"/api/growth/work-materials/{material['material']['id']}/confirm",
            headers=self._headers(self.alice),
            json=decision_payload,
        )
        self.assertEqual(200, decision.status_code, decision.text)
        confirmed_materials = self.client.get(
            "/api/growth/work-materials?status=confirmed",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, confirmed_materials.status_code, confirmed_materials.text)
        self.assertEqual(material["material"]["id"], confirmed_materials.json()["items"][0]["id"])
        replay_decision = self.client.post(
            f"/api/growth/work-materials/{material['material']['id']}/confirm",
            headers=self._headers(self.alice),
            json=decision_payload,
        )
        self.assertEqual(200, replay_decision.status_code, replay_decision.text)

        board = self.client.get("/api/growth/work-board", headers=self._headers(self.alice))
        self.assertEqual(200, board.status_code, board.text)
        focus = next(row for row in board.json()["quadrants"] if row["key"] == "focus")
        self.assertIn(item["id"], {row["work_item_id"] for row in focus["items"]})
        timeline = self.client.get(
            f"/api/growth/work-items/{item['id']}/timeline",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, timeline.status_code, timeline.text)
        self.assertEqual("focus", timeline.json()["current_placement"]["quadrant"])
        self.assertEqual("confirmed", timeline.json()["entries"][0]["placement_events"][0]["status"])

        cleared = self.client.delete("/api/auth/data", headers=self._headers(self.alice))
        self.assertEqual(200, cleared.status_code, cleared.text)
        with SessionLocal() as db:
            for model in (
                GrowthWorkPlacementEvent,
                GrowthWorkMaterialLink,
                GrowthWorkMaterialStatement,
                GrowthWorkMaterialRelation,
                GrowthWorkMaterialRequest,
                GrowthWorkMaterial,
            ):
                self.assertEqual(0, db.query(model).filter(model.user_id == self.alice["user_id"]).count())

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

if __name__ == "__main__":
    unittest.main()
