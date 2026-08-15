from __future__ import annotations

import importlib.util
import tempfile
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

    def test_utf8_character_split_across_read_chunks_is_not_corrupted(self) -> None:
        insert_prefix = b"\nINSERT INTO `raw_job_records` VALUES (1,'"
        padding = b"-" * ((1024 * 1024 - 1 - len(insert_prefix)) % (1024 * 1024))
        suffix = (
            "官网','api','https://example.invalid/jobs/1',NULL,"
            "'2026-08-01 10:00:00',200,'fixture',NULL,NULL,'{}','abc',"
            "'success',NULL,'2026-08-01 10:00:00');\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tempdir:
            dump = Path(tempdir) / "split.sql"
            dump.write_bytes(padding + insert_prefix + suffix)
            result = AUDIT_MODULE.audit_dump(
                dump,
                ROOT.parent.parent / "Pin/db/database_init.sql",
                datetime(2026, 8, 15, tzinfo=timezone.utc),
            )
        self.assertEqual(
            {"官网": 1}, result["distributions"]["raw_job_records.source_site"]
        )


if __name__ == "__main__":
    unittest.main()
