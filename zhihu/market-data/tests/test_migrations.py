import unittest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from market_data.db import CoreBase, RawBase, StagingBase
from market_data.models import core, raw, staging  # noqa: F401


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
                "raw_processing_attempts",
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
        metadata_by_domain = {
            "staging": StagingBase.metadata,
            "raw": RawBase.metadata,
            "core": CoreBase.metadata,
        }
        for domain, required in expected.items():
            metadata = metadata_by_domain[domain]
            table_names = set(metadata.tables)
            self.assertTrue(required.issubset(table_names))
            forbidden = set().union(*(tables for key, tables in expected.items() if key != domain))
            self.assertTrue(table_names.isdisjoint(forbidden))
            ddl = "\n".join(
                str(CreateTable(table).compile(dialect=mysql.dialect()))
                for table in metadata.sorted_tables
            )
            self.assertIn("CREATE TABLE", ddl)
            self.assertNotIn("sqlite", ddl.lower())

        core_indexes = {
            index.name
            for table in CoreBase.metadata.tables.values()
            for index in table.indexes
        }
        self.assertIn("ix_market_jobs_order", core_indexes)


if __name__ == "__main__":
    unittest.main()
