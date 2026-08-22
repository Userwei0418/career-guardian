from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mysql_test_support import mysql_test

from app.api.deps import get_current_user
from app.db.session import Base, engine, get_db
from app.main import app
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.schemas.cashflow import FinancialTransactionCreate, FinancialTransactionUpdate
from app.services.cashflow_service import build_month_summary, build_recurring_expense_insights, parse_month


def transaction(
    *,
    direction: str,
    amount: str,
    transaction_date: date,
    category_id: int | None = None,
    status: str = "confirmed",
    nature: str | None = None,
):
    return SimpleNamespace(
        direction=direction,
        amount=Decimal(amount),
        transaction_date=transaction_date,
        category_id=category_id,
        status=status,
        nature=nature,
    )


class CashflowSummaryTest(unittest.TestCase):
    def test_summary_keeps_income_expense_equal_and_excludes_transfers(self):
        summary = build_month_summary(
            month="2026-08",
            transactions=[
                transaction(direction="income", amount="12000.00", transaction_date=date(2026, 8, 5), category_id=1),
                transaction(direction="expense", amount="3200.55", transaction_date=date(2026, 8, 6), category_id=2),
                transaction(direction="transfer", amount="5000.00", transaction_date=date(2026, 8, 7)),
            ],
            category_names={1: "工资", 2: "住房"},
        )

        self.assertEqual(Decimal("12000.00"), summary["income"])
        self.assertEqual(Decimal("3200.55"), summary["expense"])
        self.assertEqual(Decimal("8799.45"), summary["net"])
        self.assertEqual(Decimal("5000.00"), summary["transfer_amount"])
        self.assertEqual("recording", summary["state"])
        self.assertEqual("工资", summary["income_categories"][0]["category_name"])
        self.assertEqual("住房", summary["expense_categories"][0]["category_name"])

    def test_pending_and_excluded_records_do_not_change_confirmed_totals(self):
        summary = build_month_summary(
            month="2026-08",
            transactions=[
                transaction(direction="income", amount="800.00", transaction_date=date(2026, 8, 8), category_id=1, status="pending"),
                transaction(direction="expense", amount="99.00", transaction_date=date(2026, 8, 9), category_id=2, status="excluded"),
            ],
            category_names={1: "兼职副业", 2: "餐饮"},
        )

        self.assertEqual(Decimal("0.00"), summary["income"])
        self.assertEqual(Decimal("0.00"), summary["expense"])
        self.assertEqual(1, summary["pending_count"])
        self.assertEqual(1, summary["excluded_count"])
        self.assertEqual("needs_confirmation", summary["state"])

    def test_expense_natures_include_all_confirmed_expenses_and_all_five_buckets(self):
        transactions = [
            transaction(
                direction="expense",
                amount="1.00",
                transaction_date=date(2026, 8, 1),
                category_id=2,
                nature="flexible",
            )
            for _ in range(205)
        ]
        transactions.extend(
            [
                transaction(
                    direction="expense",
                    amount="3000.50",
                    transaction_date=date(2026, 8, 2),
                    category_id=2,
                    nature="fixed",
                ),
                transaction(
                    direction="expense",
                    amount="88.80",
                    transaction_date=date(2026, 8, 3),
                    category_id=2,
                    nature=None,
                ),
                transaction(
                    direction="expense",
                    amount="999.00",
                    transaction_date=date(2026, 8, 4),
                    category_id=2,
                    nature="one_off",
                    status="pending",
                ),
                transaction(
                    direction="income",
                    amount="20000.00",
                    transaction_date=date(2026, 8, 5),
                    category_id=1,
                    nature="fixed",
                ),
                transaction(
                    direction="transfer",
                    amount="5000.00",
                    transaction_date=date(2026, 8, 6),
                    nature="reimbursable",
                ),
            ]
        )

        summary = build_month_summary(
            month="2026-08",
            transactions=transactions,
            category_names={1: "工资", 2: "综合支出"},
        )

        natures = summary["expense_natures"]
        self.assertEqual(
            ["fixed", "flexible", "one_off", "reimbursable", "other"],
            [item["nature"] for item in natures],
        )
        by_nature = {item["nature"]: item for item in natures}
        self.assertEqual({"nature": "fixed", "amount": Decimal("3000.50"), "count": 1}, by_nature["fixed"])
        self.assertEqual({"nature": "flexible", "amount": Decimal("205.00"), "count": 205}, by_nature["flexible"])
        self.assertEqual({"nature": "one_off", "amount": Decimal("0.00"), "count": 0}, by_nature["one_off"])
        self.assertEqual({"nature": "reimbursable", "amount": Decimal("0.00"), "count": 0}, by_nature["reimbursable"])
        self.assertEqual({"nature": "other", "amount": Decimal("88.80"), "count": 1}, by_nature["other"])
        self.assertEqual(summary["expense"], sum(item["amount"] for item in natures))

    def test_empty_month_does_not_pretend_zero_is_a_complete_fact(self):
        summary = build_month_summary(month="2026-08", transactions=[], category_names={})

        self.assertEqual("not_started", summary["state"])
        self.assertEqual(0, summary["confirmed_count"])

    def test_recurring_expense_insights_separate_stable_and_variable_patterns(self):
        summaries = [
            {
                "month": "2026-06",
                "expense_merchants": [
                    {"merchant_name": "会员服务", "amount": Decimal("30.00"), "count": 1},
                    {"merchant_name": "生鲜平台", "amount": Decimal("220.00"), "count": 3},
                ],
            },
            {
                "month": "2026-07",
                "expense_merchants": [
                    {"merchant_name": "会员服务", "amount": Decimal("30.00"), "count": 1},
                    {"merchant_name": "生鲜平台", "amount": Decimal("410.00"), "count": 5},
                    {"merchant_name": "只出现一次", "amount": Decimal("99.00"), "count": 1},
                ],
            },
            {
                "month": "2026-08",
                "expense_merchants": [
                    {"merchant_name": "会员服务", "amount": Decimal("32.00"), "count": 1},
                    {"merchant_name": "生鲜平台", "amount": Decimal("180.00"), "count": 2},
                ],
            },
        ]

        items = build_recurring_expense_insights(summaries)

        self.assertEqual(["会员服务", "生鲜平台"], [item["merchant_name"] for item in items])
        stable, variable = items
        self.assertEqual("stable_monthly", stable["pattern_type"])
        self.assertEqual("high", stable["confidence_tier"])
        self.assertEqual(3, stable["months_seen"])
        self.assertEqual(Decimal("30.67"), stable["average_amount"])
        self.assertEqual("recurring_variable", variable["pattern_type"])
        self.assertEqual(10, variable["occurrence_count"])

    def test_month_parser_requires_canonical_year_month(self):
        self.assertEqual(date(2027, 1, 1), parse_month("2026-12")[2])
        with self.assertRaises(HTTPException):
            parse_month("2026-8")
        for unsupported in ("0001-01", "0999-12", "9999-12"):
            with self.subTest(month=unsupported), self.assertRaises(HTTPException):
                parse_month(unsupported)

    def test_manual_create_and_update_reject_mysql_unsupported_dates(self):
        for unsupported in (date(1, 1, 1), date(999, 12, 31), date(9999, 1, 1)):
            with self.subTest(value=unsupported):
                with self.assertRaises(ValidationError):
                    FinancialTransactionCreate(
                        direction="income",
                        amount="1.00",
                        transaction_date=unsupported,
                    )
                with self.assertRaises(ValidationError):
                    FinancialTransactionUpdate(transaction_date=unsupported)

    def test_update_cannot_clear_required_financial_facts(self):
        with self.assertRaises(ValueError):
            FinancialTransactionUpdate(amount=None)

    def test_create_and_update_keep_amounts_as_exact_decimals(self):
        created = FinancialTransactionCreate(
            direction="income",
            amount="123456789.01",
            transaction_date=date(2026, 8, 5),
        )
        updated = FinancialTransactionUpdate(amount=999_999_999_999.99)

        self.assertIsInstance(created.amount, Decimal)
        self.assertEqual(Decimal("123456789.01"), created.amount)
        self.assertIsInstance(updated.amount, Decimal)
        self.assertEqual(Decimal("999999999999.99"), updated.amount)

    def test_amount_rejects_database_rounding_and_range_overflow(self):
        invalid_amounts = (
            Decimal("0"),
            Decimal("-0.01"),
            Decimal("0.001"),
            Decimal("1000000000000.00"),
        )

        for amount in invalid_amounts:
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                FinancialTransactionCreate(
                    direction="expense",
                    amount=amount,
                    transaction_date=date(2026, 8, 5),
                )
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                FinancialTransactionUpdate(amount=amount)


