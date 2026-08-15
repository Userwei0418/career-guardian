import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "resume-guard-test-secret-not-for-production"

from fastapi.testclient import TestClient

from app.api.routes.market import get_market_client
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.schemas.market import JobDetailResponse
from app.services.document_service import extract_text
from app.services.opportunity_analysis_service import OpportunityAnalysisResult
from app.services.opportunity_analysis_service import extract_resume_skills


class _MarketStub:
    def get_job(self, job_id: str) -> JobDetailResponse:
        return JobDetailResponse.model_validate(
            {
                "availability": "available",
                "data_mode": "historical",
                "job": {
                    "job_id": job_id,
                    "title": "数据分析实习生",
                    "company_name": "样例科技",
                    "city": "上海",
                    "recruitment_type": "internship",
                    "salary_min": 180,
                    "salary_max": 220,
                    "salary_period": "day",
                    "skills": ["Python", "SQL", "Tableau"],
                    "status": "open",
                    "data_mode": "historical",
                    "quality": {
                        "grade": "B",
                        "sample_size": 1,
                        "methodology_version": "test-v1",
                    },
                    "sources": [
                        {
                            "source_id": "test-source:1",
                            "source_name": "测试岗位源",
                            "source_url": "https://jobs.example.invalid/1",
                            "observed_at": "2026-08-15T00:00:00Z",
                        }
                    ],
                },
                "company": {"company_id": "company:1", "name": "样例科技"},
                "description": "协助完成经营数据分析和周报。",
                "requirements": "熟悉 Python、SQL 和 Tableau。",
                "responsibilities": "负责清洗数据、制作看板。",
                "education_requirement": "本科及以上",
                "major_requirement": "统计学、计算机相关专业",
                "first_seen_at": "2026-08-01T00:00:00Z",
                "last_seen_at": "2026-08-15T00:00:00Z",
                "quality_score": 86,
                "quality_reasons": [],
                "gate_policy_version": "test-v1",
                "gate_evaluated_at": "2026-08-15T00:00:00Z",
            }
        )


class ResumeOpportunityGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_market_client, None)
        cls.client.close()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("resume-alice")
        self.bob = self._register("resume-bob")
        app.dependency_overrides[get_market_client] = lambda: _MarketStub()

    def tearDown(self):
        app.dependency_overrides.pop(get_market_client, None)

    def _register(self, username: str) -> dict:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "resume-secure-password"},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _create_resume(self, auth: dict, name: str = "数据分析简历") -> dict:
        response = self.client.post(
            "/api/resumes/paste",
            headers=self._headers(auth),
            json={
                "display_name": name,
                "text": "应届统计学本科生，使用 Python 和 SQL 完成销售数据清洗与可视化项目，熟悉 Excel。曾负责定义指标、检查异常数据并完成课程项目汇报。",
            },
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_resume_versions_are_private_and_only_one_is_active(self):
        first = self._create_resume(self.alice)
        second = self.client.post(
            "/api/resumes/paste",
            headers=self._headers(self.alice),
            json={
                "display_name": "投递版",
                "text": "应届生，参与校园数据项目，掌握 Python、SQL、Tableau 和 Power BI，能够完成数据分析报告。",
            },
        )
        self.assertEqual(201, second.status_code, second.text)
        self.assertEqual(2, second.json()["version_number"])

        listed = self.client.get("/api/resumes/", headers=self._headers(self.alice)).json()
        self.assertEqual([2, 1], [item["version_number"] for item in listed])
        self.assertEqual(1, sum(1 for item in listed if item["is_active"]))
        self.assertNotIn("content_text", listed[0])

        activated = self.client.patch(
            f"/api/resumes/{first['id']}/activate", headers=self._headers(self.alice)
        )
        self.assertEqual(200, activated.status_code, activated.text)
        self.assertTrue(activated.json()["is_active"])
        foreign = self.client.patch(
            f"/api/resumes/{first['id']}/activate", headers=self._headers(self.bob)
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

    def test_txt_upload_is_parsed_without_persisting_original_file(self):
        before = set(Path(tempfile.gettempdir()).glob("*.txt"))
        response = self.client.post(
            "/api/resumes/upload",
            headers=self._headers(self.alice),
            files={
                "file": (
                    "resume.txt",
                    "应届生数据分析简历。掌握 Python、SQL 和 Excel，参与过校园调研、数据清洗和可视化项目。".encode(),
                    "text/plain",
                )
            },
        )
        self.assertEqual(201, response.status_code, response.text)
        self.assertEqual("text", response.json()["parse_mode"])
        self.assertGreater(response.json()["text_length"], 50)
        self.assertEqual(before, set(Path(tempfile.gettempdir()).glob("*.txt")))

    @patch("app.api.routes.opportunity_guard.analyze_resume_against_job")
    def test_guard_creates_traceable_draft_and_reuses_same_resume_job(self, analyze):
        analyze.return_value = OpportunityAnalysisResult(
            analysis_mode="rules",
            match_score=67,
            matched_skills=["Python", "SQL"],
            missing_skills=["Tableau"],
            strengths=["简历有数据清洗项目证据"],
            risks=["Tableau 暂未找到证据"],
            suggestions=["补充 Tableau 看板作品"],
            summary="当前简历覆盖两项明示技能，仍需补充可视化工具证据。",
        )
        resume = self._create_resume(self.alice)
        payload = {"job_id": "core:9", "resume_version_id": resume["id"]}
        created = self.client.post(
            "/api/opportunity/guard", headers=self._headers(self.alice), json=payload
        )
        self.assertEqual(201, created.status_code, created.text)
        body = created.json()
        self.assertFalse(body["reused"])
        self.assertEqual(67, body["match_score"])
        self.assertEqual("rules", body["analysis_mode"])

        repeated = self.client.post(
            "/api/opportunity/guard", headers=self._headers(self.alice), json=payload
        )
        self.assertEqual(201, repeated.status_code, repeated.text)
        self.assertTrue(repeated.json()["reused"])
        self.assertEqual(body["event_id"], repeated.json()["event_id"])
        self.assertEqual(1, analyze.call_count)

        with SessionLocal() as db:
            event = db.query(CareerEvent).one()
            self.assertEqual("resume_match", event.stage)
            self.assertEqual(2, db.query(Evidence).filter_by(event_id=event.id).count())
            finding = db.query(GuardianFinding).filter_by(event_id=event.id).one()
            self.assertEqual("calculation", finding.source_type)
            action = db.query(ActionItem).filter_by(event_id=event.id).one()
            self.assertEqual("draft", action.status)
            self.assertTrue(action.requires_confirmation)
            self.assertEqual(1, db.query(OpportunityAnalysis).count())

        event_detail = self.client.get(
            f"/api/events/{body['event_id']}", headers=self._headers(self.alice)
        )
        self.assertEqual(200, event_detail.status_code, event_detail.text)
        self.assertEqual("简历与岗位明示要求匹配度 67%", event_detail.json()["findings"][0]["title"])

    def test_guard_rejects_another_users_resume_and_clear_removes_resume_graph(self):
        resume = self._create_resume(self.alice)
        foreign = self.client.post(
            "/api/opportunity/guard",
            headers=self._headers(self.bob),
            json={"job_id": "core:9", "resume_version_id": resume["id"]},
        )
        self.assertEqual(404, foreign.status_code, foreign.text)

        cleared = self.client.delete("/api/auth/data", headers=self._headers(self.alice))
        self.assertEqual(200, cleared.status_code, cleared.text)
        self.assertEqual([], self.client.get("/api/resumes/", headers=self._headers(self.alice)).json())
        with SessionLocal() as db:
            self.assertEqual(0, db.query(ResumeVersion).count())


class ResumeDocumentExtractionTest(unittest.TestCase):
    def test_text_extraction_supports_utf8_and_rejects_too_short(self):
        result = extract_text(("数据分析简历：Python、SQL、Excel。" * 5).encode(), "resume.txt")
        self.assertEqual("text", result.parse_mode)
        self.assertIn("Python", result.raw_text)
        too_short = extract_text("过短".encode(), "resume.txt")
        self.assertEqual("failed", too_short.parse_mode)

    def test_skill_extraction_does_not_turn_chinese_text_into_c_plus_plus(self):
        skills = extract_resume_skills("掌握 Python、SQL 和 Excel，具备沟通能力。")
        self.assertEqual(["Python", "SQL", "Excel", "沟通能力"], skills)
        self.assertNotIn("C++", skills)


if __name__ == "__main__":
    unittest.main()
