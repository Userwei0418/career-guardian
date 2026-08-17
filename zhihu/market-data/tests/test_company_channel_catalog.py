from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from market_data.adapters.company_channel import CompanyChannelAdapter, validate_compat_parser_source
from market_data.company_channel_catalog import (
    CATALOG_PATH,
    COMPAT_PARSER_ROOT,
    load_company_channel_catalog,
    migrate_company_channel_catalog,
)
from market_data.fingerprints import business_payload_hash
from market_data.db import RawBase, make_engine, make_session_factory
from market_data.models.raw import DataSource, RecruitmentCompany
from market_data.schemas import SourceDefinition


class CompanyChannelCatalogTests(unittest.TestCase):
    def test_packaged_catalog_and_parsers_are_self_contained(self) -> None:
        catalog = load_company_channel_catalog()
        self.assertTrue(CATALOG_PATH.is_file())
        self.assertTrue(COMPAT_PARSER_ROOT.is_dir())
        self.assertGreater(len(catalog["companies"]), 600)
        self.assertGreater(len(list(COMPAT_PARSER_ROOT.glob("gen_*.py"))), 500)
        self.assertNotIn("Pin/", CATALOG_PATH.read_text(encoding="utf-8"))

    def test_company_rows_are_grouped_and_split_into_channels_idempotently(self) -> None:
        catalog = {
            "schema_version": "career-guardian-company-channels-v1",
            "companies": [
                {
                    "company_code": "com_1",
                    "company_name": "示例科技",
                    "career_url": "https://jobs.example.com",
                    "logo_url": "",
                    "enabled": True,
                    "configuration": {
                        "urls": {
                            "xiaozhao_1": "https://jobs.example.com/campus",
                            "shixi_1": "https://jobs.example.com/intern",
                        },
                        "func_name": "gen_50524",
                        "detail_selector": ".job-detail",
                    },
                },
                {
                    "company_code": "com_2",
                    "company_name": "示例科技",
                    "career_url": "https://jobs.example.com",
                    "logo_url": "",
                    "enabled": True,
                    "configuration": {
                        "urls": {"shezhao_1": "https://jobs.example.com/social"},
                        "func_name": "gen_50524",
                    },
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tempdir:
            engine = make_engine(f"sqlite:///{Path(tempdir) / 'raw.sqlite3'}")
            RawBase.metadata.create_all(engine)
            with make_session_factory(engine)() as session:
                first = migrate_company_channel_catalog(session, catalog)
                second = migrate_company_channel_catalog(session, catalog)
                companies = list(session.scalars(select(RecruitmentCompany)))
                channels = list(session.scalars(select(DataSource).order_by(DataSource.code)))
            engine.dispose()
        self.assertEqual(1, len(companies))
        self.assertEqual(3, len(channels))
        self.assertTrue(all(item.code.startswith("channel-") for item in channels))
        self.assertTrue(all(item.adapter_type == "company_channel" for item in channels))
        self.assertEqual(["campus", "internship", "social"], sorted(item.channel_type for item in channels))
        self.assertTrue(all(item.configuration_status == "ready" for item in channels))
        self.assertEqual(3, first["channels_created"])
        self.assertEqual(0, second["channels_created"])
        self.assertEqual(3, second["channels_updated"])

    def test_zhiye_parser_uses_semantic_class_prefixes(self) -> None:
        html = """
        <div class="style__STJobList-editor__sc-7hlpxf-0 changedHash">
          <div class="style__STListItem-editor__sc-10r1nhd-0 newHash">
            <div class="style__STJobTitle-editor__sc-10r1nhd-4 titleHash">高级IE工程师</div>
            <div class="style__STLabelText-editor__sc-10r1nhd-13 one">社会招聘</div>
            <div class="style__STLabelText-editor__sc-10r1nhd-13 two">全职</div>
            <div class="style__STLabelText-editor__sc-10r1nhd-13 three">福建省·厦门市</div>
            <div class="style__STJobTime-editor__sc-10r1nhd-16 timeHash">2026-08-14 发布</div>
            <div class="style__STDetailPanel-editor__sc-10r1nhd-17 hidden">
              <div class="style__STDetailTitle-editor__sc-10r1nhd-18">工作职责</div>
              <div class="style__STDetailDesc-editor__sc-10r1nhd-19">1. 负责产线规划与改善。\n2. 推动标准流程落地。</div>
              <div class="style__STDetailTitle-editor__sc-10r1nhd-18">任职资格</div>
              <div class="style__STDetailDesc-editor__sc-10r1nhd-19">本科及以上学历，工业工程相关专业优先。</div>
            </div>
          </div>
        </div>
        """
        items = CompanyChannelAdapter._extract_zhiye(html)
        self.assertEqual(1, len(items))
        self.assertEqual("高级IE工程师", items[0]["announcement_name"])
        self.assertEqual("福建省·厦门市", items[0]["hd_loc"])
        self.assertEqual("2026-08-14", items[0]["publish_time"])
        self.assertIn("产线规划", items[0]["responsibilities"])
        self.assertIn("本科及以上", items[0]["requirements"])
        self.assertIn("工作职责", items[0]["_detail_text"])
        self.assertEqual("embedded_panel", items[0]["_detail_strategy"])

    def test_zhiye_reported_total_is_read_from_job_heading(self) -> None:
        self.assertEqual(
            101,
            CompanyChannelAdapter._zhiye_reported_total("全部职位（共 101 个）"),
        )
        self.assertEqual(
            1234,
            CompanyChannelAdapter._zhiye_reported_total("职位(共 1,234 个)"),
        )
        self.assertIsNone(CompanyChannelAdapter._zhiye_reported_total("职位列表"))

    def test_zhiye_infinite_scroll_loads_until_reported_total(self) -> None:
        class Locator:
            def __init__(self, page, body: bool = False) -> None:
                self.page = page
                self.body = body

            def inner_text(self) -> str:
                return "全部职位（共 101 个）" if self.body else ""

            def count(self) -> int:
                return self.page.counts[self.page.index]

        class Page:
            counts = [20, 40, 60, 80, 100, 101]

            def __init__(self) -> None:
                self.index = 0

            def locator(self, selector: str) -> Locator:
                return Locator(self, body=selector == "body")

            def evaluate(self, _script: str) -> None:
                self.index = min(self.index + 1, len(self.counts) - 1)

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

        source = SourceDefinition(
            code="test-zhiye",
            name="测试北森渠道",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={"max_records": 500, "max_scroll_rounds": 30},
        )
        result = CompanyChannelAdapter()._load_all_zhiye_items(Page(), source)
        self.assertEqual(101, result["records_discovered"])
        self.assertEqual(6, result["batches_loaded"])
        self.assertEqual("reported_total_reached", result["pagination_stop_reason"])

    def test_generic_pagination_supports_scroll_load_more_and_next_page(self) -> None:
        class Adapter(CompanyChannelAdapter):
            def _extract_items(self, _source, html: str):
                return json.loads(html), "test"

        class Page:
            def __init__(self, mode: str, cumulative: bool) -> None:
                self.mode = mode
                self.cumulative = cumulative
                self.index = 0
                self.pages = [
                    [{"id": "job-1"}, {"id": "job-2"}],
                    [{"id": "job-3"}, {"id": "job-4"}],
                    [{"id": "job-5"}],
                ]
                self.first = self

            def content(self) -> str:
                items = (
                    [item for page in self.pages[: self.index + 1] for item in page]
                    if self.cumulative
                    else self.pages[self.index]
                )
                return json.dumps(items)

            def locator(self, selector: str):
                self.selector = selector
                return self

            def count(self) -> int:
                if self.selector == "body":
                    return 1
                expected = ".more" if self.mode == "load_more" else ".next"
                return int(self.selector == expected and self.index < len(self.pages) - 1)

            def inner_text(self) -> str:
                return ""

            def is_visible(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def click(self, timeout: int) -> None:
                self.index = min(self.index + 1, len(self.pages) - 1)

            def evaluate(self, _script: str) -> None:
                self.index = min(self.index + 1, len(self.pages) - 1)

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

        adapter = Adapter()
        for mode, cumulative in (
            ("infinite_scroll", True),
            ("load_more", True),
            ("next_button", False),
        ):
            source = SourceDefinition(
                code=f"test-{mode}",
                name="测试通用翻页",
                adapter_type="company_channel",
                base_url="https://jobs.example.com",
                allowed_hosts=["jobs.example.com"],
                config={
                    "pagination": {
                        "mode": mode,
                        "load_more_selectors": [".more"],
                        "next_selectors": [".next"],
                        "max_batches": 10,
                        "stable_rounds": 1,
                    }
                },
            )
            items, _, metadata = adapter._collect_paginated_items(
                Page(mode, cumulative), source
            )
            self.assertEqual(5, len(items), mode)
            self.assertEqual(
                {
                    "infinite_scroll": "no_more_items",
                    "load_more": "load_more_not_found",
                    "next_button": "next_button_not_found",
                }[mode],
                metadata["pagination_stop_reason"],
                mode,
            )

    def test_incremental_collection_stops_at_stable_identifier_overlap(self) -> None:
        class Adapter(CompanyChannelAdapter):
            def _extract_items(self, _source, html: str):
                return json.loads(html), "test"

        class Page:
            pages = [
                [{"id": "new-1"}, {"id": "new-2"}],
                [{"id": "known-1"}],
                [{"id": "known-2"}],
                [{"id": "must-not-read"}],
            ]

            def __init__(self) -> None:
                self.index = 0
                self.first = self

            def content(self) -> str:
                return json.dumps(self.pages[self.index])

            def locator(self, selector: str):
                self.selector = selector
                return self

            def count(self) -> int:
                return int(self.selector == ".next" and self.index < 3)

            def inner_text(self) -> str:
                return ""

            def is_visible(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def click(self, timeout: int) -> None:
                self.index += 1

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

        source = SourceDefinition(
            code="test-incremental",
            name="测试增量边界",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={
                "pagination": {
                    "mode": "next_button",
                    "next_selectors": [".next"],
                    "stable_rounds": 1,
                },
                "_collection": {
                    "mode": "incremental",
                    "known_external_ids": ["known-1", "known-2"],
                    "known_batch_streak": 2,
                },
            },
        )
        items, _, metadata = Adapter()._collect_paginated_items(Page(), source)
        self.assertEqual(
            ["new-1", "new-2", "known-1", "known-2"],
            [item["id"] for item in items],
        )
        self.assertEqual(
            "incremental_boundary_reached", metadata["pagination_stop_reason"]
        )
        self.assertEqual(2, metadata["unchanged_known_streak"])

    def test_incremental_collection_does_not_stop_for_changed_known_item(self) -> None:
        class Adapter(CompanyChannelAdapter):
            def _extract_items(self, _source, html: str):
                return json.loads(html), "test"

        class Page:
            pages = [
                [{"id": "known-1", "title": "更新后的岗位"}],
                [{"id": "known-2", "title": "未变化岗位"}],
            ]

            def __init__(self) -> None:
                self.index = 0
                self.first = self

            def content(self) -> str:
                return json.dumps(self.pages[self.index])

            def locator(self, selector: str):
                self.selector = selector
                return self

            def count(self) -> int:
                return int(self.selector == ".next" and self.index < 1)

            def inner_text(self) -> str:
                return ""

            def is_visible(self) -> bool:
                return True

            def is_enabled(self) -> bool:
                return True

            def click(self, timeout: int) -> None:
                self.index += 1

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

        source = SourceDefinition(
            code="test-changed-known",
            name="测试已知岗位更新",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={
                "pagination": {
                    "mode": "next_button",
                    "next_selectors": [".next"],
                    "stable_rounds": 1,
                },
                "_collection": {
                    "mode": "incremental",
                    "known_external_ids": ["known-1", "known-2"],
                    "known_content_hashes": {
                        "known-1": "outdated",
                        "known-2": business_payload_hash(
                            {"id": "known-2", "title": "未变化岗位"}
                        ),
                    },
                    "known_batch_streak": 2,
                },
            },
        )
        items, _, metadata = Adapter()._collect_paginated_items(Page(), source)
        self.assertEqual(["known-1", "known-2"], [item["id"] for item in items])
        self.assertEqual("next_button_not_found", metadata["pagination_stop_reason"])
        self.assertEqual(1, metadata["unchanged_known_streak"])

    def test_compat_parser_path_cannot_be_overridden_outside_package(self) -> None:
        source = SourceDefinition(
            code="test-source",
            name="测试渠道",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={
                "platform_type": "custom-rendered",
                "compat_parser": "../../outside",
                "parser_root": "/tmp/should-not-be-used",
            },
        )
        with self.assertRaisesRegex(Exception, "名称不合法"):
            CompanyChannelAdapter().validate_configuration(source)

    def test_compat_parser_rejects_network_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            parser_path = Path(tempdir) / "unsafe.py"
            parser_path.write_text("import requests\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "未允许的依赖"):
                validate_compat_parser_source(parser_path)


if __name__ == "__main__":
    unittest.main()
