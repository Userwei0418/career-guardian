from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from market_data.db import CoreBase, StagingBase
from market_data.models.core import Job, JobSource, MarketInsightSnapshot, RejectedLegacyJob
from market_data.models.staging import (
    LegacyCompanyRecord,
    LegacyImportBatch,
    LegacyJobRecord,
    LegacyJobSourceRecord,
)
from market_data.providers import CoreMarketProvider
from market_data.services.legacy_promotion import promote_legacy_batch, resolve_salary


class LegacyPromotionTests(unittest.TestCase):
    def test_salary_text_is_normalized_before_market_statistics(self) -> None:
        self.assertEqual(
            (20000, 30000, "month"),
            resolve_salary({"salary_text": "20-30K/月", "salary_unit": "月"})[:3],
        )
        self.assertEqual(
            (33333, 41667, "month"),
            resolve_salary({"salary_text": "40万-50万", "salary_unit": "月"})[:3],
        )
        self.assertEqual(
            (200, 300, "day"),
            resolve_salary({"salary_text": "200-300元/天", "salary_unit": "天"})[:3],
        )
        self.assertEqual(
            (None, None, "unknown"),
            resolve_salary({"salary_min": 20, "salary_max": 30, "salary_unit": "月"})[:3],
        )

    def test_quality_gate_cleans_lineage_and_core_provider_reads_only_promoted_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            staging_url = f"sqlite:///{root / 'staging.sqlite3'}"
            core_url = f"sqlite:///{root / 'core.sqlite3'}"
            staging_engine = create_engine(staging_url)
            core_engine = create_engine(core_url)
            StagingBase.metadata.create_all(staging_engine)
            CoreBase.metadata.create_all(core_engine)
            observed_at = datetime.fromisoformat("2026-08-01T08:00:00")

            with Session(staging_engine) as session:
                batch = LegacyImportBatch(
                    dump_sha256="a" * 64,
                    source_basename="synthetic.sql",
                    import_mode="fixture",
                    status="completed",
                )
                session.add(batch)
                session.flush()
                session.add(
                    LegacyCompanyRecord(
                        batch_id=batch.id,
                        legacy_company_id=1,
                        name="脱敏数据科技有限公司",
                        status=1,
                        legacy_payload={"industry": "企业服务", "size_range": "100-499人"},
                    )
                )
                common = {
                    "title": "数据分析培训生",
                    "normalized_title": "数据分析师",
                    "city": "上海",
                    "job_category": "数据分析",
                    "job_description": "负责数据清洗、指标体系建设和业务分析，使用 SQL 与 Python 支持团队完成经营决策。" * 2,
                    "job_requirements": "本科应届生，具备数据分析基础。",
                    "experience_min_months": 36,
                    "education_level": "本科",
                    "skill_tags": ["SQL", "Python", "SQL"],
                    "salary_min": 10000,
                    "salary_max": 15000,
                    "salary_unit": "month",
                    "published_at": observed_at.isoformat(),
                    "first_seen_at": observed_at.isoformat(),
                    "last_seen_at": observed_at.isoformat(),
                    "status": "open",
                    "is_campus": 1,
                }
                session.add_all(
                    [
                        LegacyJobRecord(
                            batch_id=batch.id,
                            legacy_job_id=10,
                            title=common["title"],
                            company_id=1,
                            source_site="fixture",
                            source_job_id="job-10",
                            published_at=observed_at,
                            legacy_payload=common,
                        ),
                        LegacyJobRecord(
                            batch_id=batch.id,
                            legacy_job_id=11,
                            title=common["title"],
                            company_id=1,
                            source_site="fixture",
                            source_job_id="job-11",
                            published_at=observed_at,
                            legacy_payload={**common, "title": "无来源岗位"},
                        ),
                        LegacyJobSourceRecord(
                            batch_id=batch.id,
                            legacy_source_id=100,
                            legacy_job_id=10,
                            source_site="fixture",
                            source_job_id="job-10",
                            source_url="https://jobs.example.invalid/10",
                            first_seen_at=observed_at,
                            last_seen_at=observed_at,
                            legacy_payload={
                                "source_url": "https://jobs.example.invalid/10",
                                "is_official": 1,
                            },
                        ),
                    ]
                )
                session.commit()
                batch_id = batch.id

            with Session(staging_engine) as staging_session, Session(
                core_engine, expire_on_commit=False
            ) as core_session:
                result = promote_legacy_batch(staging_session, core_session, batch_id, chunk_size=1)
                promoted = core_session.scalar(select(func.count()).select_from(Job))
                rejected = core_session.scalar(select(func.count()).select_from(RejectedLegacyJob))
                job = core_session.scalar(select(Job))
                lineage = core_session.scalar(select(JobSource))
                self.assertEqual("completed", result.status)
                self.assertEqual(1, promoted)
                self.assertEqual(1, rejected)
                self.assertEqual("unknown", job.status)
                self.assertEqual("legacy_staging", lineage.provenance_type)
                self.assertGreaterEqual(job.quality_score, 55)
                repeated = promote_legacy_batch(
                    staging_session, core_session, batch_id, chunk_size=1
                )
                self.assertEqual(1, repeated.promoted_count)
                self.assertEqual(1, repeated.rejected_count)
                self.assertEqual(0, repeated.duplicate_count)
                self.assertTrue(repeated.summary["reconciled_from_final_state"])

            provider = CoreMarketProvider(core_url)
            search = provider.search_jobs("数据", "上海", 10)
            filtered_search = provider.search_jobs(
                None,
                "上海",
                10,
                company="脱敏数据",
                job_title="培训生",
                major="本科",
                recruitment_type="campus",
            )
            internship_search = provider.search_jobs(
                None, None, 10, recruitment_type="internship"
            )
            detail = provider.get_job("core:1")
            salary = provider.salary_insight("数据分析师", "上海")
            skills = provider.skill_insight("数据分析师", 5)
            recommended = provider.search_jobs(
                None,
                "上海",
                10,
                job_title="数据分析师",
                sort_by="relevance",
                match_major="数据",
                match_skills=["SQL"],
                match_experience_months=0,
                match_education_level=2,
            )
            overview = provider.compute_overview("数据分析师")
            stale_payload = overview.model_dump(mode="json")
            stale_payload["job_count"] = 99
            with Session(core_engine) as session:
                session.add(
                    MarketInsightSnapshot(
                        scope_key="job_family:数据分析师",
                        payload=stale_payload,
                        source_updated_at=datetime.fromisoformat("2000-01-01T00:00:00"),
                        generated_at=datetime.fromisoformat("2000-01-01T00:00:00"),
                    )
                )
                session.commit()
            refreshed_overview = provider.overview("数据分析师")
            with Session(core_engine) as session:
                refreshed_snapshot = session.scalar(
                    select(MarketInsightSnapshot).where(
                        MarketInsightSnapshot.scope_key == "job_family:数据分析师"
                    )
                )
                refreshed_job_count = refreshed_snapshot.payload["job_count"]
            provider.close()
            self.assertEqual(1, search.total)
            self.assertEqual(1, filtered_search.total)
            self.assertEqual("campus", filtered_search.recruitment_type)
            self.assertEqual(0, internship_search.total)
            self.assertEqual("core:1", search.jobs[0].job_id)
            self.assertEqual("unknown", search.jobs[0].status)
            self.assertIsNotNone(detail)
            self.assertEqual("core:1", detail.job.job_id)
            self.assertIn("负责数据清洗", detail.description)
            self.assertEqual("脱敏数据科技有限公司", detail.company.name)
            self.assertTrue(detail.job.sources)
            self.assertEqual(1, salary.sample_size)
            self.assertEqual(12500, salary.p50)
            self.assertTrue(salary.sources)
            self.assertEqual({"SQL", "Python"}, {item.name for item in skills.skills})
            self.assertEqual(1, skills.sample_size)
            self.assertTrue(skills.sources)
            self.assertEqual("relevance", recommended.sort_by)
            self.assertEqual(1, recommended.candidate_total)
            self.assertGreater(recommended.jobs[0].match_score, 0)
            self.assertEqual(["SQL"], recommended.jobs[0].matched_skills)
            self.assertIn("经历年限暂未达到岗位门槛", recommended.jobs[0].match_reasons)
            self.assertIn("学历达到岗位门槛", recommended.jobs[0].match_reasons)
            self.assertEqual(1, overview.job_count)
            self.assertEqual(12500, overview.salary_p50)
            self.assertEqual(1, refreshed_overview.job_count)
            self.assertEqual(1, refreshed_job_count)

            staging_engine.dispose()
            core_engine.dispose()


if __name__ == "__main__":
    unittest.main()
