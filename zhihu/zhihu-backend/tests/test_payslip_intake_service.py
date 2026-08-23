from __future__ import annotations

import unittest
from io import BytesIO
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import fitz
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.cashflow import (
    confirm_economic_relation,
    confirm_transaction_fact_split,
    reverse_transaction_fact_split,
)
from app.api.routes.payslips import (
    confirm_arrival_links,
    confirm_selected_recognition_candidates,
    create_payslip,
    delete_payslip,
    get_arrival_suggestions,
    get_payslip,
    get_recognition_batch,
    exclude_recognition_candidate,
    list_arrival_link_revisions,
    list_open_recognition_batches,
    list_payslips,
    recognize_payslip,
    reopen_recognition_candidate,
    reverse_arrival_link,
    restore_payslip,
    update_recognition_candidate,
)
from app.db.session import Base
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.cashflow import (
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRelation,
    EconomicFactRelationRevision,
    EconomicFactRevision,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialTransaction,
)
from app.models.payslip import (
    Payslip,
    PayslipArrivalLink,
    PayslipArrivalLinkRevision,
    PayslipMaterialLink,
    PayslipRecognitionCandidateDraft,
)
from app.models.cashflow_import import FinancialImportBatch, FinancialRecognitionArtifact
from app.models.contract import Contract
from app.models.offer import Offer
from app.models.opportunity_target import JobTarget  # Registers Offer.job_target_id metadata for isolated DDL.
from app.models.personal_attachment import PersonalAttachmentCleanupJob, PersonalAttachmentVersion
from app.models.user import User
from app.schemas.cashflow import (
    EconomicFactSplitComponentInput,
    EconomicFactSplitConfirmRequest,
    EconomicRelationConfirmRequest,
)
from app.schemas.payslip import (
    PayslipArrivalLinkCreateRequest,
    PayslipArrivalLinkItem,
    PayslipCreateRequest,
    PayslipGuardianSummary,
    PayslipMaterialPreferenceInput,
    PayslipRecognitionCandidate,
    PayslipRecognitionBulkConfirmItem,
    PayslipRecognitionBulkConfirmRequest,
    PayslipRecognitionCandidateUpdateRequest,
    PayslipRecognitionResponse,
)
from app.services import payslip_intake_service as intake
from app.services.payslip_service import (
    analyze_payslip,
    build_material_comparisons,
    build_month_comparison,
    build_arrival_suggestions,
    build_payslip_guardian_summary,
    enrich_arrival_suggestions_with_ai,
    extract_contract_monthly_salary,
)
from app.services.economic_fact_service import get_transaction_fact, sync_transaction_fact


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

    def test_offer_probation_and_salary_components_are_checked_field_by_field(self):
        offer = SimpleNamespace(
            id=31,
            name="Offer 试用期",
            company_name="测试科技有限公司",
            monthly_salary=Decimal("12000"),
            fixed_salary=Decimal("8000"),
            variable_salary=Decimal("1600"),
            allowance=Decimal("300"),
            bonus="年终奖根据绩效发放",
            probation_months=3,
            probation_salary_rate=Decimal("0.80"),
            start_date="2026-08-15",
        )

        comparison = build_material_comparisons(
            {
                "pay_month": "2026-09",
                "employer_name": "测试科技",
                "gross_salary": 9600,
                "base_salary": 8000,
                "performance": 1300,
                "allowance": 300,
                "bonus": None,
            },
            [offer],
            [],
        )[0]

        checks = {item["field"]: item for item in comparison["field_checks"]}
        self.assertEqual("matched", checks["gross_salary"]["status"])
        self.assertEqual("试用期应发", checks["gross_salary"]["label"])
        self.assertEqual("matched", checks["base_salary"]["status"])
        self.assertEqual("different", checks["performance"]["status"])
        self.assertEqual("unknown", checks["bonus"]["status"])
        self.assertEqual("different", comparison["status"])

    def test_contract_pay_day_is_compared_without_treating_it_as_actual_arrival(self):
        contract = SimpleNamespace(
            id=41,
            display_name="劳动合同",
            employer="测试公司",
            probation=None,
            salary_terms="税前月薪 10000 元，次月 10 日发放。",
        )

        comparison = build_material_comparisons(
            {
                "gross_salary": 10000,
                "employer_name": "测试公司",
                "agreed_pay_date": date(2026, 9, 12),
            },
            [],
            [contract],
        )[0]

        checks = {item["field"]: item for item in comparison["field_checks"]}
        self.assertEqual("matched", checks["gross_salary"]["status"])
        self.assertEqual("次月10日", checks["agreed_pay_date"]["reference_value"])
        self.assertEqual("different", checks["agreed_pay_date"]["status"])
        self.assertEqual("different", comparison["status"])

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
            linked_fact_ids=set(),
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
            linked_fact_ids=set(),
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

    def test_guardian_summary_never_calls_missing_arrival_a_leak_or_late_payment(self):
        payslip = {
            "id": 51,
            "gross_salary": 12000,
            "social_insurance": 500,
            "housing_fund": 800,
            "individual_tax": 300,
            "attendance_deductions": 0,
            "meal_deductions": 0,
            "other_deductions": 0,
            "net_salary": 10400,
            "agreed_pay_date": date(2026, 1, 10),
        }
        summary = build_payslip_guardian_summary(
            payslip=payslip,
            material_comparisons=[],
            arrival_summary=SimpleNamespace(
                match_status="unmatched",
                net_salary=Decimal("10400"),
                confirmed_amount=Decimal("0"),
                remaining_amount=Decimal("10400"),
                links=[],
            ),
            month_comparison={"previous_payslip_id": None, "changes": []},
            offers=[],
        )
        PayslipGuardianSummary.model_validate(summary)

        checks = {item["key"]: item for item in summary["checks"]}
        self.assertEqual("confirmed", checks["arithmetic"]["status"])
        self.assertEqual("unverified", checks["arrival_amount"]["status"])
        self.assertEqual("unverified", checks["arrival_time"]["status"])
        self.assertNotIn("漏发", checks["arrival_amount"]["title"])
        self.assertNotIn("迟发", checks["arrival_amount"]["title"])

    def test_guardian_summary_turns_confirmed_differences_into_hr_questions(self):
        payslip = {
            "id": 52,
            "gross_salary": 10000,
            "social_insurance": 500,
            "housing_fund": 700,
            "individual_tax": 200,
            "attendance_deductions": 0,
            "meal_deductions": 0,
            "other_deductions": 0,
            "net_salary": 8600,
            "agreed_pay_date": date(2026, 9, 10),
        }
        summary = build_payslip_guardian_summary(
            payslip=payslip,
            material_comparisons=[
                {
                    "material_title": "Offer A",
                    "field_checks": [
                        {"field": "gross_salary", "label": "约定税前月薪", "status": "different"}
                    ],
                }
            ],
            arrival_summary=SimpleNamespace(
                match_status="partial",
                net_salary=Decimal("8600"),
                confirmed_amount=Decimal("8000"),
                remaining_amount=Decimal("600"),
                links=[SimpleNamespace(transaction_date=date(2026, 9, 12))],
            ),
            month_comparison={
                "previous_payslip_id": 50,
                "changes": [
                    {"field": "net_salary", "label": "实发工资", "difference": -500},
                ],
            },
            offers=[],
        )
        PayslipGuardianSummary.model_validate(summary)

        checks = {item["key"]: item for item in summary["checks"]}
        self.assertEqual("attention", checks["material_consistency"]["status"])
        self.assertEqual("attention", checks["arrival_amount"]["status"])
        self.assertEqual("attention", checks["month_change"]["status"])
        self.assertTrue(any("Offer A" in question for question in summary["hr_questions"]))
        self.assertTrue(any("600.00" in question for question in summary["hr_questions"]))

    def test_guardian_summary_only_flags_late_after_amount_and_dates_are_confirmed(self):
        summary = build_payslip_guardian_summary(
            payslip={
                "id": 53,
                "gross_salary": 10000,
                "social_insurance": 500,
                "housing_fund": 700,
                "individual_tax": 200,
                "attendance_deductions": 0,
                "meal_deductions": 0,
                "other_deductions": 0,
                "net_salary": 8600,
                "agreed_pay_date": date(2026, 9, 10),
            },
            material_comparisons=[],
            arrival_summary=SimpleNamespace(
                match_status="matched",
                net_salary=Decimal("8600"),
                confirmed_amount=Decimal("8600"),
                remaining_amount=Decimal("0"),
                links=[SimpleNamespace(transaction_date=date(2026, 9, 12))],
            ),
            month_comparison={"previous_payslip_id": None, "changes": []},
            offers=[],
        )

        checks = {item["key"]: item for item in summary["checks"]}
        self.assertEqual("confirmed", checks["arrival_amount"]["status"])
        self.assertEqual("attention", checks["arrival_time"]["status"])
        self.assertIn("晚 2 天", checks["arrival_time"]["title"])


