from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from market_data.db import RawBase, make_engine, make_session_factory
from market_data.models.raw import DataSource, RecruitmentCompany
from market_data.pin_migration import migrate_pin_company_rows


class PinCollectionMigrationTests(unittest.TestCase):
    def test_company_rows_are_grouped_and_split_into_channels_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            parser_root = Path(tempdir) / "parsers"
            parser_root.mkdir()
            (parser_root / "gen_1.py").write_text("", encoding="utf-8")
            engine = make_engine(f"sqlite:///{Path(tempdir) / 'raw.sqlite3'}")
            RawBase.metadata.create_all(engine)
            rows = [
                {
                    "com_id": "com_1",
                    "com_name": "示例科技",
                    "career_url": "https://jobs.example.com",
                    "json_config": {
                        "urls": {
                            "xiaozhao_1": "https://jobs.example.com/campus",
                            "shixi_1": "https://jobs.example.com/intern",
                        },
                        "func_name": "gen_1",
                        "detail_selector": ".job-detail",
                    },
                    "is_active": 1,
                },
                {
                    "com_id": "com_2",
                    "com_name": "示例科技",
                    "career_url": "https://jobs.example.com",
                    "json_config": {
                        "urls": {"shezhao_1": "https://jobs.example.com/social"},
                        "func_name": "gen_1",
                    },
                    "is_active": 1,
                },
            ]
            with make_session_factory(engine)() as session:
                first = migrate_pin_company_rows(session, rows, parser_root=parser_root)
                second = migrate_pin_company_rows(session, rows, parser_root=parser_root)
                companies = list(session.scalars(select(RecruitmentCompany)))
                channels = list(session.scalars(select(DataSource).order_by(DataSource.code)))
            engine.dispose()
            self.assertEqual(1, len(companies))
            self.assertEqual(3, len(channels))
            self.assertEqual(["campus", "internship", "social"], sorted(item.channel_type for item in channels))
            self.assertTrue(all(item.configuration_status == "ready" for item in channels))
            self.assertEqual(3, first["channels_created"])
            self.assertEqual(0, second["channels_created"])
            self.assertEqual(3, second["channels_updated"])


if __name__ == "__main__":
    unittest.main()
