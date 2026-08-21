import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.routes.salary_calcs import _monthly_savings, _source_context, _summary


class SalaryCalculationProjectionTest(unittest.TestCase):
    def build_calculation(self, result_json):
        return SimpleNamespace(
            id=12,
            name="商汤 Offer · 到手核算",
            city="深圳",
            monthly_salary=7500,
            result_take_home=6171,
            result_annual_take_home=74052,
            result_savings_rate=36,
            result_json=result_json,
            created_at=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
        )

    def test_summary_exposes_offer_source_and_monthly_savings(self):
        calculation = self.build_calculation({
            "monthly_savings": 2271,
            "source_context": {
                "source_type": "offer",
                "offer_id": 7,
                "offer_name": "商汤 Offer",
            },
        })

        summary = _summary(calculation)

        self.assertEqual(7, summary.source_context["offer_id"])
        self.assertEqual(2271, summary.result_monthly_savings)
        self.assertEqual("商汤 Offer", summary.source_context["offer_name"])

    def test_invalid_metadata_is_not_presented_as_offer_link(self):
        calculation = self.build_calculation({"monthly_savings": "unknown", "source_context": "offer:7"})

        self.assertIsNone(_source_context(calculation))
        self.assertIsNone(_monthly_savings(calculation))

    def test_zero_monthly_savings_is_preserved(self):
        calculation = self.build_calculation({"monthly_savings": 0, "source_context": {"source_type": "standalone"}})

        summary = _summary(calculation)

        self.assertEqual(0, summary.result_monthly_savings)
        self.assertEqual("standalone", summary.source_context["source_type"])


if __name__ == "__main__":
    unittest.main()
