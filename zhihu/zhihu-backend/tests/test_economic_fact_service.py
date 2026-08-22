from __future__ import annotations

import json
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.cashflow import (
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
from app.schemas.cashflow import EconomicRelationConfirmRequest
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
                }
            },
        )

        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("40.00"), summary["expense"])
        self.assertEqual(Decimal("-40.00"), summary["net"])

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


if __name__ == "__main__":
    unittest.main()
