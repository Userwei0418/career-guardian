from __future__ import annotations

import csv
import json
import unittest
from io import BytesIO, StringIO
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.cashflow import (
    ask_confirmed_cashflow,
    confirm_fact_evidence_batch_merge,
    confirm_fact_evidence_merge,
    confirm_transaction_fact_split,
    confirm_economic_relation,
    export_confirmed_cashflow,
    get_relation_suggestions,
    get_cashflow_conversation,
    get_summary,
    list_cashflow_conversations,
    list_transaction_relations,
    list_transaction_page,
    reverse_fact_evidence_merge,
    reverse_transaction_fact_split,
    reverse_economic_relation,
)
from app.db.session import Base
from app.models.career_case import CareerCase
from app.models.career_event import CareerEvent  # Registers Payslip.career_event_id metadata for isolated DDL.
from app.models.contract import Contract  # Registers Payslip agreed-date provenance metadata for isolated DDL.
from app.models.cashflow import (
    CashflowConversation,
    CashflowConversationTurn,
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRevision,
    EconomicFactRelation,
    EconomicFactRelationRevision,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialTransaction,
)
from app.models.user import User
from app.models.offer import Offer  # Registers Payslip.linked_offer_id metadata for isolated DDL.
from app.models.payslip import Payslip, PayslipArrivalLink
from app.schemas.cashflow import (
    CashflowAskRequest,
    EconomicFactMergeBatchConfirmRequest,
    EconomicFactMergeBatchItem,
    EconomicFactMergeConfirmRequest,
    EconomicFactSplitComponentInput,
    EconomicFactSplitConfirmRequest,
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
    get_transaction_fact,
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
            category_id=2,
            nature="flexible",
            description="午餐",
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
            pay_month="2026-09",
            pay_date=None,
            agreed_pay_date=date(2026, 10, 8),
            agreed_pay_date_source_type="material_suggestion",
            agreed_pay_date_source_contract_id=22,
            agreed_pay_date_schedule="次月1日",
            agreed_pay_date_adjustment="defer",
            agreed_pay_date_calendar_version="cn-workday-2026-gbfmd-2025-7",
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
        material_link = SimpleNamespace(
            payslip_id=5,
            offer_id=None,
            contract_id=22,
            application_status="preferred",
            priority_rank=10,
            user_note="工资日期以补充协议为准",
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
            material_links=[material_link],
            arrival_links=[],
            scope_description="当前账户中符合导出筛选条件的已确认结构化数据",
            filters={"month": "2026-08", "category_id": 2},
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
        self.assertEqual(
            "当前账户中符合导出筛选条件的已确认结构化数据",
            manifest["scope"],
        )
        self.assertEqual({"month": "2026-08", "category_id": 2}, manifest["filters"])
        self.assertEqual(1, manifest["counts"]["economic_facts"])
        self.assertNotIn("绝不能进入导出的 OCR 原文".encode(), all_bytes)
        self.assertIn("'=危险公式", transactions_csv)
        self.assertIn("经济事实类型,事实角色,拆分项数,拆分明细,是否计入收支,分配至其他事实,本笔计入金额", transactions_csv)
        self.assertIn("面馆", facts_csv)
        self.assertIn("金额,币种,分类,支出性质,说明,主流水ID", facts_csv)
        self.assertIn("版本状态,上一版工资条ID", payslips_csv)
        self.assertIn("superseded,4", payslips_csv)
        self.assertIn("约定日期来源,约定日期来源合同ID,合同发薪口径,节假日调整选择,工作日日历版本", payslips_csv)
        self.assertIn("2026-10-08,material_suggestion,22,次月1日,defer,cn-workday-2026-gbfmd-2025-7", payslips_csv)
        payslip_export_row = next(csv.DictReader(StringIO(payslips_csv)))
        contract_preferences = json.loads(payslip_export_row["关联合同适用口径"])
        self.assertEqual(22, contract_preferences[0]["material_id"])
        self.assertEqual("preferred", contract_preferences[0]["application_status"])
        self.assertEqual("工资日期以补充协议为准", contract_preferences[0]["user_note"])

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
            material_links=[material_link],
            arrival_links=[],
        )
        with ZipFile(BytesIO(direct_workbook)) as workbook:
            self.assertIn("xl/worksheets/sheet5.xml", workbook.namelist())

    def test_export_keeps_mixed_transaction_total_and_emits_component_classification(self):
        mixed = transaction(
            8,
            direction="expense",
            amount="100.00",
            transaction_date=date(2026, 8, 11),
            merchant="聚合支付",
            category_id=9,
        )
        mixed.external_key = "mixed-8"
        mixed.source_type = "import_wechat"
        mixed.confirmed_at = datetime(2026, 8, 11, 12, 0, 0)
        refund = transaction(
            9,
            direction="income",
            amount="20.00",
            transaction_date=date(2026, 8, 12),
            merchant="部分退款",
            category_id=4,
        )
        refund.external_key = "refund-9"
        refund.source_type = "import_wechat"
        refund.confirmed_at = datetime(2026, 8, 12, 12, 0, 0)
        component_facts = [
            SimpleNamespace(
                id=81,
                primary_transaction_id=None,
                fact_type="expense",
                title="工作餐",
                occurred_date=date(2026, 8, 11),
                amount=Decimal("30.00"),
                currency="CNY",
                category_id=2,
                nature="flexible",
                description="午餐",
                created_at=datetime(2026, 8, 11, 12, 1, 0),
                updated_at=datetime(2026, 8, 11, 12, 1, 0),
            ),
            SimpleNamespace(
                id=82,
                primary_transaction_id=None,
                fact_type="expense",
                title="打车",
                occurred_date=date(2026, 8, 11),
                amount=Decimal("70.00"),
                currency="CNY",
                category_id=3,
                nature="reimbursable",
                description="出行",
                created_at=datetime(2026, 8, 11, 12, 1, 0),
                updated_at=datetime(2026, 8, 11, 12, 1, 0),
            ),
        ]
        allocations = [
            SimpleNamespace(
                fact_id=fact_item.id,
                transaction_id=8,
                role="split_component",
                allocated_amount=fact_item.amount,
                status="confirmed",
            )
            for fact_item in component_facts
        ]
        refund_fact = SimpleNamespace(
            id=90,
            primary_transaction_id=9,
            fact_type="refund",
            title="部分退款",
            occurred_date=date(2026, 8, 12),
            amount=Decimal("20.00"),
            currency="CNY",
            category_id=4,
            nature=None,
            description="退工作餐",
            created_at=datetime(2026, 8, 12, 12, 1, 0),
            updated_at=datetime(2026, 8, 12, 12, 1, 0),
        )
        allocations.append(SimpleNamespace(
            fact_id=refund_fact.id,
            transaction_id=refund.id,
            role="primary",
            allocated_amount=refund_fact.amount,
            status="confirmed",
        ))
        relation = SimpleNamespace(
            id=901,
            source_fact_id=refund_fact.id,
            target_fact_id=component_facts[0].id,
            relation_type="refunds",
            allocated_amount=Decimal("20.00"),
            detection_method="manual",
            reasons=["用户确认退款对应工作餐"],
            confirmed_at=datetime(2026, 8, 12, 12, 2, 0),
        )

        payload = build_cashflow_export_bundle(
            generated_at=datetime(2026, 8, 23, 12, 0, 0),
            business_data_epoch=4,
            ledger_revision=13,
            transactions=[mixed, refund],
            category_names={2: "餐饮", 3: "出行", 4: "退款", 9: "综合支出"},
            facts=[*component_facts, refund_fact],
            allocations=allocations,
            relations=[relation],
            payslips=[],
            material_links=[],
            arrival_links=[],
        )

        with ZipFile(BytesIO(payload)) as archive:
            transactions_csv = archive.read("confirmed-transactions.csv").decode("utf-8-sig")
            facts_csv = archive.read("economic-facts.csv").decode("utf-8-sig")
            relations_csv = archive.read("economic-relations.csv").decode("utf-8-sig")

        self.assertIn("已拆分（见经济事实）", transactions_csv)
        self.assertIn("decomposed,2,餐饮:30.00:工作餐;出行:70.00:打车,是,0.00,100.00", transactions_csv)
        self.assertIn("工作餐,2026-08-11,30.00,CNY,餐饮,flexible,午餐", facts_csv)
        self.assertIn("打车,2026-08-11,70.00,CNY,出行,reimbursable,出行", facts_csv)
        self.assertIn("901,refunds,20.00,9,部分退款,8,工作餐", relations_csv)


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
                CareerCase.__table__,
                FinancialCategory.__table__,
                FinancialTransaction.__table__,
                EconomicFact.__table__,
                EconomicFactAllocation.__table__,
                EconomicFactRevision.__table__,
                EconomicFactRelation.__table__,
                EconomicFactRelationRevision.__table__,
                FinancialLedgerRevisionEvent.__table__,
                CashflowConversation.__table__,
                CashflowConversationTurn.__table__,
                Payslip.__table__,
                PayslipArrivalLink.__table__,
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
                allocated_amount=Decimal("8800.00"),
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
        merge_revisions = self.db.query(EconomicFactRevision).filter(
            EconomicFactRevision.fact_id.in_([bank_fact.id, wallet_fact.id])
        ).all()
        self.assertEqual(2, len(merge_revisions))
        self.assertEqual(1, len({item.ledger_revision for item in merge_revisions}))
        self.assertEqual({"merge_evidence"}, {item.operation for item in merge_revisions})

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
        latest_revisions = self.db.query(EconomicFactRevision).filter(
            EconomicFactRevision.fact_id.in_([bank_fact.id, wallet_fact.id])
        ).all()
        self.assertEqual(4, len(latest_revisions))
        self.assertEqual(
            {"merge_evidence", "unmerge_evidence", "restore_evidence_remainder"},
            {item.operation for item in latest_revisions},
        )

    def test_partial_fact_evidence_allocation_preserves_the_unmatched_remainder(self):
        income_category = self.db.query(FinancialCategory).filter(
            FinancialCategory.direction == "income"
        ).one()
        salary = FinancialTransaction(
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
        mixed_deposit = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("10000.00"),
            transaction_date=date(2026, 8, 5),
            merchant="微信零钱",
            description="工资及其他款项转入",
            source_type="import_wechat",
            status="confirmed",
        )
        self.db.add_all([salary, mixed_deposit])
        self.db.flush()
        salary_fact = sync_transaction_fact(self.db, transaction=salary, user_id=self.user.id)
        remainder_fact = sync_transaction_fact(self.db, transaction=mixed_deposit, user_id=self.user.id)
        self.db.commit()

        membership = confirm_fact_evidence_merge(
            EconomicFactMergeConfirmRequest(
                primary_transaction_id=salary.id,
                evidence_transaction_id=mixed_deposit.id,
                allocated_amount=Decimal("8800.00"),
                reasons=["其中 8800 元与工资到账相符"],
                detection_method="manual",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)
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

        self.assertEqual(Decimal("10060.00"), summary["income"])
        self.assertEqual(4, summary["confirmed_count"])
        self.assertEqual(Decimal("1200.00"), self.db.get(EconomicFact, remainder_fact.id).amount)
        self.assertEqual("confirmed", self.db.get(EconomicFact, remainder_fact.id).status)
        self.assertEqual(Decimal("8800.00"), membership.members[1].allocated_amount)
        self.assertEqual("split", page_by_id[mixed_deposit.id].economic_fact_role)
        self.assertEqual(Decimal("8800.00"), page_by_id[mixed_deposit.id].allocated_to_other_facts)
        self.assertEqual(Decimal("1200.00"), page_by_id[mixed_deposit.id].effective_cashflow_amount)
        captured = {}

        def fake_answer(**kwargs):
            captured.update(kwargs["context"])
            return {
                "answer": "按剩余有效金额回答",
                "mode": "program",
                "references": [],
                "follow_up_questions": [],
            }

        with patch("app.api.routes.cashflow._payslip_guardians_for_chat", return_value=[]), patch(
            "app.api.routes.cashflow.answer_cashflow_question",
            side_effect=fake_answer,
        ):
            response = ask_confirmed_cashflow(
                CashflowAskRequest(question="本月收入是多少？", month="2026-08"),
                user=self.user,
                db=self.db,
            )
        detail_by_id = {
            item["transaction_id"]: item
            for item in captured["recent_confirmed_transactions"]
        }
        self.assertEqual(4, response.transaction_count)
        self.assertEqual("1200.00", detail_by_id[mixed_deposit.id]["amount"])

        reverse_fact_evidence_merge(
            salary_fact.id,
            mixed_deposit.id,
            user=self.user,
            db=self.db,
        )
        restored = get_summary(month="2026-08", user=self.user, db=self.db)
        self.assertEqual(Decimal("18860.00"), restored["income"])
        self.assertEqual(Decimal("10000.00"), self.db.get(EconomicFact, remainder_fact.id).amount)

    def test_batch_fact_evidence_merge_is_one_atomic_ledger_change(self):
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
        wallet_exact = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("8800.00"),
            transaction_date=date(2026, 8, 5),
            merchant="微信零钱",
            description="工资转入",
            source_type="import_wechat",
            status="confirmed",
        )
        wallet_mixed = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("10000.00"),
            transaction_date=date(2026, 8, 5),
            merchant="支付宝余额",
            description="工资及其他款项",
            source_type="import_alipay",
            status="confirmed",
        )
        self.db.add_all([bank, wallet_exact, wallet_mixed])
        self.db.flush()
        bank_fact = sync_transaction_fact(self.db, transaction=bank, user_id=self.user.id)
        exact_fact = sync_transaction_fact(self.db, transaction=wallet_exact, user_id=self.user.id)
        mixed_fact = sync_transaction_fact(self.db, transaction=wallet_mixed, user_id=self.user.id)
        self.db.commit()
        revision_before = self.user.financial_ledger_revision

        membership = confirm_fact_evidence_batch_merge(
            EconomicFactMergeBatchConfirmRequest(
                primary_transaction_id=bank.id,
                allocations=[
                    EconomicFactMergeBatchItem(
                        evidence_transaction_id=wallet_exact.id,
                        allocated_amount=Decimal("8800.00"),
                        reasons=["金额、日期和工资摘要一致"],
                        detection_method="program",
                    ),
                    EconomicFactMergeBatchItem(
                        evidence_transaction_id=wallet_mixed.id,
                        allocated_amount=Decimal("8800.00"),
                        reasons=["仅工资部分属于同一事实"],
                        detection_method="manual",
                    ),
                ],
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)
        batch_events = self.db.query(FinancialLedgerRevisionEvent).filter(
            FinancialLedgerRevisionEvent.user_id == self.user.id,
            FinancialLedgerRevisionEvent.event_type == "fact_evidence_batch_merge",
        ).all()

        self.assertEqual(bank_fact.id, membership.fact.id)
        self.assertEqual(3, len(membership.members))
        self.assertEqual(Decimal("10060.00"), summary["income"])
        self.assertEqual(4, summary["confirmed_count"])
        self.assertEqual("superseded", self.db.get(EconomicFact, exact_fact.id).status)
        self.assertEqual(Decimal("1200.00"), self.db.get(EconomicFact, mixed_fact.id).amount)
        self.assertEqual(1, len(batch_events))
        self.assertEqual(revision_before + 1, self.user.financial_ledger_revision)
        fact_revisions = self.db.query(EconomicFactRevision).filter(
            EconomicFactRevision.ledger_revision == self.user.financial_ledger_revision
        ).all()
        self.assertEqual(3, len(fact_revisions))
        self.assertEqual({"batch_merge_evidence"}, {item.operation for item in fact_revisions})

    def test_mixed_expense_can_be_split_into_confirmed_facts_and_undone(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        transport = FinancialCategory(direction="expense", name="出行", is_system=True)
        self.db.add_all([dining, transport])
        self.db.commit()

        split = confirm_transaction_fact_split(
            self.expense.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("30.00"),
                        category_id=dining.id,
                        title="工作餐",
                        nature="flexible",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("70.00"),
                        category_id=transport.id,
                        title="打车",
                        description="同一笔聚合扣款中的出行部分",
                        nature="reimbursable",
                    ),
                ],
                reason="核对聚合账单后拆分",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)
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

        self.assertEqual(Decimal("100.00"), split.allocated_amount)
        self.assertEqual(Decimal("0.00"), split.remaining_amount)
        self.assertEqual(2, len(split.components))
        self.assertEqual(Decimal("100.00"), summary["expense"])
        self.assertEqual(3, summary["confirmed_count"])
        self.assertEqual(
            {"餐饮": Decimal("30.00"), "出行": Decimal("70.00")},
            {item["category_name"]: item["amount"] for item in summary["expense_categories"]},
        )
        self.assertEqual("decomposed", page_by_id[self.expense.id].economic_fact_role)
        self.assertEqual(2, page_by_id[self.expense.id].split_component_count)
        original_fact = self.db.query(EconomicFact).filter(
            EconomicFact.primary_transaction_id == self.expense.id
        ).one()
        self.assertEqual("superseded", original_fact.status)
        self.assertEqual(3, self.db.query(EconomicFactRevision).filter(
            EconomicFactRevision.ledger_revision == split.ledger_revision
        ).count())

        restored = reverse_transaction_fact_split(
            self.expense.id,
            user=self.user,
            db=self.db,
        )
        restored_summary = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual(0, len(restored.components))
        self.assertEqual(Decimal("100.00"), restored.remaining_amount)
        self.assertEqual(2, restored_summary["confirmed_count"])
        self.assertEqual(
            {"购物": Decimal("100.00")},
            {item["category_name"]: item["amount"] for item in restored_summary["expense_categories"]},
        )
        self.assertEqual("confirmed", self.db.get(EconomicFact, original_fact.id).status)

    def test_transaction_page_filters_follow_confirmed_split_facts(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        transport = FinancialCategory(direction="expense", name="出行", is_system=True)
        self.db.add_all([dining, transport])
        self.db.commit()

        confirm_transaction_fact_split(
            self.expense.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("30.00"),
                        category_id=dining.id,
                        title="工作餐",
                        nature="flexible",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("70.00"),
                        category_id=transport.id,
                        title="打车",
                        description="晚高峰出行",
                        nature="reimbursable",
                    ),
                ],
                reason="核对聚合账单后拆分",
            ),
            user=self.user,
            db=self.db,
        )

        def page(**filters):
            return list_transaction_page(
                transaction_id=filters.get("transaction_id"),
                month="2026-08",
                direction=filters.get("direction"),
                transaction_status="confirmed",
                category_id=filters.get("category_id"),
                nature=filters.get("nature"),
                keyword=filters.get("keyword"),
                merchant_name=filters.get("merchant_name"),
                source_type=filters.get("source_type"),
                start_date=filters.get("start_date"),
                end_date=filters.get("end_date"),
                sort="date_desc",
                limit=50,
                offset=0,
                user=self.user,
                db=self.db,
            )

        self.assertEqual([self.expense.id], [item.id for item in page(category_id=dining.id)["items"]])
        self.assertEqual([self.expense.id], [item.id for item in page(transaction_id=self.expense.id)["items"]])
        self.assertEqual([], page(transaction_id=self.refund.id, direction="expense")["items"])
        self.assertEqual([self.expense.id], [item.id for item in page(nature="reimbursable")["items"]])
        self.assertEqual([self.expense.id], [item.id for item in page(keyword="晚高峰")["items"]])
        self.assertEqual([self.expense.id], [item.id for item in page(merchant_name="打车")["items"]])
        self.assertEqual(
            [self.expense.id],
            [item.id for item in page(direction="expense", source_type="manual")["items"]],
        )
        self.assertEqual([], page(category_id=self.expense.category_id)["items"])
        self.assertEqual([], page(direction="expense", start_date=date(2026, 8, 2))["items"])

        with patch(
            "app.api.routes.cashflow.build_cashflow_export_bundle",
            return_value=b"filtered-export",
        ) as build_export:
            export_confirmed_cashflow(
                export_format="bundle",
                transaction_id=self.expense.id,
                month="2026-08",
                direction="expense",
                category_id=dining.id,
                nature=None,
                keyword=None,
                merchant_name=None,
                source_type=None,
                start_date=None,
                end_date=None,
                user=self.user,
                db=self.db,
            )
        export_args = build_export.call_args.kwargs
        self.assertEqual([self.expense.id], [item.id for item in export_args["transactions"]])
        self.assertEqual(
            {dining.id, transport.id},
            {item.category_id for item in export_args["facts"]},
        )
        self.assertEqual(
            {"transaction_id": self.expense.id, "month": "2026-08", "direction": "expense", "category_id": dining.id},
            export_args["filters"],
        )

        with self.assertRaises(HTTPException) as invalid_range:
            page(start_date=date(2026, 8, 9), end_date=date(2026, 8, 1))
        self.assertEqual(400, invalid_range.exception.status_code)

    def test_split_requires_exact_amount_conservation(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        self.db.add(dining)
        self.db.commit()

        with self.assertRaises(HTTPException) as caught:
            confirm_transaction_fact_split(
                self.expense.id,
                EconomicFactSplitConfirmRequest(
                    components=[
                        EconomicFactSplitComponentInput(
                            amount=Decimal("30.00"),
                            category_id=dining.id,
                            title="工作餐",
                            nature="flexible",
                        ),
                        EconomicFactSplitComponentInput(
                            amount=Decimal("60.00"),
                            category_id=dining.id,
                            title="其他",
                            nature="other",
                        ),
                    ],
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, caught.exception.status_code)
        self.assertIn("当前为 90.00 元", caught.exception.detail)
        self.assertEqual("confirmed", self.db.query(EconomicFact).filter(
            EconomicFact.primary_transaction_id == self.expense.id
        ).one().status)

    def test_split_component_can_receive_partial_refund_and_undo_restores_only_that_component(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        transport = FinancialCategory(direction="expense", name="出行", is_system=True)
        self.db.add_all([dining, transport])
        self.db.commit()
        split = confirm_transaction_fact_split(
            self.expense.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("30.00"),
                        category_id=dining.id,
                        title="工作餐",
                        nature="flexible",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("70.00"),
                        category_id=transport.id,
                        title="打车",
                        nature="reimbursable",
                    ),
                ],
                reason="测试拆分事实参与关系",
            ),
            user=self.user,
            db=self.db,
        )
        refund_fact = get_transaction_fact(
            self.db,
            transaction_id=self.refund.id,
            user_id=self.user.id,
        )
        dining_fact_id = split.components[0].fact_id

        with patch("app.services.payslip_intake_service._call_payslip_llm", return_value=None), patch(
            "app.api.routes.cashflow._fact_payslip_evidence",
            return_value=[],
        ):
            workspace = get_relation_suggestions(
                self.refund.id,
                user=self.user,
                db=self.db,
            )
        self.assertEqual(
            {item.fact_id for item in split.components},
            {item.target_fact_id for item in workspace.suggestions},
        )

        relation = confirm_economic_relation(
            EconomicRelationConfirmRequest(
                source_transaction_id=self.refund.id,
                target_transaction_id=self.expense.id,
                source_fact_id=refund_fact.id,
                target_fact_id=dining_fact_id,
                relation_type="refunds",
                allocated_amount=Decimal("20.00"),
                reasons=["用户确认只退工作餐部分"],
                detection_method="manual",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)
        relations = list_transaction_relations(
            self.expense.id,
            user=self.user,
            db=self.db,
        )

        self.assertEqual(self.expense.id, relation.target_transaction_id)
        self.assertEqual(dining_fact_id, relation.target_fact_id)
        self.assertEqual([relation.id], [item.id for item in relations])
        self.assertEqual(Decimal("40.00"), summary["income"])
        self.assertEqual(Decimal("80.00"), summary["expense"])
        self.assertEqual(
            {"餐饮": Decimal("10.00"), "出行": Decimal("70.00")},
            {item["category_name"]: item["amount"] for item in summary["expense_categories"]},
        )
        relation_revision = self.db.query(EconomicFactRelationRevision).filter(
            EconomicFactRelationRevision.relation_id == relation.id,
            EconomicFactRelationRevision.operation == "confirm",
        ).one()
        fact_revisions = self.db.query(EconomicFactRevision).filter(
            EconomicFactRevision.ledger_revision == relation_revision.ledger_revision,
        ).all()
        self.assertEqual({refund_fact.id, dining_fact_id}, {item.fact_id for item in fact_revisions})
        self.assertEqual({"relation_confirm"}, {item.operation for item in fact_revisions})

        with self.assertRaises(HTTPException) as caught:
            reverse_transaction_fact_split(
                self.expense.id,
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, caught.exception.status_code)

        reverse_economic_relation(relation.id, user=self.user, db=self.db)
        restored = get_summary(month="2026-08", user=self.user, db=self.db)
        self.assertEqual(Decimal("60.00"), restored["income"])
        self.assertEqual(Decimal("100.00"), restored["expense"])
        self.assertEqual("income", self.db.get(EconomicFact, refund_fact.id).fact_type)
        self.assertEqual("expense", self.db.get(EconomicFact, dining_fact_id).fact_type)
        self.assertEqual(
            "reimbursable_expense",
            self.db.get(EconomicFact, split.components[1].fact_id).fact_type,
        )

    def test_relation_capacity_counts_allocations_from_both_fact_sides(self):
        first = confirm_economic_relation(
            EconomicRelationConfirmRequest(
                source_transaction_id=self.refund.id,
                target_transaction_id=self.expense.id,
                relation_type="refunds",
                allocated_amount=Decimal("60.00"),
            ),
            user=self.user,
            db=self.db,
        )
        income_category = self.db.query(FinancialCategory).filter(
            FinancialCategory.direction == "income"
        ).one()
        transfer_in = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("50.00"),
            transaction_date=date(2026, 8, 9),
            merchant="我的银行账户",
            description="账户互转转入",
            source_type="manual",
            status="confirmed",
        )
        self.db.add(transfer_in)
        self.db.flush()
        transfer_fact = sync_transaction_fact(
            self.db,
            transaction=transfer_in,
            user_id=self.user.id,
        )
        self.db.commit()
        expense_fact = get_transaction_fact(
            self.db,
            transaction_id=self.expense.id,
            user_id=self.user.id,
        )

        with self.assertRaises(HTTPException) as caught:
            confirm_economic_relation(
                EconomicRelationConfirmRequest(
                    source_transaction_id=self.expense.id,
                    target_transaction_id=transfer_in.id,
                    source_fact_id=expense_fact.id,
                    target_fact_id=transfer_fact.id,
                    relation_type="transfer_pair",
                    allocated_amount=Decimal("50.00"),
                ),
                user=self.user,
                db=self.db,
            )
        self.assertEqual(409, caught.exception.status_code)
        self.assertIn("可关联金额不足", caught.exception.detail)
        self.assertEqual("confirmed", self.db.get(EconomicFactRelation, first.id).status)

    def test_split_component_transfer_removes_only_selected_component(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        transport = FinancialCategory(direction="expense", name="出行", is_system=True)
        self.db.add_all([dining, transport])
        self.db.flush()
        income_category = self.db.query(FinancialCategory).filter(
            FinancialCategory.direction == "income"
        ).one()
        transfer_in = FinancialTransaction(
            user_id=self.user.id,
            category_id=income_category.id,
            direction="income",
            amount=Decimal("30.00"),
            transaction_date=date(2026, 8, 2),
            merchant="我的钱包",
            description="银行卡转入钱包",
            source_type="manual",
            status="confirmed",
        )
        self.db.add(transfer_in)
        self.db.flush()
        transfer_fact = sync_transaction_fact(
            self.db,
            transaction=transfer_in,
            user_id=self.user.id,
        )
        self.db.commit()
        split = confirm_transaction_fact_split(
            self.expense.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("30.00"),
                        category_id=dining.id,
                        title="钱包充值",
                        nature="other",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("70.00"),
                        category_id=transport.id,
                        title="实际出行支出",
                        nature="flexible",
                    ),
                ],
            ),
            user=self.user,
            db=self.db,
        )
        transfer_component_id = split.components[0].fact_id

        relation = confirm_economic_relation(
            EconomicRelationConfirmRequest(
                source_transaction_id=transfer_in.id,
                target_transaction_id=self.expense.id,
                source_fact_id=transfer_fact.id,
                target_fact_id=transfer_component_id,
                relation_type="transfer_pair",
                allocated_amount=Decimal("30.00"),
                reasons=["用户确认这一项是账户互转"],
                detection_method="manual",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual(Decimal("60.00"), summary["income"])
        self.assertEqual(Decimal("70.00"), summary["expense"])
        self.assertEqual(Decimal("30.00"), summary["transfer_amount"])
        self.assertEqual(
            {"出行": Decimal("70.00")},
            {item["category_name"]: item["amount"] for item in summary["expense_categories"]},
        )
        self.assertEqual("transfer", self.db.get(EconomicFact, transfer_component_id).fact_type)

        reverse_economic_relation(relation.id, user=self.user, db=self.db)
        restored = get_summary(month="2026-08", user=self.user, db=self.db)
        self.assertEqual(Decimal("90.00"), restored["income"])
        self.assertEqual(Decimal("100.00"), restored["expense"])
        self.assertEqual(Decimal("0.00"), restored["transfer_amount"])
        self.assertEqual("expense", self.db.get(EconomicFact, transfer_component_id).fact_type)

    def test_split_reimbursable_component_tracks_reimbursement_without_reclassifying_other_items(self):
        dining = FinancialCategory(direction="expense", name="餐饮", is_system=True)
        transport = FinancialCategory(direction="expense", name="出行", is_system=True)
        self.db.add_all([dining, transport])
        self.db.commit()
        split = confirm_transaction_fact_split(
            self.expense.id,
            EconomicFactSplitConfirmRequest(
                components=[
                    EconomicFactSplitComponentInput(
                        amount=Decimal("30.00"),
                        category_id=dining.id,
                        title="个人餐食",
                        nature="flexible",
                    ),
                    EconomicFactSplitComponentInput(
                        amount=Decimal("70.00"),
                        category_id=transport.id,
                        title="公务打车",
                        nature="reimbursable",
                    ),
                ],
            ),
            user=self.user,
            db=self.db,
        )
        refund_fact = get_transaction_fact(
            self.db,
            transaction_id=self.refund.id,
            user_id=self.user.id,
        )
        reimbursable_fact_id = split.components[1].fact_id

        relation = confirm_economic_relation(
            EconomicRelationConfirmRequest(
                source_transaction_id=self.refund.id,
                target_transaction_id=self.expense.id,
                source_fact_id=refund_fact.id,
                target_fact_id=reimbursable_fact_id,
                relation_type="reimburses",
                allocated_amount=Decimal("60.00"),
                reasons=["用户确认公务打车报销"],
                detection_method="manual",
            ),
            user=self.user,
            db=self.db,
        )
        summary = get_summary(month="2026-08", user=self.user, db=self.db)

        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("40.00"), summary["expense"])
        self.assertEqual(
            {"餐饮": Decimal("30.00"), "出行": Decimal("10.00")},
            {item["category_name"]: item["amount"] for item in summary["expense_categories"]},
        )
        self.assertEqual(
            "reimbursable_expense",
            self.db.get(EconomicFact, reimbursable_fact_id).fact_type,
        )
        reverse_economic_relation(relation.id, user=self.user, db=self.db)
        self.assertEqual(
            "reimbursable_expense",
            self.db.get(EconomicFact, reimbursable_fact_id).fact_type,
        )

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
