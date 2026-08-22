import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from mysql_test_support import MYSQL_TEST_DATABASE_URL, mysql_test


class OfflineMigrationTest(unittest.TestCase):
    backend_dir = Path(__file__).resolve().parents[1]

    def _offline_environment(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        return environment

    def test_decision_guardian_migrations_render_full_round_trip(self):
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260819_0021:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=self._offline_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(upgrade.returncode, 0, upgrade.stdout + upgrade.stderr)
        self.assertLess(upgrade.stdout.index("CREATE TABLE offer_revisions"), upgrade.stdout.index("CREATE TABLE offer_decision_contexts"))
        self.assertLess(upgrade.stdout.index("CREATE TABLE offer_decision_contexts"), upgrade.stdout.index("CREATE TABLE offer_analysis_snapshots"))

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260820_0024:20260819_0021",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=self._offline_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(downgrade.returncode, 0, downgrade.stdout + downgrade.stderr)
        self.assertLess(downgrade.stdout.index("DROP TABLE offer_analysis_snapshots"), downgrade.stdout.index("DROP TABLE offer_decision_contexts"))
        self.assertLess(downgrade.stdout.index("DROP TABLE offer_decision_contexts"), downgrade.stdout.index("DROP TABLE offer_revisions"))
        self.assertLess(
            downgrade.stdout.index("DROP FOREIGN KEY fk_decision_analysis_snapshot"),
            downgrade.stdout.index("DROP INDEX ix_decision_records_analysis_snapshot_id"),
        )
        self.assertLess(
            downgrade.stdout.index(
                "DROP FOREIGN KEY fk_decision_records_offer_revision_id_offer_revisions"
            ),
            downgrade.stdout.index("DROP INDEX ix_decision_records_offer_revision_id"),
        )

    def test_cashflow_guardian_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260821_0028:20260822_0029",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_categories", output)
        self.assertIn("CREATE TABLE financial_transactions", output)
        self.assertIn("uq_financial_transaction_source_key", output)
        self.assertLess(
            output.index("CREATE TABLE financial_categories"),
            output.index("CREATE TABLE financial_transactions"),
        )

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260822_0029:20260821_0028",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE financial_transactions"),
            output.index("DROP TABLE financial_categories"),
        )

    def test_cashflow_import_candidate_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260822_0029:20260822_0030",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_import_batches", output)
        self.assertIn("CREATE TABLE financial_transaction_candidates", output)
        self.assertIn("CREATE TABLE personal_attachment_cleanup_jobs", output)
        self.assertIn("ADD COLUMN business_data_epoch", output)
        self.assertIn("uq_fin_import_batch_source_hash_parser", output)
        self.assertIn("uq_fin_tx_candidate_batch_row", output)
        self.assertIn("fk_fin_tx_candidate_batch_owner", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertIn("ON DELETE SET NULL", output)
        self.assertLess(
            output.index("CREATE TABLE financial_import_batches"),
            output.index("CREATE TABLE financial_transaction_candidates"),
        )

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260822_0030:20260822_0029",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN business_data_epoch", output)
        self.assertIn("DROP TABLE personal_attachment_cleanup_jobs", output)
        self.assertLess(
            output.index("DROP TABLE financial_transaction_candidates"),
            output.index("DROP TABLE financial_import_batches"),
        )

    def test_cashflow_recognition_artifact_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260822_0030:20260823_0031",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE financial_recognition_artifacts", output)
        self.assertIn("MEDIUMTEXT", output)
        self.assertIn("uq_personal_attachment_id_owner", output)
        self.assertIn("fk_fin_recognition_artifact_batch_owner", output)
        self.assertIn("fk_fin_recognition_artifact_attachment_owner", output)
        self.assertIn("ON DELETE CASCADE", output)
        self.assertIn("ON DELETE RESTRICT", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260823_0031:20260822_0030",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertLess(
            output.index("DROP TABLE financial_recognition_artifacts"),
            output.index("DROP INDEX uq_personal_attachment_id_owner"),
        )

    def test_offer_fact_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260819_0021:20260820_0022",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_revisions", output)
        self.assertIn("CREATE TABLE offer_fact_assertions", output)
        self.assertIn("ALTER TABLE decision_records", output)
        self.assertIn("20260820_0022", output)

    def test_offer_decision_context_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0022:20260820_0023",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_decision_contexts", output)
        self.assertIn("uq_offer_decision_contexts_offer_id", output)
        self.assertIn("20260820_0023", output)

    def test_offer_analysis_snapshot_migration_renders_without_database_connection(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "mysql+pymysql://offline:offline@127.0.0.1:1/offline",
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0023:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("CREATE TABLE offer_analysis_snapshots", output)
        self.assertIn("ADD COLUMN analysis_snapshot_id", output)
        self.assertIn("fk_decision_analysis_snapshot", output)
        self.assertNotIn(
            "fk_decision_records_analysis_snapshot_id_offer_analysis_snapshots",
            output,
        )
        self.assertIn("20260820_0024", output)

    def test_labor_contract_review_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0024:20260820_0025",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE contract_review_snapshots", output)
        self.assertIn("source_attachment_id", output)
        self.assertIn("fk_contract_source_attachment", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260820_0025:20260820_0024",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE contract_review_snapshots", output)
        self.assertLess(
            output.index("DROP FOREIGN KEY fk_contract_source_attachment"),
            output.index("DROP INDEX ix_contracts_source_attachment_id"),
        )

    def test_contract_ai_review_metadata_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "upgrade",
                "20260820_0025:20260821_0026",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("clause_segments", output)
        self.assertIn("prompt_version", output)
        self.assertIn("redaction_version", output)
        self.assertIn("ai_status", output)

        downgrade = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "downgrade",
                "20260821_0026:20260820_0025",
                "--sql",
            ],
            cwd=self.backend_dir,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN clause_segments", output)

    def test_contract_document_quality_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260821_0026:20260821_0027", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("LONGTEXT", output.upper())
        self.assertIn("parse_quality", output)
        self.assertIn("ai_batch_count", output)
        self.assertIn("coverage_report", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260821_0027:20260821_0026", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP COLUMN coverage_report", output)
        self.assertIn("DROP COLUMN parse_quality", output)

    def test_contract_follow_up_history_migration_renders_full_round_trip(self):
        environment = self._offline_environment()
        upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20260821_0027:20260821_0028", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = upgrade.stdout + upgrade.stderr
        self.assertEqual(upgrade.returncode, 0, output)
        self.assertIn("CREATE TABLE contract_follow_up_turns", output)
        self.assertIn("review_snapshot_id", output)
        self.assertIn("ON DELETE CASCADE", output)

        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "20260821_0028:20260821_0027", "--sql"],
            cwd=self.backend_dir, env=environment, capture_output=True, text=True, check=False,
        )
        output = downgrade.stdout + downgrade.stderr
        self.assertEqual(downgrade.returncode, 0, output)
        self.assertIn("DROP TABLE contract_follow_up_turns", output)


