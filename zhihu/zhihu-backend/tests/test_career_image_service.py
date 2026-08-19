import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from mysql_test_support import mysql_test

from app.db.session import Base, SessionLocal, engine
from app.main import app as _app  # noqa: F401 - load the complete ORM metadata graph
from app.models.ai_configuration import CareerImageGeneration
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.ai_configuration_service import EffectiveImageConfiguration
from app.services.career_image_service import (
    CareerImageProviderError,
    _utcnow,
    _validate_result_url,
    build_career_image_summary,
    build_image_prompt,
    mark_current_staleness,
    pending_generation,
    refresh_generation,
    start_generation,
)


def _image_configuration() -> EffectiveImageConfiguration:
    return EffectiveImageConfiguration(
        setting_id=None,
        provider_name="SenseAudio",
        base_url="https://api.senseaudio.cn/v1",
        model="senseaudio-image-2.0-260319",
        landscape_size="1536x864",
        square_size="1024x1024",
        poll_interval_seconds=3,
        timeout_seconds=900,
        style_prompt="温暖克制的 2.5D 编辑插画，玉石绿主色。",
        landscape_prompt="16:9 横向首页主视觉，左侧留白。",
        square_prompt="1:1 方形个人中心插画，主体居中。",
        api_key="test-image-key",
        source="test",
    )


class CareerImagePromptTest(unittest.TestCase):
    def test_prompt_has_fixed_style_and_privacy_boundaries(self):
        summary = {
            "career_stage": "职业起步期",
            "target_roles": ["数据分析师"],
            "confirmed_skills": ["Python", "SQL"],
            "evidence_based_strengths": ["能够完成数据清洗和可视化"],
            "growth_focus": ["业务理解"],
            "career_priorities": ["成长空间"],
            "evidence_counts": {"resume_versions": 1},
        }

        landscape = build_image_prompt(
            summary,
            variant="landscape",
            style_prompt="温暖克制的 2.5D 编辑插画",
            scene_prompt="16:9 横向首页主视觉",
        )
        square = build_image_prompt(
            summary,
            variant="square",
            style_prompt="温暖克制的 2.5D 编辑插画",
            scene_prompt="1:1 方形个人中心插画",
        )

        self.assertIn("16:9 横向首页主视觉", landscape)
        self.assertIn("1:1 方形个人中心插画", square)
        for prompt in (landscape, square):
            self.assertIn("匿名、性别中性的风格化人物", prompt)
            self.assertIn("禁止出现任何文字", prompt)
            self.assertIn("不推断年龄、性别、民族、健康、宗教", prompt)
            self.assertNotIn("test-image-key", prompt)

    def test_prompt_keeps_server_safety_rules_when_admin_prompts_change(self):
        prompt = build_image_prompt(
            {"target_roles": ["产品经理"]},
            variant="square",
            style_prompt="低饱和拼贴风格",
            scene_prompt="人物居中并使用柔和背景",
        )
        self.assertIn("低饱和拼贴风格", prompt)
        self.assertIn("人物居中并使用柔和背景", prompt)
        self.assertIn("禁止出现任何文字", prompt)
        self.assertIn("不得出现简历、证件、联系方式", prompt)

    def test_result_url_rejects_non_https_and_private_hosts(self):
        for url in ("http://images.example.com/a.png", "https://127.0.0.1/a.png"):
            with self.subTest(url=url), self.assertRaises(CareerImageProviderError):
                _validate_result_url(url)


