import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


class MigrationTest(unittest.TestCase):
    def test_empty_database_upgrades_to_head(self):
        database_path = Path(tempfile.gettempdir()) / "career-guardian-migration-test.sqlite3"
        database_path.unlink(missing_ok=True)
        database_url = f"sqlite:///{database_path}"
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": database_url,
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )

        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            migration_engine = create_engine(database_url)
            try:
                tables = set(inspect(migration_engine).get_table_names())
            finally:
                migration_engine.dispose()

            self.assertTrue(
                {
                    "alembic_version",
                    "users",
                    "career_cases",
                    "offers",
                    "contracts",
                    "findings",
                    "salary_calculations",
                    "review_rules",
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
                }.issubset(tables)
            )
            verification_engine = create_engine(database_url)
            try:
                offer_columns = {
                    column["name"] for column in inspect(verification_engine).get_columns("offers")
                }
                target_columns = {
                    column["name"] for column in inspect(verification_engine).get_columns("job_targets")
                }
                draft_columns = {
                    column["name"] for column in inspect(verification_engine).get_columns("resume_tailoring_drafts")
                }
                analysis_columns = {
                    column["name"] for column in inspect(verification_engine).get_columns("opportunity_analyses")
                }
                with verification_engine.connect() as connection:
                    article_count = connection.scalar(text("SELECT COUNT(*) FROM knowledge_articles"))
                    category_count = connection.scalar(
                        text("SELECT COUNT(DISTINCT category) FROM knowledge_articles")
                    )
            finally:
                verification_engine.dispose()
            self.assertIn("career_event_id", offer_columns)
            self.assertTrue({
                "job_target_id", "source_attachment_id", "offer_kind", "decision_status",
                "response_deadline", "facts_confirmed_at", "employment_type", "department",
                "job_level", "work_mode",
            }.issubset(offer_columns))
            self.assertTrue({"plan_status", "plan_error", "plan_started_at", "advice_kind", "advice_summary", "advice_source_analysis_id", "advice_updated_at"}.issubset(target_columns))
            self.assertTrue({"error_message", "generation_started_at", "generation_completed_at"}.issubset(draft_columns))
            self.assertTrue({"scoring_version", "score_breakdown"}.issubset(analysis_columns))
            self.assertEqual(31, article_count)
            self.assertEqual(8, category_count)
        finally:
            database_path.unlink(missing_ok=True)

    def test_existing_offer_case_is_backfilled_to_decision_event(self):
        database_path = Path(tempfile.gettempdir()) / "career-guardian-backfill-test.sqlite3"
        database_path.unlink(missing_ok=True)
        database_url = f"sqlite:///{database_path}"
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": database_url,
                "JWT_SECRET": "migration-test-secret-only-not-for-production",
            }
        )
        backend_dir = Path(__file__).resolve().parents[1]

        try:
            before = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "a31f5740d0c5"],
                cwd=backend_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(before.returncode, 0, before.stdout + before.stderr)

            migration_engine = create_engine(database_url)
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (username, password_hash, is_active) "
                        "VALUES ('legacy-user', 'not-used', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO career_cases (user_id, type, title, status, current_step) "
                        "VALUES (1, 'offer_analysis', '历史 Offer', 'in_progress', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO offers (case_id, company_name, salary_months, probation_months, probation_salary_rate) "
                        "VALUES (1, '历史公司', 12, 0, 0.8)"
                    )
                )
            migration_engine.dispose()

            after = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=backend_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

            migration_engine = create_engine(database_url)
            try:
                with migration_engine.connect() as connection:
                    row = connection.execute(
                        text(
                            "SELECT ce.event_type, ce.legacy_case_id, o.career_event_id "
                            "FROM career_events ce JOIN offers o ON o.career_event_id = ce.id"
                        )
                    ).one()
            finally:
                migration_engine.dispose()
            self.assertEqual(tuple(row), ("decision", 1, 1))
        finally:
            database_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
