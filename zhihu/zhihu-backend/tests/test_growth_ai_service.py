import json
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from app.schemas.growth import GrowthAnalyzeRequest, GrowthConfirmIntakeRequest
from app.services.ai_configuration_service import EffectiveAIConfiguration
from app.services.growth_ai_service import analyze_with_ai, analyze_with_rules, redact_growth_text


class GrowthRuleAnalysisTest(unittest.TestCase):
    def test_local_rules_separate_emotion_and_work(self):
        result = analyze_with_rules("我很焦虑；今天完成客户汇报；整理项目文档")

        self.assertEqual(result.analysis_mode, "rules")
        self.assertTrue(result.emotion.detected)
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all("焦虑" not in candidate.title for candidate in result.candidates))
        self.assertIn("客户汇报", result.candidates[0].title)

    def test_local_rules_redact_direct_identifiers_before_candidate_creation(self):
        text = "联系客户 13800138000；把结果发到 test@example.com"
        result = analyze_with_rules(text)

        serialized = json.dumps(
            [candidate.model_dump() for candidate in result.candidates], ensure_ascii=False
        )
        self.assertNotIn("13800138000", serialized)
        self.assertNotIn("test@example.com", serialized)
        self.assertIn("[手机号已隐藏]", serialized)
        self.assertIn("[邮箱已隐藏]", serialized)

    def test_redaction_covers_id_and_account(self):
        value = redact_growth_text("身份证 110105199001011234，账号 6222021234567890123")
        self.assertNotIn("110105199001011234", value)
        self.assertNotIn("6222021234567890123", value)

    def test_ai_requires_explicit_external_processing_consent(self):
        with self.assertRaises(ValidationError):
            GrowthAnalyzeRequest(
                request_id="growth-test-001",
                text="整理客户汇报",
                use_ai=True,
                allow_external_processing=False,
            )

    def test_emotion_text_requires_explicit_retention(self):
        with self.assertRaises(ValidationError):
            GrowthConfirmIntakeRequest(
                selected=[{"candidate_key": "candidate-1"}],
                retain_emotion=False,
                emotion_text="这周很焦虑",
            )


class GrowthAIAnalysisTest(unittest.TestCase):
    def _configuration(self):
        return EffectiveAIConfiguration(
            setting_id=1,
            provider_name="Test Provider",
            base_url="https://api.senseaudio.cn/v1",
            model="test-model",
            tts_enabled=False,
            tts_model="",
            tts_voice_id="",
            realtime_enabled=False,
            realtime_model="",
            realtime_voice_id="",
            interview_agent_name="",
            interview_agent_prompt="",
            interview_greeting="",
            api_key="secret",
            source="stored",
        )

    @patch("app.services.growth_ai_service._audit")
    @patch("app.services.growth_ai_service.httpx.post")
    @patch("app.services.growth_ai_service.effective_ai_configuration")
    def test_ai_only_sends_redacted_text_and_returns_unconfirmed_candidates(
        self,
        effective_configuration,
        post,
        audit,
    ):
        effective_configuration.return_value = self._configuration()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "candidates": [
                                    {
                                        "title": "完成客户汇报",
                                        "description": None,
                                        "fact_excerpt": "完成客户汇报",
                                        "impact_level": "high",
                                        "energy_level": "unknown",
                                        "selection_reason": "涉及客户沟通",
                                        "confidence": 0.8,
                                    }
                                ],
                                "emotion": {
                                    "detected": True,
                                    "summary": "模型自由文本不应直接保存",
                                    "deidentified_fact": None,
                                },
                            },
                            ensure_ascii=False,
                        )
                    },
                }
            ],
            "usage": {"total_tokens": 100},
        }
        post.return_value = response

        result = analyze_with_ai(
            user_id=7,
            text="我很焦虑，联系 13800138000 后完成客户汇报",
        )

        sent = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("13800138000", sent)
        self.assertIn("[手机号已隐藏]", sent)
        self.assertEqual(result.candidates[0].title, "完成客户汇报")
        self.assertEqual(
            result.emotion.summary,
            "检测到情绪表达；默认不会保存原文，也不会进入周报或职业资产。",
        )
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
