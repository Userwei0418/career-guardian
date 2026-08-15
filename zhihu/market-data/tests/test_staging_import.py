from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from market_data.db import StagingBase
from market_data.models.staging import LegacyImportBatch, LegacyJobRecord


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "import_pin_legacy", ROOT / "scripts/import_pin_legacy.py"
)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


class StagingImportTests(unittest.TestCase):
    def test_fixture_import_only_writes_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "staging.sqlite3"
            url = f"sqlite:///{path}"
            engine = create_engine(url)
            StagingBase.metadata.create_all(engine)
            batch_id, count = IMPORTER.import_jobs(
                ROOT / "tests/fixtures/pin_backup_sample.sql",
                ROOT.parent.parent / "Pin/db/database_init.sql",
                url,
                "fixture",
                None,
            )
            with Session(engine) as session:
                batch = session.get(LegacyImportBatch, batch_id)
                rows = session.scalar(select(func.count()).select_from(LegacyJobRecord))
            self.assertEqual(2, count)
            self.assertEqual(2, rows)
            self.assertEqual("completed", batch.status)
            self.assertEqual("fixture", batch.import_mode)
            engine.dispose()

    def test_formal_import_requires_explicit_environment_and_exact_hash(self) -> None:
        previous = os.environ.pop("PIN_LEGACY_IMPORT_APPROVED", None)
        try:
            with self.assertRaises(RuntimeError):
                IMPORTER.assert_import_allowed("formal", "actual", "actual")
            os.environ["PIN_LEGACY_IMPORT_APPROVED"] = "true"
            with self.assertRaises(RuntimeError):
                IMPORTER.assert_import_allowed("formal", "actual", "wrong")
            IMPORTER.assert_import_allowed("formal", "actual", "actual")
        finally:
            if previous is None:
                os.environ.pop("PIN_LEGACY_IMPORT_APPROVED", None)
            else:
                os.environ["PIN_LEGACY_IMPORT_APPROVED"] = previous


if __name__ == "__main__":
    unittest.main()
