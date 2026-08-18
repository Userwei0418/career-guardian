from __future__ import annotations

import unittest
from types import SimpleNamespace

from market_data.management import _is_raw_only_source
from market_data.school_channel_catalog import (
    CATALOG_PATH,
    COMPAT_PARSER_ROOT,
    load_school_channel_catalog,
    _promotion_mapping,
)


class SchoolChannelCatalogTests(unittest.TestCase):
    def test_packaged_school_catalog_is_self_contained(self) -> None:
        catalog = load_school_channel_catalog()
        text = CATALOG_PATH.read_text(encoding="utf-8")
        self.assertGreater(len(catalog["schools"]), 300)
        self.assertGreater(len(list(COMPAT_PARSER_ROOT.glob("gen_*.py"))), 80)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("qzclawler/", text)
        self.assertTrue(
            all(
                (school.get("configuration") or {}).get("urls")
                for school in catalog["schools"]
            )
        )

    def test_catalog_declares_unified_job_pipeline(self) -> None:
        catalog = load_school_channel_catalog()
        urls = [
            url
            for school in catalog["schools"]
            for url in ((school.get("configuration") or {}).get("urls") or {}).values()
        ]
        self.assertTrue(urls)
        self.assertTrue(all(isinstance(url, str) and url for url in urls))
        mapping = _promotion_mapping()
        self.assertIn("company_name", mapping)
        self.assertIn("title", mapping)
        self.assertIn("description", mapping)
        self.assertIn("detail_url", mapping)

    def test_school_source_never_uses_legacy_raw_only_branch(self) -> None:
        source = SimpleNamespace(source_kind="school_announcement", config={"raw_only": True})
        self.assertFalse(_is_raw_only_source(source))
        company = SimpleNamespace(source_kind="company_channel", config={"raw_only": True})
        self.assertTrue(_is_raw_only_source(company))


if __name__ == "__main__":
    unittest.main()
