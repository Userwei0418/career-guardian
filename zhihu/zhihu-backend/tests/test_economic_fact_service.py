from __future__ import annotations

import json
import unittest
from io import BytesIO
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.cashflow import (
    ask_confirmed_cashflow,
    confirm_economic_relation,
    get_summary,
    reverse_economic_relation,
)
from app.db.session import Base
from app.models.cashflow import (
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRelation,
    FinancialCategory,
    FinancialTransaction,
)
from app.models.user import User
from app.schemas.cashflow import CashflowAskRequest, EconomicRelationConfirmRequest
from app.services.cashflow_chat_service import (
    answer_cashflow_question,
    build_cashflow_chat_context,
)
from app.services.cashflow_export_service import build_cashflow_export_bundle
from app.services.cashflow_service import build_month_summary
from app.services.economic_fact_service import (
    build_relation_suggestions,
    enrich_relation_suggestions_with_ai,
    sync_transaction_fact,
)


def transaction(
    transaction_id: int,
    *,
    direction: str,
    amount: str,
    transaction_date: date,
    merchant: str = "",
    description: str = "",
    nature: str | None = None,
    category_id: int | None = None,
):
    return SimpleNamespace(
        id=transaction_id,
        direction=direction,
        amount=Decimal(amount),
        transaction_date=transaction_date,
        merchant=merchant,
        description=description,
        nature=nature,
        category_id=category_id,
        currency="CNY",
        status="confirmed",
    )


def fact(fact_id: int, transaction_id: int):
    return SimpleNamespace(id=fact_id, primary_transaction_id=transaction_id)


class EconomicFactSuggestionTest(unittest.TestCase):
    def test_exact_refund_is_high_confidence_and_explains_why(self):
        incoming = transaction(
            2,
            direction="income",
            amount="68.00",
            transaction_date=date(2026, 8, 5),
            merchant="某电商",
            description="订单退款到账",
        )
        expense = transaction(
            1,
            direction="expense",
            amount="68.00",
            transaction_date=date(2026, 8, 3),
            merchant="某电商",
        )

        suggestions = build_relation_suggestions(
            transaction=incoming,
            fact=fact(20, 2),
            candidates=[(expense, fact(10, 1))],
            existing_pairs=set(),
        )

        self.assertEqual(1, len(suggestions))
        suggestion = suggestions[0]
        self.assertEqual("refunds", suggestion["relation_type"])
        self.assertEqual("high", suggestion["confidence_tier"])
        self.assertIn("两笔金额完全一致", suggestion["reasons"])
        self.assertEqual("某电商", suggestion["target_title"])

    def test_transfer_words_win_over_refund_and_plain_unrelated_pair_is_skipped(self):
        incoming = transaction(
            3,
            direction="income",
            amount="500.00",
            transaction_date=date(2026, 8, 6),
            description="银行卡转入微信零钱",
        )
        transfer_out = transaction(
            2,
            direction="expense",
            amount="500.00",
            transaction_date=date(2026, 8, 6),
            description="转出至微信",
        )
        unrelated = transaction(
            1,
            direction="expense",
            amount="500.00",
            transaction_date=date(2026, 8, 5),
            merchant="餐厅",
        )

        suggestions = build_relation_suggestions(
            transaction=incoming,
            fact=fact(30, 3),
            candidates=[(transfer_out, fact(20, 2)), (unrelated, fact(10, 1))],
            existing_pairs=set(),
        )

        self.assertEqual(1, len(suggestions))
        self.assertEqual("transfer_pair", suggestions[0]["relation_type"])
        self.assertEqual("high", suggestions[0]["confidence_tier"])

    def test_ai_adds_assessment_but_never_promotes_program_tier(self):
        current = transaction(
            2,
            direction="income",
            amount="60.00",
            transaction_date=date(2026, 8, 10),
            merchant="某店",
        )
        prior = transaction(
            1,
            direction="expense",
            amount="100.00",
            transaction_date=date(2026, 8, 1),
            merchant="某店",
        )
        suggestions = build_relation_suggestions(
            transaction=current,
            fact=fact(20, 2),
            candidates=[(prior, fact(10, 1))],
            existing_pairs=set(),
        )
        self.assertEqual("medium", suggestions[0]["confidence_tier"])
        response = json.dumps(
            {
                "assessments": [
                    {
                        "source_transaction_id": 2,
                        "target_transaction_id": 1,
                        "relation_type": "refunds",
                        "assessment": "likely",
                        "reason": "商家一致且为部分金额，疑似部分退款",
                    }
                ]
            },
            ensure_ascii=False,
        )

        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=response):
            enriched = enrich_relation_suggestions_with_ai(
                suggestions,
                transaction=current,
                user_id=8,
                expected_data_epoch=3,
            )

        self.assertEqual("medium", enriched[0]["confidence_tier"])
        self.assertEqual("completed", enriched[0]["ai_status"])
        self.assertEqual("likely", enriched[0]["ai_assessment"])


