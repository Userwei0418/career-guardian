import os
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "career-guardian-fp00-test.sqlite3"
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH}"
os.environ["JWT_SECRET"] = "fp00-test-secret-only-not-for-production"

from fastapi.testclient import TestClient

from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.api.routes.market_admin import get_market_admin_client
from app.models.finding import Finding
from app.models.ai_configuration import AIConfigurationAudit, AIInvocationLog, AIProviderSetting
from app.models.knowledge_article import KnowledgeArticle
from app.models.opportunity_target import JobTarget
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.services.assistant_service import _call_llm
from app.services.ai_configuration_service import effective_ai_configuration, record_ai_invocation
from app.services.speech_service import plan_audio_cache_hash, synthesize_plan_summary


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

    def test_knowledge_api_reads_published_articles_from_database(self):
        with SessionLocal() as db:
            db.add(
                KnowledgeArticle(
                    slug="database-backed-article",
                    title="数据库文章",
                    category="新手必知",
                    tags=["MySQL"],
                    keywords=["数据库"],
                    summary="数据库读取验证",
                    content="正文",
                    sort_order=1,
                )
            )
            db.commit()
        response = self.client.get(
            "/api/knowledge/", headers=self._headers(self.alice)
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("database-backed-article", response.json()[0]["slug"])

    def test_finance_contract_preserves_structured_housing_withdrawal_rules(self):
        headers = self._headers(self.alice)
        response = self.client.get(
            "/api/finance/housing-fund?monthly_contribution=3600&months_paid=24",
            headers=headers,
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertGreater(body["current_balance"], 0)
        self.assertEqual(
            {"scene", "condition", "amount"},
            set(body["withdrawal_rules"][0]),
        )

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

    def test_offer_archive_links_target_attachment_and_deadline_with_owner_scope(self):
        with SessionLocal() as db:
            alice_user = db.query(User).filter(User.username == "alice").one()
            bob_user = db.query(User).filter(User.username == "bob").one()
            alice_target = JobTarget(user_id=alice_user.id, job_id="core:alice", status="target", job_snapshot={"title": "后端开发工程师"})
            bob_target = JobTarget(user_id=bob_user.id, job_id="core:bob", status="target", job_snapshot={"title": "越权岗位"})
            alice_attachment = PersonalAttachmentVersion(
                user_id=alice_user.id, document_type="offer", logical_key="alice-offer", version_number=1,
                display_name="Alice Offer", original_filename="offer.pdf", content_type="application/pdf",
                storage_path="personal/alice-offer.pdf", file_size=10, content_hash="a" * 64, is_active=True,
            )
            bob_attachment = PersonalAttachmentVersion(
                user_id=bob_user.id, document_type="offer", logical_key="bob-offer", version_number=1,
                display_name="Bob Offer", original_filename="offer.pdf", content_type="application/pdf",
                storage_path="personal/bob-offer.pdf", file_size=10, content_hash="b" * 64, is_active=True,
            )
            db.add_all([alice_target, bob_target, alice_attachment, bob_attachment])
            db.commit()
            ids = alice_target.id, bob_target.id, alice_attachment.id, bob_attachment.id

        alice_target_id, bob_target_id, alice_attachment_id, bob_attachment_id = ids
        headers = self._headers(self.alice)
        created = self.client.post(
            "/api/offers/",
            headers=headers,
            json={
                "company_name": "目标公司",
                "job_title": "后端开发工程师",
                "job_target_id": alice_target_id,
                "source_attachment_id": alice_attachment_id,
                "offer_kind": "verbal",
                "response_deadline": "2026-08-20T18:00:00",
            },
        )
        self.assertEqual(200, created.status_code, created.text)
        body = created.json()
        self.assertEqual(alice_target_id, body["job_target_id"])
        self.assertEqual(alice_attachment_id, body["source_attachment_id"])
        self.assertEqual("verbal", body["offer_kind"])
        self.assertEqual("evaluating", body["decision_status"])
        self.assertIsNotNone(body["facts_confirmed_at"])

        foreign_target = self.client.post(
            "/api/offers/",
            headers=headers,
            json={"company_name": "越权目标", "job_target_id": bob_target_id},
        )
        foreign_attachment = self.client.post(
            "/api/offers/",
            headers=headers,
            json={"company_name": "越权附件", "source_attachment_id": bob_attachment_id},
        )
        self.assertEqual(404, foreign_target.status_code, foreign_target.text)
        self.assertEqual(404, foreign_attachment.status_code, foreign_attachment.text)

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

    def test_market_collection_management_is_admin_only(self):
        class FakeMarketAdminClient:
            @staticmethod
            def list_sources():
                return {
                    "sources": [
                        {
                            "code": "official-api",
                            "name": "官方招聘 API",
                            "adapter_type": "api",
                            "base_url": "https://jobs.example.com/api",
                            "allowed_hosts": ["jobs.example.com"],
                            "terms_review_status": "approved",
                            "enabled": True,
                            "can_run": True,
                            "raw_record_count": 12,
                            "updated_at": "2026-08-15T08:00:00",
                        }
                    ]
                }

            @staticmethod
            def list_tasks(limit: int = 50):
                return {"tasks": [], "total": 0}

            @staticmethod
            def run_source(source_code: str):
                return {
                    "id": 1,
                    "task_uid": "00000000-0000-0000-0000-000000000001",
                    "source_code": source_code,
                    "source_name": "官方招聘 API",
                    "adapter_type": "api",
                    "trigger_type": "live",
                    "status": "succeeded",
                    "attempt_count": 1,
                    "records_seen": 2,
                    "records_stored": 2,
                    "duplicate_records": 0,
                    "failed_records": 0,
                    "started_at": "2026-08-15T08:00:00",
                    "completed_at": "2026-08-15T08:00:01",
                    "created_at": "2026-08-15T08:00:00",
                }

            @staticmethod
            def get_gate_settings():
                configuration = {
                    "policy_version": "career-guardian-job-core-v1",
                    "minimum_core_score": 55,
                    "minimum_description_chars": 50,
                    "live_freshness_days": 14,
                    "maximum_future_hours": 48,
                    "maximum_salary": 1000000,
                    "required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "score_weights": {
                        "identity": 30,
                        "source_url": 15,
                        "content_hash": 5,
                        "description": 15,
                        "city": 10,
                        "published_at": 5,
                        "observed_at": 5,
                        "skills": 5,
                        "salary": 10,
                    },
                }
                return {
                    "active": {
                        "id": 1,
                        "policy_version": configuration["policy_version"],
                        "status": "active",
                        "configuration": configuration,
                        "change_note": "initial",
                        "created_by": "system",
                        "published_by": "system",
                        "created_at": "2026-08-15T08:00:00",
                        "updated_at": "2026-08-15T08:00:00",
                        "published_at": "2026-08-15T08:00:00",
                        "certified_jobs": 12,
                    },
                    "draft": None,
                    "certified_job_counts": {configuration["policy_version"]: 12},
                    "supported_required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "immutable_required_facts": ["company_name", "title", "source_url", "content_hash", "observed_at"],
                    "score_dimensions": list(configuration["score_weights"]),
                    "publish_scope": "future_ingestion",
                }

        with SessionLocal() as db:
            admin = db.query(User).filter(User.id == self.alice["user_id"]).one()
            admin.is_admin = True
            db.commit()

        app.dependency_overrides[get_market_admin_client] = lambda: FakeMarketAdminClient()
        try:
            ordinary = self.client.get(
                "/api/admin/market/sources",
                headers=self._headers(self.bob),
            )
            self.assertEqual(403, ordinary.status_code, ordinary.text)

            sources = self.client.get(
                "/api/admin/market/sources",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, sources.status_code, sources.text)
            self.assertEqual("official-api", sources.json()["sources"][0]["code"])

            gate = self.client.get(
                "/api/admin/market/gate",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, gate.status_code, gate.text)
            self.assertEqual("career-guardian-job-core-v1", gate.json()["active"]["policy_version"])

            run = self.client.post(
                "/api/admin/market/sources/official-api/runs",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, run.status_code, run.text)
            self.assertEqual("succeeded", run.json()["status"])
        finally:
            app.dependency_overrides.pop(get_market_admin_client, None)

    def test_ai_configuration_is_admin_only_encrypted_and_masked(self):
        with SessionLocal() as db:
            admin = db.query(User).filter(User.id == self.alice["user_id"]).one()
            admin.is_admin = True
            db.commit()

        ordinary = self.client.get(
            "/api/admin/ai/config",
            headers=self._headers(self.bob),
        )
        self.assertEqual(403, ordinary.status_code, ordinary.text)

        test_key = "sk-test-admin-configuration-1234567890"
        saved = self.client.put(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
            json={
                "provider_name": "SenseAudio",
                "base_url": "https://api.senseaudio.cn/v1/",
                "model": "deepseek-v4-flash",
                "api_key": test_key,
                "is_enabled": True,
            },
        )
        self.assertEqual(200, saved.status_code, saved.text)
        body = saved.json()
        self.assertEqual("https://api.senseaudio.cn/v1", body["base_url"])
        self.assertEqual("database", body["source"])
        self.assertTrue(body["tts_enabled"])
        self.assertEqual("senseaudio-tts-1.5-260319", body["tts_model"])
        self.assertEqual("senseaudio-realtime-1.0", body["realtime_model"])
        self.assertEqual("已配置（尾号 7890）", body["api_key_masked"])
        self.assertNotIn("api_key", body)
        self.assertNotIn(test_key, saved.text)

        with SessionLocal() as db:
            stored = db.query(AIProviderSetting).one()
            self.assertNotIn(test_key, stored.api_key_encrypted)
            encrypted_before = stored.api_key_encrypted

        preserved = self.client.put(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
            json={
                "provider_name": "SenseAudio",
                "base_url": "https://api.senseaudio.cn/v1",
                "model": "deepseek-v4-flash",
                "is_enabled": True,
            },
        )
        self.assertEqual(200, preserved.status_code, preserved.text)
        with SessionLocal() as db:
            self.assertEqual(encrypted_before, db.query(AIProviderSetting).one().api_key_encrypted)

        class FakeLLMResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return json.dumps(
                    {
                        "choices": [{"message": {"content": "OK"}}],
                        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
                    }
                ).encode()

        with SessionLocal() as db, patch(
            "app.services.assistant_service.urllib.request.urlopen",
            return_value=FakeLLMResponse(),
        ) as urlopen:
            self.assertEqual("OK", _call_llm("test", feature="runtime_test", db=db, user_id=self.alice["user_id"]))
            request = urlopen.call_args.args[0]
            self.assertEqual("https://api.senseaudio.cn/v1/chat/completions", request.full_url)
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
            invocation = db.query(AIInvocationLog).one()
            self.assertEqual(("runtime_test", "success", 4), (invocation.feature, invocation.status, invocation.total_tokens))
            self.assertEqual(("text", 4, "tokens"), (invocation.modality, invocation.usage_amount, invocation.usage_unit))

        ordinary_logs = self.client.get(
            "/api/admin/ai/invocations",
            headers=self._headers(self.bob),
        )
        self.assertEqual(403, ordinary_logs.status_code, ordinary_logs.text)
        invocation_logs = self.client.get(
            "/api/admin/ai/invocations?page=1&page_size=10&feature=runtime_test&status=success",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, invocation_logs.status_code, invocation_logs.text)
        log_body = invocation_logs.json()
        self.assertEqual((1, 1, 1), (log_body["total"], log_body["page"], log_body["total_pages"]))
        self.assertEqual("runtime_test", log_body["items"][0]["feature"])
        self.assertEqual("text", log_body["items"][0]["modality"])
        self.assertIn("text", log_body["modalities"])

        self.assertEqual((self.alice["user_id"], "alice"), (log_body["items"][0]["user_id"], log_body["items"][0]["username"]))
        self.assertEqual((3, 1, 4), (
            log_body["items"][0]["prompt_tokens"],
            log_body["items"][0]["completion_tokens"],
            log_body["items"][0]["total_tokens"],
        ))
        self.assertIn("runtime_test", log_body["features"])
        self.assertNotIn('"messages"', invocation_logs.text.lower())
        self.assertNotIn('"content"', invocation_logs.text.lower())
        self.assertNotIn(test_key, invocation_logs.text)

        with SessionLocal() as db:
            configuration = effective_ai_configuration(db)
            self.assertIsNotNone(configuration)
            record_ai_invocation(
                db,
                configuration,
                feature="test_tts_usage",
                modality="audio",
                model="senseaudio-tts-test",
                status="success",
                latency_ms=120,
                usage_amount=96,
                usage_unit="characters",
                user_id=self.alice["user_id"],
            )
            record_ai_invocation(
                db,
                configuration,
                feature="test_realtime_usage",
                modality="realtime",
                model="senseaudio-realtime-test",
                status="success",
                latency_ms=5000,
                usage_amount=5,
                usage_unit="seconds",
                user_id=self.alice["user_id"],
            )

        usage_summary = self.client.get("/api/admin/ai/config", headers=self._headers(self.alice))
        self.assertEqual(200, usage_summary.status_code, usage_summary.text)
        self.assertEqual(
            (3, 1, 4),
            (
                usage_summary.json()["usage"]["prompt_tokens"],
                usage_summary.json()["usage"]["completion_tokens"],
                usage_summary.json()["usage"]["total_tokens"],
            ),
        )
        usage_buckets = {
            (item["modality"], item["usage_unit"]): item["amount"]
            for item in usage_summary.json()["usage"]["usage_breakdown"]
        }
        self.assertEqual(4, usage_buckets[("text", "tokens")])
        self.assertEqual(96, usage_buckets[("audio", "characters")])
        self.assertEqual(5, usage_buckets[("realtime", "seconds")])

        with patch("app.api.routes.ai_admin._call_llm", return_value="OK"):
            tested = self.client.post(
                "/api/admin/ai/config/test",
                headers=self._headers(self.alice),
            )
        self.assertEqual(200, tested.status_code, tested.text)
        self.assertTrue(tested.json()["success"])
        current = self.client.get(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
        )
        self.assertEqual("success", current.json()["last_test_status"])

        blocked_host = self.client.put(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
            json={
                "provider_name": "未知服务",
                "base_url": "https://example.invalid/v1",
                "model": "some-model",
                "is_enabled": True,
            },
        )
        self.assertEqual(400, blocked_host.status_code, blocked_host.text)
        with SessionLocal() as db:
            actions = [row.action for row in db.query(AIConfigurationAudit).order_by(AIConfigurationAudit.id)]
            self.assertEqual(["created", "updated", "connection_test_success"], actions)

        short_secret = "tiny"
        invalid_secret = self.client.put(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
            json={
                "provider_name": "SenseAudio",
                "base_url": "https://api.senseaudio.cn/v1",
                "model": "deepseek-v4-flash",
                "api_key": short_secret,
                "is_enabled": True,
            },
        )
        self.assertEqual(422, invalid_secret.status_code, invalid_secret.text)
        self.assertNotIn(short_secret, invalid_secret.text)

    def test_tts_uses_audio_configuration_and_logs_character_usage(self):
        with SessionLocal() as db:
            admin = db.query(User).filter(User.id == self.alice["user_id"]).one()
            admin.is_admin = True
            db.commit()
        self.client.put(
            "/api/admin/ai/config",
            headers=self._headers(self.alice),
            json={
                "provider_name": "SenseAudio",
                "base_url": "https://api.senseaudio.cn/v1",
                "model": "deepseek-v4-flash",
                "tts_enabled": True,
                "tts_model": "senseaudio-tts-1.5-260319",
                "tts_voice_id": "female_0033_b",
                "realtime_enabled": False,
                "realtime_model": "senseaudio-realtime-1.0",
                "realtime_voice_id": "f_y_0035_c",
                "api_key": "sk-test-tts-configuration-1234567890",
                "is_enabled": True,
            },
        )

        class FakeTTSResponse:
            def raise_for_status(self):
                return None

            @staticmethod
            def json():
                return {
                    "base_resp": {"status_code": 0},
                    "data": {"status": 2, "audio": "494433"},
                    "extra_info": {"usage_characters": 12},
                }

        with SessionLocal() as db, patch("app.services.speech_service.httpx.post", return_value=FakeTTSResponse()) as post:
            configuration = effective_ai_configuration(db)
            original_hash = plan_audio_cache_hash("这是能力路线摘要", configuration)
            self.assertNotEqual(original_hash, plan_audio_cache_hash("这是能力路线摘要", replace(configuration, tts_voice_id="female_0038_b")))
            self.assertNotEqual(original_hash, plan_audio_cache_hash("这是另一份能力路线摘要", configuration))
            audio, content_type = synthesize_plan_summary(db, user_id=self.alice["user_id"], text="这是能力路线摘要")
            self.assertEqual((b"ID3", "audio/mpeg"), (audio, content_type))
            self.assertEqual("https://api.senseaudio.cn/v1/t2a_v2", post.call_args.args[0])
            payload = post.call_args.kwargs["json"]
            self.assertFalse(payload["stream"])
            self.assertEqual("female_0033_b", payload["voice_setting"]["voice_id"])
            invocation = db.query(AIInvocationLog).one()
            self.assertEqual(
                ("audio", "target_plan_tts", 12, "characters"),
                (invocation.modality, invocation.feature, invocation.usage_amount, invocation.usage_unit),
            )


if __name__ == "__main__":
    unittest.main()
