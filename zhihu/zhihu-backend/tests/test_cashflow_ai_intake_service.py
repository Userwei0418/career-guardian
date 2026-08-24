from __future__ import annotations

import json
import subprocess
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.core.config import settings
from app.services import cashflow_ai_intake_service as intake


def _configuration() -> SimpleNamespace:
    return SimpleNamespace(
        setting_id=7,
        provider_name="test-provider",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="test-text-model",
        api_key="test-only-key",
    )


def _model_response(
    transactions: list[dict],
    *,
    finish_reason: str | None = "stop",
) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {
                    "content": json.dumps(
                        {"transactions": transactions},
                        ensure_ascii=False,
                    )
                },
            }
        ],
        "usage": {
            "prompt_tokens": 30,
            "completion_tokens": 20,
            "total_tokens": 50,
        },
    }
    return response


def _category_response(classifications: list[dict]) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {"classifications": classifications},
                        ensure_ascii=False,
                    )
                },
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }
    return response


def _valid_expense(**overrides) -> dict:
    payload = {
        "occurrence": "occurred",
        "direction": "expense",
        "amount": "36.50",
        "currency": "CNY",
        "transaction_date": "2026-08-21",
        "merchant": "午饭商户",
        "description": "工作午饭",
        "category_name": "餐饮",
        "nature": "flexible",
        "evidence_quote": "昨天午饭 36.50 元",
        "confidence": 0.94,
    }
    payload.update(overrides)
    return payload


def _png_stub(width: int, height: int, payload: bytes = b"") -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + payload
    )


class CashflowTextAIIntakeTest(unittest.TestCase):
    def test_program_date_parser_rejects_decimal_noise_but_keeps_wallet_date_headers(self):
        reference = date(2026, 8, 24)

        self.assertEqual(
            (None, False),
            intake._program_date_from_text(
                '| ELLA ™“Z1.7U',
                reference_date=reference,
            ),
        )
        self.assertEqual(
            (None, False),
            intake._program_date_from_text(
                "发红包 支出 -1.70",
                reference_date=reference,
            ),
        )
        self.assertEqual(
            (date(2026, 8, 20), True),
            intake._program_date_from_text(
                "8月20日 星期四",
                reference_date=reference,
            ),
        )
        self.assertEqual(
            (date(2026, 8, 20), True),
            intake._program_date_from_text(
                "08-20 12:30 微信支付",
                reference_date=reference,
            ),
        )

    def test_text_is_redacted_before_model_call_and_candidates_require_review(self):
        raw_card = "6222 0212 3456 7890"
        raw_phone = "13800138000"
        raw_formatted_phone = "138-0013-8000"
        raw_email = "owner@example.com"
        user_text = (
            f"昨天午饭 36.50 元，卡号 {raw_card}，手机号 {raw_phone}，"
            f"备用手机 {raw_formatted_phone}，邮箱 {raw_email}"
        )
        response = _model_response([_valid_expense()])

        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit") as audit,
        ):
            result = intake.parse_text_intake(user_id=42, text=user_text)

        request_payload = post.call_args.kwargs["json"]
        remote_user_content = request_payload["messages"][1]["content"]
        remote_payload = json.loads(remote_user_content)
        self.assertNotIn(raw_card, remote_user_content)
        self.assertNotIn(raw_phone, remote_user_content)
        self.assertNotIn(raw_formatted_phone, remote_user_content)
        self.assertNotIn(raw_email, remote_user_content)
        self.assertIn("[账号已隐藏]", remote_payload["text"])
        self.assertIn("[手机号已隐藏]", remote_payload["text"])
        self.assertIn("[邮箱已隐藏]", remote_payload["text"])

        self.assertEqual(1, len(result.parsed))
        candidate = result.parsed[0]
        self.assertEqual("expense", candidate.direction)
        self.assertEqual("36.50", str(candidate.amount))
        self.assertEqual("昨天午饭 36.50 元", candidate.evidence["evidence_quote"])
        self.assertIn(
            "AI_REVIEW_REQUIRED",
            {warning["code"] for warning in candidate.warnings},
        )
        serialized_candidate = json.dumps(
            {
                "original_payload": candidate.original_payload,
                "evidence": candidate.evidence,
            },
            ensure_ascii=False,
        )
        self.assertNotIn(raw_card, serialized_candidate)
        self.assertNotIn(raw_phone, serialized_candidate)
        self.assertNotIn(raw_email, serialized_candidate)
        audit.assert_called_once()
        self.assertEqual(intake.TEXT_FEATURE, audit.call_args.kwargs["feature"])
        self.assertEqual("text", audit.call_args.kwargs["modality"])
        self.assertEqual("success", audit.call_args.kwargs["status"])

    def test_planned_transaction_remains_an_invalid_candidate(self):
        response = _model_response([_valid_expense(occurrence="planned")])

        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_text_intake(
                user_id=42,
                text="下周准备交房租 3000 元",
            )

        self.assertIn(
            "TRANSACTION_NOT_OCCURRED",
            {issue["code"] for issue in result.parsed[0].validation_errors},
        )
        self.assertEqual("planned", result.parsed[0].original_payload["occurrence"])

    def test_explicit_foreign_or_uncertain_currency_never_defaults_to_cny(self):
        for currency, expected_code in (("USD", "UNSUPPORTED_CURRENCY"), ("uncertain", "CURRENCY_REQUIRED")):
            with self.subTest(currency=currency):
                response = _model_response([_valid_expense(currency=currency, amount="100.00")])
                with (
                    patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
                    patch.object(intake.httpx, "post", return_value=response),
                    patch.object(intake, "_audit"),
                ):
                    result = intake.parse_text_intake(
                        user_id=42,
                        text="已收到 100 美元",
                    )
                candidate = result.parsed[0]
                self.assertNotEqual("CNY", candidate.currency)
                self.assertIn(expected_code, {item["code"] for item in candidate.validation_errors})

    def test_invalid_model_schema_is_rejected_and_audited_as_failed(self):
        response = _model_response(
            [
                _valid_expense(
                    direction="outgoing",
                    amount="12.345",
                )
            ]
        )

        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit") as audit,
        ):
            with self.assertRaises(HTTPException) as raised:
                intake.parse_text_intake(user_id=42, text="昨天支出 12.345 元")

        self.assertEqual(502, raised.exception.status_code)
        self.assertEqual("cashflow_ai_parse_failed", raised.exception.detail["code"])
        audit.assert_called_once()
        self.assertEqual("failed", audit.call_args.kwargs["status"])
        self.assertEqual(
            "ModelResponseSchemaInvalid",
            audit.call_args.kwargs["error_code"],
        )

    def test_non_terminal_finish_reason_is_rejected_before_candidate_creation(self):
        response = _model_response([_valid_expense()], finish_reason="length")

        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit") as audit,
        ):
            with self.assertRaises(HTTPException) as raised:
                intake.parse_text_intake(user_id=42, text="昨天午饭 36.50 元")

        self.assertEqual(502, raised.exception.status_code)
        self.assertEqual("cashflow_ai_parse_failed", raised.exception.detail["code"])
        audit.assert_called_once()
        self.assertEqual("failed", audit.call_args.kwargs["status"])
        self.assertEqual(
            "ModelFinishReason:length",
            audit.call_args.kwargs["error_code"],
        )

    def test_unconfigured_model_returns_503_and_records_unavailable_attempt(self):
        with (
            patch.object(intake, "effective_ai_configuration", return_value=None),
            patch.object(intake.httpx, "post") as post,
            patch.object(intake, "_audit") as audit,
        ):
            with self.assertRaises(HTTPException) as raised:
                intake.parse_text_intake(user_id=42, text="今天工资到账 12000 元")

        self.assertEqual(503, raised.exception.status_code)
        self.assertEqual("cashflow_ai_unavailable", raised.exception.detail["code"])
        post.assert_not_called()
        audit.assert_called_once_with(
            None,
            feature=intake.TEXT_FEATURE,
            modality="text",
            user_id=42,
            status="failed",
            error_code="AIConfigurationUnavailable",
            expected_data_epoch=None,
        )