class CashflowAmountApiValidationTest(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_create_rejects_amounts_that_mysql_would_round_or_overflow(self):
        for amount in (0.001, 1_000_000_000_000.00):
            with self.subTest(amount=amount):
                response = self.client.post(
                    "/api/cashflow/transactions",
                    json={
                        "direction": "income",
                        "amount": amount,
                        "transaction_date": "2026-08-05",
                    },
                )

                self.assertEqual(422, response.status_code, response.text)
                fields = response.json()["error"]["fields"]
                self.assertTrue(
                    any(error["loc"] == ["body", "amount"] for error in fields),
                    response.text,
                )

    def test_update_rejects_amounts_that_mysql_would_round_or_overflow(self):
        for amount in (0.001, 1_000_000_000_000.00):
            with self.subTest(amount=amount):
                response = self.client.put(
                    "/api/cashflow/transactions/1",
                    json={"amount": amount},
                )

                self.assertEqual(422, response.status_code, response.text)
                fields = response.json()["error"]["fields"]
                self.assertTrue(
                    any(error["loc"] == ["body", "amount"] for error in fields),
                    response.text,
                )


class _SummaryQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_criteria):
        return self

    def all(self):
        return self.rows


class _SummaryDb:
    def __init__(self, transactions, categories):
        self.transactions = transactions
        self.categories = categories

    def query(self, model):
        if model is FinancialTransaction:
            return _SummaryQuery(self.transactions)
        if model is FinancialCategory:
            return _SummaryQuery(self.categories)
        raise AssertionError(f"unexpected query model: {model}")


