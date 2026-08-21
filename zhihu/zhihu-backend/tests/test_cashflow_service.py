from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient

from mysql_test_support import mysql_test

from app.db.session import Base, engine
from app.main import app
from app.schemas.cashflow import FinancialTransactionUpdate
from app.services.cashflow_service import build_month_summary, parse_month


def transaction(
    *,
    direction: str,
    amount: str,
    transaction_date: date,
    category_id: int | None = None,
    status: str = "confirmed",
):
    return SimpleNamespace(
        direction=direction,
        amount=Decimal(amount),
        transaction_date=transaction_date,
        category_id=category_id,
        status=status,
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

        self.assertEqual(12000.0, summary["income"])
        self.assertEqual(3200.55, summary["expense"])
        self.assertEqual(8799.45, summary["net"])
        self.assertEqual(5000.0, summary["transfer_amount"])
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

        self.assertEqual(0.0, summary["income"])
        self.assertEqual(0.0, summary["expense"])
        self.assertEqual(1, summary["pending_count"])
        self.assertEqual(1, summary["excluded_count"])
        self.assertEqual("needs_confirmation", summary["state"])

    def test_empty_month_does_not_pretend_zero_is_a_complete_fact(self):
        summary = build_month_summary(month="2026-08", transactions=[], category_names={})

        self.assertEqual("not_started", summary["state"])
        self.assertEqual(0, summary["confirmed_count"])

    def test_month_parser_requires_canonical_year_month(self):
        self.assertEqual(date(2027, 1, 1), parse_month("2026-12")[2])
        with self.assertRaises(HTTPException):
            parse_month("2026-8")

    def test_update_cannot_clear_required_financial_facts(self):
        with self.assertRaises(ValueError):
            FinancialTransactionUpdate(amount=None)


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
        self.assertEqual(10000, body["income"])
        self.assertEqual(2500.5, body["expense"])
        self.assertEqual(7499.5, body["net"])
        self.assertEqual(5000, body["transfer_amount"])
        self.assertEqual(1, body["pending_count"])

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
        self.assertEqual(0, summary["income"])


if __name__ == "__main__":
    unittest.main()
