from __future__ import annotations

import unittest
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from market_data.db import RawBase
from market_data.models.raw import CrawlTask, DataSource, RawProcessingAttempt, RawRecord
from market_data.services.raw_processing import (
    SemanticNormalizationResult,
    prepare_raw_candidate,
    split_detail_sections,
)


class FakeSemanticNormalizer:
    def normalize(self, **_: object) -> SemanticNormalizationResult:
        return SemanticNormalizationResult(
            responsibilities=("负责消息推送系统设计", "不在原文中的架构责任"),
            requirements=("熟悉 Java 和 Redis",),
            skill_tags=("Java", "Kubernetes"),
            provider="test",
            model="test-model",
        )


class RawProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        RawBase.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.source = DataSource(
            code="test-source",
            name="测试渠道",
            adapter_type="html",
            base_url="https://example.com/jobs",
            allowed_hosts=["example.com"],
            config={"semantic_cleaning": {"enabled": True}},
        )
        self.session.add(self.source)
        self.session.flush()
        self.task = CrawlTask(
            task_uid="task-1",
            source_id=self.source.id,
            adapter_type="html",
        )
        self.session.add(self.task)
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def make_raw(self, detail: str) -> RawRecord:
        now = datetime(2026, 8, 17, 8, 0, 0)
        raw = RawRecord(
            source_id=self.source.id,
            crawl_task_id=self.task.id,
            external_id="job-1",
            source_url="https://example.com/jobs/1",
            fetched_at=now,
            content_type="application/json",
            raw_payload={"title": "Java 工程师", "_detail_text": detail},
            content_hash="a" * 64,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.session.add(raw)
        self.session.commit()
        return raw

    def test_explicit_headings_are_split_without_ai(self) -> None:
        sections = split_detail_sections(
            "岗位职责：1. 负责服务开发\n任职要求：1. 熟悉 Java\n福利待遇：五险一金"
        )
        self.assertIn("负责服务开发", sections["responsibilities"])
        self.assertIn("熟悉 Java", sections["requirements"])
        self.assertEqual("五险一金", sections["benefits"])

    def test_ai_items_without_exact_source_evidence_are_rejected(self) -> None:
        raw = self.make_raw("负责消息推送系统设计，要求熟悉 Java 和 Redis。")
        normalized = prepare_raw_candidate(
            self.session, self.source, raw, FakeSemanticNormalizer()
        )
        self.assertEqual("负责消息推送系统设计", normalized["responsibilities"])
        self.assertEqual("熟悉 Java 和 Redis", normalized["requirements"])
        self.assertEqual(["Java"], normalized["skill_tags"])
        self.assertNotIn("Kubernetes", str(normalized))
        attempts = list(
            self.session.scalars(
                select(RawProcessingAttempt)
                .where(RawProcessingAttempt.raw_record_id == raw.id)
                .order_by(RawProcessingAttempt.attempt_no)
            )
        )
        self.assertEqual(
            ["deterministic_normalization", "semantic_normalization", "post_validation"],
            [item.stage for item in attempts],
        )
        self.assertIn("unsupported_ai_evidence_rejected", attempts[1].reason_codes)

    def test_missing_detail_is_recorded_and_never_fabricated(self) -> None:
        raw = self.make_raw("")
        normalized = prepare_raw_candidate(self.session, self.source, raw)
        self.assertNotIn("responsibilities", normalized)
        self.assertNotIn("requirements", normalized)
        self.assertEqual("insufficient_source_detail", raw.processing_status)
        attempts = list(
            self.session.scalars(
                select(RawProcessingAttempt).where(RawProcessingAttempt.raw_record_id == raw.id)
            )
        )
        self.assertEqual("failed", attempts[-1].status)
        self.assertEqual(["source_detail_missing"], attempts[-1].reason_codes)


if __name__ == "__main__":
    unittest.main()
