import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
TEST_UPLOAD_DIR = Path(tempfile.gettempdir()) / "career-guardian-resume-upload-tests"
shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "resume-guard-test-secret-not-for-production"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOAD_DIR)

from fastapi.testclient import TestClient

from app.api.routes.market import get_market_client
from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.opportunity_target import JobTarget, ResumeTailoringDraft
from app.schemas.market import JobDetailResponse
from app.services.document_service import extract_text
from app.services.opportunity_analysis_service import OpportunityAnalysisResult
from app.services.opportunity_analysis_service import analyze_resume_against_job, extract_resume_skills


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
        shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)

    def setUp(self):
        self._previous_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = str(TEST_UPLOAD_DIR)
        shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("resume-alice")
        self.bob = self._register("resume-bob")
        app.dependency_overrides[get_market_client] = lambda: _MarketStub()

    def tearDown(self):
        app.dependency_overrides.pop(get_market_client, None)
        shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
        settings.UPLOAD_DIR = self._previous_upload_dir

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

    def test_txt_upload_persists_private_versioned_original_and_full_detail(self):
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
        self.assertTrue(response.json()["has_original_file"])
        self.assertEqual("rules", response.json()["profile_parse_mode"])
        attachment_id = response.json()["attachment_version_id"]
        detail = self.client.get(
            f"/api/resumes/{response.json()['id']}", headers=self._headers(self.alice)
        )
        self.assertEqual(200, detail.status_code, detail.text)
        self.assertIn("Python", detail.json()["content_text"])
        self.assertIn("skills", detail.json()["structured_profile"])
        attachment = self.client.get(
            f"/api/attachments/{attachment_id}/file", headers=self._headers(self.alice)
        )
        self.assertEqual(200, attachment.status_code, attachment.text)
        self.assertIn("Python", attachment.content.decode())
        foreign = self.client.get(
            f"/api/attachments/{attachment_id}/file", headers=self._headers(self.bob)
        )
        self.assertEqual(404, foreign.status_code, foreign.text)
        with SessionLocal() as db:
            stored = db.get(PersonalAttachmentVersion, attachment_id)
            self.assertEqual(1, stored.version_number)
            self.assertTrue((TEST_UPLOAD_DIR / stored.storage_path).is_file())

    def test_reuploading_same_content_creates_a_new_resume_and_attachment_version(self):
        payload = ("应届生简历，使用 Python 和 SQL 完成课程数据分析、清洗和可视化项目。" * 2).encode()
        created = []
        for _ in range(2):
            result = self.client.post(
                "/api/resumes/upload",
                headers=self._headers(self.alice),
                files={"file": ("resume.txt", payload, "text/plain")},
            )
            self.assertEqual(201, result.status_code, result.text)
            created.append(result.json())
        self.assertEqual([1, 2], [item["version_number"] for item in created])
        self.assertNotEqual(created[0]["id"], created[1]["id"])
        self.assertNotEqual(created[0]["attachment_version_id"], created[1]["attachment_version_id"])

    def test_user_can_save_and_promote_job_to_target_with_owned_resume(self):
        resume = self._create_resume(self.alice)
        saved = self.client.post(
            "/api/opportunity/targets",
            headers=self._headers(self.alice),
            json={"job_id": "core:9", "status": "saved"},
        )
        self.assertEqual(201, saved.status_code, saved.text)
        self.assertEqual("数据分析实习生", saved.json()["job_snapshot"]["title"])
        self.assertIsNone(saved.json()["resume_version_id"])

        promoted = self.client.post(
            "/api/opportunity/targets",
            headers=self._headers(self.alice),
            json={"job_id": "core:9", "status": "target", "resume_version_id": resume["id"]},
        )
        self.assertEqual(201, promoted.status_code, promoted.text)
        self.assertEqual(saved.json()["id"], promoted.json()["id"])
        self.assertEqual("target", promoted.json()["status"])
        self.assertEqual(resume["id"], promoted.json()["resume_version_id"])
        self.assertEqual([], self.client.get("/api/opportunity/targets", headers=self._headers(self.bob)).json())

    @patch("app.api.routes.opportunity_targets.build_tailoring_draft")
    @patch("app.api.routes.opportunity_targets.build_learning_plan")
    def test_target_plan_and_tailoring_require_confirmation_before_new_resume(self, build_plan, build_draft):
        resume = self._create_resume(self.alice)
        target = self.client.post(
            "/api/opportunity/targets",
            headers=self._headers(self.alice),
            json={"job_id": "core:9", "status": "target", "resume_version_id": resume["id"]},
        ).json()
        build_plan.return_value = ({
            "summary": "你已有数据处理基础，可以先补一份看板作品。",
            "current_foundations": ["Python 项目"],
            "capability_gaps": [{"name": "Tableau", "priority": "high", "reason": "岗位明示", "evidence_status": "missing"}],
            "learning_route": [{"stage": "1", "title": "补作品", "duration": "2 周", "goals": [], "actions": ["完成看板"], "deliverable": "作品链接"}],
        }, "ai")
        plan = self.client.post(
            f"/api/opportunity/targets/{target['id']}/learning-plan", headers=self._headers(self.alice)
        )
        self.assertEqual(200, plan.status_code, plan.text)
        self.assertEqual("ai", plan.json()["mode"])

        tailored_text = "应届统计学本科生。\n项目经历：使用 Python 和 SQL 完成销售数据清洗与可视化，并汇报分析结论。\n技能：Python、SQL、Excel。"
        build_draft.return_value = (
            tailored_text,
            [{"section": "项目经历", "type": "rewrite", "before": "完成课程项目汇报", "after": "汇报分析结论", "reason": "突出表达结果"}],
            ["Tableau 暂无原文证据，未写入新简历"],
            "ai",
        )
        draft = self.client.post(
            f"/api/opportunity/targets/{target['id']}/resume-drafts", headers=self._headers(self.alice)
        )
        self.assertEqual(201, draft.status_code, draft.text)
        self.assertEqual("draft", draft.json()["status"])
        self.assertIn("完成课程项目汇报", draft.json()["source_text"])
        before_confirm = self.client.get("/api/resumes/", headers=self._headers(self.alice)).json()
        self.assertEqual(1, len(before_confirm))

        confirmed = self.client.post(
            f"/api/opportunity/resume-drafts/{draft.json()['id']}/confirm", headers=self._headers(self.alice)
        )
        self.assertEqual(201, confirmed.status_code, confirmed.text)
        self.assertEqual(2, confirmed.json()["version_number"])
        self.assertEqual("ai_tailored", confirmed.json()["creation_source"])
        self.assertEqual(resume["id"], confirmed.json()["parent_resume_version_id"])
        self.assertEqual("core:9", confirmed.json()["source_job_id"])
        original = self.client.get(f"/api/resumes/{resume['id']}", headers=self._headers(self.alice)).json()
        self.assertIn("完成课程项目汇报", original["content_text"])

    @patch("app.api.routes.opportunity_targets.build_tailoring_draft")
    def test_noop_tailoring_draft_cannot_create_duplicate_resume(self, build_draft):
        resume = self._create_resume(self.alice)
        target = self.client.post(
            "/api/opportunity/targets",
            headers=self._headers(self.alice),
            json={"job_id": "core:9", "status": "target", "resume_version_id": resume["id"]},
        ).json()
        source_text = self.client.get(f"/api/resumes/{resume['id']}", headers=self._headers(self.alice)).json()["content_text"]
        build_draft.return_value = (
            source_text,
            [{"section": "项目", "type": "rewrite", "before": "Python", "after": "Python", "reason": "无需修改"}],
            ["岗位差距较大"],
            "ai",
        )
        draft = self.client.post(
            f"/api/opportunity/targets/{target['id']}/resume-drafts", headers=self._headers(self.alice)
        ).json()
        confirmed = self.client.post(
            f"/api/opportunity/resume-drafts/{draft['id']}/confirm", headers=self._headers(self.alice)
        )
        self.assertEqual(409, confirmed.status_code, confirmed.text)
        self.assertEqual(1, len(self.client.get("/api/resumes/", headers=self._headers(self.alice)).json()))

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

        analyze.return_value = OpportunityAnalysisResult(
            analysis_mode="ai",
            match_score=72,
            matched_skills=["Python", "SQL"],
            missing_skills=["Tableau"],
            strengths=["你已经用 Python 和 SQL 完成过真实的数据项目"],
            risks=["Tableau 在当前简历中还没有证据，但不等于你不会使用"],
            suggestions=["把课程项目整理成一页可展示的数据分析案例"],
            summary="这份岗位值得尝试。你已经有数据处理基础，下一步优先补一份能展示分析过程的作品。",
        )
        refreshed = self.client.post(
            "/api/opportunity/guard",
            headers=self._headers(self.alice),
            json={**payload, "force_refresh": True},
        )
        self.assertEqual(201, refreshed.status_code, refreshed.text)
        self.assertFalse(refreshed.json()["reused"])
        self.assertEqual(72, refreshed.json()["match_score"])
        self.assertEqual(body["event_id"], refreshed.json()["event_id"])
        self.assertEqual(2, analyze.call_count)

        with SessionLocal() as db:
            event = db.query(CareerEvent).one()
            self.assertEqual("resume_match", event.stage)
            self.assertEqual(2, db.query(Evidence).filter_by(event_id=event.id).count())
            finding = db.query(GuardianFinding).filter_by(event_id=event.id).one()
            self.assertEqual("ai_assistance", finding.source_type)
            action = db.query(ActionItem).filter_by(event_id=event.id).one()
            self.assertEqual("draft", action.status)
            self.assertTrue(action.requires_confirmation)
            self.assertEqual(1, db.query(OpportunityAnalysis).count())

        event_detail = self.client.get(
            f"/api/events/{body['event_id']}", headers=self._headers(self.alice)
        )
        self.assertEqual(200, event_detail.status_code, event_detail.text)
        self.assertEqual("这份简历与岗位明示要求的契合度为 72%", event_detail.json()["findings"][0]["title"])

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
            self.assertEqual(0, db.query(PersonalAttachmentVersion).count())


class ResumeDocumentExtractionTest(unittest.TestCase):
    @patch("app.services.opportunity_analysis_service._call_llm")
    def test_ai_result_uses_second_person_and_cannot_mark_resume_evidence_missing(self, call_llm):
        call_llm.return_value = """{
          "match_score": 60,
          "matched_skills": ["Java"],
          "missing_skills": ["Kafka", "Dubbo"],
          "strengths": ["该候选人具备 Java 项目经验"],
          "risks": [],
          "suggestions": [],
          "summary": "候选人具备后端基础，可以尝试。"
        }"""
        result = analyze_resume_against_job(
            "使用 Java 和 Kafka 完成订单系统项目。",
            ["Java", "Kafka"],
            {"skills": ["Java", "Kafka", "Dubbo"]},
        )
        self.assertEqual(["Dubbo"], result.missing_skills)
        self.assertIn("你具备", result.strengths[0])
        self.assertNotIn("候选人", result.summary)

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