class CashflowSummaryApiContractTest(unittest.TestCase):
    def setUp(self):
        summary_db = _SummaryDb(
            transactions=[
                transaction(
                    direction="income",
                    amount="1000.00",
                    transaction_date=date(2026, 8, 1),
                    category_id=1,
                ),
                transaction(
                    direction="expense",
                    amount="25.25",
                    transaction_date=date(2026, 8, 2),
                    category_id=2,
                    nature="fixed",
                ),
                transaction(
                    direction="expense",
                    amount="4.75",
                    transaction_date=date(2026, 8, 3),
                    category_id=2,
                    nature=None,
                ),
                transaction(
                    direction="expense",
                    amount="500.00",
                    transaction_date=date(2026, 8, 4),
                    category_id=2,
                    nature="reimbursable",
                    status="pending",
                ),
            ],
            categories=[
                SimpleNamespace(id=1, name="工资"),
                SimpleNamespace(id=2, name="日常支出"),
            ],
        )
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        app.dependency_overrides[get_db] = lambda: summary_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)

    def test_summary_api_exposes_complete_expense_nature_breakdown(self):
        response = self.client.get("/api/cashflow/summary?month=2026-08")

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("30.00", body["expense"])
        self.assertEqual(
            ["fixed", "flexible", "one_off", "reimbursable", "other"],
            [item["nature"] for item in body["expense_natures"]],
        )
        by_nature = {item["nature"]: item for item in body["expense_natures"]}
        self.assertEqual({"nature": "fixed", "amount": "25.25", "count": 1}, by_nature["fixed"])
        self.assertEqual({"nature": "other", "amount": "4.75", "count": 1}, by_nature["other"])
        self.assertEqual({"nature": "reimbursable", "amount": "0.00", "count": 0}, by_nature["reimbursable"])
        self.assertEqual(Decimal(body["expense"]), sum(Decimal(item["amount"]) for item in body["expense_natures"]))


