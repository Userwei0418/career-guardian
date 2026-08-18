import os
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import mysql_test_support  # noqa: F401 - installs safe non-production test settings

os.environ["JWT_SECRET"] = "strategy-repair-worker-test-secret"

from app.schemas.market_admin import MarketStrategyRepairCandidate
from app.services.strategy_repair_worker import StrategyRepairWorker


def candidate(status: str = "ai_pending") -> MarketStrategyRepairCandidate:
    return MarketStrategyRepairCandidate(
        id=7,
        source_code="channel-a",
        source_name="渠道 A",
        failure_task_id=11,
        status=status,
        origin="ai",
        failure_signature="selector_changed:runtimeerror:selector missing",
        proposed_strategy={},
        replay_summary={"generation_retryable": True},
        canary_summary={},
        created_by="system",
        created_at=datetime(2026, 8, 17, 8, 0, 0),
    )


class StrategyRepairWorkerTests(unittest.TestCase):
    def test_worker_claims_before_generation_and_keeps_system_subject(self):
        worker = StrategyRepairWorker()
        client = Mock()
        client.list_strategy_repairs.return_value = [candidate()]
        client.claim_strategy_repair.return_value = candidate("ai_generating")
        client.get_strategy_repair_evidence.return_value = {
            "source_code": "channel-a",
            "source_name": "渠道 A",
            "adapter_type": "company_channel",
            "failure_signature": "selector_changed",
            "evidence": {"page_title": "校园招聘"},
        }
        worker._client = client
        strategy = {"pagination": {"mode": "single_page"}}
        with patch(
            "app.services.strategy_repair_worker.generate_strategy_document",
            return_value=strategy,
        ) as generate:
            self.assertEqual(1, worker.run_once())
        client.backfill_strategy_repairs.assert_called_once_with(limit=200)
        client.claim_strategy_repair.assert_called_once()
        self.assertIsNone(generate.call_args.kwargs["user_id"])
        client.complete_strategy_repair.assert_called_once_with(
            7, worker._actor, strategy
        )

    def test_worker_records_retryable_generation_failure(self):
        worker = StrategyRepairWorker()
        client = Mock()
        client.list_strategy_repairs.return_value = [candidate()]
        client.claim_strategy_repair.return_value = candidate("ai_generating")
        client.get_strategy_repair_evidence.return_value = {
            "source_code": "channel-a",
            "source_name": "渠道 A",
            "adapter_type": "company_channel",
            "failure_signature": "selector_changed",
            "evidence": {},
        }
        worker._client = client
        with patch(
            "app.services.strategy_repair_worker.generate_strategy_document",
            side_effect=ValueError("AI 没有返回修复候选"),
        ):
            self.assertEqual(1, worker.run_once())
        client.fail_strategy_repair.assert_called_once()
        self.assertEqual(7, client.fail_strategy_repair.call_args.args[0])
        self.assertEqual(worker._actor, client.fail_strategy_repair.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
