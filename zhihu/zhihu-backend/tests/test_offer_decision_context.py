import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from pydantic import ValidationError

from app.schemas.offer import OfferDecisionContextUpdate, OfferDecisionSetupRequest
from app.schemas.report import OfferAnalysisSnapshotCreate
from app.api.routes.offers import _build_offer_attention


class OfferDecisionContextSchemaTest(unittest.TestCase):
    def test_normalizes_blank_text_and_deduplicates_user_boundaries(self):
        context = OfferDecisionContextUpdate(
            baseline_type="continue_search",
            baseline_label="   ",
            baseline_notes="  等另一场面试结束  ",
            must_haves=[" 固定收入覆盖生活 ", "固定收入覆盖生活", ""],
            red_lines=["长期无偿加班"],
            acceptable_tradeoffs=["通勤增加，换取方向匹配"],
        )
        self.assertIsNone(context.baseline_label)
        self.assertEqual(context.baseline_notes, "等另一场面试结束")
        self.assertEqual(context.must_haves, ["固定收入覆盖生活"])

    def test_rejects_more_than_five_red_lines(self):
        with self.assertRaises(ValidationError):
            OfferDecisionContextUpdate(red_lines=[f"红线 {index}" for index in range(6)])

    def test_setup_only_accepts_priorities_used_by_single_offer_analysis(self):
        with self.assertRaises(ValidationError):
            OfferDecisionSetupRequest(
                priorities=["platform"],
                decision_context=OfferDecisionContextUpdate(),
            )

    def test_unknown_numeric_baseline_can_remain_null(self):
        context = OfferDecisionContextUpdate(
            baseline_type="current_job",
            baseline_monthly_take_home=None,
            baseline_annual_bonus=None,
        )
        self.assertIsNone(context.baseline_monthly_take_home)
        self.assertIsNone(context.baseline_annual_bonus)

    def test_analysis_snapshot_keeps_unknown_living_cost_null(self):
        snapshot = OfferAnalysisSnapshotCreate(
            living_cost=None,
            variable_realization=0.6,
            extra_salary_months_realization=0.8,
        )
        self.assertIsNone(snapshot.living_cost)

    def test_analysis_snapshot_rejects_invalid_realization_rate(self):
        with self.assertRaises(ValidationError):
            OfferAnalysisSnapshotCreate(variable_realization=1.2)

    def test_attention_marks_near_response_deadline_urgent(self):
        now = datetime(2026, 8, 20, 9, 0, 0)
        offer = SimpleNamespace(
            id=9,
            name="Offer A",
            company_name="示例公司",
            job_title="产品经理",
            decision_status="evaluating",
            response_deadline=now + timedelta(days=2),
        )
        attention = _build_offer_attention(offer, [], now=now)
        self.assertTrue(attention.is_urgent)
        self.assertEqual(attention.next_kind, "response_deadline")
        self.assertEqual(attention.overdue_count, 0)

    def test_attention_prioritizes_overdue_review_before_later_response(self):
        now = datetime(2026, 8, 20, 9, 0, 0)
        offer = SimpleNamespace(
            id=10,
            name="Offer B",
            company_name="示例公司",
            job_title="研发工程师",
            decision_status="on_hold",
            response_deadline=now + timedelta(days=5),
        )
        review = SimpleNamespace(
            title="重新评估：Offer B",
            due_at=now - timedelta(hours=1),
        )
        attention = _build_offer_attention(offer, [review], now=now)
        self.assertTrue(attention.is_overdue)
        self.assertEqual(attention.next_kind, "review")
        self.assertIn("复盘时间已经到了", attention.primary_message)

    def test_attention_keeps_missing_deadline_unknown(self):
        offer = SimpleNamespace(
            id=11,
            name="Offer C",
            company_name=None,
            job_title=None,
            decision_status="evaluating",
            response_deadline=None,
        )
        attention = _build_offer_attention(offer, [], now=datetime(2026, 8, 20, 9, 0, 0))
        self.assertFalse(attention.is_urgent)
        self.assertIsNone(attention.next_due_at)
        self.assertIn("待确认", attention.primary_message)


if __name__ == "__main__":
    unittest.main()