@mysql_test
class CareerImageWorkflowTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            user = User(
                username="career-image-user",
                password_hash="not-used-in-service-test",
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(
                UserProfile(
                    user_id=user.id,
                    career_stage="early_career",
                    years_of_experience=1,
                    target_roles=["星河集团数据分析师", "13800138000"],
                    skills=["Python", "SQL", "person@example.com"],
                    priorities=["成长空间", "https://private.example/resume"],
                )
            )
            db.commit()
            self.user_id = user.id

    def test_summary_is_minimal_deterministic_and_redacted(self):
        with SessionLocal() as db:
            first, fingerprint, message = build_career_image_summary(db, self.user_id)
            second, second_fingerprint, _ = build_career_image_summary(db, self.user_id)

        rendered = json.dumps(first, ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)
        self.assertEqual(fingerprint, second_fingerprint)
        self.assertEqual(64, len(fingerprint))
        self.assertIn("Python", first["confirmed_skills"])
        self.assertIn("已确认", message)
        self.assertNotIn("13800138000", rendered)
        self.assertNotIn("person@example.com", rendered)
        self.assertNotIn("private.example", rendered)
        self.assertNotIn("星河集团", rendered)

    def test_async_dual_image_success_and_failed_refresh_keeps_old_current(self):
        configuration = _image_configuration()
        with SessionLocal() as db, patch(
            "app.services.career_image_service.effective_image_configuration",
            return_value=configuration,
        ), patch(
            "app.services.career_image_service._submit_variant",
            side_effect=[("landscape-task-1", 4), ("square-task-1", 5)],
        ):
            first = start_generation(db, self.user_id)
            self.assertEqual("submitted", first.status)
            self.assertEqual("landscape-task-1", first.landscape_task_id)
            self.assertEqual("square-task-1", first.square_task_id)

            def complete_variant(_db, row, _configuration, variant):
                setattr(row, f"{variant}_status", "completed")
                setattr(row, f"{variant}_image", b"generated-image")
                setattr(row, f"{variant}_content_type", "image/png")

            with patch(
                "app.services.career_image_service._poll_variant",
                side_effect=complete_variant,
            ):
                first = refresh_generation(db, first)

            self.assertEqual("completed", first.status)
            self.assertTrue(first.is_current)
            self.assertTrue(first.landscape_image)
            self.assertTrue(first.square_image)

            profile = db.query(UserProfile).filter(UserProfile.user_id == self.user_id).one()
            profile.skills = ["Python", "SQL", "Tableau"]
            db.commit()
            current, _message, ready = mark_current_staleness(db, self.user_id)
            self.assertTrue(ready)
            self.assertTrue(current.is_stale)

            with patch(
                "app.services.career_image_service._submit_variant",
                side_effect=[("landscape-task-2", 3), CareerImageProviderError("provider_down")],
            ):
                second = start_generation(db, self.user_id)
            self.assertEqual(2, second.version_number)
            self.assertEqual("failed", second.square_status)

            def finish_landscape_only(_db, row, _configuration, variant):
                if variant == "landscape":
                    row.landscape_status = "completed"
                    row.landscape_image = b"new-landscape"
                    row.landscape_content_type = "image/png"

            with patch(
                "app.services.career_image_service._poll_variant",
                side_effect=finish_landscape_only,
            ):
                second = refresh_generation(db, second)

            self.assertEqual("partial", second.status)
            self.assertFalse(second.is_current)
            old = db.get(CareerImageGeneration, first.id)
            self.assertTrue(old.is_current)

    def test_expired_local_deadline_polls_provider_before_marking_timeout(self):
        configuration = _image_configuration()
        with SessionLocal() as db, patch(
            "app.services.career_image_service.effective_image_configuration",
            return_value=configuration,
        ), patch(
            "app.services.career_image_service._submit_variant",
            side_effect=[("late-landscape", 2), ("late-square", 2)],
        ):
            row = start_generation(db, self.user_id)
            row.submitted_at = _utcnow() - timedelta(seconds=configuration.timeout_seconds + 1)
            db.commit()

            def complete_late_variant(_db, generation, _configuration, variant):
                setattr(generation, f"{variant}_status", "completed")
                setattr(generation, f"{variant}_image", b"late-image")
                setattr(generation, f"{variant}_content_type", "image/png")

            with patch(
                "app.services.career_image_service._poll_variant",
                side_effect=complete_late_variant,
            ) as poll:
                row = refresh_generation(db, row)

            self.assertEqual(2, poll.call_count)
            self.assertEqual("completed", row.status)
            self.assertIsNone(row.landscape_error)
            self.assertIsNone(row.square_error)

    def test_false_timeout_can_reconcile_late_provider_result(self):
        configuration = _image_configuration()
        with SessionLocal() as db, patch(
            "app.services.career_image_service.effective_image_configuration",
            return_value=configuration,
        ), patch(
            "app.services.career_image_service._submit_variant",
            side_effect=[("recover-landscape", 2), ("recover-square", 2)],
        ):
            row = start_generation(db, self.user_id)
            row.status = "failed"
            row.landscape_status = "failed"
            row.square_status = "failed"
            row.landscape_error = "generation_timeout"
            row.square_error = "generation_timeout"
            row.completed_at = _utcnow()
            db.commit()

            def recover_variant(_db, generation, _configuration, variant):
                setattr(generation, f"{variant}_status", "completed")
                setattr(generation, f"{variant}_image", b"recovered-image")
                setattr(generation, f"{variant}_content_type", "image/png")

            with patch(
                "app.services.career_image_service._poll_variant",
                side_effect=recover_variant,
            ):
                row = refresh_generation(db, row)

            self.assertEqual("completed", row.status)
            self.assertTrue(row.is_current)
            self.assertIsNone(row.landscape_error)
            self.assertIsNone(row.square_error)

    def test_current_page_read_resumes_latest_mysql_task_after_navigation(self):
        configuration = _image_configuration()
        with SessionLocal() as db, patch(
            "app.services.career_image_service.effective_image_configuration",
            return_value=configuration,
        ), patch(
            "app.services.career_image_service._submit_variant",
            side_effect=[("resume-landscape", 2), ("resume-square", 2)],
        ):
            created = start_generation(db, self.user_id)
            generation_id = created.id

        # Simulate leaving the page: the next request has a new SQLAlchemy
        # session and no component-local task id, so it must recover from MySQL.
        with SessionLocal() as db, patch(
            "app.services.career_image_service.effective_image_configuration",
            return_value=configuration,
        ), patch(
            "app.services.career_image_service._poll_variant",
        ) as poll:
            resumed = pending_generation(db, self.user_id)

        self.assertIsNotNone(resumed)
        self.assertEqual(generation_id, resumed.id)
        self.assertIn(resumed.status, {"submitted", "generating"})
        self.assertEqual(2, poll.call_count)


if __name__ == "__main__":
    unittest.main()
