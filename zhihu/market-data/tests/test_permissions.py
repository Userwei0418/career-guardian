from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PermissionBoundaryTests(unittest.TestCase):
    def test_market_reader_is_core_only(self) -> None:
        sql = (ROOT / "scripts/bootstrap_mysql_permissions.sql").read_text(encoding="utf-8")
        reader_grants = [
            line.strip()
            for line in sql.splitlines()
            if line.strip().startswith("GRANT") and "career_guardian_market_reader" in line
        ]
        self.assertEqual(8, len(reader_grants))
        self.assertTrue(all("ON `zhihu`.`market_" in line for line in reader_grants))
        self.assertTrue(all("pin_legacy_staging" not in line and "market_raw" not in line for line in reader_grants))

    def test_raw_worker_has_no_staging_or_core_grant(self) -> None:
        sql = (ROOT / "scripts/bootstrap_mysql_permissions.sql").read_text(encoding="utf-8")
        raw_worker_grants = [
            line for line in sql.splitlines() if "career_guardian_raw_worker" in line and "GRANT" in line
        ]
        self.assertEqual(1, len(raw_worker_grants))
        self.assertIn("`market_raw`.*", raw_worker_grants[0])


if __name__ == "__main__":
    unittest.main()
