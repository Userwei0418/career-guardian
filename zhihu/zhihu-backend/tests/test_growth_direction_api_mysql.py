from __future__ import annotations

import unittest
from datetime import datetime, timezone

try:
    from mysql_test_support import mysql_test
except ModuleNotFoundError:
    from tests.mysql_test_support import mysql_test

from fastapi.testclient import TestClient

from app.api.routes.market import get_market_client
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models.growth import (
    GrowthFutureTarget,
    GrowthGapSnapshot,
    GrowthMarketSignal,
    GrowthMilestone,
    GrowthWorkIntake,
    GrowthWorkItem,
)
from app.schemas.market import MarketSourceRef, SkillInsightResponse, SkillItem


class FakeMarketClient:
    insight: SkillInsightResponse

    def skill_insight(self, job_family: str, limit: int) -> SkillInsightResponse:
        return self.insight


@mysql_test
class GrowthDirectionApiMysqlTest(unittest.TestCase):
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
        self.alice = self._register("direction-alice", "direction-alice-password")
        self.bob = self._register("direction-bob", "direction-bob-password")
        self.market = FakeMarketClient()
        app.dependency_overrides[get_market_client] = lambda: self.market

    def tearDown(self):
        app.dependency_overrides.pop(get_market_client, None)
        Base.metadata.drop_all(bind=engine)

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    @staticmethod
    def _insight(*, availability: str, grade: str, sample_size: int, skills: list[tuple[str, int]], note: str | None = None) -> SkillInsightResponse:
        now = datetime.now(timezone.utc)
        return SkillInsightResponse(
            availability=availability,
            data_mode="historical",
            job_family="高级产品经理",
            sample_size=sample_size,
            calculated_at=now,
            methodology_version="market-skill-test-v1",
            quality_grade=grade,
            skills=[SkillItem(name=name, count=count, share=(count / sample_size if sample_size else None)) for name, count in skills],
            sources=[MarketSourceRef(source_id="market-test", source_name="隔离测试岗位样本", observed_at=now)],
            note=note,
        )

    def test_target_signal_gap_milestone_and_human_gated_action_loop(self):
        target_payload = {"request_id": "target-request-001", "target_type": "role", "title": "高级产品经理", "source_label": "本人职业规划"}
        target = self.client.post("/api/growth/direction/targets", headers=self._headers(self.alice), json=target_payload)
        self.assertEqual(201, target.status_code, target.text)
        replay = self.client.post("/api/growth/direction/targets", headers=self._headers(self.alice), json=target_payload)
        self.assertEqual(target.json()["id"], replay.json()["id"])
        conflict = self.client.post("/api/growth/direction/targets", headers=self._headers(self.alice), json={**target_payload, "title": "另一个目标"})
        self.assertEqual(409, conflict.status_code, conflict.text)
        foreign = self.client.post(f"/api/growth/direction/targets/{target.json()['id']}/confirm", headers=self._headers(self.bob), json={"expected_version": 1})
        self.assertEqual(404, foreign.status_code, foreign.text)
        active = self.client.post(f"/api/growth/direction/targets/{target.json()['id']}/confirm", headers=self._headers(self.alice), json={"expected_version": 1})
        self.assertEqual(200, active.status_code, active.text)
        self.assertEqual("active", active.json()["status"])
        self.assertEqual(2, active.json()["version"])

        self.market.insight = self._insight(availability="insufficient_sample", grade="insufficient", sample_size=2, skills=[("团队管理", 1)], note="仅 2 个样本")
        foreign_market = self.client.post("/api/growth/direction/market-signals/refresh", headers=self._headers(self.bob), json={"request_id": "market-request-foreign", "target_id": active.json()["id"], "limit": 8})
        self.assertEqual(404, foreign_market.status_code, foreign_market.text)
        weak = self.client.post("/api/growth/direction/market-signals/refresh", headers=self._headers(self.alice), json={"request_id": "market-request-weak-001", "target_id": active.json()["id"], "limit": 8})
        self.assertEqual(200, weak.status_code, weak.text)
        self.assertEqual("weak", weak.json()["signals"][0]["status"])
        weak_gap = self.client.post("/api/growth/direction/gaps", headers=self._headers(self.alice), json={"request_id": "gap-request-weak-001", "target_id": active.json()["id"]})
        self.assertEqual(201, weak_gap.status_code, weak_gap.text)
        self.assertEqual([], weak_gap.json()["gap_items"])
        self.assertIn("团队管理", weak_gap.json()["unknown_items"])

        candidate = self.client.post("/api/growth/assets/skills", headers=self._headers(self.alice), json={"skill_name": "产品策略", "source_layer": "user_claimed", "evidence_ids": []})
        self.assertEqual(201, candidate.status_code, candidate.text)
        confirmed_skill = self.client.post(f"/api/growth/assets/skills/{candidate.json()['id']}/confirm", headers=self._headers(self.alice), json={"expected_version": 1, "evidence_ids": []})
        self.assertEqual("user_claimed", confirmed_skill.json()["source_layer"])

        self.market.insight = self._insight(availability="available", grade="B", sample_size=20, skills=[("产品策略", 15), ("团队管理", 12)])
        strong = self.client.post("/api/growth/direction/market-signals/refresh", headers=self._headers(self.alice), json={"request_id": "market-request-strong-001", "target_id": active.json()["id"], "limit": 8})
        self.assertEqual(200, strong.status_code, strong.text)
        gap = self.client.post("/api/growth/direction/gaps", headers=self._headers(self.alice), json={"request_id": "gap-request-strong-001", "target_id": active.json()["id"]})
        self.assertEqual(201, gap.status_code, gap.text)
        self.assertEqual([], gap.json()["matched_items"])
        self.assertTrue(any("产品策略" in item and "待补证据" in item for item in gap.json()["unknown_items"]))
        self.assertIn("团队管理", gap.json()["gap_items"])
        gap_confirmed = self.client.post(f"/api/growth/direction/gaps/{gap.json()['id']}/confirm", headers=self._headers(self.alice), json={"expected_version": gap.json()["version"]})
        self.assertEqual(200, gap_confirmed.status_code, gap_confirmed.text)
        self.assertEqual("confirmed", gap_confirmed.json()["status"])

        milestone = self.client.post("/api/growth/direction/milestones", headers=self._headers(self.alice), json={"request_id": "milestone-request-001", "target_id": active.json()["id"], "gap_snapshot_id": gap_confirmed.json()["id"], "title": "形成一次带人实践", "success_criteria": "有一条本人确认的带人项目证据", "timeframe": "30d"})
        self.assertEqual(201, milestone.status_code, milestone.text)
        milestone_confirmed = self.client.patch(f"/api/growth/direction/milestones/{milestone.json()['id']}", headers=self._headers(self.alice), json={"expected_version": 1, "status": "confirmed"})
        self.assertEqual(200, milestone_confirmed.status_code, milestone_confirmed.text)
        self.assertEqual(2, milestone_confirmed.json()["version"])
        proposal = self.client.post(f"/api/growth/direction/milestones/{milestone_confirmed.json()['id']}/action-proposal", headers=self._headers(self.alice))
        self.assertEqual(200, proposal.status_code, proposal.text)
        with SessionLocal() as db:
            self.assertEqual(1, db.query(GrowthWorkIntake).filter(GrowthWorkIntake.user_id == self.alice["user_id"]).count())
            self.assertEqual(0, db.query(GrowthWorkItem).filter(GrowthWorkItem.user_id == self.alice["user_id"]).count())
        accepted = self.client.post(f"/api/growth/intakes/{proposal.json()['intake_id']}/confirm", headers=self._headers(self.alice), json={"selected": [{"candidate_key": proposal.json()["candidate_key"], "title": proposal.json()["title"]}]})
        self.assertEqual(201, accepted.status_code, accepted.text)
        workspace = self.client.get("/api/growth/direction/workspace", headers=self._headers(self.alice))
        self.assertEqual(200, workspace.status_code, workspace.text)
        self.assertEqual("confirmed", workspace.json()["milestones"][0]["status"])

        cleared = self.client.delete("/api/auth/data", headers=self._headers(self.alice))
        self.assertEqual(200, cleared.status_code, cleared.text)
        with SessionLocal() as db:
            for model in (GrowthMilestone, GrowthGapSnapshot, GrowthMarketSignal, GrowthFutureTarget):
                self.assertEqual(0, db.query(model).filter(model.user_id == self.alice["user_id"]).count())


if __name__ == "__main__":
    unittest.main()
