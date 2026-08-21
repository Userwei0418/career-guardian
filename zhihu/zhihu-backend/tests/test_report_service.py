import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.offer import Offer
from app.services.offer_fact_service import normalize_hr_fact_value
from app.services.report_service import generate_offer_report


class OfferReportServiceTest(unittest.TestCase):
    def build_offer(self, **overrides):
        values = {
            "id": 7,
            "offer_kind": "written",
            "company_name": "海岳科技",
            "job_title": "Java 后端工程师",
            "city": "上海",
            "monthly_salary": 20000,
            "fixed_salary": 16000,
            "variable_salary": 4000,
            "allowance": 500,
            "salary_months": 14,
            "probation_months": 3,
            "probation_salary_rate": 0.8,
            "work_location": "上海市浦东新区",
            "working_hours": "弹性工作制",
            "response_deadline": datetime(2026, 8, 20, tzinfo=timezone.utc),
            "facts_confirmed_at": datetime(2026, 8, 16, tzinfo=timezone.utc),
        }
        values.update(overrides)
        return Offer(**values)

    def test_report_separates_facts_assumptions_and_income_scenarios(self):
        profile = SimpleNamespace(monthly_budget=8000, savings_goal=5000)
        target = SimpleNamespace(
            id=3,
            job_snapshot={"title": "Java 后端工程师", "company_name": "海岳科技"},
            advice_summary="方向一致，但需要确认团队培养和业务边界。",
            plan_status="ready",
        )

        report = generate_offer_report(
            self.build_offer(),
            priorities=["income", "growth", "city_life"],
            profile=profile,
            target=target,
            variable_realization=0.5,
            extra_salary_months_realization=0.5,
        )

        self.assertEqual(3, len(report["scenarios"]))
        self.assertLess(report["scenarios"][0]["annual_take_home"], report["scenarios"][1]["annual_take_home"])
        self.assertLess(report["scenarios"][1]["annual_take_home"], report["scenarios"][2]["annual_take_home"])
        self.assertEqual("个人预算", report["assumptions"]["living_cost_source"])
        self.assertEqual(0, report["fact_ledger"]["confirmed_count"])
        self.assertEqual(9, report["fact_ledger"]["recorded_count"])
        self.assertEqual([], report["fact_ledger"]["missing"])
        self.assertTrue(report["career_context"]["linked"])
        self.assertEqual("已接上目标岗位准备", report["decision_axes"][3]["title"])

    def test_report_does_not_treat_missing_facts_as_bad_offer(self):
        report = generate_offer_report(
            self.build_offer(company_name=None, monthly_salary=None, fixed_salary=None, variable_salary=None),
            profile=SimpleNamespace(monthly_budget=None, savings_goal=None),
        )

        self.assertEqual("blocked", report["stance"]["level"])
        self.assertIn("公司", report["fact_ledger"]["missing"])
        self.assertIn("月薪", report["fact_ledger"]["missing"])
        self.assertEqual("unknown", report["decision_axes"][0]["status"])

    def test_missing_defaults_block_calculation_instead_of_becoming_12_zero_and_80_percent(self):
        report = generate_offer_report(
            self.build_offer(salary_months=None, probation_months=None, probation_salary_rate=None),
            profile=SimpleNamespace(monthly_budget=None, savings_goal=None),
        )

        self.assertEqual("blocked", report["calculation"]["status"])
        self.assertEqual([], report["scenarios"])
        self.assertIsNone(report["income"]["annual_take_home"])
        self.assertIn("年薪月数", report["fact_ledger"]["missing"])

    def test_monthly_and_annual_variable_pay_conflict_stops_numeric_conclusion(self):
        report = generate_offer_report(
            self.build_offer(monthly_salary=7500, fixed_salary=None, variable_salary=60000),
            profile=SimpleNamespace(monthly_budget=4000, savings_goal=None),
        )

        self.assertEqual("blocked", report["calculation"]["status"])
        self.assertEqual([], report["scenarios"])
        self.assertTrue(any(item["code"] == "variable_salary_period_conflict" for item in report["calculation"]["blockers"]))
        self.assertEqual("blocked", report["stance"]["level"])

    def test_missing_city_does_not_silently_use_hangzhou(self):
        report = generate_offer_report(
            self.build_offer(city=None),
            profile=SimpleNamespace(monthly_budget=None, savings_goal=None),
        )

        self.assertIsNone(report["city"])
        self.assertEqual("城市待确认", report["assumptions"]["living_cost_source"])
        self.assertEqual("blocked", report["calculation"]["status"])

    def test_hr_fact_normalization_requires_explicit_monthly_period(self):
        with self.assertRaisesRegex(ValueError, "必须明确为每月金额"):
            normalize_hr_fact_value("variable_salary", "60000", period="year")
        self.assertEqual(5000, normalize_hr_fact_value("variable_salary", "5000", period="month"))

    def test_hr_fact_normalization_keeps_percentage_visible_and_bounded(self):
        self.assertEqual(0.8, normalize_hr_fact_value("probation_salary_rate", "80"))
        self.assertEqual(0.8, normalize_hr_fact_value("probation_salary_rate", "0.8"))
        with self.assertRaisesRegex(ValueError, "0–1"):
            normalize_hr_fact_value("probation_salary_rate", "180")


if __name__ == "__main__":
    unittest.main()
