import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from mysql_test_support import MYSQL_TEST_DATABASE_URL, mysql_test


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
            offer_columns = {
                column["name"] for column in inspector.get_columns("offers")
            }
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
            with migration_engine.connect() as connection:
                article_count = connection.scalar(
                    text("SELECT COUNT(*) FROM knowledge_articles")
                )
                category_count = connection.scalar(
                    text("SELECT COUNT(DISTINCT category) FROM knowledge_articles")
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
            }.issubset(tables)
        )
        self.assertIn("career_event_id", offer_columns)
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
        self.assertEqual(31, article_count)
        self.assertEqual(8, category_count)

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


if __name__ == "__main__":
    unittest.main()