class PayslipRecognitionDraftTest(unittest.TestCase):
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
                PersonalAttachmentVersion.__table__,
                Offer.__table__,
                Contract.__table__,
                FinancialImportBatch.__table__,
                FinancialRecognitionArtifact.__table__,
                Payslip.__table__,
                PayslipMaterialLink.__table__,
                PayslipArrivalLink.__table__,
                PayslipArrivalLinkRevision.__table__,
                PayslipRecognitionCandidateDraft.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.user = User(
            username="payslip-recognition-draft",
            password_hash="test",
            business_data_epoch=0,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(
            self.engine,
            tables=[
                PayslipRecognitionCandidateDraft.__table__,
                PayslipArrivalLinkRevision.__table__,
                PayslipArrivalLink.__table__,
                PayslipMaterialLink.__table__,
                Payslip.__table__,
                Contract.__table__,
                Offer.__table__,
                FinancialRecognitionArtifact.__table__,
                FinancialImportBatch.__table__,
                PersonalAttachmentVersion.__table__,
                ActionItem.__table__,
                GuardianFinding.__table__,
                Evidence.__table__,
                CareerEvent.__table__,
                CareerCase.__table__,
                User.__table__,
            ],
        )
        self.engine.dispose()

    @staticmethod
    def _upload(
        content: bytes,
        *,
        filename: str = "两个月工资条.csv",
        content_type: str = "text/csv",
    ) -> UploadFile:
        return UploadFile(
            file=BytesIO(content),
            filename=filename,
            headers=Headers({"content-type": content_type}),
        )

    @staticmethod
    def _recognition_result() -> PayslipRecognitionResponse:
        return PayslipRecognitionResponse(
            source_type="file",
            original_filename="两个月工资条.csv",
            original_file_retained=False,
            candidates=[
                PayslipRecognitionCandidate(
                    row_number=1,
                    confidence=0.96,
                    confidence_tier="high",
                    reasons=["月份、应发和实发完整"],
                    employer_name="测试公司",
                    pay_month="2026-07",
                    gross_salary=Decimal("12000.00"),
                    net_salary=Decimal("10500.00"),
                ),
                PayslipRecognitionCandidate(
                    row_number=2,
                    confidence=0.72,
                    confidence_tier="medium",
                    reasons=["扣款字段不完整"],
                    warnings=["社保待确认"],
                    employer_name="测试公司",
                    pay_month="2026-08",
                    gross_salary=Decimal("12100.00"),
                    net_salary=Decimal("10600.00"),
                ),
            ],
        )

    def test_recognition_batch_is_resumable_deduplicated_and_confirmed_only_by_user(self):
        content = b"private payslip fixture"
        with patch(
            "app.api.routes.payslips.recognize_payslip_upload",
            return_value=self._recognition_result(),
        ) as recognizer:
            created = recognize_payslip(
                file=self._upload(content),
                confirm_external_processing=False,
                user=self.user,
                db=self.db,
            )

        self.assertIsNotNone(created.batch_id)
        self.assertFalse(created.resumed_existing_batch)
        self.assertEqual(2, len(created.candidates))
        self.assertEqual(0, self.db.query(Payslip).count())
        self.assertEqual(1, self.db.query(FinancialImportBatch).count())
        self.assertEqual(2, self.db.query(PayslipRecognitionCandidateDraft).count())
        self.assertEqual(1, self.db.query(FinancialRecognitionArtifact).filter_by(artifact_type="normalized_rows").count())
        self.assertIsNone(self.db.query(FinancialImportBatch).one().attachment_version_id)

        resumed = recognize_payslip(
            file=self._upload(content),
            confirm_external_processing=False,
            user=self.user,
            db=self.db,
        )
        self.assertTrue(resumed.resumed_existing_batch)
        self.assertEqual(created.batch_id, resumed.batch_id)
        self.assertEqual(1, recognizer.call_count)
        self.assertEqual(1, len(list_open_recognition_batches(user=self.user, db=self.db)))

        first = resumed.candidates[0]
        edited = first.model_copy(update={"net_salary": Decimal("10480.00")})
        updated = update_recognition_candidate(
            first.candidate_id,
            PayslipRecognitionCandidateUpdateRequest(version=first.version, candidate=edited),
            user=self.user,
            db=self.db,
        )
        updated_first = updated.candidates[0]
        self.assertEqual(Decimal("10480.00"), updated_first.net_salary)
        self.assertGreater(updated_first.version, first.version)

        second = updated.candidates[1]
        excluded = exclude_recognition_candidate(
            second.candidate_id,
            version=second.version,
            user=self.user,
            db=self.db,
        )
        self.assertEqual("excluded", excluded.candidates[1].review_status)
        reopened = reopen_recognition_candidate(
            second.candidate_id,
            version=excluded.candidates[1].version,
            user=self.user,
            db=self.db,
        )
        self.assertEqual("pending", reopened.candidates[1].review_status)

        confirmed_candidate = reopened.candidates[0]
        saved = create_payslip(
            PayslipCreateRequest(
                pay_month="2026-07",
                employer_name="测试公司",
                gross_salary=12000,
                net_salary=10480,
                source_type="file",
                recognition_confidence=0.96,
                recognition_candidate_id=confirmed_candidate.candidate_id,
                recognition_candidate_version=confirmed_candidate.version,
            ),
            user=self.user,
            db=self.db,
        )
        restored_batch = get_recognition_batch(created.batch_id, user=self.user, db=self.db)
        restored_first = restored_batch.candidates[0]
        self.assertEqual("confirmed", restored_first.review_status)
        self.assertEqual(saved.payslip.id, restored_first.payslip_id)
        self.assertEqual(1, self.db.query(Payslip).count())
        self.assertEqual(1, len(list_open_recognition_batches(user=self.user, db=self.db)))

        with self.assertRaises(HTTPException) as stale:
            update_recognition_candidate(
                confirmed_candidate.candidate_id,
                PayslipRecognitionCandidateUpdateRequest(
                    version=confirmed_candidate.version,
                    candidate=confirmed_candidate,
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, stale.exception.status_code)

    def test_ocr_batch_retains_complete_text_but_no_original_attachment(self):
        result = self._recognition_result().model_copy(update={
            "source_type": "ocr",
            "original_filename": "八月工资条.png",
            "raw_text": "测试公司 2026年8月 应发12100 实发10600",
            "candidates": [self._recognition_result().candidates[1]],
        })
        with patch(
            "app.api.routes.payslips.recognize_payslip_upload",
            return_value=result,
        ):
            created = recognize_payslip(
                file=self._upload(
                    b"fake image bytes",
                    filename="八月工资条.png",
                    content_type="image/png",
                ),
                confirm_external_processing=True,
                user=self.user,
                db=self.db,
            )

        self.assertEqual("ocr", created.source_type)
        self.assertFalse(created.original_file_retained)
        self.assertEqual(result.raw_text, created.raw_text)
        artifact = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=created.batch_id,
            artifact_type="ocr_text",
        ).one()
        self.assertEqual(result.raw_text, artifact.content_text)
        self.assertIsNone(artifact.attachment_version_id)
        self.assertEqual(0, self.db.query(Payslip).count())
        candidate = created.candidates[0]
        saved = create_payslip(
            PayslipCreateRequest(
                pay_month="2026-08",
                employer_name="测试公司",
                gross_salary=12100,
                net_salary=10600,
                source_type="manual",
                raw_text="客户端伪造的 OCR 原文",
                recognition_candidate_id=candidate.candidate_id,
                recognition_candidate_version=candidate.version,
            ),
            user=self.user,
            db=self.db,
        )
        self.assertEqual("ocr", saved.payslip.source_type)
        stored = self.db.query(Payslip).filter_by(id=saved.payslip.id).one()
        self.assertEqual(result.raw_text, stored.raw_text)

    def test_bulk_confirm_is_atomic_and_only_accepts_selected_high_confidence_candidates(self):
        with patch(
            "app.api.routes.payslips.recognize_payslip_upload",
            return_value=self._recognition_result(),
        ):
            created = recognize_payslip(
                file=self._upload(b"mixed confidence batch"),
                confirm_external_processing=False,
                user=self.user,
                db=self.db,
            )
        request = PayslipRecognitionBulkConfirmRequest(items=[
            PayslipRecognitionBulkConfirmItem(candidate_id=item.candidate_id, version=item.version)
            for item in created.candidates
        ])
        with self.assertRaises(HTTPException) as blocked:
            confirm_selected_recognition_candidates(
                created.batch_id,
                request,
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, blocked.exception.status_code)
        self.assertIn("不是绿色高置信项", str(blocked.exception.detail))
        self.assertEqual(0, self.db.query(Payslip).count())
        self.assertEqual(
            ["pending", "pending"],
            [item.review_status for item in get_recognition_batch(created.batch_id, user=self.user, db=self.db).candidates],
        )

        all_high = self._recognition_result()
        all_high.candidates[1] = all_high.candidates[1].model_copy(update={
            "confidence": 0.95,
            "confidence_tier": "high",
            "warnings": [],
        })
        with patch(
            "app.api.routes.payslips.recognize_payslip_upload",
            return_value=all_high,
        ):
            high_batch = recognize_payslip(
                file=self._upload(b"all high batch"),
                confirm_external_processing=False,
                user=self.user,
                db=self.db,
            )
        material_case = CareerCase(
            user_id=self.user.id,
            type="payslip_review",
            title="批量工资条材料",
        )
        self.db.add(material_case)
        self.db.flush()
        labor_contract = Contract(
            case_id=material_case.id,
            display_name="批量确认适用合同",
            document_kind="labor_contract",
            employer="测试公司",
            salary_terms="税前月薪 12000 元",
        )
        self.db.add(labor_contract)
        self.db.commit()
        confirmed = confirm_selected_recognition_candidates(
            high_batch.batch_id,
            PayslipRecognitionBulkConfirmRequest(
                items=[
                    PayslipRecognitionBulkConfirmItem(
                        candidate_id=item.candidate_id,
                        version=item.version,
                    )
                    for item in high_batch.candidates
                ],
                linked_contract_ids=[labor_contract.id],
                material_preferences=[
                    PayslipMaterialPreferenceInput(
                        material_type="contract",
                        material_id=labor_contract.id,
                        application_status="preferred",
                        priority_rank=10,
                    )
                ],
            ),
            user=self.user,
            db=self.db,
        )
        self.assertEqual(2, len(confirmed.payslip_ids))
        self.assertEqual("completed", confirmed.batch.batch_status)
        self.assertEqual(
            ["confirmed", "confirmed"],
            [item.review_status for item in confirmed.batch.candidates],
        )
        self.assertEqual(2, self.db.query(Payslip).count())
        links = self.db.query(PayslipMaterialLink).order_by(PayslipMaterialLink.payslip_id.asc()).all()
        self.assertEqual(2, len(links))
        self.assertTrue(all(item.contract_id == labor_contract.id for item in links))
        self.assertTrue(all(item.application_status == "preferred" for item in links))
        open_batch_ids = {
            item.batch_id for item in list_open_recognition_batches(user=self.user, db=self.db)
        }
        self.assertNotIn(high_batch.batch_id, open_batch_ids)
        self.assertIn(created.batch_id, open_batch_ids)

    def test_material_preference_is_user_owned_and_supplement_does_not_silently_override_contract(self):
        case = CareerCase(user_id=self.user.id, type="payslip_review", title="材料适用性核对")
        event = CareerEvent(
            user_id=self.user.id,
            event_type="income",
            title="2026 年 8 月工资核对",
            status="active",
        )
        self.db.add_all([case, event])
        self.db.flush()
        labor_contract = Contract(
            case_id=case.id,
            career_event_id=event.id,
            display_name="劳动合同",
            document_kind="labor_contract",
            employer="测试公司",
            salary_terms="税前月薪 12000 元",
        )
        supplement = Contract(
            case_id=case.id,
            career_event_id=event.id,
            display_name="薪资补充协议",
            document_kind="supplemental_agreement",
            employer="测试公司",
            salary_terms="绩效口径另行核定",
        )
        self.db.add_all([labor_contract, supplement])
        self.db.commit()

        saved = create_payslip(
            PayslipCreateRequest(
                career_event_id=event.id,
                linked_contract_ids=[labor_contract.id, supplement.id],
                material_preferences=[
                    PayslipMaterialPreferenceInput(
                        material_type="contract",
                        material_id=labor_contract.id,
                        application_status="preferred",
                        priority_rank=10,
                        user_note="当前发薪以这份劳动合同为准",
                    ),
                    PayslipMaterialPreferenceInput(
                        material_type="contract",
                        material_id=supplement.id,
                        application_status="unresolved",
                        priority_rank=20,
                    ),
                ],
                pay_month="2026-08",
                employer_name="测试公司",
                gross_salary=Decimal("12000.00"),
                net_salary=Decimal("10500.00"),
            ),
            user=self.user,
            db=self.db,
        )

        detail = get_payslip(saved.payslip.id, user=self.user, db=self.db)
        materials = {
            (item.material_type, item.material_id): item
            for item in detail.materials
        }
        self.assertEqual("preferred", materials[("contract", labor_contract.id)].application_status)
        self.assertEqual("labor_contract", materials[("contract", labor_contract.id)].document_kind)
        self.assertEqual(
            "当前发薪以这份劳动合同为准",
            materials[("contract", labor_contract.id)].user_note,
        )
        self.assertEqual("unresolved", materials[("contract", supplement.id)].application_status)
        self.assertEqual("supplemental_agreement", materials[("contract", supplement.id)].document_kind)
        comparisons = {
            (item.material_type, item.material_id): item
            for item in detail.material_comparisons
        }
        self.assertEqual("preferred", comparisons[("contract", labor_contract.id)].application_status)
        self.assertEqual("unresolved", comparisons[("contract", supplement.id)].application_status)
        self.assertNotEqual(
            comparisons[("contract", labor_contract.id)].explanation,
            comparisons[("contract", supplement.id)].explanation,
        )

        before = self.db.query(Payslip).count()
        with self.assertRaises(HTTPException) as multiple_preferred:
            create_payslip(
                PayslipCreateRequest(
                    career_event_id=event.id,
                    linked_contract_ids=[labor_contract.id, supplement.id],
                    material_preferences=[
                        PayslipMaterialPreferenceInput(
                            material_type="contract",
                            material_id=labor_contract.id,
                            application_status="preferred",
                        ),
                        PayslipMaterialPreferenceInput(
                            material_type="contract",
                            material_id=supplement.id,
                            application_status="preferred",
                        ),
                    ],
                    pay_month="2026-09",
                    gross_salary=Decimal("12000.00"),
                    net_salary=Decimal("10500.00"),
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(400, multiple_preferred.exception.status_code)
        self.assertEqual(before, self.db.query(Payslip).count())

        with self.assertRaises(HTTPException) as unlinked_preference:
            create_payslip(
                PayslipCreateRequest(
                    career_event_id=event.id,
                    linked_contract_ids=[labor_contract.id],
                    material_preferences=[
                        PayslipMaterialPreferenceInput(
                            material_type="contract",
                            material_id=supplement.id,
                            application_status="reference",
                        ),
                    ],
                    pay_month="2026-09",
                    gross_salary=Decimal("12000.00"),
                    net_salary=Decimal("10500.00"),
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(400, unlinked_preference.exception.status_code)
        self.assertEqual(before, self.db.query(Payslip).count())


class PayslipArrivalEconomicFactTest(unittest.TestCase):
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
                EconomicFact.__table__,
                EconomicFactAllocation.__table__,
                EconomicFactRevision.__table__,
                EconomicFactRelation.__table__,
                EconomicFactRelationRevision.__table__,
                FinancialLedgerRevisionEvent.__table__,
                Payslip.__table__,
                PayslipArrivalLink.__table__,
                PayslipArrivalLinkRevision.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.user = User(username="payslip-fact-user", password_hash="test", business_data_epoch=0)
        self.db.add(self.user)
        self.db.flush()
        case = CareerCase(user_id=self.user.id, type="payslip_review", title="工资到账事实核对")
        self.db.add(case)
        self.db.flush()
        self.payslip = Payslip(
            case_id=case.id,
            pay_month="2026-08",
            pay_date=date(2026, 9, 10),
            employer_name="测试公司",
            gross_salary=Decimal("10000.00"),
            net_salary=Decimal("9000.00"),
            record_status="active",
        )
        salary_category = FinancialCategory(direction="income", name="工资", is_system=True)
        other_income_category = FinancialCategory(direction="income", name="其他收入", is_system=True)
        expense_category = FinancialCategory(direction="expense", name="转账支出", is_system=True)
        self.db.add_all([self.payslip, salary_category, other_income_category, expense_category])
        self.db.flush()
        self.salary_category_id = salary_category.id
        self.other_income_category_id = other_income_category.id
        self.expense_category_id = expense_category.id
        self.mixed_income = FinancialTransaction(
            user_id=self.user.id,
            category_id=salary_category.id,
            direction="income",
            amount=Decimal("10000.00"),
            transaction_date=date(2026, 9, 10),
            merchant="测试公司",
            description="8月工资及差旅款",
            source_type="manual",
            status="confirmed",
        )
        self.db.add(self.mixed_income)
        self.db.flush()
        sync_transaction_fact(self.db, transaction=self.mixed_income, user_id=self.user.id)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_split_income_arrival_is_confirmed_by_fact_and_fully_reversible(self):
        split = confirm_transaction_fact_split(
            self.mixed_income.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("9000.00"),
                        category_id=self.salary_category_id,
                        title="8月工资到账",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("1000.00"),
                        category_id=self.other_income_category_id,
                        title="差旅返还",
                    ),
                ],
                reason="一笔到账包含工资和其他收入",
            ),
            user=self.user,
            db=self.db,
        )
        salary_fact_id = split.components[0].fact_id
        other_fact_id = split.components[1].fact_id

        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=None):
            suggestions = get_arrival_suggestions(
                self.payslip.id,
                user=self.user,
                db=self.db,
            ).suggestions
        self.assertEqual({salary_fact_id, other_fact_id}, {item.economic_fact_id for item in suggestions})
        salary_suggestion = next(item for item in suggestions if item.economic_fact_id == salary_fact_id)
        self.assertEqual("high", salary_suggestion.confidence_tier)
        self.assertTrue(salary_suggestion.is_split_component)
        self.assertEqual(Decimal("10000.00"), salary_suggestion.source_transaction_amount)
        self.assertEqual(Decimal("9000.00"), salary_suggestion.available_amount)

        with self.assertRaises(HTTPException) as ambiguous:
            confirm_arrival_links(
                self.payslip.id,
                PayslipArrivalLinkCreateRequest(links=[PayslipArrivalLinkItem(
                    transaction_id=self.mixed_income.id,
                    allocated_amount=Decimal("9000.00"),
                )]),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, ambiguous.exception.status_code)
        self.assertIn("明确选择工资到账部分", ambiguous.exception.detail)

        summary = confirm_arrival_links(
            self.payslip.id,
            PayslipArrivalLinkCreateRequest(links=[PayslipArrivalLinkItem(
                transaction_id=self.mixed_income.id,
                economic_fact_id=salary_fact_id,
                allocated_amount=Decimal("9000.00"),
                reasons=["程序金额一致，用户确认工资子事实"],
            )]),
            user=self.user,
            db=self.db,
        )
        self.assertEqual("matched", summary.match_status)
        self.assertEqual(salary_fact_id, summary.links[0].economic_fact_id)
        self.assertEqual("8月工资到账", summary.links[0].fact_title)
        self.assertTrue(summary.links[0].is_split_component)
        self.assertIsNotNone(summary.links[0].ledger_revision)
        link = self.db.get(PayslipArrivalLink, summary.links[0].id)
        revisions = list_arrival_link_revisions(
            self.payslip.id,
            link.id,
            user=self.user,
            db=self.db,
        )
        self.assertEqual(["confirm"], [item.operation for item in revisions])
        self.assertEqual(link.ledger_revision, revisions[0].ledger_revision)

        expense = FinancialTransaction(
            user_id=self.user.id,
            category_id=self.expense_category_id,
            direction="expense",
            amount=Decimal("1.00"),
            transaction_date=date(2026, 9, 10),
            description="账户互转",
            source_type="manual",
            status="confirmed",
        )
        self.db.add(expense)
        self.db.flush()
        expense_fact = sync_transaction_fact(self.db, transaction=expense, user_id=self.user.id)
        self.db.commit()
        with self.assertRaises(HTTPException) as reused:
            confirm_economic_relation(
                EconomicRelationConfirmRequest(
                    source_transaction_id=self.mixed_income.id,
                    target_transaction_id=expense.id,
                    source_fact_id=salary_fact_id,
                    target_fact_id=expense_fact.id,
                    relation_type="transfer_pair",
                    allocated_amount=Decimal("1.00"),
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, reused.exception.status_code)
        self.assertIn("可关联金额不足", reused.exception.detail)

        with self.assertRaises(HTTPException) as split_blocked:
            reverse_transaction_fact_split(
                self.mixed_income.id,
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, split_blocked.exception.status_code)
        self.assertIn("工资到账证据", split_blocked.exception.detail)

        restored = reverse_arrival_link(
            self.payslip.id,
            link.id,
            user=self.user,
            db=self.db,
        )
        self.assertEqual("unmatched", restored.match_status)
        revisions = list_arrival_link_revisions(
            self.payslip.id,
            link.id,
            user=self.user,
            db=self.db,
        )
        self.assertEqual(["reverse", "confirm"], [item.operation for item in revisions])
        self.assertGreater(revisions[0].ledger_revision, revisions[1].ledger_revision)

        unsplit = reverse_transaction_fact_split(
            self.mixed_income.id,
            user=self.user,
            db=self.db,
        )
        self.assertEqual([], unsplit.components)
        restored_fact = get_transaction_fact(
            self.db,
            transaction_id=self.mixed_income.id,
            user_id=self.user.id,
        )
        self.assertEqual(Decimal("10000.00"), Decimal(restored_fact.amount))


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
                EconomicFact.__table__,
                EconomicFactAllocation.__table__,
                EconomicFactRevision.__table__,
                EconomicFactRelation.__table__,
                EconomicFactRelationRevision.__table__,
                FinancialLedgerRevisionEvent.__table__,
                Payslip.__table__,
                PayslipMaterialLink.__table__,
                PayslipArrivalLink.__table__,
                PayslipArrivalLinkRevision.__table__,
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
        arrival_fact = sync_transaction_fact(
            self.db,
            transaction=arrival,
            user_id=self.user.id,
        )
        self.arrival_link = PayslipArrivalLink(
            payslip_id=self.current.id,
            transaction_id=arrival.id,
            economic_fact_id=arrival_fact.id,
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
        delete_revision = self.db.query(PayslipArrivalLinkRevision).filter(
            PayslipArrivalLinkRevision.link_id == self.arrival_link.id,
        ).one()
        self.assertEqual("reverse", delete_revision.operation)
        self.assertIn("工资条被删除", delete_revision.reason)
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
        revision = self.db.query(PayslipArrivalLinkRevision).filter(
            PayslipArrivalLinkRevision.link_id == self.arrival_link.id,
        ).one()
        self.assertEqual("reverse", revision.operation)
        self.assertIn("修订版", revision.reason)
        self.assertEqual(1, len([item for item in list_payslips(True, user=self.user, db=self.db) if item.record_status == "active"]))

        with self.assertRaises(HTTPException) as history_error:
            get_arrival_suggestions(self.current.id, user=self.user, db=self.db)
        self.assertEqual(409, history_error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
