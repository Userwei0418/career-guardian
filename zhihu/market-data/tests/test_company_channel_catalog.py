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
from market_data.schemas import SourceDefinition, SourceSnapshot


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

    def test_repair_strategy_overrides_selectors_and_runtime_limits(self) -> None:
        source = SourceDefinition(
            code="test-repair-strategy",
            name="测试修复候选",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={
                "platform_type": "zhiye",
                "pagination": {"mode": "auto"},
                "detail_selectors": [".old-detail"],
                "_collection_strategy": {
                    "matched_selector": ".repaired-list",
                    "item_selectors": [".repaired-item"],
                    "detail_selectors": [".repaired-detail"],
                    "pagination": {
                        "mode": "next_button",
                        "max_records": 17,
                        "max_rounds": 3,
                        "stable_rounds": 1,
                        "scroll_pause_ms": 321,
                        "next_selectors": [".repaired-next"],
                    },
                },
            },
        )
        adapter = CompanyChannelAdapter()
        self.assertEqual(
            [".repaired-list", ".repaired-item"],
            adapter._selector_candidates(source)[:2],
        )
        settings = adapter._pagination_settings(source)
        self.assertEqual("next_button", settings["mode"])
        self.assertEqual(17, settings["max_records"])
        self.assertEqual(3, settings["max_batches"])
        self.assertEqual(321, settings["wait_milliseconds"])
        self.assertEqual([".repaired-next"], settings["next_selectors"])
        self.assertEqual(
            [".repaired-detail", ".old-detail"],
            adapter._detail_selector_candidates(source),
        )

    def test_repair_item_selector_is_used_by_the_real_extraction_path(self) -> None:
        source = SourceDefinition(
            code="test-repair-extraction",
            name="测试修复提取",
            adapter_type="company_channel",
            base_url="https://jobs.example.com/list",
            allowed_hosts=["jobs.example.com"],
            config={
                "_collection_strategy": {
                    "matched_selector": "article.repaired-job-card",
                    "item_selectors": ["article.repaired-job-card"],
                    "detail_selectors": ["main.job-detail"],
                    "pagination": {"mode": "single_page"},
                }
            },
        )
        html = """
        <article class="repaired-job-card" data-job-id="job-42">
          <a href="/position/job-42"><h3 class="job-title">声明式解析工程师</h3></a>
          <span class="location">上海</span><time>发布于 2026-08-18</time>
        </article>
        """
        items, mode = CompanyChannelAdapter()._extract_items(source, html)
        self.assertEqual("declarative_dom:article.repaired-job-card", mode)
        self.assertEqual(1, len(items))
        self.assertEqual("声明式解析工程师", items[0]["announcement_name"])
        self.assertEqual("/position/job-42", items[0]["link"])
        self.assertEqual("job-42", items[0]["job_id"])
        self.assertEqual("上海", items[0]["hd_loc"])

    def test_run_options_override_pagination_and_detail_delay(self) -> None:
        source = SourceDefinition(
            code="test-run-options",
            name="测试单次采集参数",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            min_interval_seconds=3,
            config={
                "pagination": {"mode": "single_page", "max_records": 10},
                "_runtime": {
                    "run_options": {
                        "max_pages": 4,
                        "max_records": 35,
                        "detail_delay_min_seconds": 5,
                        "detail_delay_max_seconds": 9,
                    }
                },
            },
        )
        adapter = CompanyChannelAdapter()
        settings = adapter._pagination_settings(source)
        self.assertEqual("auto", settings["mode"])
        self.assertEqual(4, settings["max_batches"])
        self.assertEqual(35, settings["max_records"])
        self.assertEqual((5_000, 9_000), adapter._detail_pacing(source))

    def test_explicit_empty_state_is_successful_zero_record_snapshot(self) -> None:
        class Locator:
            def __init__(self, selector: str) -> None:
                self.selector = selector

            def count(self) -> int:
                return int(self.selector == ".empty-title")

            def nth(self, _index: int):
                return self

            def is_visible(self) -> bool:
                return True

            def inner_text(self) -> str:
                return "抱歉，暂时没有您要找的职位~" if self.selector == ".empty-title" else ""

        class Page:
            def locator(self, selector: str) -> Locator:
                return Locator(selector)

        source = SourceDefinition(
            code="test-empty-source",
            name="测试官网空状态",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
        )
        adapter = CompanyChannelAdapter()
        empty_state = adapter._detect_confirmed_empty_state(Page(), source)
        self.assertEqual(".empty-title", empty_state["selector"])
        result = adapter.parse(
            source,
            SourceSnapshot(
                source_url=source.base_url,
                content_type="application/json",
                content={"items": []},
                http_status=200,
                transport_metadata={"source_empty": True},
            ),
        )
        self.assertEqual([], result.records)

    def test_detail_capture_falls_back_to_rendered_main_and_keeps_full_html(self) -> None:
        class Locator:
            def __init__(self, selector: str) -> None:
                self.selector = selector
                self.first = self

            def count(self) -> int:
                return int(self.selector == "main")

            def is_visible(self) -> bool:
                return self.selector == "main"

            def inner_text(self) -> str:
                return (
                    "车辆资产运营实习生\n职位描述\n负责业务数据分析与复盘。\n"
                    "负责整理经营指标并定期输出业务报告。\n"
                    "职位要求\n本科及以上学历，熟悉 Excel 与数据分析，具备清晰的沟通能力。"
                )

        class Page:
            frames = []

            def content(self) -> str:
                return "<html><body><main><h1>车辆资产运营实习生</h1><p>完整正文</p></main></body></html>"

            def locator(self, selector: str) -> Locator:
                return Locator(selector)

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

        source = SourceDefinition(
            code="test-detail-fallback",
            name="测试详情回退",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
            config={"detail_selector_timeout_milliseconds": 250},
        )
        captured = CompanyChannelAdapter()._capture_rendered_detail(
            Page(), source, ["div.atsx-layout"]
        )
        self.assertEqual("fallback_selector", captured["capture_mode"])
        self.assertEqual("main", captured["selector"])
        self.assertIn("完整正文", captured["html"])
        self.assertIn("职位要求", captured["text"])

    def test_missing_link_can_open_detail_by_visible_title(self) -> None:
        detail_text = (
            "岗位职责\n1. 负责车辆资产运营与数据分析，持续优化运营流程。\n"
            "任职要求\n1. 本科及以上学历，具备良好的沟通与问题分析能力。"
        )

        class TextLocator:
            def __init__(self, page) -> None:
                self.page = page

            def count(self) -> int:
                return 1

            def nth(self, _index: int):
                return self

            def is_visible(self) -> bool:
                return True

            def click(self, timeout: int) -> None:
                self.page.url = "https://jobs.example.com/#/detail/job-1"
                self.page.detail = True

            def evaluate(self, _script: str) -> str:
                return ""

        class DetailLocator:
            def __init__(self, page) -> None:
                self.page = page
                self.first = self

            def count(self) -> int:
                return 1 if self.page.detail else 0

            def is_visible(self) -> bool:
                return self.page.detail

            def inner_text(self) -> str:
                return detail_text if self.page.detail else ""

        class Page:
            def __init__(self) -> None:
                self.url = "https://jobs.example.com/#/jobs"
                self.detail = False
                self.frames = [self]

            def get_by_text(self, _title: str, exact: bool = True):
                return TextLocator(self)

            def locator(self, _selector: str):
                return DetailLocator(self)

            def content(self) -> str:
                return (
                    f"<html><main>{detail_text}</main></html>"
                    if self.detail
                    else "<html><main><div>车辆资产运营实习生</div></main></html>"
                )

            def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

            def wait_for_load_state(self, *_args, **_kwargs) -> None:
                return None

            def goto(self, url: str, **_kwargs) -> None:
                self.url = url
                self.detail = False

        page = Page()
        context = type("Context", (), {"pages": [page]})()
        source = SourceDefinition(
            code="title-click",
            name="标题点击测试",
            adapter_type="company_channel",
            base_url="https://jobs.example.com/#/jobs",
            allowed_hosts=["jobs.example.com"],
            config={"minimum_detail_characters": 40},
        )
        captured, detail_url = CompanyChannelAdapter()._capture_detail_by_title_click(
            page,
            context,
            source,
            {"announcement_name": "车辆资产运营实习生"},
            ["main"],
        )
        self.assertIsNotNone(captured)
        assert captured is not None
        self.assertEqual("https://jobs.example.com/#/detail/job-1", detail_url)
        self.assertEqual("title_click:configured_selector", captured["capture_mode"])
        self.assertIn("本科及以上", captured["text"])
        self.assertEqual("https://jobs.example.com/#/jobs", page.url)

    def test_explicit_semantic_job_links_survive_dynamic_class_names(self) -> None:
        html = """
        <a class="new-card-hash" href="#/job/c548b35e-18ab-46fe-afce-5a6e1d361cff">
          <h3 class="job-title-next-build">AI全栈开发工程师</h3>
          <span>MJ026459</span><span>发布于 2026-06-23</span>
        </a>
        """
        source = SourceDefinition(
            code="test-58-semantic",
            name="58同城 · 校园招聘",
            adapter_type="company_channel",
            base_url="https://campus.58.com/campus-recruitment/58/150953/#/jobs",
            allowed_hosts=["campus.58.com"],
            config={
                "compat_parser": "gen_50256",
                "job_link_selectors": ["a[href*='#/job/']"],
            },
        )
        items, mode = CompanyChannelAdapter()._extract_items(source, html)
        self.assertEqual("semantic_links", mode)
        self.assertEqual(1, len(items))
        self.assertEqual("AI全栈开发工程师", items[0]["announcement_name"])
        self.assertEqual("MJ026459", items[0]["job_id"])
        self.assertEqual("2026-06-23", items[0]["publish_time"])
        self.assertIn("#/job/c548b35e", items[0]["link"])

    def test_hotjob_card_id_builds_declarative_detail_url(self) -> None:
        html = """
        <div id="6a61ffe1e05c792b8ecc3c17" class="list-card-item1">
          <span class="top-label">区域业务主管8853</span>
          <span class="pub-time">发布时间：2026-07-23</span>
          <div class="pos-summary">BNC上海办</div>
        </div>
        """
        source = SourceDefinition(
            code="test-hotjob-template",
            name="健合 · 社会招聘",
            adapter_type="company_channel",
            base_url="https://wecruit.hotjob.cn/SU62ac460fbef57c0f6fa4b738/pb/social.html",
            allowed_hosts=["wecruit.hotjob.cn"],
            config={
                "compat_parser": "gen_00003",
                "detail_url_template": (
                    "https://wecruit.hotjob.cn/SU62ac460fbef57c0f6fa4b738/pb/"
                    "posDetail.html?postId={post_id}&postType={post_type}"
                ),
                "detail_post_type": "society",
            },
        )
        items = CompanyChannelAdapter()._extract_compat_items(source, html)
        self.assertEqual("6a61ffe1e05c792b8ecc3c17", items[0]["post_id"])
        detail_url = CompanyChannelAdapter._detail_url_from_template(source, items[0])
        self.assertEqual(
            "https://wecruit.hotjob.cn/SU62ac460fbef57c0f6fa4b738/pb/"
            "posDetail.html?postId=6a61ffe1e05c792b8ecc3c17&postType=society",
            detail_url,
        )

    def test_parse_stores_rendered_html_as_raw_evidence(self) -> None:
        source = SourceDefinition(
            code="test-raw-html",
            name="测试详情原文",
            adapter_type="company_channel",
            base_url="https://jobs.example.com",
            allowed_hosts=["jobs.example.com"],
        )
        snapshot = SourceSnapshot(
            source_url="https://jobs.example.com",
            content_type="application/json",
            content={
                "items": [
                    {
                        "announcement_name": "数据分析实习生",
                        "_source_url": "https://jobs.example.com/1",
                        "_detail_text": "职位描述 负责数据分析 职位要求 本科",
                        "_detail_html": "<html><body>完整渲染详情</body></html>",
                    }
                ]
            },
        )
        record = CompanyChannelAdapter().parse(source, snapshot).records[0]
        self.assertIn("完整渲染详情", record.raw_text or "")
        self.assertNotIn("_detail_html", record.raw_payload or {})
        self.assertIn("_detail_text", record.raw_payload or {})

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

    def test_incremental_collection_stops_after_repeated_published_overlap_batches(self) -> None:
        class Adapter(CompanyChannelAdapter):
            def _extract_items(self, _source, html: str):
                return json.loads(html), "test"

        class Page:
            pages = [
                [{"id": "new-1", "publish_time": "2026-08-16"}],
                [{"id": "old-1", "publish_time": "2026-08-07"}],
                [{"id": "old-2", "publish_time": "2026年8月6日 发布"}],
                [{"id": "must-not-read", "publish_time": "2026-08-05"}],
            ]

            def __init__(self) -> None:
                self.index = 0
                self.first = self

            def content(self) -> str:
                return json.dumps(self.pages[self.index], ensure_ascii=False)

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
            code="test-published-boundary",
            name="测试发布时间边界",
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
                    "published_high_watermark": "2026-08-15T00:00:00",
                    "published_overlap_days": 7,
                    "published_boundary_streak": 2,
                },
            },
        )
        items, _, metadata = Adapter()._collect_paginated_items(Page(), source)
        self.assertEqual(["new-1", "old-1", "old-2"], [item["id"] for item in items])
        self.assertEqual(
            "published_overlap_boundary_reached",
            metadata["pagination_stop_reason"],
        )
        self.assertEqual("2026-08-08T00:00:00", metadata["published_boundary_cutoff"])
        self.assertEqual(2, metadata["published_overlap_streak"])

    def test_incremental_collection_never_uses_undated_batch_as_published_boundary(self) -> None:
        class Adapter(CompanyChannelAdapter):
            def _extract_items(self, _source, html: str):
                return json.loads(html), "test"

        class Page:
            pages = [
                [{"id": "old-1", "publish_time": "2026-08-07"}],
                [{"id": "unknown-date"}],
                [{"id": "old-2", "publish_time": "2026-08-06"}],
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
                return int(self.selector == ".next" and self.index < 2)

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
            code="test-undated-boundary",
            name="测试无日期批次",
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
                    "published_high_watermark": "2026-08-15T00:00:00",
                    "published_overlap_days": 7,
                    "published_boundary_streak": 2,
                },
            },
        )
        items, _, metadata = Adapter()._collect_paginated_items(Page(), source)
        self.assertEqual(3, len(items))
        self.assertEqual("next_button_not_found", metadata["pagination_stop_reason"])
        self.assertEqual(1, metadata["published_overlap_streak"])

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
