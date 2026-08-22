from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import fitz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.payslips import create_payslip, delete_payslip, list_payslips, restore_payslip
from app.db.session import Base
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.models.payslip import Payslip, PayslipArrivalLink, PayslipMaterialLink
from app.models.user import User
from app.schemas.payslip import PayslipCreateRequest
from app.services import payslip_intake_service as intake
from app.services.payslip_service import (
    analyze_payslip,
    build_material_comparisons,
    build_month_comparison,
    build_arrival_suggestions,
    enrich_arrival_suggestions_with_ai,
    extract_contract_monthly_salary,
)


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

    def test_pdf_embedded_text_is_extracted_locally_then_sent_redacted_to_existing_ai(self):
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Test Company Payslip")
        page.insert_text((72, 92), "Pay Month 2026-08 Gross Salary 12000 Net Salary 10500")
        content = document.tobytes()
        document.close()
        model_output = """{"payslips":[{"employer_name":"Test Company","pay_month":"2026-08","gross_salary":12000,"net_salary":10500,"confidence":0.94,"evidence":{"gross_salary":"Gross Salary 12000"}}]}"""

        with patch.object(intake, "_call_payslip_llm", return_value=model_output) as call:
            result = intake.recognize_payslip_upload(
                user_id=9,
                filename="工资条.pdf",
                content=content,
                content_type="application/pdf",
                confirm_external_processing=True,
            )

        self.assertEqual("ocr", result.source_type)
        self.assertFalse(result.original_file_retained)
        self.assertIn("Gross Salary 12000", result.raw_text or "")
        self.assertIn("Gross Salary 12000", call.call_args.args[0])
        self.assertEqual(Decimal("10500.00"), result.candidates[0].net_salary)

    def test_scanned_pdf_page_is_rendered_for_local_ocr(self):
        document = fitz.open()
        document.new_page()
        content = document.tobytes()
        document.close()
        model_output = """{"payslips":[{"pay_month":"2026-08","gross_salary":12000,"net_salary":10500,"confidence":0.9}]}"""

        with patch.object(intake, "_local_ocr", return_value="2026年8月 应发工资12000 实发工资10500") as local_ocr, patch.object(
            intake,
            "_call_payslip_llm",
            return_value=model_output,
        ):
            result = intake.recognize_payslip_upload(
                user_id=9,
                filename="scan.pdf",
                content=content,
                content_type="application/pdf",
                confirm_external_processing=True,
            )

        self.assertEqual("image/png", local_ocr.call_args.kwargs["detected_type"])
        self.assertEqual("2026-08", result.candidates[0].pay_month)

    def test_pdf_requires_processing_consent_and_rejects_excess_pages(self):
        one_page = fitz.open()
        one_page.new_page()
        one_page_content = one_page.tobytes()
        one_page.close()
        with self.assertRaises(intake.PayslipRecognitionError) as consent_error:
            intake.recognize_payslip_upload(
                user_id=9,
                filename="scan.pdf",
                content=one_page_content,
                content_type="application/pdf",
                confirm_external_processing=False,
            )
        self.assertEqual("payslip_ocr_consent_required", consent_error.exception.code)

        many_pages = fitz.open()
        for _ in range(intake.MAX_PAYSLIP_PDF_PAGES + 1):
            many_pages.new_page()
        many_pages_content = many_pages.tobytes()
        many_pages.close()
        with self.assertRaises(intake.PayslipRecognitionError) as pages_error:
            intake.recognize_payslip_upload(
                user_id=9,
                filename="too-many-pages.pdf",
                content=many_pages_content,
                content_type="application/pdf",
                confirm_external_processing=True,
            )
        self.assertEqual("payslip_pdf_too_many_pages", pages_error.exception.code)

    def test_offer_and_contract_are_compared_independently(self):
        offers = [SimpleNamespace(id=11, name="Offer A", company_name=None, monthly_salary=12000)]
        contracts = [
            SimpleNamespace(
                id=21,
                display_name="劳动合同 A",
                employer=None,
                salary_terms="税前月薪为人民币 10,000 元，奖金另计。",
            ),
            SimpleNamespace(
                id=22,
                display_name="劳动合同 B",
                employer=None,
                salary_terms="年薪及奖金由双方另行约定。",
            ),
        ]

        comparisons = build_material_comparisons(12000, offers, contracts)

        self.assertEqual(["matched", "different", "unknown"], [item["status"] for item in comparisons])
        self.assertEqual(10000, extract_contract_monthly_salary(contracts[0].salary_terms))
        self.assertIsNone(extract_contract_monthly_salary(contracts[1].salary_terms))
        self.assertEqual(2000, comparisons[1]["difference"])

    def test_arrival_matching_explains_exact_and_split_candidates(self):
        transactions = [
            SimpleNamespace(
                id=31,
                amount=Decimal("10500.00"),
                transaction_date=date(2026, 9, 10),
                merchant="测试公司",
                description="8月工资",
            ),
            SimpleNamespace(
                id=32,
                amount=Decimal("5000.00"),
                transaction_date=date(2026, 9, 11),
                merchant=None,
                description="工资补发",
            ),
        ]

        suggestions = build_arrival_suggestions(
            net_salary=10500,
            reference_date=date(2026, 9, 10),
            employer_name="测试公司",
            transactions=transactions,
            linked_transaction_ids=set(),
        )

        self.assertEqual("high", suggestions[0]["confidence_tier"])
        self.assertEqual(Decimal("10500.00"), suggestions[0]["suggested_allocation"])
        self.assertEqual("medium", suggestions[1]["confidence_tier"])
        self.assertIn("拆分到账", suggestions[1]["reasons"][0])

    def test_ai_explains_ambiguous_arrival_without_promoting_it_to_high(self):
        suggestions = build_arrival_suggestions(
            net_salary=10500,
            reference_date=date(2026, 9, 10),
            employer_name="测试公司",
            transactions=[
                SimpleNamespace(
                    id=32,
                    amount=Decimal("5000.00"),
                    transaction_date=date(2026, 9, 11),
                    merchant=None,
                    description="工资补发",
                )
            ],
            linked_transaction_ids=set(),
        )
        with patch(
            "app.services.payslip_intake_service._call_payslip_llm",
            return_value='{"assessments":[{"transaction_id":32,"assessment":"likely","reason":"摘要明确为工资补发"}]}',
        ):
            result = enrich_arrival_suggestions_with_ai(
                suggestions,
                payslip_id=8,
                pay_month="2026-08",
                net_salary=10500,
                employer_name="测试公司",
                user_id=9,
                expected_data_epoch=1,
            )

        self.assertEqual("completed", result[0]["ai_status"])
        self.assertEqual("likely", result[0]["ai_assessment"])
        self.assertEqual("medium", result[0]["confidence_tier"])

    def test_month_comparison_only_uses_fields_known_in_both_payslips(self):
        previous = SimpleNamespace(
            id=40,
            pay_month="2026-07",
            gross_salary=Decimal("12000"),
            net_salary=Decimal("10400"),
            performance=None,
        )
        current = SimpleNamespace(
            id=41,
            pay_month="2026-08",
            gross_salary=Decimal("11800"),
            net_salary=Decimal("10100"),
            performance=Decimal("1000"),
        )

        comparison = build_month_comparison(current, previous)

        self.assertEqual(40, comparison["previous_payslip_id"])
        self.assertEqual(
            {"gross_salary": -200, "net_salary": -300},
            {item["field"]: item["difference"] for item in comparison["changes"]},
        )
        self.assertNotIn("performance", {item["field"] for item in comparison["changes"]})


class PayslipLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                CareerCase.__table__,
                CareerEvent.__table__,
                Evidence.__table__,
                GuardianFinding.__table__,
                ActionItem.__table__,
                FinancialCategory.__table__,
                FinancialTransaction.__table__,
                Payslip.__table__,
                PayslipMaterialLink.__table__,
                PayslipArrivalLink.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.user = User(username="payslip-lifecycle", password_hash="test", business_data_epoch=0)
        self.db.add(self.user)
        self.db.flush()
        case = CareerCase(user_id=self.user.id, type="payslip_review", title="工资核对")
        event = CareerEvent(user_id=self.user.id, event_type="income", title="工资核对", status="active")
        self.db.add_all([case, event])
        self.db.flush()
        self.previous = Payslip(
            case_id=case.id,
            career_event_id=event.id,
            pay_month="2026-08",
            gross_salary=Decimal("12000.00"),
            net_salary=Decimal("10500.00"),
            record_status="superseded",
        )
        self.current = Payslip(
            case_id=case.id,
            career_event_id=event.id,
            pay_month="2026-08",
            gross_salary=Decimal("12100.00"),
            net_salary=Decimal("10600.00"),
            record_status="active",
        )
        self.db.add_all([self.previous, self.current])
        self.db.flush()
        self.current.supersedes_payslip_id = self.previous.id
        arrival = FinancialTransaction(
            user_id=self.user.id,
            direction="income",
            amount=Decimal("10600.00"),
            transaction_date=date(2026, 9, 10),
            source_type="manual",
            status="confirmed",
        )
        self.db.add(arrival)
        self.db.flush()
        self.arrival_link = PayslipArrivalLink(
            payslip_id=self.current.id,
            transaction_id=arrival.id,
            allocated_amount=Decimal("10600.00"),
            status="confirmed",
            confirmed_by_user_id=self.user.id,
        )
        self.db.add(self.arrival_link)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_delete_is_recoverable_and_revision_chain_never_has_two_active_versions(self):
        deleted = delete_payslip(self.current.id, user=self.user, db=self.db)

        self.assertEqual("deleted", deleted.record_status)
        self.db.refresh(self.previous)
        self.db.refresh(self.arrival_link)
        self.assertEqual("active", self.previous.record_status)
        self.assertEqual("reversed", self.arrival_link.status)
        self.assertNotIn(self.current.id, [item.id for item in list_payslips(False, user=self.user, db=self.db)])

        restored = restore_payslip(self.current.id, user=self.user, db=self.db)

        self.assertEqual("active", restored.record_status)
        self.db.refresh(self.previous)
        self.assertEqual("superseded", self.previous.record_status)
        self.assertEqual(2, len(list_payslips(True, user=self.user, db=self.db)))

    def test_revision_preserves_history_and_requires_arrival_reconfirmation(self):
        result = create_payslip(
            PayslipCreateRequest(
                career_event_id=self.current.career_event_id,
                supersedes_payslip_id=self.current.id,
                pay_month="2026-08",
                employer_name="测试公司",
                gross_salary=12200,
                net_salary=10700,
            ),
            user=self.user,
            db=self.db,
        )

        self.db.refresh(self.current)
        self.db.refresh(self.arrival_link)
        self.assertEqual(self.current.id, result.payslip.supersedes_payslip_id)
        self.assertEqual("active", result.payslip.record_status)
        self.assertEqual("superseded", self.current.record_status)
        self.assertEqual("reversed", self.arrival_link.status)
        self.assertEqual(1, len([item for item in list_payslips(True, user=self.user, db=self.db) if item.record_status == "active"]))


if __name__ == "__main__":
    unittest.main()