class EconomicFactSummaryTest(unittest.TestCase):
    def test_refund_is_not_income_and_offsets_original_expense(self):
        expense = transaction(
            1,
            direction="expense",
            amount="100.00",
            transaction_date=date(2026, 8, 1),
            category_id=2,
            nature="flexible",
            merchant="某电商",
        )
        refund = transaction(
            2,
            direction="income",
            amount="60.00",
            transaction_date=date(2026, 8, 8),
            category_id=1,
        )
        summary = build_month_summary(
            month="2026-08",
            transactions=[expense, refund],
            category_names={1: "其他收入", 2: "购物"},
            relation_effects={
                2: {
                    "income_remove": Decimal("60.00"),
                    "expense_offset": Decimal("60.00"),
                    "offset_category_id": 2,
                    "offset_category_name": "购物",
                    "offset_nature": "flexible",
                    "offset_merchant": "某电商",
                }
            },
        )

        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("40.00"), summary["expense"])
        self.assertEqual(Decimal("-40.00"), summary["net"])
        self.assertEqual(Decimal("40.00"), summary["expense_merchants"][0]["amount"])

    def test_linked_bank_to_wallet_pair_counts_only_as_transfer(self):
        outgoing = transaction(
            1,
            direction="expense",
            amount="500.00",
            transaction_date=date(2026, 8, 1),
            category_id=2,
        )
        incoming = transaction(
            2,
            direction="income",
            amount="500.00",
            transaction_date=date(2026, 8, 1),
            category_id=1,
        )
        summary = build_month_summary(
            month="2026-08",
            transactions=[outgoing, incoming],
            category_names={1: "其他收入", 2: "其他支出"},
            relation_effects={
                1: {"expense_remove": Decimal("500.00"), "transfer_add": Decimal("500.00")},
                2: {"income_remove": Decimal("500.00")},
            },
        )

        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("0.00"), summary["expense"])
        self.assertEqual(Decimal("500.00"), summary["transfer_amount"])

    def test_ai_answer_rejects_references_not_present_in_confirmed_context(self):
        ledger_transaction = transaction(
            7,
            direction="expense",
            amount="36.00",
            transaction_date=date(2026, 8, 10),
            merchant="面馆",
            category_id=2,
        )
        context, references = build_cashflow_chat_context(
            data_start=date(2026, 3, 1),
            data_end=date(2026, 8, 31),
            transactions=[ledger_transaction],
            category_names={2: "餐饮"},
            fact_types={7: "expense"},
            monthly_summaries=[],
            relations=[],
        )
        model_output = json.dumps(
            {
                "answer": "这笔餐饮支出为 36 元。",
                "referenced_transaction_ids": [7, 999, 7],
                "follow_up_questions": ["本月餐饮一共多少？"],
            },
            ensure_ascii=False,
        )
        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=model_output):
            result = answer_cashflow_question(
                question="这笔钱是什么？",
                history=[],
                context=context,
                reference_by_id=references,
                user_id=1,
                expected_data_epoch=0,
            )

        self.assertEqual("ai", result["mode"])
        self.assertEqual([7], [item["transaction_id"] for item in result["references"]])

    def test_program_summary_is_returned_when_ai_is_unavailable(self):
        context = {
            "monthly_summaries": [
                {"month": "2026-08", "income": "100.00", "expense": "20.00", "net": "80.00"}
            ]
        }
        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=None):
            result = answer_cashflow_question(
                question="本月怎么样？",
                history=[],
                context=context,
                reference_by_id={},
                user_id=1,
                expected_data_epoch=0,
            )

        self.assertEqual("program", result["mode"])
        self.assertIn("AI 服务当前不可用", result["answer"])

    def test_export_contains_only_structured_confirmed_files(self):
        ledger_transaction = transaction(
            7,
            direction="expense",
            amount="36.00",
            transaction_date=date(2026, 8, 10),
            merchant="=危险公式",
            category_id=2,
        )
        ledger_transaction.external_key = "12345678901234567890"
        ledger_transaction.source_type = "import_wechat"
        ledger_transaction.confirmed_at = None
        economic_fact = SimpleNamespace(
            id=70,
            primary_transaction_id=7,
            fact_type="expense",
            title="面馆",
        )
        payslip = SimpleNamespace(
            id=5,
            record_status="superseded",
            supersedes_payslip_id=4,
            pay_month="2026-08",
            pay_date=None,
            agreed_pay_date=None,
            employer_name="示例公司",
            gross_salary=Decimal("100.00"),
            base_salary=None,
            performance=None,
            bonus=None,
            overtime_pay=None,
            allowance=None,
            social_insurance=None,
            housing_fund=None,
            individual_tax=None,
            attendance_deductions=None,
            meal_deductions=None,
            other_deductions=None,
            net_salary=Decimal("100.00"),
            custom_items=[],
            source_type="ocr",
            recognition_confidence=Decimal("0.9000"),
            raw_text="绝不能进入导出的 OCR 原文",
            created_at=None,
        )
        payload = build_cashflow_export_bundle(
            generated_at=datetime(2026, 8, 23, 12, 0, 0),
            business_data_epoch=4,
            transactions=[ledger_transaction],
            category_names={2: "餐饮"},
            facts=[economic_fact],
            relations=[],
            payslips=[payslip],
            material_links=[],
            arrival_links=[],
        )

        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(
                {"manifest.json", "confirmed-transactions.csv", "economic-relations.csv", "payslips.csv"},
                set(archive.namelist()),
            )
            manifest = json.loads(archive.read("manifest.json"))
            all_bytes = b"".join(archive.read(name) for name in archive.namelist())
            transactions_csv = archive.read("confirmed-transactions.csv").decode("utf-8-sig")
            payslips_csv = archive.read("payslips.csv").decode("utf-8-sig")

        self.assertFalse(manifest["contains_original_files"])
        self.assertFalse(manifest["contains_ocr_text_or_slices"])
        self.assertNotIn("绝不能进入导出的 OCR 原文".encode(), all_bytes)
        self.assertIn("'=危险公式", transactions_csv)
        self.assertIn("版本状态,上一版工资条ID", payslips_csv)
        self.assertIn("superseded,4", payslips_csv)


