from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


class MigrationIsolationTests(unittest.TestCase):
    def test_staging_raw_and_core_migrate_to_isolated_schema_targets(self) -> None:
        expected = {
            "staging": {
                "legacy_import_batches",
                "legacy_table_stats",
                "legacy_job_records",
                "legacy_company_records",
                "legacy_job_source_records",
                "legacy_raw_records",
            },
            "raw": {
                "collection_templates",
                "recruitment_companies",
                "crawl_batches",
                "data_sources",
                "crawl_tasks",
                "raw_records",
                "crawl_log_entries",
            },
            "core": {
                "market_job_families",
                "market_cities",
                "market_skills",
                "market_recruitment_types",
                "market_companies",
                "market_jobs",
                "market_job_sources",
                "market_job_skills",
                "market_core_promotion_batches",
                "market_rejected_legacy_jobs",
                "market_quality_gate_policies",
                "market_insight_snapshots",
            },
        }
        with tempfile.TemporaryDirectory() as tempdir:
            paths = {domain: Path(tempdir) / f"{domain}.sqlite3" for domain in expected}
            env = os.environ.copy()
            env.update(
                {
                    "MARKET_STAGING_DATABASE_URL": f"sqlite:///{paths['staging']}",
                    "MARKET_RAW_DATABASE_URL": f"sqlite:///{paths['raw']}",
                    "MARKET_CORE_DATABASE_URL": f"sqlite:///{paths['core']}",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            for domain in expected:
                subprocess.run(
                    [
                        str(Path(os.sys.executable)),
                        "-m",
                        "alembic",
                        "-c",
                        str(ROOT / "alembic.ini"),
                        "-x",
                        f"domain={domain}",
                        "upgrade",
                        "head",
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            table_sets = {
                domain: set(inspect(create_engine(f"sqlite:///{path}")).get_table_names())
                for domain, path in paths.items()
            }
            for domain, required in expected.items():
                self.assertTrue(required.issubset(table_sets[domain]))
                forbidden = set().union(*(tables for key, tables in expected.items() if key != domain))
                self.assertTrue(table_sets[domain].isdisjoint(forbidden))
            core_engine = create_engine(f"sqlite:///{paths['core']}")
            try:
                with core_engine.connect() as connection:
                    active_policy = connection.execute(
                        text(
                            "SELECT policy_version FROM market_quality_gate_policies "
                            "WHERE status='active'"
                        )
                    ).scalar_one()
                core_indexes = {
                    item["name"] for item in inspect(core_engine).get_indexes("market_jobs")
                }
            finally:
                core_engine.dispose()
            self.assertEqual("career-guardian-job-core-v1", active_policy)
            self.assertIn("ix_market_jobs_order", core_indexes)


if __name__ == "__main__":
    unittest.main()
