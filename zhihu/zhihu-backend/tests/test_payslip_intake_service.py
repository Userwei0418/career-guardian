from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from app.services import payslip_intake_service as intake
from app.services.payslip_service import analyze_payslip


class PayslipIntakeServiceTest(unittest.TestCase):
    def test_csv_recognition_preserves_unknown_fields_and_custom_items(self):
        content = (
            "工资月份,发薪单位,应发工资,基本工资,个税,实发工资,通讯补贴\n"
            "2026-08,测试公司,12000,10000,300,10500,200\n"
        ).encode("utf-8")

        result = intake.recognize_payslip_upload(
            user_id=7,
            filename="工资条.csv",
            content=content,
            content_type="text/csv",
            confirm_external_processing=False,
        )

        self.assertFalse(result.original_file_retained)
        self.assertEqual("file", result.source_type)
        self.assertEqual(1, len(result.candidates))
        candidate = result.candidates[0]
        self.assertEqual("2026-08", candidate.pay_month)
        self.assertEqual(Decimal("12000.00"), candidate.gross_salary)
        self.assertIsNone(candidate.social_insurance)
        self.assertIn("social_insurance", candidate.unknown_fields)
        self.assertEqual([{"name": "通讯补贴", "value": "200"}], candidate.custom_items)

    def test_incomplete_deductions_never_become_zero_or_false_mismatch(self):
        result = analyze_payslip(
            {
                "gross_salary": 12000,
                "social_insurance": None,
                "housing_fund": 800,
                "individual_tax": 300,
                "attendance_deductions": None,
                "meal_deductions": None,
                "other_deductions": None,
                "net_salary": 10500,
            }
        )

        self.assertEqual("unknown", result["arithmetic_status"])
        self.assertIsNone(result["calculated_net"])
        self.assertIsNone(result["deductions"]["total"])
        self.assertIsNone(result["deductions"]["social_insurance"])
        self.assertNotIn("工资条数字校验异常", {item["title"] for item in result["findings"]})

    def test_complete_deductions_still_produce_deterministic_arithmetic(self):
        result = analyze_payslip(
            {
                "gross_salary": 12000,
                "social_insurance": 500,
                "housing_fund": 800,
                "individual_tax": 300,
                "attendance_deductions": 0,
                "meal_deductions": 0,
                "other_deductions": 0,
                "net_salary": 10400,
            }
        )

        self.assertEqual("matched", result["arithmetic_status"])
        self.assertEqual(10400, result["calculated_net"])
        self.assertEqual([], result["unknown_fields"])

    def test_ocr_text_is_redacted_before_existing_ai_is_called(self):
        model_output = """{"payslips":[{"employer_name":"测试公司","pay_month":"2026-08","gross_salary":12000,"net_salary":10500,"confidence":0.94,"evidence":{"gross_salary":"应发 12000"}}]}"""
        raw_text = "测试公司 工资条 卡号 6222021234567890 手机 13800138000 应发 12000 实发 10500 2026年8月"
        with patch.object(intake, "_call_payslip_llm", return_value=model_output) as call:
            candidates = intake._ai_ocr_candidates(raw_text, user_id=9)

        prompt = call.call_args.args[0]
        self.assertNotIn("6222021234567890", prompt)
        self.assertNotIn("13800138000", prompt)
        self.assertIn("[账号已隐藏]", prompt)
        self.assertEqual("high", candidates[0].confidence_tier)
        self.assertIsNone(candidates[0].social_insurance)


if __name__ == "__main__":
    unittest.main()