@mysql_test
class MigrationTest(unittest.TestCase):
    backend_dir = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": MYSQL_TEST_DATABASE_URL,
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        self._reset_test_schema()

    def tearDown(self):
        self._reset_test_schema()

    def _reset_test_schema(self):
        engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            table_names = inspect(engine).get_table_names()
            preparer = engine.dialect.identifier_preparer
            with engine.begin() as connection:
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
                for table_name in table_names:
                    connection.execute(
                        text(f"DROP TABLE IF EXISTS {preparer.quote(table_name)}")
                    )
                connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        finally:
            engine.dispose()

    def _alembic(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=self.backend_dir,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_empty_database_upgrades_to_head(self):
        result = self._alembic("upgrade", "head")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            tables = set(inspector.get_table_names())
            self.assertIn("offer_revisions", tables)
            self.assertIn("offer_fact_assertions", tables)
            self.assertIn("offer_decision_contexts", tables)
            self.assertIn("offer_analysis_snapshots", tables)
            self.assertIn("contract_review_snapshots", tables)
            offer_columns = {
                column["name"] for column in inspector.get_columns("offers")
            }
            contract_columns = {
                column["name"] for column in inspector.get_columns("contracts")
            }
            contract_review_columns = {
                column["name"]
                for column in inspector.get_columns("contract_review_snapshots")
            }
            raw_text_type = next(column["type"] for column in inspector.get_columns("contracts") if column["name"] == "raw_text")
            decision_columns = {
                column["name"] for column in inspector.get_columns("decision_records")
            }
            self.assertTrue({"offer_revision_id", "preflight_snapshot", "acknowledged_unknowns"}.issubset(decision_columns))
            self.assertIn("analysis_snapshot_id", decision_columns)
            target_columns = {
                column["name"] for column in inspector.get_columns("job_targets")
            }
            draft_columns = {
                column["name"]
                for column in inspector.get_columns("resume_tailoring_drafts")
            }
            analysis_columns = {
                column["name"]
                for column in inspector.get_columns("opportunity_analyses")
            }
            invocation_columns = {
                column["name"]
                for column in inspector.get_columns("ai_invocation_logs")
            }
            provider_columns = {
                column["name"]
                for column in inspector.get_columns("ai_provider_settings")
            }
            import_batch_columns = {
                column["name"]
                for column in inspector.get_columns("financial_import_batches")
            }
            import_candidate_columns = {
                column["name"]
                for column in inspector.get_columns("financial_transaction_candidates")
            }
            recognition_artifact_columns = {
                column["name"]
                for column in inspector.get_columns("financial_recognition_artifacts")
            }
            import_batch_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("financial_import_batches")
            }
            import_candidate_unique_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("financial_transaction_candidates")
            }
            user_columns = {
                column["name"] for column in inspector.get_columns("users")
            }
            with migration_engine.connect() as connection:
                article_count = connection.scalar(
                    text("SELECT COUNT(*) FROM knowledge_articles")
                )
                category_count = connection.scalar(
                    text("SELECT COUNT(DISTINCT category) FROM knowledge_articles")
                )
                financial_category_count = connection.scalar(
                    text("SELECT COUNT(*) FROM financial_categories WHERE is_system = 1")
                )
        finally:
            migration_engine.dispose()

        self.assertTrue(
            {
                "alembic_version",
                "users",
                "career_cases",
                "offers",
                "career_events",
                "evidence",
                "guardian_findings",
                "action_items",
                "decision_records",
                "outcomes",
                "knowledge_articles",
                "resume_versions",
                "opportunity_analyses",
                "ai_provider_settings",
                "ai_invocation_logs",
                "ai_configuration_audits",
                "personal_attachment_versions",
                "job_targets",
                "resume_tailoring_drafts",
                "career_image_generations",
                "financial_categories",
                "financial_transactions",
                "financial_import_batches",
                "financial_transaction_candidates",
                "financial_recognition_artifacts",
                "personal_attachment_cleanup_jobs",
            }.issubset(tables)
        )
        self.assertIn("business_data_epoch", user_columns)
        self.assertTrue(
            {
                "clause_segments",
                "provider_name",
                "model_name",
                "prompt_version",
                "redaction_version",
                "ai_status",
                "ai_input_clause_count",
                "redaction_report",
                "ai_batch_count",
                "ai_completed_batch_count",
                "coverage_report",
            }.issubset(contract_review_columns)
        )
        self.assertIn("LONGTEXT", str(raw_text_type).upper())
        self.assertIn("career_event_id", offer_columns)
        self.assertTrue(
            {
                "source_attachment_id",
                "display_name",
                "document_kind",
                "status",
                "parse_status",
                "parse_mode",
                "parse_notice",
                "page_count",
                "text_page_count",
                "ocr_page_count",
                "parse_error_code",
                "parse_quality",
                "archived_at",
            }.issubset(contract_columns)
        )
        self.assertTrue(
            {
                "job_target_id",
                "source_attachment_id",
                "offer_kind",
                "decision_status",
                "response_deadline",
                "facts_confirmed_at",
                "employment_type",
                "department",
                "job_level",
                "work_mode",
            }.issubset(offer_columns)
        )
        self.assertTrue(
            {
                "plan_status",
                "plan_error",
                "plan_started_at",
                "advice_kind",
                "advice_summary",
                "advice_source_analysis_id",
                "advice_updated_at",
            }.issubset(target_columns)
        )
        self.assertTrue(
            {"error_message", "generation_started_at", "generation_completed_at"}.issubset(
                draft_columns
            )
        )
        self.assertTrue(
            {"scoring_version", "score_breakdown"}.issubset(analysis_columns)
        )
        self.assertTrue(
            {"estimated_cost_microunits", "cost_currency"}.issubset(
                invocation_columns
            )
        )
        self.assertTrue(
            {
                "image_enabled",
                "image_model",
                "image_api_key_encrypted",
                "image_api_key_suffix",
                "image_style_prompt",
                "image_landscape_prompt",
                "image_square_prompt",
            }.issubset(provider_columns)
        )
        self.assertTrue(
            {
                "origin_type",
                "source_type",
                "attachment_version_id",
                "content_hash",
                "parser_version",
                "column_mapping",
                "exact_duplicate_count",
                "possible_duplicate_count",
                "version",
            }.issubset(import_batch_columns)
        )
        self.assertTrue(
            {
                "batch_id",
                "user_id",
                "category_name",
                "external_key",
                "fingerprint",
                "duplicate_transaction_id",
                "transaction_id",
                "validation_errors",
                "warnings",
                "version",
            }.issubset(import_candidate_columns)
        )
        self.assertTrue(
            {
                "batch_id",
                "user_id",
                "artifact_type",
                "sequence_number",
                "status",
                "content_text",
                "content_json",
                "attachment_version_id",
                "content_hash",
                "byte_size",
                "source_locator",
                "artifact_metadata",
            }.issubset(recognition_artifact_columns)
        )
        self.assertIn("uq_fin_import_batch_source_hash_parser", import_batch_unique_constraints)
        self.assertIn("uq_fin_tx_candidate_batch_row", import_candidate_unique_constraints)
        self.assertEqual(31, article_count)
        self.assertEqual(8, category_count)
        self.assertEqual(20, financial_category_count)

    def test_cashflow_import_candidate_round_trip_from_0029(self):
        before = self._alembic("upgrade", "20260822_0029")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("financial_import_batches", inspector.get_table_names())
            self.assertIn("financial_transaction_candidates", inspector.get_table_names())
            self.assertIn("personal_attachment_cleanup_jobs", inspector.get_table_names())
            self.assertIn(
                "business_data_epoch",
                {column["name"] for column in inspector.get_columns("users")},
            )
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260822_0029")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("financial_import_batches", inspector.get_table_names())
            self.assertNotIn("financial_transaction_candidates", inspector.get_table_names())
            self.assertNotIn("personal_attachment_cleanup_jobs", inspector.get_table_names())
            self.assertNotIn(
                "business_data_epoch",
                {column["name"] for column in inspector.get_columns("users")},
            )
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_cashflow_recognition_artifact_round_trip_from_0030(self):
        before = self._alembic("upgrade", "20260822_0030")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260823_0031")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("financial_recognition_artifacts", inspector.get_table_names())
            artifact_columns = {
                column["name"]
                for column in inspector.get_columns("financial_recognition_artifacts")
            }
            self.assertTrue(
                {
                    "batch_id",
                    "user_id",
                    "artifact_type",
                    "sequence_number",
                    "content_text",
                    "content_json",
                    "content_hash",
                }.issubset(artifact_columns)
            )
            attachment_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(
                    "personal_attachment_versions"
                )
            }
            self.assertIn(
                "uq_personal_attachment_id_owner",
                attachment_constraints,
            )
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260822_0030")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("financial_recognition_artifacts", inspector.get_table_names())
            attachment_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(
                    "personal_attachment_versions"
                )
            }
            self.assertNotIn(
                "uq_personal_attachment_id_owner",
                attachment_constraints,
            )
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260823_0031")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_existing_offer_case_is_backfilled_to_decision_event(self):
        before = self._alembic("upgrade", "a31f5740d0c5")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, is_active) "
                        "VALUES ('legacy-user', 'not-used', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO career_cases "
                        "(user_id, type, title, status, current_step) "
                        "VALUES (1, 'offer_analysis', '历史 Offer', 'in_progress', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO offers "
                        "(case_id, company_name, salary_months, probation_months, "
                        "probation_salary_rate) "
                        "VALUES (1, '历史公司', 12, 0, 0.8)"
                    )
                )
        finally:
            migration_engine.dispose()

        after = self._alembic("upgrade", "head")
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT ce.event_type, ce.legacy_case_id, o.career_event_id "
                        "FROM career_events ce "
                        "JOIN offers o ON o.career_event_id = ce.id"
                    )
                ).one()
        finally:
            migration_engine.dispose()
        self.assertEqual(tuple(row), ("decision", 1, 1))

    def test_labor_contract_review_round_trip_from_0024(self):
        before = self._alembic("upgrade", "20260820_0024")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, is_active) "
                        "VALUES ('legacy-contract-user', 'not-used', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO career_cases "
                        "(user_id, type, title, status, current_step) "
                        "VALUES (1, 'contract_review', '历史劳动合同', 'in_progress', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO contracts (case_id, employer, raw_text) "
                        "VALUES (1, '历史公司', '历史劳动合同文本')"
                    )
                )
        finally:
            migration_engine.dispose()

        upgraded = self._alembic("upgrade", "20260820_0025")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertIn("contract_review_snapshots", inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("contracts")}
            self.assertIn("source_attachment_id", columns)
            with migration_engine.connect() as connection:
                row = connection.execute(
                    text("SELECT document_kind, status, parse_status FROM contracts WHERE id = 1")
                ).one()
            self.assertEqual(tuple(row), ("labor_contract", "active", "ready"))
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260820_0024")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            self.assertNotIn("contract_review_snapshots", inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("contracts")}
            self.assertNotIn("source_attachment_id", columns)
        finally:
            migration_engine.dispose()

    def test_contract_document_quality_round_trip_from_0026(self):
        before = self._alembic("upgrade", "20260821_0026")
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

        upgraded = self._alembic("upgrade", "20260821_0027")
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            contract_columns = {column["name"]: column for column in inspector.get_columns("contracts")}
            snapshot_columns = {column["name"] for column in inspector.get_columns("contract_review_snapshots")}
            self.assertIn("LONGTEXT", str(contract_columns["raw_text"]["type"]).upper())
            self.assertTrue({"parse_error_code", "text_page_count", "ocr_page_count", "parse_quality"}.issubset(contract_columns))
            self.assertTrue({"ai_batch_count", "ai_completed_batch_count", "coverage_report"}.issubset(snapshot_columns))
        finally:
            migration_engine.dispose()

        downgraded = self._alembic("downgrade", "20260821_0026")
        self.assertEqual(downgraded.returncode, 0, downgraded.stdout + downgraded.stderr)
        migration_engine = create_engine(MYSQL_TEST_DATABASE_URL)
        try:
            inspector = inspect(migration_engine)
            contract_columns = {column["name"]: column for column in inspector.get_columns("contracts")}
            snapshot_columns = {column["name"] for column in inspector.get_columns("contract_review_snapshots")}
            self.assertNotIn("parse_quality", contract_columns)
            self.assertNotIn("coverage_report", snapshot_columns)
            self.assertNotIn("LONGTEXT", str(contract_columns["raw_text"]["type"]).upper())
        finally:
            migration_engine.dispose()

        restored = self._alembic("upgrade", "20260821_0027")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)


if __name__ == "__main__":
    unittest.main()
