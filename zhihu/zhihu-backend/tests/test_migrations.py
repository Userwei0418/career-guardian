import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect


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
                }.issubset(tables)
            )
        finally:
            database_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
