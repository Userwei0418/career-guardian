from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_pin_backup", ROOT / "scripts/audit_pin_backup.py"
)
assert SPEC and SPEC.loader
AUDIT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT_MODULE)


class BackupAuditTests(unittest.TestCase):
    def test_streaming_audit_reports_only_aggregates(self) -> None:
        result = AUDIT_MODULE.audit_dump(
            ROOT / "tests/fixtures/pin_backup_sample.sql",
            ROOT.parent.parent / "Pin/db/database_init.sql",
            datetime(2026, 8, 15, tzinfo=timezone.utc),
        )
        self.assertEqual("read_only_streaming_no_import", result["mode"])
        self.assertEqual(2, result["table_counts"]["jobs"])
        self.assertEqual(1, result["duplicate_rows_after_first"]["jobs.dedupe_key"])
        self.assertEqual(1, result["anomalies"]["jobs.salary_min_gt_max"])
        self.assertEqual(1, result["anomalies"]["jobs.published_at.future"])
        serialized = str(result)
        self.assertNotIn("\u6570\u636e\u5206\u6790\u57f9\u8bad\u751f", serialized)


if __name__ == "__main__":
    unittest.main()