class EconomicRelationPersistenceTest(unittest.TestCase):
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
                FinancialCategory.__table__,
                FinancialTransaction.__table__,
                EconomicFact.__table__,
                EconomicFactAllocation.__table__,
                EconomicFactRelation.__table__,
            ],
        )
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.user = User(username="economic-fact-user", password_hash="test", business_data_epoch=0)
        self.db.add(self.user)
        self.db.flush()
        income_category = FinancialCategory(direction="income", name="其他收入", is_system=True)
        expense_category = FinancialCategory(direction="expense", name="购物", is_system=True)
        self.db.add_all([income_category, expense_category])
        self.db.flush()
        self.expense = FinancialTransaction(
            user_id=self.user.id,
            category_id=expense_category.id,
            direction="expense",
            amount=Decimal("100.00"),
            transaction_date=date(2026, 8, 1),
            merchant="某电商",
            nature="flexible",
            source_type="manual",
            status="confirmed",
        )
        self.refund = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("60.00"),
            transaction_date=date(2026, 8, 8),
            merchant="某电商",
            description="部分退款",
            source_type="manual",
            status="confirmed",
        )
        self.db.add_all([self.expense, self.refund])
        self.db.flush()
        sync_transaction_fact(self.db, transaction=self.expense, user_id=self.user.id)
        sync_transaction_fact(self.db, transaction=self.refund, user_id=self.user.id)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_user_confirmation_changes_summary_and_undo_restores_it(self):
        relation = confirm_economic_relation(
            EconomicRelationConfirmRequest(
                source_transaction_id=self.refund.id,
                target_transaction_id=self.expense.id,
                relation_type="refunds",
                allocated_amount=Decimal("60.00"),
                reasons=["金额和商户相符"],
                detection_method="program",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual("refunds", relation.relation_type)
        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("40.00"), summary["expense"])

        reversed_relation = reverse_economic_relation(relation.id, user=self.user, db=self.db)
        restored = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual("reversed", reversed_relation.status)
        self.assertEqual(Decimal("60.00"), restored["income"])
        self.assertEqual(Decimal("100.00"), restored["expense"])

    def test_cashflow_question_route_uses_only_confirmed_range(self):
        pending = FinancialTransaction(
            user_id=self.user.id,
            category_id=self.expense.category_id,
            direction="expense",
            amount=Decimal("999.00"),
            transaction_date=date(2026, 8, 12),
            source_type="manual",
            status="pending",
        )
        self.db.add(pending)
        self.db.commit()
        captured = {}

        def fake_answer(**kwargs):
            captured.update(kwargs["context"])
            return {
                "answer": "按已确认账本回答",
                "mode": "program",
                "references": [],
                "follow_up_questions": [],
            }

        with patch("app.api.routes.cashflow.answer_cashflow_question", side_effect=fake_answer):
            response = ask_confirmed_cashflow(
                CashflowAskRequest(question="最近收支如何？", month="2026-08"),
                user=self.user,
                db=self.db,
            )

        self.assertEqual(2, response.transaction_count)
        self.assertEqual(2, captured["scope"]["confirmed_transaction_count"])
        self.assertNotIn("999.00", json.dumps(captured, ensure_ascii=False, default=str))


if __name__ == "__main__":
    unittest.main()
