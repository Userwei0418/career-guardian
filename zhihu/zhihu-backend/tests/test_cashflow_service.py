from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mysql_test_support import mysql_test

from app.api.deps import get_current_user
from app.api.routes.cashflow import (
    _budget_response,
    _cashflow_report_html,
    _month_close_snapshot,
    _build_month_end_forecast,
)
from app.db.session import Base, engine, get_db
from app.main import app
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.schemas.cashflow import (
    CashflowMonthlyReportResponse,
    FinancialBudgetUpsert,
    FinancialTransactionCreate,
    FinancialTransactionUpdate,
    RecurringExpenseDecisionUpsert,
)
from app.services.cashflow_service import (
    build_month_summary,
    build_recurring_expense_insights,
    financial_transaction_snapshot,
    parse_month,
    recurring_merchant_fingerprint,
)


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
    def test_subscription_reminder_requires_a_charge_date(self):
        with self.assertRaises(ValidationError):
            RecurringExpenseDecisionUpsert(
                merchant_name="视频会员",
                decision_type="subscription",
                reminder_days_before=3,
            )

    def test_month_end_forecast_uses_actuals_for_a_finished_month(self):
        forecast = _build_month_end_forecast(
            month_start=date(2025, 7, 1),
            month_end=date(2025, 8, 1),
            summary={
                "income": Decimal("9000.00"),
                "expense": Decimal("3000.00"),
                "confirmed_count": 8,
            },
            budgets=[],
        )

        self.assertEqual("actual", forecast["state"])
        self.assertEqual(Decimal("3000.00"), forecast["projected_expense"])
        self.assertEqual(Decimal("6000.00"), forecast["projected_net"])

    def test_readable_report_is_confirmed_ledger_html_without_original_files(self):
        report = CashflowMonthlyReportResponse.model_validate({
            "month": "2026-08",
            "ledger_revision": 7,
            "readiness": "ready",
            "income": Decimal("100.00"),
            "expense": Decimal("40.00"),
            "net": Decimal("60.00"),
            "confirmed_count": 2,
            "pending_count": 0,
            "subscription_count": 0,
            "fixed_expense_count": 0,
            "highlights": [{"level": "info", "title": "程序结论", "detail": "只含已确认事实"}],
            "generated_at": datetime(2026, 8, 23, 8, 0, 0),
        })

        html = _cashflow_report_html(report)

        self.assertIn("2026-08 收支守护报告", html)
        self.assertIn("可信账本 r7", html)
        self.assertIn("只使用用户已确认的经济事实", html)
        self.assertNotIn("OCR 原图", html)

    def test_month_close_fingerprint_ignores_generation_time_and_global_revision(self):
        report = {
            "month": "2026-08",
            "ledger_revision": 4,
            "readiness": "ready",
            "income": Decimal("100.00"),
            "expense": Decimal("40.00"),
            "net": Decimal("60.00"),
            "savings_rate_percent": 60.0,
            "confirmed_count": 2,
            "pending_count": 0,
            "top_expense_category": None,
            "top_expense_merchant": None,
            "subscription_count": 0,
            "fixed_expense_count": 0,
            "budget_alerts": [],
            "highlights": [],
            "generated_at": datetime(2026, 8, 23, 8, 0, 0),
        }
        snapshot, fingerprint = _month_close_snapshot(report)
        report["ledger_revision"] = 8
        report["generated_at"] = datetime(2026, 8, 23, 9, 0, 0)
        _, refreshed_fingerprint = _month_close_snapshot(report)

        self.assertEqual("100.00", snapshot["income"])
        self.assertEqual(fingerprint, refreshed_fingerprint)
        report["net"] = Decimal("59.00")
        _, changed_fingerprint = _month_close_snapshot(report)
        self.assertNotEqual(fingerprint, changed_fingerprint)

    def test_month_close_fingerprint_ignores_volatile_forecast_and_settlement_age(self):
        report = {
            "month": "2026-08",
            "ledger_revision": 4,
            "readiness": "ready",
            "income": Decimal("100.00"),
            "expense": Decimal("40.00"),
            "net": Decimal("60.00"),
            "confirmed_count": 2,
            "pending_count": 0,
            "subscription_count": 0,
            "fixed_expense_count": 0,
            "forecast": {
                "state": "in_progress",
                "as_of": date(2026, 8, 22),
                "elapsed_days": 22,
                "days_in_month": 31,
                "projected_income": Decimal("100.00"),
                "projected_expense": Decimal("56.36"),
                "projected_net": Decimal("43.64"),
                "basis": "按日均支出外推",
            },
            "settlement_outlook": {
                "as_of": date(2026, 8, 22),
                "open_reimbursement_count": 1,
                "open_reimbursement_amount": Decimal("20.00"),
                "possible_refund_count": 0,
                "possible_refund_amount": Decimal("0.00"),
                "items": [{
                    "fact_id": 8,
                    "kind": "reimbursement_due",
                    "title": "差旅",
                    "occurred_date": date(2026, 8, 10),
                    "original_amount": Decimal("20.00"),
                    "settled_amount": Decimal("0.00"),
                    "remaining_amount": Decimal("20.00"),
                    "age_days": 12,
                    "cross_month": False,
                }],
            },
            "generated_at": datetime(2026, 8, 22, 8, 0, 0),
        }
        _, fingerprint = _month_close_snapshot(report)
        report["forecast"]["as_of"] = date(2026, 8, 23)
        report["forecast"]["projected_expense"] = Decimal("57.00")
        report["settlement_outlook"]["as_of"] = date(2026, 8, 23)
        report["settlement_outlook"]["items"][0]["age_days"] = 13
        _, refreshed_fingerprint = _month_close_snapshot(report)

        self.assertEqual(fingerprint, refreshed_fingerprint)

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
        self.assertEqual(64, len(stable["merchant_fingerprint"]))
        self.assertEqual("recurring_variable", variable["pattern_type"])
        self.assertEqual(10, variable["occurrence_count"])

    def test_recurring_merchant_fingerprint_normalizes_case_and_spacing(self):
        self.assertEqual(
            recurring_merchant_fingerprint("  NETFLIX   会员 "),
            recurring_merchant_fingerprint("netflix 会员"),
        )
        self.assertNotEqual(
            recurring_merchant_fingerprint("netflix 会员"),
            recurring_merchant_fingerprint("其他会员"),
        )

    def test_budget_execution_uses_relation_adjusted_summary_amount(self):
        budget = SimpleNamespace(
            id=7,
            month="2026-08",
            category_id=None,
            amount=Decimal("1000.00"),
            status="active",
            version=2,
            confirmed_at=datetime(2026, 8, 1, 9, 0),
            reversed_at=None,
        )
        response = _budget_response(
            budget,
            summary={"expense": Decimal("850.00"), "expense_categories": []},
            category_name=None,
        )

        self.assertEqual("near_limit", response.execution_state)
        self.assertEqual(Decimal("850.00"), response.spent_amount)
        self.assertEqual(Decimal("150.00"), response.remaining_amount)
        self.assertEqual(85.0, response.utilization_percent)

    def test_budget_month_requires_canonical_supported_month(self):
        FinancialBudgetUpsert(month="2026-08", amount="1000.00")
        for unsupported in ("2026-8", "0999-12", "9999-01"):
            with self.subTest(month=unsupported), self.assertRaises(ValidationError):
                FinancialBudgetUpsert(month=unsupported, amount="1000.00")

    def test_transaction_snapshot_is_json_safe_and_preserves_exact_money(self):
        snapshot = financial_transaction_snapshot(SimpleNamespace(
            id=9,
            direction="expense",
            amount=Decimal("123.40"),
            currency="CNY",
            transaction_date=date(2026, 8, 23),
            occurred_at=None,
            category_id=2,
            merchant="测试商户",
            description=None,
            nature="flexible",
            source_type="manual",
            source_ref=None,
            external_key=None,
            status="confirmed",
            confirmed_at=datetime(2026, 8, 23, 10, 0),
            excluded_reason=None,
            deleted_at=None,
        ))

        self.assertEqual("123.40", snapshot["amount"])
        self.assertEqual("2026-08-23", snapshot["transaction_date"])
        self.assertEqual("2026-08-23T10:00:00", snapshot["confirmed_at"])

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

    def test_monthly_total_and_category_budgets_are_reversible_and_owner_scoped(self):
        expense_category = self._category(self.alice, "expense", "测试餐饮")
        self._transaction(
            self.alice,
            direction="expense",
            amount=850,
            category_id=expense_category["id"],
            nature="flexible",
        )
        total = self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "amount": 1000},
        )
        self.assertEqual(200, total.status_code, total.text)
        self.assertEqual("near_limit", total.json()["execution_state"])
        stale_update = self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "amount": 1100},
        )
        self.assertEqual(409, stale_update.status_code, stale_update.text)
        updated_total = self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "amount": 1100, "expected_version": total.json()["version"]},
        )
        self.assertEqual(200, updated_total.status_code, updated_total.text)
        total = updated_total
        category = self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "category_id": expense_category["id"], "amount": 500},
        )
        self.assertEqual(200, category.status_code, category.text)
        self.assertEqual("over_budget", category.json()["execution_state"])

        listed = self.client.get(
            "/api/cashflow/budgets?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(2, len(listed.json()))
        foreign_delete = self.client.delete(
            f"/api/cashflow/budgets/{total.json()['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign_delete.status_code, foreign_delete.text)

        removed = self.client.delete(
            f"/api/cashflow/budgets/{total.json()['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual("reversed", removed.json()["status"])
        self.assertEqual(
            1,
            len(self.client.get(
                "/api/cashflow/budgets?month=2026-08",
                headers=self._headers(self.alice),
            ).json()),
        )
        restored = self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "amount": 1200},
        )
        self.assertEqual(total.json()["id"], restored.json()["id"])
        self.assertEqual("active", restored.json()["status"])

    def test_recurring_decision_ledger_is_reclassifiable_reversible_and_owner_scoped(self):
        created = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={
                "merchant_name": "会员服务",
                "decision_type": "subscription",
                "evidence": ["连续三个月出现"],
            },
        )
        self.assertEqual(200, created.status_code, created.text)
        self.assertEqual(1, len(self.client.get(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
        ).json()))
        self.assertEqual([], self.client.get(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.bob),
        ).json())

        updated = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={"merchant_name": "会员服务", "decision_type": "fixed_expense"},
        )
        self.assertEqual(created.json()["id"], updated.json()["id"])
        self.assertEqual("fixed_expense", updated.json()["decision_type"])
        self.assertGreater(updated.json()["version"], created.json()["version"])
        foreign_reverse = self.client.delete(
            f"/api/cashflow/recurring-decisions/{created.json()['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign_reverse.status_code, foreign_reverse.text)
        reversed_response = self.client.delete(
            f"/api/cashflow/recurring-decisions/{created.json()['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual("reversed", reversed_response.json()["status"])
        self.assertEqual([], self.client.get(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
        ).json())

    def test_subscription_schedule_is_user_confirmed_versioned_and_visible_in_monthly_report(self):
        created = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={
                "merchant_name": "视频会员",
                "decision_type": "subscription",
                "renewal_cycle": "monthly",
                "next_charge_date": "2026-08-28",
                "auto_renewal": True,
                "reminder_days_before": 3,
            },
        )
        self.assertEqual(200, created.status_code, created.text)
        body = created.json()
        self.assertEqual("2026-08-28", body["next_charge_date"])
        self.assertTrue(body["auto_renewal"])
        self.assertEqual(3, body["reminder_days_before"])

        updated = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={
                "merchant_name": "视频会员",
                "decision_type": "subscription",
                "renewal_cycle": "yearly",
                "next_charge_date": "2026-08-29",
                "auto_renewal": False,
                "reminder_days_before": 7,
                "expected_version": body["version"],
            },
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual("yearly", updated.json()["renewal_cycle"])
        stale = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={
                "merchant_name": "视频会员",
                "decision_type": "subscription",
                "expected_version": body["version"],
            },
        )
        self.assertEqual(409, stale.status_code, stale.text)

        report = self.client.get(
            "/api/cashflow/monthly-report?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, report.status_code, report.text)
        reminder = next(item for item in report.json()["highlights"] if item["title"].startswith("订阅扣款计划"))
        self.assertIn("2026-08-29", reminder["detail"])
        self.assertIn("不自动续费", reminder["detail"])

        fixed = self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={
                "merchant_name": "视频会员",
                "decision_type": "fixed_expense",
                "expected_version": updated.json()["version"],
            },
        )
        self.assertEqual(200, fixed.status_code, fixed.text)
        self.assertIsNone(fixed.json()["next_charge_date"])
        self.assertIsNone(fixed.json()["auto_renewal"])

    def test_monthly_report_uses_confirmed_ledger_budgets_and_user_decisions(self):
        income_category = self._category(self.alice, "income", "测试收入")
        expense_category = self._category(self.alice, "expense", "测试住房")
        self._transaction(self.alice, amount=10000, category_id=income_category["id"])
        self._transaction(
            self.alice,
            direction="expense",
            amount=2500,
            category_id=expense_category["id"],
            nature="fixed",
            merchant="房东",
        )
        self.client.post(
            "/api/cashflow/budgets",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "amount": 2000},
        )
        self.client.post(
            "/api/cashflow/recurring-decisions",
            headers=self._headers(self.alice),
            json={"merchant_name": "房东", "decision_type": "fixed_expense"},
        )

        response = self.client.get(
            "/api/cashflow/monthly-report?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("ready", body["readiness"])
        self.assertEqual("7500.00", body["net"])
        self.assertEqual(75.0, body["savings_rate_percent"])
        self.assertEqual("测试住房", body["top_expense_category"]["category_name"])
        self.assertEqual("房东", body["top_expense_merchant"]["merchant_name"])
        self.assertEqual(1, body["fixed_expense_count"])
        self.assertEqual("over_budget", body["budget_alerts"][0]["execution_state"])

    def test_monthly_report_tracks_cross_month_reimbursement_year_comparison_and_html_export(self):
        income_category = self._category(self.alice, "income", "测试退款收入")
        expense_category = self._category(self.alice, "expense", "测试差旅")
        self._transaction(
            self.alice,
            amount=900,
            transaction_date="2025-08-05",
            category_id=income_category["id"],
        )
        self._transaction(
            self.alice,
            direction="expense",
            amount=100,
            transaction_date="2025-08-06",
            category_id=expense_category["id"],
            nature="flexible",
        )
        reimbursable = self._transaction(
            self.alice,
            direction="expense",
            amount=200,
            transaction_date="2026-07-28",
            category_id=expense_category["id"],
            nature="reimbursable",
            merchant="出差酒店",
        )
        reimbursement = self._transaction(
            self.alice,
            amount=80,
            transaction_date="2026-08-12",
            category_id=income_category["id"],
            merchant="公司报销",
        )
        linked = self.client.post(
            "/api/cashflow/relations",
            headers=self._headers(self.alice),
            json={
                "source_transaction_id": reimbursement["id"],
                "target_transaction_id": reimbursable["id"],
                "relation_type": "reimburses",
                "allocated_amount": 80,
            },
        )
        self.assertEqual(201, linked.status_code, linked.text)
        self._transaction(
            self.alice,
            amount=50,
            transaction_date="2026-08-15",
            category_id=income_category["id"],
            merchant="平台退款待核对",
        )

        response = self.client.get(
            "/api/cashflow/monthly-report?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("50.00", body["year_comparison"]["current_income"])
        self.assertEqual("120.00", body["year_comparison"]["current_expense"])
        self.assertEqual("800.00", body["year_comparison"]["previous_net"])
        self.assertEqual(1, body["settlement_outlook"]["open_reimbursement_count"])
        self.assertEqual("120.00", body["settlement_outlook"]["open_reimbursement_amount"])
        self.assertEqual(1, body["settlement_outlook"]["possible_refund_count"])
        self.assertEqual("50.00", body["settlement_outlook"]["possible_refund_amount"])
        reimbursement_item = next(
            item for item in body["settlement_outlook"]["items"]
            if item["kind"] == "reimbursement_due"
        )
        self.assertTrue(reimbursement_item["cross_month"])

        exported = self.client.get(
            "/api/cashflow/monthly-report/export?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, exported.status_code, exported.text)
        self.assertIn("text/html", exported.headers["content-type"])
        self.assertIn("待报销 1 项", exported.text)
        self.assertIn("只使用用户已确认的经济事实", exported.text)

    def test_transaction_edits_keep_snapshots_and_advance_the_ledger_revision(self):
        income_category = self._category(self.alice, "income", "修订测试收入")
        transaction = self._transaction(
            self.alice,
            amount=1000,
            category_id=income_category["id"],
        )
        created_history = self.client.get(
            f"/api/cashflow/transactions/{transaction['id']}/revisions",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, created_history.status_code, created_history.text)
        self.assertEqual("create", created_history.json()[0]["operation"])
        self.assertEqual(1, created_history.json()[0]["ledger_revision"])

        updated = self.client.put(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.alice),
            json={"amount": 900, "revision_reason": "核对到账后更正"},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        history = self.client.get(
            f"/api/cashflow/transactions/{transaction['id']}/revisions",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual(["update", "create"], [item["operation"] for item in history])
        self.assertEqual("1000.00", history[0]["before_snapshot"]["amount"])
        self.assertEqual("900.00", history[0]["after_snapshot"]["amount"])
        self.assertEqual("核对到账后更正", history[0]["reason"])
        self.assertEqual(2, history[0]["ledger_revision"])
        foreign_history = self.client.get(
            f"/api/cashflow/transactions/{transaction['id']}/revisions",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, foreign_history.status_code, foreign_history.text)

        self.client.delete(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.alice),
        )
        restored = self.client.post(
            f"/api/cashflow/transactions/{transaction['id']}/restore",
            headers=self._headers(self.alice),
            json={},
        )
        self.assertEqual(200, restored.status_code, restored.text)
        restored_history = self.client.get(
            f"/api/cashflow/transactions/{transaction['id']}/revisions",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual(
            ["restore", "delete", "update", "create"],
            [item["operation"] for item in restored_history],
        )
        ledger_history = self.client.get(
            "/api/cashflow/ledger-revisions?limit=8",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, ledger_history.status_code, ledger_history.text)
        self.assertEqual(
            [4, 3, 2, 1],
            [item["revision_number"] for item in ledger_history.json()],
        )
        self.assertEqual([], self.client.get(
            "/api/cashflow/ledger-revisions",
            headers=self._headers(self.bob),
        ).json())
        report = self.client.get(
            "/api/cashflow/monthly-report?month=2026-08",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual(4, report["ledger_revision"])

    def test_transaction_revision_cannot_break_confirmed_fact_allocations(self):
        income_category = self._category(self.alice, "income", "关系保护收入")
        expense_category = self._category(self.alice, "expense", "关系保护支出")
        refund = self._transaction(self.alice, amount=80, category_id=income_category["id"])
        expense = self._transaction(
            self.alice,
            direction="expense",
            amount=100,
            category_id=expense_category["id"],
            nature="flexible",
        )
        relation = self.client.post(
            "/api/cashflow/relations",
            headers=self._headers(self.alice),
            json={
                "source_transaction_id": refund["id"],
                "target_transaction_id": expense["id"],
                "relation_type": "refunds",
                "allocated_amount": 80,
            },
        )
        self.assertEqual(201, relation.status_code, relation.text)

        too_small = self.client.put(
            f"/api/cashflow/transactions/{refund['id']}",
            headers=self._headers(self.alice),
            json={"amount": 79},
        )
        self.assertEqual(409, too_small.status_code, too_small.text)
        delete_linked = self.client.delete(
            f"/api/cashflow/transactions/{expense['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(409, delete_linked.status_code, delete_linked.text)
        safe_edit = self.client.put(
            f"/api/cashflow/transactions/{expense['id']}",
            headers=self._headers(self.alice),
            json={"merchant": "更正后商户", "revision_reason": "只更正商户"},
        )
        self.assertEqual(200, safe_edit.status_code, safe_edit.text)

    def test_relation_revisions_and_batch_reverse_are_atomic(self):
        income_category = self._category(self.alice, "income", "关系修订收入")
        expense_category = self._category(self.alice, "expense", "关系修订支出")
        refunds = [
            self._transaction(self.alice, amount=amount, category_id=income_category["id"])
            for amount in (30, 40, 50)
        ]
        expenses = [
            self._transaction(
                self.alice,
                direction="expense",
                amount=amount,
                category_id=expense_category["id"],
                nature="flexible",
            )
            for amount in (30, 40, 50)
        ]
        relations = []
        for refund, expense, amount in zip(refunds, expenses, (30, 40, 50)):
            response = self.client.post(
                "/api/cashflow/relations",
                headers=self._headers(self.alice),
                json={
                    "source_transaction_id": refund["id"],
                    "target_transaction_id": expense["id"],
                    "relation_type": "refunds",
                    "allocated_amount": amount,
                },
            )
            self.assertEqual(201, response.status_code, response.text)
            relations.append(response.json())

        confirmation_history = self.client.get(
            f"/api/cashflow/relations/{relations[0]['id']}/revisions",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, confirmation_history.status_code, confirmation_history.text)
        self.assertEqual("confirm", confirmation_history.json()[0]["operation"])
        self.assertEqual("confirmed", confirmation_history.json()[0]["after_snapshot"]["status"])
        self.assertEqual(404, self.client.get(
            f"/api/cashflow/relations/{relations[0]['id']}/revisions",
            headers=self._headers(self.bob),
        ).status_code)

        atomic_failure = self.client.post(
            "/api/cashflow/relations/batch-reverse",
            headers=self._headers(self.alice),
            json={"relation_ids": [relations[2]["id"], 999999]},
        )
        self.assertEqual(409, atomic_failure.status_code, atomic_failure.text)
        still_active = self.client.get(
            f"/api/cashflow/transactions/{refunds[2]['id']}/relations",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual([relations[2]["id"]], [item["id"] for item in still_active])

        reversed_response = self.client.post(
            "/api/cashflow/relations/batch-reverse",
            headers=self._headers(self.alice),
            json={
                "relation_ids": [relations[0]["id"], relations[1]["id"]],
                "reason": "对账后确认不是退款",
            },
        )
        self.assertEqual(200, reversed_response.status_code, reversed_response.text)
        self.assertEqual(["reversed", "reversed"], [item["status"] for item in reversed_response.json()])
        reversal_history = self.client.get(
            f"/api/cashflow/relations/{relations[0]['id']}/revisions",
            headers=self._headers(self.alice),
        ).json()
        self.assertEqual(["reverse", "confirm"], [item["operation"] for item in reversal_history])
        self.assertEqual("confirmed", reversal_history[0]["before_snapshot"]["status"])
        self.assertEqual("reversed", reversal_history[0]["after_snapshot"]["status"])
        self.assertEqual("对账后确认不是退款", reversal_history[0]["reason"])

    def test_month_close_preserves_versions_and_detects_report_changes(self):
        income_category = self._category(self.alice, "income", "月结收入")
        expense_category = self._category(self.alice, "expense", "月结支出")
        income = self._transaction(self.alice, amount=1000, category_id=income_category["id"])
        self._transaction(
            self.alice,
            direction="expense",
            amount=300,
            category_id=expense_category["id"],
            nature="flexible",
        )

        closed = self.client.post(
            "/api/cashflow/monthly-closes",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "expected_ledger_revision": 2},
        )
        self.assertEqual(201, closed.status_code, closed.text)
        self.assertEqual(1, closed.json()["version"])
        self.assertTrue(closed.json()["is_current"])
        self.assertFalse(closed.json()["is_stale"])
        self.assertEqual("700.00", closed.json()["report_snapshot"]["net"])
        self.assertEqual([], self.client.get(
            "/api/cashflow/monthly-closes?month=2026-08",
            headers=self._headers(self.bob),
        ).json())

        changed = self.client.put(
            f"/api/cashflow/transactions/{income['id']}",
            headers=self._headers(self.alice),
            json={"amount": 900, "revision_reason": "月结后发现到账有误"},
        )
        self.assertEqual(200, changed.status_code, changed.text)
        history = self.client.get(
            "/api/cashflow/monthly-closes?month=2026-08",
            headers=self._headers(self.alice),
        ).json()
        self.assertTrue(history[0]["is_stale"])
        duplicate_close = self.client.post(
            "/api/cashflow/monthly-closes",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "expected_ledger_revision": 3},
        )
        self.assertEqual(409, duplicate_close.status_code, duplicate_close.text)

        reopened = self.client.post(
            f"/api/cashflow/monthly-closes/{closed.json()['id']}/reopen",
            headers=self._headers(self.alice),
            json={},
        )
        self.assertEqual(200, reopened.status_code, reopened.text)
        self.assertEqual("reopened", reopened.json()["status"])
        self.assertFalse(reopened.json()["is_current"])
        foreign_reopen = self.client.post(
            f"/api/cashflow/monthly-closes/{closed.json()['id']}/reopen",
            headers=self._headers(self.bob),
            json={},
        )
        self.assertEqual(404, foreign_reopen.status_code, foreign_reopen.text)

        reclosed = self.client.post(
            "/api/cashflow/monthly-closes",
            headers=self._headers(self.alice),
            json={"month": "2026-08", "expected_ledger_revision": 3},
        )
        self.assertEqual(201, reclosed.status_code, reclosed.text)
        self.assertEqual(2, reclosed.json()["version"])
        self.assertEqual("600.00", reclosed.json()["report_snapshot"]["net"])

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

    def test_deleted_transaction_restores_the_same_formal_record(self):
        expense_category = self._category(self.alice, "expense", "可恢复支出")
        transaction = self._transaction(
            self.alice,
            direction="expense",
            amount=88.8,
            category_id=expense_category["id"],
            nature="flexible",
        )
        deleted = self.client.delete(
            f"/api/cashflow/transactions/{transaction['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertEqual(transaction["id"], deleted.json()["transaction_id"])

        trash = self.client.get(
            "/api/cashflow/transactions/trash",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, trash.status_code, trash.text)
        self.assertEqual(1, trash.json()["total"])
        self.assertEqual(transaction["id"], trash.json()["items"][0]["id"])

        restored = self.client.post(
            f"/api/cashflow/transactions/{transaction['id']}/restore",
            headers=self._headers(self.alice),
            json={},
        )
        self.assertEqual(200, restored.status_code, restored.text)
        self.assertEqual(transaction["id"], restored.json()["id"])
        self.assertEqual("confirmed", restored.json()["status"])

        empty_trash = self.client.get(
            "/api/cashflow/transactions/trash",
            headers=self._headers(self.alice),
        )
        self.assertEqual(0, empty_trash.json()["total"])

        summary = self.client.get(
            "/api/cashflow/summary?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual("88.80", summary.json()["expense"])

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
