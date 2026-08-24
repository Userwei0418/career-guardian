from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import settings
from app.services import cashflow_tencent_ocr_service as service


def _point(x: int, y: int) -> SimpleNamespace:
    return SimpleNamespace(X=x, Y=y)


def _detection(
    text: str,
    *,
    top: int,
    confidence: float = 98.5,
) -> SimpleNamespace:
    return SimpleNamespace(
        DetectedText=text,
        Confidence=confidence,
        Polygon=[
            _point(20, top),
            _point(620, top),
            _point(620, top + 44),
            _point(20, top + 44),
        ],
        ItemPolygon=None,
    )


class CashflowTencentOCRServiceTest(unittest.TestCase):
    def setUp(self):
        self.original = {
            "enabled": settings.TENCENT_OCR_ENABLED,
            "secret_id": settings.TENCENT_OCR_SECRET_ID,
            "secret_key": settings.TENCENT_OCR_SECRET_KEY,
            "soft_limit": settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT,
        }
        settings.TENCENT_OCR_ENABLED = True
        settings.TENCENT_OCR_SECRET_ID = "test-secret-id"
        settings.TENCENT_OCR_SECRET_KEY = "test-secret-key"
        settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT = 900

    def tearDown(self):
        settings.TENCENT_OCR_ENABLED = self.original["enabled"]
        settings.TENCENT_OCR_SECRET_ID = self.original["secret_id"]
        settings.TENCENT_OCR_SECRET_KEY = self.original["secret_key"]
        settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT = self.original["soft_limit"]

    def test_general_accurate_response_is_sorted_and_keeps_coordinates(self):
        response = SimpleNamespace(
            RequestId="request-for-debug-only",
            TextDetections=[
                _detection("餐饮 美团外卖 -36.50", top=220),
                _detection("8月24日 星期一", top=40),
            ],
        )
        with (
            patch.object(service, "_monthly_call_count", return_value=0),
            patch.object(service, "_sdk_general_accurate_ocr", return_value=response),
            patch.object(service, "_record_invocation") as audit,
        ):
            result = service.recognize_with_tencent_cloud(
                user_id=7,
                content=b"synthetic-png-with-digits-2026",
            )

        self.assertEqual("8月24日 星期一\n餐饮 美团外卖 -36.50", result.text)
        self.assertEqual("request-for-debug-only", result.request_id)
        self.assertEqual(2, len(result.line_positions()))
        self.assertEqual(40, result.line_positions()[0]["polygon"][0]["y"])
        audit.assert_called_once()
        self.assertEqual("success", audit.call_args.kwargs["status"])
        self.assertTrue(audit.call_args.kwargs["request_sent"])

    def test_monthly_soft_limit_stops_before_sending_image(self):
        settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT = 2
        with (
            patch.object(service, "_monthly_call_count", return_value=2),
            patch.object(service, "_sdk_general_accurate_ocr") as invoke,
        ):
            with self.assertRaises(service.TencentOCRError) as raised:
                service.recognize_with_tencent_cloud(
                    user_id=7,
                    content=b"synthetic-png-with-digits-2026",
                )

        self.assertEqual("TencentOCRMonthlySoftLimitReached", raised.exception.code)
        self.assertFalse(raised.exception.request_sent)
        invoke.assert_not_called()

    def test_sdk_failure_is_safe_and_marks_possible_transmission(self):
        with (
            patch.object(service, "_monthly_call_count", return_value=0),
            patch.object(service, "_sdk_general_accurate_ocr", side_effect=RuntimeError("secret must not leak")),
            patch.object(service, "_record_invocation") as audit,
        ):
            with self.assertRaises(service.TencentOCRError) as raised:
                service.recognize_with_tencent_cloud(
                    user_id=7,
                    content=b"synthetic-png-with-digits-2026",
                )

        self.assertEqual("RuntimeError", raised.exception.code)
        self.assertNotIn("secret must not leak", raised.exception.user_message)
        self.assertTrue(raised.exception.request_sent)
        self.assertEqual("failed", audit.call_args.kwargs["status"])


if __name__ == "__main__":
    unittest.main()