class CashflowVisionAIIntakeTest(unittest.TestCase):
    def setUp(self):
        self.original_tencent_ocr_enabled = settings.TENCENT_OCR_ENABLED
        settings.TENCENT_OCR_ENABLED = False

    def tearDown(self):
        settings.TENCENT_OCR_ENABLED = self.original_tencent_ocr_enabled

    def test_provider_labels_are_not_used_as_merchants(self):
        self.assertEqual(
            "金鑫",
            intake._clean_program_merchant(
                "收转账 19:19|转账-来自金鑫 +200.00",
                matched_amount="+200.00",
            ),
        )
        self.assertEqual(
            "国信同源",
            intake._clean_program_merchant(
                "保险 21:12|国信同源 -100.00",
                matched_amount="-100.00",
            ),
        )
        self.assertIsNone(
            intake._clean_program_merchant(
                "旅行 01:10 -753.00",
                matched_amount="-753.00",
            )
        )

    def test_image_magic_is_authoritative_and_declared_type_must_not_conflict(self):
        png = b"\x89PNG\r\n\x1a\n" + b"test"
        jpeg = b"\xff\xd8\xff" + b"test"

        self.assertEqual("image/png", intake._validated_image_type(png, "image/png"))
        self.assertEqual(
            "image/png",
            intake._validated_image_type(png, "application/octet-stream"),
        )
        self.assertEqual("image/jpeg", intake._validated_image_type(jpeg, "image/jpeg"))

        with self.assertRaises(HTTPException) as mismatch:
            intake._validated_image_type(jpeg, "image/png")
        self.assertEqual(400, mismatch.exception.status_code)
        self.assertEqual("cashflow_vision_invalid_file", mismatch.exception.detail["code"])

        with self.assertRaises(HTTPException) as unknown:
            intake._validated_image_type(b"not-an-image", "image/png")
        self.assertEqual(400, unknown.exception.status_code)

    def test_ocr_temp_file_is_removed_and_only_redacted_text_reaches_model(self):
        image = _png_stub(1200, 1800, b"synthetic-image-content")
        raw_card = "6222021234567890"
        raw_formatted_phone = "138 0013 8000"
        captured_path: list[Path] = []

        def fake_tesseract(arguments, **_kwargs):
            temporary_path = Path(arguments[1])
            captured_path.append(temporary_path)
            self.assertTrue(temporary_path.exists())
            self.assertEqual(image, temporary_path.read_bytes())
            return subprocess.CompletedProcess(
                arguments,
                returncode=0,
                stdout=f"昨天午饭 36.50 元 卡号 {raw_card} 手机 {raw_formatted_phone}",
                stderr="",
            )

        response = _model_response([_valid_expense()])
        with (
            patch.object(intake.subprocess, "run", side_effect=fake_tesseract) as run,
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit") as audit,
        ):
            result = intake.parse_vision_intake(
                user_id=42,
                content=image,
                content_type="image/png",
            )

        run.assert_called_once()
        self.assertEqual("tesseract", run.call_args.args[0][0])
        self.assertEqual(1, len(captured_path))
        self.assertFalse(captured_path[0].exists())

        request_payload = post.call_args.kwargs["json"]
        system_prompt = request_payload["messages"][0]["content"]
        messages_json = json.dumps(request_payload["messages"], ensure_ascii=False)
        remote_payload = json.loads(request_payload["messages"][1]["content"])
        self.assertIn('"transactions"', system_prompt)
        self.assertIn('"occurrence"', system_prompt)
        self.assertIn('"direction"', system_prompt)
        self.assertIn('"confidence"', system_prompt)
        self.assertNotIn(raw_card, messages_json)
        self.assertNotIn(raw_formatted_phone, messages_json)
        self.assertIn("[账号已隐藏]", remote_payload["ocr_text"])
        self.assertIn("[手机号已隐藏]", remote_payload["ocr_text"])
        self.assertNotIn("data:image", messages_json)
        self.assertNotIn("base64", messages_json.lower())
        self.assertNotIn("synthetic-image-content", messages_json)

        self.assertEqual("image/png", result.content_type)
        self.assertIn(raw_card, result.ocr_text or "")
        self.assertIn(raw_formatted_phone, result.ocr_text or "")
        self.assertEqual("high", result.parsed[0].evidence["review_tier"])
        self.assertNotIn(
            "AI_REVIEW_REQUIRED",
            {warning["code"] for warning in result.parsed[0].warnings},
        )
        audit.assert_called_once()
        self.assertEqual(intake.VISION_FEATURE, audit.call_args.kwargs["feature"])
        self.assertEqual("text", audit.call_args.kwargs["modality"])
        self.assertEqual("success", audit.call_args.kwargs["status"])

    def test_highly_compressed_oversized_image_is_rejected_before_ocr(self):
        image = _png_stub(16_000, 16_000, b"tiny-compressed-payload")

        with patch.object(intake, "_local_ocr") as local_ocr:
            with self.assertRaises(HTTPException) as raised:
                intake.parse_vision_intake(
                    user_id=42,
                    content=image,
                    content_type="image/png",
                )

        self.assertEqual(413, raised.exception.status_code)
        self.assertEqual(
            "cashflow_vision_image_too_large",
            raised.exception.detail["code"],
        )
        local_ocr.assert_not_called()

    def test_segmented_validation_accepts_common_ultra_long_screenshot_without_relaxing_whole_image_ocr(self):
        image = _png_stub(1080, 90_000, b"ultra-long")

        with self.assertRaises(HTTPException):
            intake._validate_image_dimensions(image, "image/png")

        self.assertEqual(
            (1080, 90_000),
            intake._validate_image_dimensions(image, "image/png", segmented=True),
        )

    def test_complete_ocr_intake_processes_every_text_chunk_instead_of_truncating_tail(self):
        lines = [
            f"交易标记{i:02d} 2026-08-21 金额 {i + 1}.00 元 " + "商品说明" * 8
            for i in range(35)
        ]
        ocr_text = "\n".join(lines)
        chunks = intake._split_ocr_text_for_complete_intake(ocr_text)
        responses = [
            _model_response([
                _valid_expense(
                    amount=f"{index}.00",
                    merchant=f"分块商户{index}",
                    evidence_quote=chunk[:80],
                )
            ])
            for index, chunk in enumerate(chunks, start=1)
        ]

        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", side_effect=responses) as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="full-ocr-hash",
            )

        self.assertGreater(len(chunks), 1)
        self.assertEqual(len(chunks), post.call_count)
        remote_texts = [
            json.loads(call.kwargs["json"]["messages"][1]["content"])["ocr_text"]
            for call in post.call_args_list
        ]
        for marker in ("交易标记00", "交易标记17", "交易标记34"):
            self.assertTrue(any(marker in text for text in remote_texts), marker)
        # Every explicit program amount row survives even when the model only
        # explains one row per chunk. The AI is enrichment, not a row counter.
        self.assertEqual(len(lines), len(result.parsed))
        self.assertEqual(len(chunks), result.ocr_chunk_count)
        self.assertEqual(len(ocr_text), result.ocr_processed_characters)
        self.assertTrue(all(item.evidence["ocr_text_fully_processed"] for item in result.parsed))

    def test_complete_ocr_intake_uses_program_rules_without_calling_ai_for_clear_rows(self):
        ocr_text = "\n".join(
            (
                "2026-08-21 美团外卖 支出 ￥36.50",
                "2026-08-21 地铁 支出 ￥4.00",
            )
        )
        with patch.object(intake.httpx, "post") as post:
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="program-only-hash",
            )

        post.assert_not_called()
        self.assertEqual(2, len(result.parsed))
        self.assertEqual(2, result.program_candidate_count)
        self.assertEqual(0, result.ai_candidate_count)
        self.assertEqual(0, result.ai_chunk_count)
        self.assertTrue(all(item.evidence["detection_method"] == "program" for item in result.parsed))
        self.assertEqual(["餐饮", "交通"], [item.category_name for item in result.parsed])

    def test_complete_row_without_date_waits_for_deterministic_slice_context(self):
        ocr_text = "收转账 19:19|转账-来自金鑫 +200.00"

        with patch.object(intake.httpx, "post") as post:
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="complete-row-without-date",
            )

        post.assert_not_called()
        self.assertEqual(1, len(result.parsed))
        candidate = result.parsed[0]
        self.assertEqual("program", candidate.evidence["detection_method"])
        self.assertEqual("transfer", candidate.direction)
        self.assertEqual("金鑫", candidate.merchant)
        self.assertIsNone(candidate.transaction_date)
        self.assertIn("DATE_INVALID", {item["code"] for item in candidate.validation_errors})

    def test_explicit_source_label_maps_entertainment_apple_without_ai(self):
        with patch.object(intake.httpx, "post") as post:
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-17 娱乐 19:04 Apple 支出 ￥88.00",
                content_hash="explicit-entertainment-apple",
            )

        post.assert_not_called()
        candidate = result.parsed[0]
        self.assertEqual("娱乐", candidate.category_name)
        self.assertEqual("Apple", candidate.merchant)
        self.assertEqual("source_label", candidate.evidence["category_suggestion"]["source"])
        self.assertFalse(candidate.evidence["category_suggestion"]["requires_confirmation"])
        self.assertNotIn(
            "PROGRAM_CATEGORY_REVIEW_REQUIRED",
            {item["code"] for item in candidate.warnings},
        )

    def test_service_meituan_platform_is_reviewable_rule_not_blanket_meituan(self):
        with patch.object(intake.httpx, "post") as post:
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-17 服务 19:04 美团平台商户 支出 ￥88.00",
                content_hash="service-meituan-platform",
            )

        post.assert_not_called()
        candidate = result.parsed[0]
        self.assertEqual("美团平台商户", candidate.merchant)
        self.assertEqual("餐饮", candidate.category_name)
        self.assertEqual("program_rule", candidate.evidence["category_suggestion"]["source"])
        self.assertIn(
            "PROGRAM_CATEGORY_REVIEW_REQUIRED",
            {item["code"] for item in candidate.warnings},
        )
        unrelated = intake._program_parse_ocr_text(
            "2026-08-17 服务 19:04 美团单车 支出 ￥88.00",
            content_hash="service-meituan-bike",
            reference_date=date(2026, 8, 24),
        ).parsed[0]
        self.assertEqual("交通", unrelated.category_name)
        self.assertNotEqual("餐饮", unrelated.category_name)
        self.assertTrue(unrelated.evidence["category_suggestion"]["requires_confirmation"])

    def test_complete_ocr_intake_sends_only_unresolved_rows_to_ai(self):
        ocr_text = "\n".join(
            (
                "2026-08-21 美团外卖 支出 ￥36.50",
                "2026-08-21 星巴克 18.00 元",
            )
        )
        response = _model_response([
            _valid_expense(
                amount="18.00",
                merchant="星巴克",
                description="星巴克",
                evidence_quote="2026-08-21 星巴克 18.00 元",
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="mixed-program-ai-hash",
            )

        remote_text = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])["ocr_text"]
        self.assertNotIn("美团外卖", remote_text)
        self.assertIn("星巴克", remote_text)
        self.assertEqual(2, len(result.parsed))
        self.assertEqual(1, result.program_candidate_count)
        self.assertEqual(1, result.ai_candidate_count)
        self.assertEqual(1, result.ai_chunk_count)
        self.assertEqual(["program", "program_ai"], [item.evidence["detection_method"] for item in result.parsed])

    def test_low_quality_program_merchant_does_not_override_clear_ai_merchant(self):
        ocr_text = "2026-08-17 © te a 支出 ￥88.00"
        response = _model_response([
            _valid_expense(
                amount="88.00",
                transaction_date="2026-08-17",
                merchant="小海麦经典面片",
                description="小海麦经典面片",
                evidence_quote=ocr_text,
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="merchant-quality-gate-hash",
            )

        self.assertEqual(1, len(result.parsed))
        candidate = result.parsed[0]
        self.assertEqual("小海麦经典面片", candidate.merchant)
        self.assertEqual("小海麦经典面片", candidate.description)
        self.assertEqual("ai_replaced_low_quality_program_value", candidate.evidence["merchant_resolution"])
        self.assertNotIn("PROGRAM_MERCHANT_REVIEW", {item["code"] for item in candidate.warnings})

    def test_ai_provider_label_is_not_persisted_as_a_ledger_category(self):
        ocr_text = "2026-08-17 生活缴费 12:53 支出 ￥30.00"
        response = _model_response([
            _valid_expense(
                amount="30.00",
                transaction_date="2026-08-17",
                merchant="生活缴费",
                description="生活缴费",
                category_name="生活缴费",
                evidence_quote=ocr_text,
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="invalid-provider-label-category",
            )

        candidate = result.parsed[0]
        self.assertIsNone(candidate.category_name)
        self.assertIn("AI_CATEGORY_UNCERTAIN", {item["code"] for item in candidate.warnings})

    def test_phone_bill_is_classified_as_communication_expense(self):
        with patch.object(intake.httpx, "post") as post:
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-21 中国移动话费 支出 ￥30.00",
                content_hash="communication-category-hash",
            )

        post.assert_not_called()
        self.assertEqual(1, len(result.parsed))
        self.assertEqual("通讯", result.parsed[0].category_name)
        self.assertEqual("fixed", result.parsed[0].nature)

    def test_ocr_redaction_preserves_row_boundaries(self):
        redacted = intake._redact_ocr_text(
            "商户甲 支出 18.00\n银行卡 6222021234567890 收入 20.00"
        )

        self.assertIn("\n", redacted)
        self.assertIn("[账号已隐藏]", redacted)

    def test_ai_extra_suggestion_without_program_amount_anchor_is_rejected(self):
        ocr_text = "\n".join(
            (
                "2026-08-21 星巴克 18.00 元",
                "2026-08-21 奶茶店 12.00 元",
            )
        )
        response = _model_response([
            _valid_expense(
                amount="18.00",
                merchant="星巴克",
                evidence_quote="2026-08-21 星巴克 18.00 元",
            ),
            _valid_expense(
                amount="12.00",
                merchant="奶茶店",
                evidence_quote="2026-08-21 奶茶店 12.00 元",
            ),
            _valid_expense(
                amount="999.00",
                merchant="模型额外建议",
                evidence_quote="2026-08-21",
            ),
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="program-ai-alignment-hash",
            )

        self.assertEqual(2, len(result.parsed))
        self.assertEqual(1, result.ai_rejected_candidate_count)
        self.assertEqual(
            ["program_ai", "program_ai"],
            [item.evidence["detection_method"] for item in result.parsed],
        )

    def test_multi_amount_unconsumed_row_calls_ai_and_keeps_every_amount_anchor(self):
        ocr_text = "\n".join(
            (
                "2026-08-21 美团外卖 支出 ￥10.00",
                "2026-08-21 甲商户 支出 ￥20.00 乙商户 支出 ￥30.00",
            )
        )
        response = _model_response([
            _valid_expense(
                amount="20.00",
                merchant="甲商户",
                evidence_quote="甲商户 支出 ￥20.00",
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="mixed-complete-and-multi-amount-hash",
            )

        remote_text = json.loads(
            post.call_args.kwargs["json"]["messages"][1]["content"]
        )["ocr_text"]
        self.assertNotIn("美团外卖", remote_text)
        self.assertIn("甲商户", remote_text)
        self.assertEqual(
            [Decimal("10.00"), Decimal("20.00"), Decimal("30.00")],
            [item.amount for item in result.parsed],
        )
        self.assertEqual(2, result.program_fallback_candidate_count)
        self.assertEqual(
            ["program", "program_ai", "program_fallback"],
            [item.evidence["detection_method"] for item in result.parsed],
        )
        unresolved = result.parsed[2]
        self.assertEqual("low", unresolved.evidence["review_tier"])
        self.assertIn(
            "AI_UNRESOLVED_MANUAL_REVIEW",
            {item["code"] for item in unresolved.warnings},
        )

    def test_integer_transaction_amount_is_kept_for_review_without_treating_counts_as_money(self):
        ocr_text = "\n".join(
            (
                "2026-08-21 美团外卖 支出 ￥10.00",
                "2026-08-21 地铁 支出 20",
                "2026-08-21 支出 20 笔",
            )
        )
        with (
            patch.object(intake, "effective_ai_configuration", return_value=None),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="integer-transaction-anchor-hash",
            )

        self.assertEqual(
            [Decimal("10.00"), Decimal("20")],
            [item.amount for item in result.parsed],
        )
        self.assertEqual(1, result.program_candidate_count)
        self.assertEqual(1, result.program_fallback_candidate_count)
        integer_candidate = result.parsed[1]
        self.assertEqual("program_fallback", integer_candidate.evidence["detection_method"])
        self.assertIn(
            "OCR_INTEGER_AMOUNT_REVIEW",
            {item["code"] for item in integer_candidate.warnings},
        )

    def test_parenthesized_card_tail_is_not_treated_as_a_second_amount(self):
        result = intake._program_parse_ocr_text(
            "2026-08-17 其他 11:11|零钱提现-到建设银行(0834) 2002.00",
            content_hash="masked-card-tail-hash",
            reference_date=date(2026, 8, 24),
        )

        candidates = [*result.parsed, *result.manual_fallbacks]
        self.assertEqual(1, len(candidates))
        self.assertEqual(Decimal("2002.00"), candidates[0].amount)
        self.assertEqual("transfer", candidates[0].direction)
        self.assertNotIn(
            "OCR_MULTI_AMOUNT_ROW_REVIEW",
            {item["code"] for item in candidates[0].warnings},
        )
        self.assertNotIn(
            "OCR_INTEGER_AMOUNT_REVIEW",
            {item["code"] for item in candidates[0].warnings},
        )

    def test_transfer_without_merchant_is_not_blocked_but_plain_refund_still_is(self):
        transfer = intake._program_parse_ocr_text(
            "2026-08-19 退款 00:18|转账-退款 +￥520.00",
            content_hash="merchantless-transfer-hash",
            reference_date=date(2026, 8, 24),
        )
        self.assertEqual(1, len(transfer.parsed))
        self.assertEqual(0, len(transfer.manual_fallbacks))
        self.assertEqual("transfer", transfer.parsed[0].direction)
        self.assertIsNone(transfer.parsed[0].merchant)
        self.assertNotIn(
            "PROGRAM_MERCHANT_REVIEW",
            {item["code"] for item in transfer.parsed[0].warnings},
        )

        plain_refund = intake._program_parse_ocr_text(
            "2026-08-19 退款 +￥520.00",
            content_hash="merchantless-refund-hash",
            reference_date=date(2026, 8, 24),
        )
        self.assertEqual(0, len(plain_refund.parsed))
        self.assertEqual(1, len(plain_refund.manual_fallbacks))
        self.assertEqual("income", plain_refund.manual_fallbacks[0].direction)
        self.assertIn(
            "PROGRAM_MERCHANT_REVIEW",
            {item["code"] for item in plain_refund.manual_fallbacks[0].warnings},
        )

    def test_high_confidence_program_ai_alignment_is_non_blocking_evidence(self):
        ocr_text = "2026-08-21 交通 11:27 支出 ￥8.70"
        response = _model_response([
            _valid_expense(
                amount="8.70",
                transaction_date="2026-08-21",
                merchant="滴滴出行",
                description="滴滴出行",
                category_name="交通",
                evidence_quote=ocr_text,
                confidence=0.96,
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="high-program-ai-alignment-hash",
            )

        candidate = result.parsed[0]
        self.assertEqual("program_ai", candidate.evidence["detection_method"])
        self.assertEqual("matched_critical_fields", candidate.evidence["ai_alignment_status"])
        self.assertFalse(candidate.evidence["ai_alignment_review_required"])
        self.assertEqual(
            "high_confidence_critical_fields_agree",
            candidate.evidence["ai_alignment_reason"],
        )
        self.assertNotIn(
            "AI_PROGRAM_ALIGNMENT_REVIEW",
            {item["code"] for item in candidate.warnings},
        )

    def test_program_ai_merchant_conflict_remains_blocking(self):
        ocr_text = "2026-08-21 甲商户 支出 ￥20"
        response = _model_response([
            _valid_expense(
                amount="20",
                transaction_date="2026-08-21",
                merchant="乙商户",
                description="乙商户",
                category_name=None,
                evidence_quote=ocr_text,
                confidence=0.96,
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="program-ai-merchant-conflict-hash",
            )

        candidate = result.parsed[0]
        self.assertTrue(candidate.evidence["ai_alignment_review_required"])
        self.assertEqual("merchant_conflict", candidate.evidence["ai_alignment_reason"])
        self.assertIn(
            "AI_PROGRAM_ALIGNMENT_REVIEW",
            {item["code"] for item in candidate.warnings},
        )

    def test_one_source_amount_anchor_accepts_at_most_one_ai_candidate(self):
        ocr_text = "2026-08-21 甲商户 支出 ￥20.00 乙商户 支出 ￥30.00"
        response = _model_response([
            _valid_expense(
                amount="20.00",
                merchant="甲商户",
                evidence_quote="甲商户 支出 ￥20.00",
            ),
            _valid_expense(
                amount="20.00",
                merchant="重复解释",
                evidence_quote="甲商户 支出 ￥20.00",
            ),
            _valid_expense(
                amount="999.00",
                merchant="无金额锚点建议",
                evidence_quote="2026-08-21",
            ),
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="one-ai-per-amount-anchor-hash",
            )

        self.assertEqual(
            [Decimal("20.00"), Decimal("30.00")],
            [item.amount for item in result.parsed],
        )
        self.assertEqual(2, result.program_fallback_candidate_count)
        self.assertEqual(2, result.ai_rejected_candidate_count)
        self.assertEqual(
            ["program_ai", "program_fallback"],
            [item.evidence["detection_method"] for item in result.parsed],
        )

    def test_repeated_same_day_same_amount_rows_are_not_silently_collapsed(self):
        line = "2026-08-21 地铁 支出 ￥4.00"
        result = intake.parse_ocr_text_intake_complete(
            user_id=42,
            ocr_text=f"{line}\n{line}",
            content_hash="legitimate-repeat-hash",
        )

        self.assertEqual(2, len(result.parsed))
        self.assertEqual(result.parsed[0].fingerprint, result.parsed[1].fingerprint)
        self.assertNotEqual(result.parsed[0].external_key, result.parsed[1].external_key)

    def test_balance_and_date_summary_are_not_transaction_candidates(self):
        result = intake.parse_ocr_text_intake_complete(
            user_id=42,
            ocr_text="\n".join(
                (
                    "余额 ￥123.45",
                    "8月20日 星期四 支出 23.00",
                    "2026-08-21 美团外卖 支出 ￥36.50",
                )
            ),
            content_hash="summary-lines-hash",
        )

        self.assertEqual(1, len(result.parsed))
        self.assertEqual(Decimal("36.50"), result.parsed[0].amount)

    def test_ai_cannot_turn_balance_date_summary_or_count_into_transaction(self):
        cases = (
            ("余额 ￥123.45", "123.45"),
            ("8月20日 星期四 支出 23.00", "23.00"),
            ("2026-08-21 支出 20 笔", "20"),
        )
        for text, amount in cases:
            with self.subTest(text=text):
                response = _model_response([
                    _valid_expense(
                        amount=amount,
                        transaction_date="2026-08-20",
                        merchant="汇总行",
                        description="汇总行",
                        evidence_quote=text,
                    )
                ])
                with (
                    patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
                    patch.object(intake.httpx, "post", return_value=response),
                    patch.object(intake, "_audit"),
                    self.assertRaises(HTTPException) as raised,
                ):
                    intake.parse_ocr_text_intake_complete(
                        user_id=42,
                        ocr_text=text,
                        content_hash=f"summary-ai-rejection-{amount}",
                    )

                self.assertEqual(422, raised.exception.status_code)
                self.assertEqual("cashflow_vision_ocr_failed", raised.exception.detail["code"])

    def test_balance_summary_rule_does_not_swallow_yuebao_transfer(self):
        ocr_text = "2026-08-21 余额宝转入 +100.00"
        response = _model_response([
            _valid_expense(
                direction="transfer",
                amount="100.00",
                transaction_date="2026-08-21",
                merchant="余额宝转入",
                description="余额宝转入",
                category_name=None,
                nature=None,
                evidence_quote=ocr_text,
            )
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text=ocr_text,
                content_hash="yuebao-transfer-hash",
            )

        self.assertEqual(1, len(result.parsed))
        candidate = result.parsed[0]
        self.assertEqual("transfer", candidate.direction)
        self.assertEqual(Decimal("100.00"), candidate.amount)
        self.assertEqual("program", candidate.evidence["detection_method"])
        self.assertEqual(1, result.program_candidate_count)
        self.assertEqual(0, result.program_fallback_candidate_count)
        self.assertEqual(0, result.ai_rejected_candidate_count)
        post.assert_not_called()
        self.assertIn(intake.OCR_PROGRAM_PARSER_VERSION, result.parser_version)

    def test_full_date_parser_does_not_truncate_two_digit_days(self):
        for day in (10, 19, 20, 21, 30, 31):
            parsed, inferred = intake._program_date_from_text(
                f"2026-08-{day:02d} 商户 支出 10.00",
                reference_date=date(2026, 8, 23),
            )
            self.assertEqual(date(2026, 8, day), parsed)
            self.assertFalse(inferred)

    def test_program_facts_are_kept_while_ai_only_enriches_unknown_category(self):
        response = _category_response([
            {
                "row_number": 1,
                "category_name": "购物",
                "nature": "flexible",
                "confidence": 0.94,
                "reason": "商贸类消费",
            }
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response) as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-21 某某商贸 支出 ￥36.50",
                content_hash="program-category-ai-hash",
            )

        remote_content = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("36.50", remote_content)
        self.assertNotIn("2026-08-21", remote_content)
        candidate = result.parsed[0]
        self.assertEqual("expense", candidate.direction)
        self.assertEqual("36.50", str(candidate.amount))
        self.assertEqual("购物", candidate.category_name)
        self.assertEqual("program", candidate.evidence["detection_method"])
        self.assertEqual("购物", candidate.evidence["category_ai_assessment"]["category_name"])
        self.assertEqual("购物", candidate.evidence["category_suggestion"]["category_name"])
        self.assertEqual("ai", candidate.evidence["category_suggestion"]["source"])
        self.assertIn("AI_CATEGORY_REVIEW_REQUIRED", {item["code"] for item in candidate.warnings})
        self.assertEqual(1, result.program_candidate_count)
        self.assertEqual(1, result.ai_candidate_count)
        self.assertEqual(1, result.ai_chunk_count)

    def test_low_confidence_ai_category_is_exposed_only_as_review_suggestion(self):
        response = _category_response([
            {
                "row_number": 1,
                "category_name": "购物",
                "nature": "flexible",
                "confidence": 0.42,
                "reason": "商户文本可能与购物有关",
            }
        ])
        with (
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-21 某某商贸 支出 ￥36.50",
                content_hash="low-confidence-category-suggestion",
            )

        candidate = result.parsed[0]
        self.assertIsNone(candidate.category_name)
        self.assertEqual("购物", candidate.evidence["category_suggestion"]["category_name"])
        self.assertEqual("ai", candidate.evidence["category_suggestion"]["source"])
        self.assertTrue(candidate.evidence["category_suggestion"]["requires_confirmation"])
        self.assertIn("AI_CATEGORY_UNCERTAIN", {item["code"] for item in candidate.warnings})

    def test_unknown_program_category_falls_back_to_human_when_ai_is_unavailable(self):
        with (
            patch.object(intake, "effective_ai_configuration", return_value=None),
            patch.object(intake.httpx, "post") as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-21 某某商贸 支出 ￥36.50",
                content_hash="program-category-manual-hash",
            )

        post.assert_not_called()
        candidate = result.parsed[0]
        self.assertIsNone(candidate.category_name)
        self.assertIn("AI_CATEGORY_UNAVAILABLE", {item["code"] for item in candidate.warnings})
        self.assertEqual(0, result.ai_candidate_count)

    def test_program_parser_never_treats_zero_amount_as_a_ready_fact(self):
        result = intake.parse_ocr_text_intake_complete(
            user_id=42,
            ocr_text="2026-08-21 美团外卖 支出 ￥0.00",
            content_hash="program-zero-amount-hash",
        )

        self.assertEqual("0.00", str(result.parsed[0].amount))
        self.assertIn("AMOUNT_INVALID", {item["code"] for item in result.parsed[0].validation_errors})

    def test_ai_unavailable_preserves_unresolved_amount_as_manual_candidate(self):
        with (
            patch.object(intake, "effective_ai_configuration", return_value=None),
            patch.object(intake.httpx, "post") as post,
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_ocr_text_intake_complete(
                user_id=42,
                ocr_text="2026-08-21 星巴克 18.00 元",
                content_hash="manual-fallback-hash",
            )

        post.assert_not_called()
        self.assertEqual(1, len(result.parsed))
        candidate = result.parsed[0]
        self.assertEqual("program_fallback", candidate.evidence["detection_method"])
        self.assertIn("DIRECTION_REQUIRED", {item["code"] for item in candidate.validation_errors})
        self.assertIn("AI_UNAVAILABLE_MANUAL_REVIEW", {item["code"] for item in candidate.warnings})

    def test_foreign_currency_ocr_candidate_is_invalid(self):
        image = _png_stub(1200, 1800, b"foreign-currency")
        response = _model_response([_valid_expense(currency="USD", amount="88.00")])
        with (
            patch.object(intake, "_local_ocr", return_value="TOTAL USD 88.00"),
            patch.object(intake, "effective_ai_configuration", return_value=_configuration()),
            patch.object(intake.httpx, "post", return_value=response),
            patch.object(intake, "_audit"),
        ):
            result = intake.parse_vision_intake(
                user_id=42,
                content=image,
                content_type="image/png",
            )
        self.assertEqual("USD", result.parsed[0].currency)
        self.assertIn(
            "UNSUPPORTED_CURRENCY",
            {item["code"] for item in result.parsed[0].validation_errors},
        )


if __name__ == "__main__":
    unittest.main()