@mysql_test
class CashflowApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.alice = self._register("cashflow-alice", "cashflow-alice-password")
        self.bob = self._register("cashflow-bob", "cashflow-bob-password")

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _category(self, auth: dict, direction: str, name: str) -> dict:
        response = self.client.post(
            "/api/cashflow/categories",
            headers=self._headers(auth),
            json={"direction": direction, "name": name},
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def _transaction(self, auth: dict, **overrides) -> dict:
        payload = {
            "direction": "income",
            "amount": 10000,
            "transaction_date": "2026-08-05",
            "category_id": overrides.pop("category_id"),
            "merchant": "测试来源",
            "status": "confirmed",
            **overrides,
        }
        response = self.client.post(
            "/api/cashflow/transactions",
            headers=self._headers(auth),
            json=payload,
        )
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    def test_income_expense_transfer_and_pending_have_deterministic_totals(self):
        income_category = self._category(self.alice, "income", "测试工资")
        expense_category = self._category(self.alice, "expense", "测试住房")
        self._transaction(self.alice, category_id=income_category["id"])
        self._transaction(
            self.alice,
            direction="expense",
            amount=2500.5,
            category_id=expense_category["id"],
            nature="fixed",
        )
        transfer = self.client.post(
            "/api/cashflow/transactions",
            headers=self._headers(self.alice),
            json={"direction": "transfer", "amount": 5000, "transaction_date": "2026-08-06"},
        )
        self.assertEqual(201, transfer.status_code, transfer.text)
        self._transaction(
            self.alice,
            amount=800,
            category_id=income_category["id"],
            status="pending",
        )

        summary = self.client.get(
            "/api/cashflow/summary?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, summary.status_code, summary.text)
        body = summary.json()
        self.assertEqual("10000.00", body["income"])
        self.assertEqual("2500.50", body["expense"])
        self.assertEqual("7499.50", body["net"])
        self.assertEqual("5000.00", body["transfer_amount"])
        self.assertEqual(1, body["pending_count"])
        self.assertEqual(
            ["fixed", "flexible", "one_off", "reimbursable", "other"],
            [item["nature"] for item in body["expense_natures"]],
        )
        self.assertEqual(
            {"nature": "fixed", "amount": "2500.50", "count": 1},
            body["expense_natures"][0],
        )
        self.assertEqual(Decimal(body["expense"]), sum(Decimal(item["amount"]) for item in body["expense_natures"]))

    def test_transactions_and_user_categories_are_owner_scoped(self):
        alice_category = self._category(self.alice, "income", "Alice 私有收入")
        transaction = self._transaction(self.alice, category_id=alice_category["id"])

        bob_list = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.bob),
        )
        self.assertEqual([], bob_list.json())
        foreign_update = self.client.put(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.bob),
            json={"amount": 1},
        )
        self.assertEqual(404, foreign_update.status_code, foreign_update.text)
        foreign_delete = self.client.delete(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign_delete.status_code, foreign_delete.text)
        foreign_category = self.client.post(
            "/api/cashflow/transactions",
            headers=self._headers(self.bob),
            json={
                "direction": "income",
                "amount": 20,
                "transaction_date": "2026-08-06",
                "category_id": alice_category["id"],
            },
        )
        self.assertEqual(404, foreign_category.status_code, foreign_category.text)

    def test_category_direction_and_soft_delete_boundaries(self):
        income_category = self._category(self.alice, "income", "仅收入")
        mismatch = self.client.post(
            "/api/cashflow/transactions",
            headers=self._headers(self.alice),
            json={
                "direction": "expense",
                "amount": 88,
                "transaction_date": "2026-08-06",
                "category_id": income_category["id"],
            },
        )
        self.assertEqual(400, mismatch.status_code, mismatch.text)
        transaction = self._transaction(self.alice, category_id=income_category["id"])
        deleted = self.client.delete(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        summary = self.client.get(
            "/api/cashflow/summary?month=2026-08",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual("not_started", summary["state"])
        self.assertEqual("0.00", summary["income"])


if __name__ == "__main__":
    unittest.main()
