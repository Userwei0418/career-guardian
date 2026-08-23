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
    confirm_fact_evidence_merge,
    confirm_economic_relation,
    get_cashflow_conversation,
    get_summary,
    list_cashflow_conversations,
    list_transaction_page,
    reverse_fact_evidence_merge,
    reverse_economic_relation,
)
from app.db.session import Base
from app.models.cashflow import (
    CashflowConversation,
    CashflowConversationTurn,
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRelation,
    EconomicFactRelationRevision,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialTransaction,
)
from app.models.user import User
from app.schemas.cashflow import (
    CashflowAskRequest,
    EconomicFactMergeConfirmRequest,
    EconomicRelationConfirmRequest,
)
from app.services.cashflow_chat_service import (
    answer_cashflow_question,
    build_cashflow_chat_context,
)
from app.services.cashflow_export_service import (
    build_cashflow_export_bundle,
    build_cashflow_export_workbook,
)
from app.services.cashflow_service import build_month_summary
from app.services.economic_fact_service import (
    build_fact_merge_suggestions,
    build_relation_suggestions,
    enrich_fact_merge_suggestions_with_ai,
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
    def test_same_amount_across_sources_is_suggested_as_one_fact_but_not_merged(self):
        bank = transaction(
            20,
            direction="income",
            amount="8800.00",
            transaction_date=date(2026, 8, 5),
            merchant="某科技公司",
            description="工资到账",
        )
        bank.source_type = "import_bank"
        wallet = transaction(
            21,
            direction="income",
            amount="8800.00",
            transaction_date=date(2026, 8, 5),
            merchant="某科技公司",
            description="工资转入",
        )
        wallet.source_type = "import_wechat"
        fact_a = SimpleNamespace(id=120, primary_transaction_id=20)
        fact_b = SimpleNamespace(id=121, primary_transaction_id=21)

        suggestions = build_fact_merge_suggestions(
            transaction=bank,
            fact=fact_a,
            candidates=[(wallet, fact_b)],
        )

        self.assertEqual(1, len(suggestions))
        self.assertEqual(21, suggestions[0]["evidence_transaction_id"])
        self.assertEqual("high", suggestions[0]["confidence_tier"])
        self.assertIn("不同账单来源", "".join(suggestions[0]["reasons"]))

    def test_ambiguous_same_fact_candidate_uses_ai_but_stays_human_confirmed(self):
        primary = transaction(
            30,
            direction="income",
            amount="1000.00",
            transaction_date=date(2026, 8, 5),
            merchant="工资",
        )
        primary.source_type = "import_bank"
        evidence = transaction(
            31,
            direction="income",
            amount="1000.00",
            transaction_date=date(2026, 8, 7),
            merchant="转入",
        )
        evidence.source_type = "import_bank"
        suggestions = build_fact_merge_suggestions(
            transaction=primary,
            fact=SimpleNamespace(id=130, primary_transaction_id=30),
            candidates=[(evidence, SimpleNamespace(id=131, primary_transaction_id=31))],
        )
        response = json.dumps(
            {
                "assessments": [
                    {
                        "primary_transaction_id": 30,
                        "evidence_transaction_id": 31,
                        "assessment": "uncertain",
                        "reason": "摘要不足以证明是账户间重复记录",
                    }
                ]
            },
            ensure_ascii=False,
        )

        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=response):
            enriched = enrich_fact_merge_suggestions_with_ai(
                suggestions,
                transaction=primary,
                user_id=8,
                expected_data_epoch=3,
            )

        self.assertEqual("medium", enriched[0]["confidence_tier"])
        self.assertEqual("completed", enriched[0]["ai_status"])
        self.assertEqual("uncertain", enriched[0]["ai_assessment"])

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
            payslip_guardians=[
                {
                    "payslip_id": 5,
                    "pay_month": "2026-08",
                    "employer_name": "示例公司",
                    "gross_salary": "10000.00",
                    "net_salary": "8600.00",
                    "attention_count": 1,
                    "unverified_count": 2,
                    "checks": [],
                    "hr_questions": [],
                }
            ],
        )
        model_output = json.dumps(
            {
                "answer": "这笔餐饮支出为 36 元。",
                "referenced_transaction_ids": [7, 999, 7],
                "referenced_payslip_ids": [5, 999, 5],
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
        self.assertEqual([5], [item["payslip_id"] for item in result["payslip_references"]])

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

    def test_program_fallback_can_report_structured_payslip_without_transactions(self):
        context = {
            "monthly_summaries": [],
            "active_payslip_guardians": [
                {
                    "payslip_id": 5,
                    "pay_month": "2026-08",
                    "net_salary": "8600.00",
                    "attention_count": 1,
                    "unverified_count": 2,
                }
            ],
        }
        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=None):
            result = answer_cashflow_question(
                question="我的工资还有什么没核清？",
                history=[],
                context=context,
                reference_by_id={},
                user_id=1,
                expected_data_epoch=0,
            )

        self.assertEqual("program", result["mode"])
        self.assertIn("实发为 ¥8600.00", result["answer"])
        self.assertIn("2 项尚未核清", result["answer"])

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
            occurred_date=date(2026, 8, 10),
            amount=Decimal("36.00"),
            currency="CNY",
            created_at=datetime(2026, 8, 10, 12, 0, 0),
            updated_at=datetime(2026, 8, 10, 12, 5, 0),
        )
        economic_allocation = SimpleNamespace(
            fact_id=70,
            transaction_id=7,
            role="primary",
            status="confirmed",
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
            ledger_revision=12,
            transactions=[ledger_transaction],
            category_names={2: "餐饮"},
            facts=[economic_fact],
            allocations=[economic_allocation],
            relations=[],
            payslips=[payslip],
            material_links=[],
            arrival_links=[],
        )

        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(
                {
                    "manifest.json",
                    "cashflow-guardian.xlsx",
                    "confirmed-transactions.csv",
                    "economic-facts.csv",
                    "economic-relations.csv",
                    "payslips.csv",
                },
                set(archive.namelist()),
            )
            manifest = json.loads(archive.read("manifest.json"))
            all_bytes = b"".join(archive.read(name) for name in archive.namelist())
            transactions_csv = archive.read("confirmed-transactions.csv").decode("utf-8-sig")
            facts_csv = archive.read("economic-facts.csv").decode("utf-8-sig")
            payslips_csv = archive.read("payslips.csv").decode("utf-8-sig")
            workbook_payload = archive.read("cashflow-guardian.xlsx")

        self.assertFalse(manifest["contains_original_files"])
        self.assertFalse(manifest["contains_ocr_text_or_slices"])
        self.assertEqual(12, manifest["ledger_revision"])
        self.assertEqual("UTC", manifest["timezone"])
        self.assertEqual(1, manifest["counts"]["economic_facts"])
        self.assertNotIn("绝不能进入导出的 OCR 原文".encode(), all_bytes)
        self.assertIn("'=危险公式", transactions_csv)
        self.assertIn("经济事实类型,事实角色,是否计入收支", transactions_csv)
        self.assertIn("面馆", facts_csv)
        self.assertIn("版本状态,上一版工资条ID", payslips_csv)
        self.assertIn("superseded,4", payslips_csv)

        with ZipFile(BytesIO(workbook_payload)) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
            ledger_xml = workbook.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertEqual(5, len([name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet")]))
            self.assertIn('name="可信账本"', workbook_xml)
            self.assertIn('name="经济事实"', workbook_xml)
            self.assertIn("=危险公式", ledger_xml)
            self.assertNotIn("<f>", ledger_xml)
            self.assertIn('<c r="D4" s="3"><v>36.00</v></c>', ledger_xml)
            self.assertIn('<c r="K4" s="8" t="inlineStr">', ledger_xml)

        direct_workbook = build_cashflow_export_workbook(
            generated_at=datetime(2026, 8, 23, 12, 0, 0),
            business_data_epoch=4,
            ledger_revision=12,
            transactions=[ledger_transaction],
            category_names={2: "餐饮"},
            facts=[economic_fact],
            allocations=[economic_allocation],
            relations=[],
            payslips=[payslip],
            material_links=[],
            arrival_links=[],
        )
        with ZipFile(BytesIO(direct_workbook)) as workbook:
            self.assertIn("xl/worksheets/sheet5.xml", workbook.namelist())


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
                EconomicFactRelationRevision.__table__,
                FinancialLedgerRevisionEvent.__table__,
                CashflowConversation.__table__,
                CashflowConversationTurn.__table__,
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

    def test_same_fact_evidence_merge_stops_double_counting_and_can_be_undone(self):
        income_category = self.db.query(FinancialCategory).filter(
            FinancialCategory.direction == "income"
        ).one()
        bank = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("8800.00"),
            transaction_date=date(2026, 8, 5),
            merchant="某科技公司",
            description="工资到账",
            source_type="import_bank",
            status="confirmed",
        )
        wallet = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("8800.00"),
            transaction_date=date(2026, 8, 5),
            merchant="某科技公司",
            description="工资转入微信零钱",
            source_type="import_wechat",
            status="confirmed",
        )
        self.db.add_all([bank, wallet])
        self.db.flush()
        bank_fact = sync_transaction_fact(self.db, transaction=bank, user_id=self.user.id)
        wallet_fact = sync_transaction_fact(self.db, transaction=wallet, user_id=self.user.id)
        self.db.commit()

        before = get_summary(month="2026-08", user=self.user, db=self.db)
        membership = confirm_fact_evidence_merge(
            EconomicFactMergeConfirmRequest(
                primary_transaction_id=bank.id,
                evidence_transaction_id=wallet.id,
                reasons=["金额、日期和发薪单位一致"],
                detection_method="program",
            ),
            user=self.user,
            db=self.db,
        )
        after = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual(Decimal("17660.00"), before["income"])
        self.assertEqual(Decimal("8860.00"), after["income"])
        self.assertEqual(3, after["confirmed_count"])
        self.assertEqual(bank_fact.id, membership.fact.id)
        self.assertEqual(["primary", "corroborating"], [item.role for item in membership.members])
        self.assertEqual("superseded", self.db.get(EconomicFact, wallet_fact.id).status)
        page = list_transaction_page(
            month="2026-08",
            direction=None,
            transaction_status="confirmed",
            category_id=None,
            nature=None,
            keyword=None,
            sort="date_desc",
            limit=50,
            offset=0,
            user=self.user,
            db=self.db,
        )
        page_by_id = {item.id: item for item in page["items"]}
        self.assertTrue(page_by_id[bank.id].counts_as_cashflow)
        self.assertEqual("primary", page_by_id[bank.id].economic_fact_role)
        self.assertFalse(page_by_id[wallet.id].counts_as_cashflow)
        self.assertEqual("corroborating", page_by_id[wallet.id].economic_fact_role)

        restored_membership = reverse_fact_evidence_merge(
            bank_fact.id,
            wallet.id,
            user=self.user,
            db=self.db,
        )
        restored = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual(1, len(restored_membership.members))
        self.assertEqual(Decimal("17660.00"), restored["income"])
        self.assertEqual(4, restored["confirmed_count"])
        self.assertEqual("confirmed", self.db.get(EconomicFact, wallet_fact.id).status)

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
            captured["history"] = kwargs["history"]
            return {
                "answer": "按已确认账本回答",
                "mode": "program",
                "references": [],
                "follow_up_questions": [],
            }

        with patch("app.api.routes.cashflow._payslip_guardians_for_chat", return_value=[]), patch(
            "app.api.routes.cashflow.answer_cashflow_question",
            side_effect=fake_answer,
        ):
            response = ask_confirmed_cashflow(
                CashflowAskRequest(question="最近收支如何？", month="2026-08"),
                user=self.user,
                db=self.db,
            )

        self.assertEqual(2, response.transaction_count)
        self.assertGreater(response.conversation_id, 0)
        self.assertGreater(response.turn_id, 0)
        self.assertEqual(2, captured["scope"]["confirmed_transaction_count"])
        self.assertNotIn("999.00", json.dumps(captured, ensure_ascii=False, default=str))

        with patch("app.api.routes.cashflow._payslip_guardians_for_chat", return_value=[]), patch(
            "app.api.routes.cashflow.answer_cashflow_question",
            side_effect=fake_answer,
        ):
            follow_up = ask_confirmed_cashflow(
                CashflowAskRequest(
                    question="再说说结余",
                    month="2026-08",
                    conversation_id=response.conversation_id,
                ),
                user=self.user,
                db=self.db,
            )

        self.assertEqual(response.conversation_id, follow_up.conversation_id)
        self.assertEqual("user", captured["history"][0]["role"])
        self.assertEqual("最近收支如何？", captured["history"][0]["content"])
        summaries = list_cashflow_conversations(month="2026-08", limit=20, user=self.user, db=self.db)
        self.assertEqual(1, len(summaries))
        self.assertEqual(2, summaries[0].turn_count)
        detail = get_cashflow_conversation(response.conversation_id, user=self.user, db=self.db)
        self.assertEqual(2, len(detail.turns))
        self.assertEqual(response.ledger_revision, detail.turns[0].response.ledger_revision)


if __name__ == "__main__":
    unittest.main()
