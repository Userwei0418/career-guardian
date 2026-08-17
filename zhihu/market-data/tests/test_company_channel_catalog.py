from __future__ import annotations

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
