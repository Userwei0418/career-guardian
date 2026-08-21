from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

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
        messages_json = json.dumps(request_payload["messages"], ensure_ascii=False)
        remote_payload = json.loads(request_payload["messages"][1]["content"])
        self.assertNotIn(raw_card, messages_json)
        self.assertNotIn(raw_formatted_phone, messages_json)
        self.assertIn("[账号已隐藏]", remote_payload["ocr_text"])
        self.assertIn("[手机号已隐藏]", remote_payload["ocr_text"])
        self.assertNotIn("data:image", messages_json)
        self.assertNotIn("base64", messages_json.lower())
        self.assertNotIn("synthetic-image-content", messages_json)

        self.assertEqual("image/png", result.content_type)
        self.assertIn(
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
