from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import random
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime
from market_data.company_channel_catalog import COMPAT_PARSER_ROOT
from market_data.detail_content import html_to_detail_text, split_detail_sections
from market_data.errors import (
    AdapterParseError,
    AdapterTransportError,
    DetailContentError,
    DetailNavigationError,
    ListParseError,
    SourceEntryError,
)
from market_data.fingerprints import business_payload_hash
from market_data.schemas import AdapterResult, RawRecordInput, SourceDefinition, SourceSnapshot
from market_data.services.network_access import resolve_network_access


PLATFORM_LIST_SELECTORS = {
    "zhiye": [
        '[class*="STJobList-editor"]',
        '[class*="STListItem-editor"]',
    ],
}

SAFE_COMPAT_IMPORTS = {"json", "bs4", "re", "urllib.parse", "datetime"}
SCHOOL_COMPAT_PARSER_ROOT = (
    Path(__file__).resolve().parent.parent / "assets" / "school_channels" / "compat_parsers"
)
COMPAT_PARSER_NAMESPACES = {
    "company": COMPAT_PARSER_ROOT,
    "school": SCHOOL_COMPAT_PARSER_ROOT,
}


def validate_compat_parser_source(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise AdapterParseError(f"兼容解析器无法安全读取：{path.stem}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules = {node.module or ""}
        else:
            continue
        if not modules.issubset(SAFE_COMPAT_IMPORTS):
            raise AdapterParseError(f"兼容解析器包含未允许的依赖：{path.stem}")


def _as_selector_list(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


class CompanyChannelAdapter(SourceAdapter):
    """Career Guardian's own browser collector for configured company channels."""

    adapter_type = "company_channel"
    version = "1.2"

    DEFAULT_LOAD_MORE_SELECTORS = (
        'button:has-text("加载更多")',
        'a:has-text("加载更多")',
        '[class*="load-more"]',
        '[class*="loadMore"]',
    )
    DEFAULT_NEXT_SELECTORS = (
        'button:has-text("下一页")',
        'a:has-text("下一页")',
        'li[title="下一页"]:not([aria-disabled="true"])',
        '[aria-label*="下一页"]',
        'button[aria-label*="Next"]',
        'a[aria-label*="Next"]',
        '.atsx-pagination-next:not(.atsx-pagination-disabled)',
        '.ant-pagination-next:not(.ant-pagination-disabled)',
        '.next:not(.disabled)',
    )
    DEFAULT_EMPTY_STATE_SELECTORS = (
        ".empty-title",
        ".empty-text",
        '[class*="empty-title"]',
        '[class*="emptyText"]',
        '[class*="empty-state"]',
        '[class*="emptyState"]',
    )
    DEFAULT_EMPTY_STATE_TEXTS = (
        "暂时没有您要找的职位",
        "暂无职位",
        "暂无招聘职位",
        "暂无在招职位",
        "没有找到相关职位",
        "当前没有职位",
    )
    DEFAULT_DETAIL_FALLBACK_SELECTORS = (
        "main",
        "article",
        '[role="main"]',
        "body",
    )

    @staticmethod
    def _zhiye_reported_total(text: str) -> int | None:
        for pattern in (
            r"全部职位[（(]共\s*([\d,]+)\s*个[）)]",
            r"职位[（(]共\s*([\d,]+)\s*个[）)]",
        ):
            match = re.search(pattern, text)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    def _load_all_zhiye_items(self, page, source: SourceDefinition) -> dict[str, object]:
        """Drive Beisen/Zhiye infinite scroll until the list is complete or safely capped."""

        item_selector = '[class*="STListItem-editor"]'
        max_records = max(1, min(int(source.config.get("max_records", 500)), 500))
        max_scroll_rounds = max(
            1, min(int(source.config.get("max_scroll_rounds", 30)), 100)
        )
        scroll_wait = max(
            200, min(int(source.config.get("scroll_wait_milliseconds", 650)), 3_000)
        )
        reported_total = self._zhiye_reported_total(page.locator("body").inner_text())
        discovered = page.locator(item_selector).count()
        batches_loaded = 1 if discovered else 0
        stable_rounds = 0
        stop_reason = "initial_page_only"

        for _ in range(max_scroll_rounds):
            if reported_total is not None and discovered >= reported_total:
                stop_reason = "reported_total_reached"
                break
            if discovered >= max_records:
                stop_reason = "max_records_reached"
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(scroll_wait)
            current = page.locator(item_selector).count()
            if current > discovered:
                discovered = current
                batches_loaded += 1
                stable_rounds = 0
            else:
                stable_rounds += 1
                if stable_rounds >= 2:
                    stop_reason = "no_more_items"
                    break
        else:
            stop_reason = "max_scroll_rounds_reached"

        return {
            "pagination_mode": "infinite_scroll",
            "batches_loaded": batches_loaded,
            "reported_total": reported_total,
            "records_discovered": discovered,
            "pagination_stop_reason": stop_reason,
            "max_records": max_records,
        }

    @staticmethod
    def _zhiye_detail_sections(node) -> tuple[str, str]:
        """Read the structured detail panel, including content hidden before expansion."""

        responsibilities: list[str] = []
        requirements: list[str] = []
        panels = node.select('[class*="STDetailPanel-editor"]') or [node]
        responsibility_titles = ("工作职责", "岗位职责", "职位职责", "职位描述", "工作内容")
        requirement_titles = ("任职资格", "任职要求", "职位要求", "招聘要求", "岗位要求")
        for panel in panels:
            for title_node in panel.select('[class*="STDetailTitle-editor"]'):
                heading = title_node.get_text(" ", strip=True)
                description_node = title_node.find_next_sibling(
                    lambda tag: tag.name and any(
                        "STDetailDesc-editor" in class_name
                        for class_name in (tag.get("class") or [])
                    )
                )
                if description_node is None:
                    continue
                text = description_node.get_text("\n", strip=True)
                if not text:
                    continue
                if any(marker in heading for marker in responsibility_titles):
                    responsibilities.append(text)
                elif any(marker in heading for marker in requirement_titles):
                    requirements.append(text)
        return "\n".join(dict.fromkeys(responsibilities)), "\n".join(dict.fromkeys(requirements))

    def _compat_parser_path(self, source: SourceDefinition) -> Path | None:
        function_name = str(source.config.get("compat_parser") or "").strip()
        if not function_name:
            return None
        if not function_name.replace("_", "").isalnum():
            raise AdapterParseError("兼容解析器名称不合法")
        namespace = str(source.config.get("compat_parser_namespace") or "company").strip()
        root = COMPAT_PARSER_NAMESPACES.get(namespace)
        if root is None:
            raise AdapterParseError("兼容解析器命名空间不合法")
        root = root.resolve()
        path = (root / f"{function_name}.py").resolve()
        if root not in path.parents or not path.is_file():
            raise AdapterParseError(f"职护内置兼容解析器不可用：{function_name}")
        validate_compat_parser_source(path)
        return path

    def validate_configuration(self, source: SourceDefinition) -> None:
        platform_type = str(source.config.get("platform_type") or "").strip()
        if platform_type in PLATFORM_LIST_SELECTORS:
            return
        strategy = source.config.get("_collection_strategy")
        if isinstance(strategy, dict) and (
            _as_selector_list(strategy.get("matched_selector"))
            or _as_selector_list(strategy.get("item_selectors"))
        ):
            return
        if self._compat_parser_path(source) is None:
            raise AdapterParseError("该渠道既没有平台解析规则，也没有职护内置兼容解析器")

    def _selector_candidates(self, source: SourceDefinition) -> list[str]:
        result: list[str] = []
        platform_type = str(source.config.get("platform_type") or "").strip()
        reusable_strategy = source.config.get("_collection_strategy")
        strategy_selectors: list[str] = []
        if isinstance(reusable_strategy, dict):
            strategy_selectors = [
                *_as_selector_list(reusable_strategy.get("matched_selector")),
                *_as_selector_list(reusable_strategy.get("item_selectors")),
            ]
        for selector in [
            *strategy_selectors,
            *PLATFORM_LIST_SELECTORS.get(platform_type, []),
            *_as_selector_list(source.config.get("list_selectors")),
            *_as_selector_list(source.config.get("table_selectors")),
            *_as_selector_list(source.config.get("table_selector")),
        ]:
            if selector not in result:
                result.append(selector)
        return result

    @staticmethod
    def _detail_selector_candidates(source: SourceDefinition) -> list[str]:
        reusable_strategy = source.config.get("_collection_strategy")
        result = (
            _as_selector_list(reusable_strategy.get("detail_selectors"))
            if isinstance(reusable_strategy, dict)
            else []
        )
        for selector in _as_selector_list(source.config.get("detail_selectors")):
            if selector not in result:
                result.append(selector)
        return result

    @staticmethod
    def _detail_pacing(source: SourceDefinition) -> tuple[int, int]:
        """Return the administrator-configured pause range between detail views.

        The legacy Pin crawler waited a random 3-10 seconds between records.
        Keep that operational safeguard while allowing a slower source-level
        minimum to take precedence.  Rendering waits remain separate: they wait
        for content, while this pause controls request cadence.
        """

        runtime = source.config.get("_runtime") or {}
        run_options = runtime.get("run_options") if isinstance(runtime, dict) else {}
        run_options = run_options if isinstance(run_options, dict) else {}
        source_minimum = max(1, int(source.min_interval_seconds)) * 1_000
        requested_minimum = run_options.get("detail_delay_min_seconds")
        requested_maximum = run_options.get("detail_delay_max_seconds")
        minimum = max(
            source_minimum,
            min(
                int(requested_minimum) * 1_000
                if requested_minimum is not None
                else int(source.config.get("detail_interval_min_milliseconds", source_minimum)),
                60_000,
            ),
        )
        maximum = max(
            minimum,
            min(
                int(requested_maximum) * 1_000
                if requested_maximum is not None
                else int(source.config.get("detail_interval_max_milliseconds", 10_000)),
                120_000,
            ),
        )
        return minimum, maximum

    @classmethod
    def _detect_confirmed_empty_state(
        cls, page, source: SourceDefinition
    ) -> dict[str, str] | None:
        """Recognize an explicit upstream zero-result state without masking parser faults."""

        configured_selectors = _as_selector_list(source.config.get("empty_state_selectors"))
        configured_texts = _as_selector_list(source.config.get("empty_state_texts"))
        markers = tuple(configured_texts or cls.DEFAULT_EMPTY_STATE_TEXTS)
        for selector in [*configured_selectors, *cls.DEFAULT_EMPTY_STATE_SELECTORS]:
            try:
                locator = page.locator(selector)
                for index in range(min(locator.count(), 20)):
                    candidate = locator.nth(index)
                    if not candidate.is_visible():
                        continue
                    text = re.sub(r"\s+", "", candidate.inner_text()).strip()
                    if text and any(re.sub(r"\s+", "", marker) in text for marker in markers):
                        return {"selector": selector, "text": text[:200]}
            except Exception:
                continue
        try:
            body_text = re.sub(r"\s+", "", page.locator("body").inner_text())
            if re.search(r"在招职位[（(]?0个[）)]?", body_text):
                return {"selector": "body", "text": "在招职位0个"}
        except Exception:
            pass
        return None

    def _wait_with_cancel(self, page, milliseconds: int) -> None:
        remaining = max(0, milliseconds)
        while remaining:
            self.raise_if_cancelled()
            chunk = min(250, remaining)
            page.wait_for_timeout(chunk)
            remaining -= chunk
        self.raise_if_cancelled()

    def _wait_for_any_selector(self, page, selectors: list[str], timeout_milliseconds: int) -> tuple[str | None, list[str]]:
        deadline = time.monotonic() + timeout_milliseconds / 1000
        invalid: list[str] = []
        while time.monotonic() < deadline:
            self.raise_if_cancelled()
            for selector in selectors:
                if selector in invalid:
                    continue
                try:
                    locator = page.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        return selector, invalid
                except Exception:
                    invalid.append(selector)
            self._wait_with_cancel(page, 250)
        return None, invalid

    @staticmethod
    def _visible_locator_text(page, selector: str) -> str:
        try:
            locator = page.locator(selector)
            if not locator.count() or not locator.first.is_visible():
                return ""
            return str(locator.first.inner_text() or "").strip()
        except Exception:
            return ""

    def _capture_rendered_detail(
        self,
        page,
        source: SourceDefinition,
        detail_selectors: list[str],
    ) -> dict[str, object]:
        """Capture immutable rendered HTML, then derive detail text with safe fallbacks."""

        full_html = str(page.content() or "")
        minimum_chars = max(
            40, min(int(source.config.get("minimum_detail_characters", 80)), 2_000)
        )
        selector_timeout = max(
            250,
            min(
                int(source.config.get("detail_selector_timeout_milliseconds", 2_000)),
                10_000,
            ),
        )
        matched_selector, invalid_selectors = self._wait_for_any_selector(
            page, detail_selectors, selector_timeout
        ) if detail_selectors else (None, [])
        if matched_selector:
            text = self._visible_locator_text(page, matched_selector)
            if len(text) >= minimum_chars:
                return {
                    "html": full_html,
                    "text": text,
                    "strategy": "detail_page",
                    "capture_mode": "configured_selector",
                    "selector": matched_selector,
                    "invalid_selectors": invalid_selectors,
                }

        fallback_selectors = [
            *_as_selector_list(source.config.get("detail_fallback_selectors")),
            *self.DEFAULT_DETAIL_FALLBACK_SELECTORS,
        ]
        for selector in dict.fromkeys(fallback_selectors):
            text = self._visible_locator_text(page, selector)
            if len(text) >= minimum_chars:
                return {
                    "html": full_html,
                    "text": text,
                    "strategy": "detail_page",
                    "capture_mode": "fallback_selector",
                    "selector": selector,
                    "invalid_selectors": invalid_selectors,
                }

        for frame in list(getattr(page, "frames", []) or [])[1:]:
            for selector in dict.fromkeys([*detail_selectors, *fallback_selectors]):
                try:
                    locator = frame.locator(selector)
                    if not locator.count() or not locator.first.is_visible():
                        continue
                    text = str(locator.first.inner_text() or "").strip()
                except Exception:
                    continue
                if len(text) >= minimum_chars:
                    return {
                        "html": full_html,
                        "text": text,
                        "strategy": "detail_page",
                        "capture_mode": "iframe_selector",
                        "selector": selector,
                        "invalid_selectors": invalid_selectors,
                    }

        full_text = html_to_detail_text(full_html)
        if len(full_text) >= minimum_chars:
            return {
                "html": full_html,
                "text": full_text,
                "strategy": "detail_page",
                "capture_mode": "full_rendered_html",
                "selector": "",
                "invalid_selectors": invalid_selectors,
            }
        return {
            "html": full_html,
            "text": "",
            "strategy": "missing",
            "capture_mode": "missing",
            "selector": "",
            "invalid_selectors": invalid_selectors,
        }

    @staticmethod
    def _detail_url_allowed(source: SourceDefinition, detail_url: str) -> bool:
        host = (urlparse(detail_url).hostname or "").lower()
        configured = _as_selector_list(source.config.get("detail_allowed_hosts"))
        allowed = {str(item).strip().lower() for item in [*source.allowed_hosts, *configured]}
        return bool(host and host in allowed)

    @staticmethod
    def _item_title(item: dict) -> str:
        return str(
            item.get("announcement_name")
            or item.get("title")
            or item.get("job_name")
            or ""
        ).strip()

    @staticmethod
    def _title_locator(page, title: str):
        if not title:
            return None
        try:
            exact = page.get_by_text(title, exact=True)
            for index in range(min(exact.count(), 10)):
                candidate = exact.nth(index)
                if candidate.is_visible():
                    return candidate
        except Exception:
            pass
        try:
            partial = page.get_by_text(title, exact=False)
            for index in range(min(partial.count(), 10)):
                candidate = partial.nth(index)
                if candidate.is_visible():
                    return candidate
        except Exception:
            return None
        return None

    def _recover_detail_link_from_title(
        self, page, base_url: str, item: dict
    ) -> str:
        locator = self._title_locator(page, self._item_title(item))
        if locator is None:
            return ""
        try:
            link = locator.evaluate(
                "node => { const anchor = node.closest('a') || node.querySelector('a'); "
                "return anchor ? (anchor.href || anchor.getAttribute('href') || '') : ''; }"
            )
        except Exception:
            return ""
        return urljoin(base_url, str(link or "").strip()) if link else ""

    @staticmethod
    def _detail_url_from_template(source: SourceDefinition, item: dict) -> str:
        """Build a declarative detail URL from IDs exposed by a list card.

        Some rendered platforms, notably Hotjob, expose a stable ``postId`` on
        the list card but do not render an anchor.  Only two escaped values are
        supported; configs cannot inject code or arbitrary format expressions.
        """

        template = str(source.config.get("detail_url_template") or "").strip()
        post_id = str(
            item.get("post_id")
            or item.get("postId")
            or item.get("id")
            or ""
        ).strip()
        if not template or not post_id:
            return ""
        if any(marker in template for marker in ("{post_id.", "{post_type.")):
            raise AdapterParseError("详情 URL 模板包含不允许的格式表达式")
        post_type = str(source.config.get("detail_post_type") or "society").strip()
        detail_url = template.replace("{post_id}", quote(post_id, safe=""))
        detail_url = detail_url.replace("{post_type}", quote(post_type, safe=""))
        if "{" in detail_url or "}" in detail_url:
            raise AdapterParseError("详情 URL 模板包含不支持的占位符")
        return detail_url

    @staticmethod
    def _apply_detail_capture(
        item: dict,
        captured: dict[str, object],
        matched_detail_selectors: list[str],
    ) -> bool:
        item["_detail_html"] = str(captured.get("html") or "")
        item["_detail_capture_mode"] = str(captured.get("capture_mode") or "missing")
        detail_text = str(captured.get("text") or "").strip()
        if not detail_text:
            item["_detail_warning"] = "detail_content_not_found"
            return False
        item["_detail_text"] = detail_text
        item["_detail_strategy"] = str(captured.get("strategy") or "detail_page")
        item["_detail_selector"] = str(captured.get("selector") or "")
        sections = split_detail_sections(detail_text)
        for key in ("responsibilities", "requirements", "benefits"):
            if sections.get(key) and not item.get(key):
                item[key] = sections[key]
        detail_selector = str(captured.get("selector") or "")
        if detail_selector and detail_selector not in matched_detail_selectors:
            matched_detail_selectors.append(detail_selector)
        return True

    def _capture_detail_by_title_click(
        self,
        page,
        context,
        source: SourceDefinition,
        item: dict,
        detail_selectors: list[str],
    ) -> tuple[dict[str, object] | None, str]:
        """Open a detail view when the list parser did not expose an href."""

        title = self._item_title(item)
        locator = self._title_locator(page, title)
        if locator is None:
            return None, ""
        list_url = str(page.url)
        before_html = str(page.content() or "")
        pages_before = list(getattr(context, "pages", []) or [])
        try:
            locator.click(timeout=3_000)
            page.wait_for_timeout(
                max(
                    250,
                    min(
                        int(source.config.get("detail_settle_milliseconds", 1_500)),
                        10_000,
                    ),
                )
            )
            pages_after = list(getattr(context, "pages", []) or [])
            new_pages = [candidate for candidate in pages_after if candidate not in pages_before]
            target = new_pages[-1] if new_pages else page
            try:
                target.wait_for_load_state("domcontentloaded", timeout=3_000)
            except Exception:
                pass
            target_url = str(target.url)
            after_html = str(target.content() or "")
            if target is page and target_url == list_url and after_html == before_html:
                return None, ""
            captured = self._capture_rendered_detail(target, source, detail_selectors)
            captured["capture_mode"] = f"title_click:{captured.get('capture_mode') or 'missing'}"
            captured["strategy"] = "title_click"
            return captured, target_url
        finally:
            pages_after = list(getattr(context, "pages", []) or [])
            for candidate in pages_after:
                if candidate not in pages_before and candidate is not page:
                    try:
                        candidate.close()
                    except Exception:
                        pass
            if str(page.url) != list_url:
                try:
                    page.goto(
                        list_url,
                        wait_until="domcontentloaded",
                        timeout=source.timeout_seconds * 1_000,
                    )
                    page.wait_for_timeout(500)
                except Exception:
                    pass

    @staticmethod
    def _extract_zhiye(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict] = []
        for node in soup.select('[class*="STListItem-editor"]'):
            title_node = node.select_one('[class*="STJobTitle-editor"]')
            title = title_node.get_text(" ", strip=True) if title_node else ""
            if not title:
                continue
            time_node = node.select_one('[class*="STJobTime-editor"]')
            published = time_node.get_text(" ", strip=True).replace("发布", "").strip() if time_node else ""
            labels = [
                item.get_text(" ", strip=True)
                for item in node.select('[class*="STLabelText-editor"]')
                if item.get_text(" ", strip=True)
            ]
            link_node = node.select_one("a[href]")
            responsibilities, requirements = CompanyChannelAdapter._zhiye_detail_sections(node)
            detail_parts = []
            if responsibilities:
                detail_parts.extend(["工作职责", responsibilities])
            if requirements:
                detail_parts.extend(["任职资格", requirements])
            location = next(
                (
                    label
                    for label in reversed(labels)
                    if any(marker in label for marker in ("省", "市", "区", "县"))
                ),
                "",
            )
            items.append(
                {
                    "announcement_name": title,
                    "publish_time": published,
                    "link": link_node.get("href", "") if link_node else "",
                    "hd_loc": location,
                    "employment_label": labels[1] if len(labels) > 1 else "",
                    "recruitment_label": labels[0] if labels else "",
                    "labels": labels,
                    "responsibilities": responsibilities,
                    "requirements": requirements,
                    "_detail_text": "\n".join(detail_parts),
                    "_detail_strategy": "embedded_panel" if detail_parts else "missing",
                }
            )
        return items

    def _retry_missing_zhiye_details(self, page, items: list[dict]) -> None:
        """Click an item and re-read its DOM when the initial snapshot lacks detail text."""

        job_nodes = page.locator('[class*="STListItem-editor"]')
        count = job_nodes.count()
        for index, item in enumerate(items):
            if item.get("responsibilities") or item.get("requirements") or index >= count:
                continue
            try:
                job_node = job_nodes.nth(index)
                clickable = job_node.locator('[class*="STListItemContent-editor"]')
                (clickable.first if clickable.count() else job_node).click(timeout=2_000)
                page.wait_for_timeout(250)
                item_html = job_node.evaluate("node => node.outerHTML")
                reparsed = self._extract_zhiye(str(item_html))
                if reparsed:
                    for key in (
                        "responsibilities",
                        "requirements",
                        "_detail_text",
                        "_detail_strategy",
                    ):
                        if reparsed[0].get(key):
                            item[key] = reparsed[0][key]
                if item.get("responsibilities") or item.get("requirements"):
                    item["_detail_strategy"] = "expanded_panel"
                else:
                    item["_detail_warning"] = "detail_content_not_found_after_expand"
            except Exception as exc:
                item["_detail_warning"] = f"detail_expand_failed:{type(exc).__name__}"

    def _extract_compat_items(self, source: SourceDefinition, html: str) -> list[dict]:
        path = self._compat_parser_path(source)
        if path is None:
            return []
        spec = importlib.util.spec_from_file_location(f"career_guardian_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise AdapterParseError(f"无法加载职护兼容解析器：{path.stem}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parser = getattr(module, "extract_table_from_html", None)
        if not callable(parser):
            raise AdapterParseError(f"兼容解析器缺少 extract_table_from_html：{path.stem}")
        with tempfile.NamedTemporaryFile(suffix=".json") as output:
            parser(html, output.name)
            output.seek(0)
            try:
                payload = json.load(output)
            except json.JSONDecodeError as exc:
                raise AdapterParseError(f"兼容解析器返回了无效 JSON：{path.stem}") from exc
        if not isinstance(payload, list):
            raise AdapterParseError("兼容解析器结果必须是列表")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _extract_declarative_items(
        source: SourceDefinition, html: str
    ) -> tuple[list[dict], str]:
        """Execute an approved declarative strategy against repeated job cards.

        Repair candidates used to be consulted only while waiting for the page;
        the actual parser ignored ``item_selectors``.  This keeps the strategy
        code-free while making replay and production use the same extraction
        path.
        """

        strategy = source.config.get("_collection_strategy")
        if not isinstance(strategy, dict):
            return [], ""
        selectors: list[str] = []
        for selector in [
            *_as_selector_list(strategy.get("matched_selector")),
            *_as_selector_list(strategy.get("item_selectors")),
        ]:
            if selector not in selectors:
                selectors.append(selector)
        if not selectors:
            return [], ""

        soup = BeautifulSoup(html, "html.parser")
        best_items: list[dict] = []
        best_selector = ""
        for selector in selectors:
            try:
                nodes = soup.select(selector)
            except Exception as exc:
                raise AdapterParseError(f"声明式岗位选择器无效：{selector}") from exc
            extracted: list[dict] = []
            seen: set[str] = set()
            for node in nodes[:2_000]:
                anchor = node if getattr(node, "name", None) == "a" else node.select_one(
                    "a[href*='job'], a[href*='position'], a[href*='career'], a[href]"
                )
                title_node = node.select_one(
                    "[data-job-title], [class*='job-title'], [class*='jobTitle'], "
                    "[class*='position-title'], [class*='positionTitle'], "
                    "[class*='title'], [class*='Title'], h1, h2, h3, h4"
                )
                title = ""
                if title_node is not None:
                    title = str(title_node.get("data-job-title") or "").strip()
                    title = title or title_node.get_text(" ", strip=True)
                if not title and anchor is not None:
                    title = str(
                        anchor.get("data-job-title")
                        or anchor.get("title")
                        or anchor.get("aria-label")
                        or ""
                    ).strip()
                    title = title or anchor.get_text(" ", strip=True)
                text = node.get_text("\n", strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if not title:
                    title = next(
                        (
                            line
                            for line in lines
                            if 2 <= len(line) <= 240
                            and not re.fullmatch(r"(?:查看|详情|申请|投递|展开)", line)
                        ),
                        "",
                    )
                title = re.sub(r"\s+", " ", title).strip()[:240]
                if len(title) < 2:
                    continue
                href = str(anchor.get("href") or "").strip() if anchor is not None else ""
                job_id = str(
                    node.get("data-job-id")
                    or node.get("data-position-id")
                    or node.get("data-id")
                    or node.get("id")
                    or ""
                ).strip()
                identity = href or job_id or f"{title}|{text[:300]}"
                if identity in seen:
                    continue
                seen.add(identity)
                location_node = node.select_one(
                    "[data-location], [class*='location'], [class*='Location'], "
                    "[class*='city'], [class*='City']"
                )
                location = ""
                if location_node is not None:
                    location = str(location_node.get("data-location") or "").strip()
                    location = location or location_node.get_text(" ", strip=True)
                published_match = re.search(
                    r"(?:发布(?:于|时间)?|更新(?:于|日期)?)?\s*"
                    r"(20\d{2}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)",
                    text,
                )
                extracted.append(
                    {
                        "announcement_name": title,
                        "link": href,
                        "job_id": job_id,
                        "hd_loc": location,
                        "publish_time": (
                            published_match.group(1) if published_match else ""
                        ),
                    }
                )
            if len(extracted) > len(best_items):
                best_items = extracted
                best_selector = selector
        return best_items, best_selector

    @staticmethod
    def _extract_semantic_job_links(source: SourceDefinition, html: str) -> list[dict]:
        """Extract job cards through explicit semantic link selectors.

        This is a safe fallback for redesigned sites whose old generated class
        names no longer match.  It runs only when the channel explicitly
        declares ``job_link_selectors`` and never guesses arbitrary links.
        """

        selectors = _as_selector_list(source.config.get("job_link_selectors"))
        if not selectors:
            return []
        soup = BeautifulSoup(html, "html.parser")
        nodes = []
        for selector in selectors:
            try:
                nodes.extend(soup.select(selector))
            except Exception as exc:
                raise AdapterParseError(f"岗位链接选择器无效：{selector}") from exc
        result: list[dict] = []
        seen: set[str] = set()
        for node in nodes:
            href = str(node.get("href") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            text = node.get_text("\n", strip=True)
            if not text:
                continue
            title_node = node.select_one(
                "h1, h2, h3, h4, [class*='title'], [class*='Title'], [data-job-title]"
            )
            title = title_node.get_text(" ", strip=True) if title_node else ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not title:
                title = next(
                    (
                        line
                        for line in lines
                        if len(line) >= 2
                        and not re.search(r"(?:发布|更新|\d{4}[-/.年])", line)
                    ),
                    "",
                )
            if not title:
                continue
            published_match = re.search(
                r"(?:发布(?:于|时间)?|更新(?:于|日期)?)?\s*"
                r"(20\d{2}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)",
                text,
            )
            job_code_match = re.search(r"\b(?:MJ|SJ|J)[A-Z0-9-]{4,}\b", text, re.I)
            result.append(
                {
                    "announcement_name": title,
                    "publish_time": published_match.group(1) if published_match else "",
                    "job_id": job_code_match.group(0) if job_code_match else "",
                    "link": href,
                }
            )
        return result

    def _extract_items(self, source: SourceDefinition, html: str) -> tuple[list[dict], str]:
        items, matched_selector = self._extract_declarative_items(source, html)
        if items:
            return items, f"declarative_dom:{matched_selector}"
        platform_type = str(source.config.get("platform_type") or "").strip()
        if platform_type == "zhiye":
            items = self._extract_zhiye(html)
            if items:
                return items, "platform:zhiye"
        items = self._extract_compat_items(source, html)
        if items:
            return items, "compat"
        items = self._extract_semantic_job_links(source, html)
        if items:
            return items, "semantic_links"
        return [], "none"

    @staticmethod
    def _external_id_for_item(item: dict) -> str:
        external_id = item.get("id") or item.get("job_id") or item.get("announcement_id")
        if external_id:
            return str(external_id)[:255]
        identity = "|".join(
            str(item.get(key) or "")
            for key in ("announcement_name", "hd_loc", "hd_dept", "link")
        )
        return hashlib.sha1(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _published_at_for_item(item: dict) -> datetime | None:
        """Read a trustworthy source publication time for incremental boundaries.

        Publication time is an auxiliary cursor only. Unknown or partial dates
        deliberately return ``None`` so an undated batch can never make the
        collector stop early.
        """

        for key in (
            "publish_time",
            "published_at",
            "publish_date",
            "release_time",
            "released_at",
            "create_time",
        ):
            value = item.get(key)
            parsed = parse_datetime(value)
            if parsed is None and value:
                text = str(value).strip().replace("发布", "").strip()
                match = re.search(
                    r"(?P<year>\d{4})\s*[年/.-]\s*(?P<month>\d{1,2})\s*[月/.-]\s*(?P<day>\d{1,2})\s*日?",
                    text,
                )
                if match:
                    try:
                        parsed = datetime(
                            int(match.group("year")),
                            int(match.group("month")),
                            int(match.group("day")),
                        )
                    except ValueError:
                        parsed = None
            if parsed is not None:
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
        return None

    def _pagination_settings(self, source: SourceDefinition) -> dict[str, object]:
        configured = source.config.get("pagination")
        pagination = dict(configured) if isinstance(configured, dict) else {}
        configured_mode = str(pagination.get("mode") or "").strip()
        reusable_strategy = source.config.get("_collection_strategy")
        reusable_pagination = (
            reusable_strategy.get("pagination")
            if isinstance(reusable_strategy, dict)
            else None
        )
        runtime = source.config.get("_runtime") or {}
        run_options = runtime.get("run_options") if isinstance(runtime, dict) else {}
        run_options = run_options if isinstance(run_options, dict) else {}
        if configured_mode in {"", "auto"} and isinstance(reusable_pagination, dict):
            allowed_reusable_keys = {
                "mode",
                "max_records",
                "max_rounds",
                "load_more_selectors",
                "next_selectors",
                "stable_rounds",
                "wait_milliseconds",
                "scroll_pause_ms",
            }
            pagination = {
                **pagination,
                **{
                    key: value
                    for key, value in reusable_pagination.items()
                    if key in allowed_reusable_keys
                },
            }
        platform_type = str(source.config.get("platform_type") or "").strip()
        mode = str(pagination.get("mode") or "").strip()
        if not mode:
            if platform_type == "zhiye":
                mode = "infinite_scroll"
            elif str(source.config.get("click_load_more") or "").upper() == "Y":
                mode = "load_more"
            elif pagination.get("next_selector") or source.config.get("next_selector"):
                mode = "next_button"
            else:
                mode = "auto"
        requested_pages = run_options.get("max_pages")
        if requested_pages is not None and int(requested_pages) > 1:
            mode = "auto"
        if mode not in {"auto", "single_page", "infinite_scroll", "load_more", "next_button"}:
            raise AdapterParseError(f"不支持的页面采集模式：{mode}")
        max_records = max(
            1,
            min(
                int(
                    run_options.get(
                        "max_records",
                        pagination.get("max_records", source.config.get("max_records", 500)),
                    )
                ),
                2_000,
            ),
        )
        max_batches = max(
            1,
            min(
                int(
                    run_options.get(
                        "max_pages",
                        pagination.get(
                            "max_batches",
                            pagination.get(
                                "max_pages",
                                pagination.get(
                                    "max_rounds",
                                    source.config.get("max_scroll_rounds", 30),
                                ),
                            ),
                        ),
                    )
                ),
                200,
            ),
        )
        wait_milliseconds = max(
            200,
            min(
                int(
                    pagination.get(
                        "wait_milliseconds",
                        pagination.get(
                            "scroll_pause_ms",
                            source.config.get("scroll_wait_milliseconds", 650),
                        ),
                    )
                ),
                5_000,
            ),
        )
        return {
            **pagination,
            "mode": mode,
            "max_records": max_records,
            "max_batches": max_batches,
            "wait_milliseconds": wait_milliseconds,
            "stable_rounds": max(1, min(int(pagination.get("stable_rounds", 2)), 5)),
            "load_more_selectors": _as_selector_list(
                pagination.get("load_more_selectors")
                or pagination.get("load_more_selector")
                or source.config.get("load_more_selector")
            ),
            "next_selectors": _as_selector_list(
                pagination.get("next_selectors")
                or pagination.get("next_selector")
                or source.config.get("next_selector")
            ),
        }

    @staticmethod
    def _first_visible(page, selectors: list[str]):
        for selector in selectors:
            try:
                locator = page.locator(selector)
                if locator.count() and locator.first.is_visible() and locator.first.is_enabled():
                    return locator.first, selector
            except Exception:
                continue
        return None, None

    def _advance_collection_page(
        self,
        page,
        mode: str,
        settings: dict[str, object],
    ) -> tuple[bool, str, str]:
        """Advance one list batch without executing migrated arbitrary Python."""

        wait_milliseconds = int(settings["wait_milliseconds"])
        actual_mode = mode
        selector = ""
        if mode == "auto":
            locator, selector = self._first_visible(
                page,
                [
                    *list(settings.get("load_more_selectors") or []),
                    *self.DEFAULT_LOAD_MORE_SELECTORS,
                ],
            )
            if locator is not None:
                actual_mode = "load_more"
            else:
                locator, selector = self._first_visible(
                    page,
                    [
                        *list(settings.get("next_selectors") or []),
                        *self.DEFAULT_NEXT_SELECTORS,
                    ],
                )
                actual_mode = "next_button" if locator is not None else "infinite_scroll"
        if actual_mode == "load_more":
            locator, selector = self._first_visible(
                page,
                [
                    *list(settings.get("load_more_selectors") or []),
                    *self.DEFAULT_LOAD_MORE_SELECTORS,
                ],
            )
            if locator is None:
                return False, actual_mode, "load_more_not_found"
            locator.click(timeout=3_000)
            page.wait_for_timeout(wait_milliseconds)
            return True, actual_mode, f"clicked:{selector}"
        if actual_mode == "next_button":
            locator, selector = self._first_visible(
                page,
                [
                    *list(settings.get("next_selectors") or []),
                    *self.DEFAULT_NEXT_SELECTORS,
                ],
            )
            if locator is None:
                return False, actual_mode, "next_button_not_found"
            locator.click(timeout=3_000)
            page.wait_for_timeout(wait_milliseconds)
            return True, actual_mode, f"clicked:{selector}"
        if actual_mode == "infinite_scroll":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(wait_milliseconds)
            return True, actual_mode, "scrolled_to_bottom"
        return False, actual_mode, "single_page"

    def _collect_paginated_items(
        self,
        page,
        source: SourceDefinition,
    ) -> tuple[list[dict], str, dict[str, object]]:
        settings = self._pagination_settings(source)
        requested_mode = str(settings["mode"])
        collection = source.config.get("_collection")
        runtime = dict(collection) if isinstance(collection, dict) else {}
        collection_mode = str(runtime.get("mode") or "full")
        known_ids = {str(item) for item in (runtime.get("known_external_ids") or []) if item}
        known_content_hashes = {
            str(key): str(value)
            for key, value in dict(runtime.get("known_content_hashes") or {}).items()
            if key and value
        }
        require_known_batch_streak = max(1, int(runtime.get("known_batch_streak", 2)))
        published_high_watermark = parse_datetime(runtime.get("published_high_watermark"))
        if published_high_watermark is not None and published_high_watermark.tzinfo is not None:
            published_high_watermark = published_high_watermark.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        published_overlap_days = max(0, min(int(runtime.get("published_overlap_days", 7)), 90))
        published_boundary_streak = max(
            1,
            min(
                int(runtime.get("published_boundary_streak", require_known_batch_streak)),
                10,
            ),
        )
        published_cutoff = (
            published_high_watermark - timedelta(days=published_overlap_days)
            if published_high_watermark is not None
            else None
        )
        reported_total = None
        if str(source.config.get("platform_type") or "") == "zhiye":
            reported_total = self._zhiye_reported_total(page.locator("body").inner_text())

        merged: dict[str, dict] = {}
        parser_modes: list[str] = []
        batches_loaded = 0
        stable_rounds = 0
        actual_modes: list[str] = []
        stop_reason = "single_page"
        action_detail = ""
        unchanged_known_streak = 0
        published_overlap_streak = 0

        for batch_index in range(int(settings["max_batches"])):
            self.raise_if_cancelled()
            items, parser_mode = self._extract_items(source, page.content())
            if not items and batch_index == 0:
                self.report_progress(
                    "job_discovery",
                    status="completed",
                    pages_loaded=0,
                    discovered=0,
                    reported_total=reported_total,
                    continuing=False,
                    stop_reason="initial_page_empty",
                )
                return [], parser_mode, {
                    "pagination_mode": requested_mode,
                    "collection_mode": collection_mode,
                    "batches_loaded": 0,
                    "reported_total": reported_total,
                    "records_discovered": 0,
                    "pagination_stop_reason": "initial_page_empty",
                }
            if parser_mode not in parser_modes:
                parser_modes.append(parser_mode)
            batch_new_ids: list[str] = []
            newly_exposed_items: list[tuple[str, dict]] = []
            for item in items:
                identity = self._external_id_for_item(item)
                if identity not in merged:
                    batch_new_ids.append(identity)
                    newly_exposed_items.append((identity, item))
                    merged[identity] = item
                elif len(str(item.get("_detail_text") or "")) > len(
                    str(merged[identity].get("_detail_text") or "")
                ):
                    merged[identity] = item
            if batch_index == 0 or batch_new_ids:
                batches_loaded += 1
            self.report_progress(
                "job_discovery",
                status="running",
                pages_loaded=batches_loaded,
                discovered=len(merged),
                reported_total=reported_total,
                continuing=True,
            )
            identified_items = newly_exposed_items
            batch_is_known_and_unchanged = bool(identified_items) and all(
                identity in known_ids
                and (
                    not known_content_hashes.get(identity)
                    or known_content_hashes[identity] == business_payload_hash(item)
                )
                for identity, item in identified_items
            )
            if (
                collection_mode == "incremental"
                and known_ids
                and batch_is_known_and_unchanged
            ):
                unchanged_known_streak += 1
                if unchanged_known_streak >= require_known_batch_streak:
                    stop_reason = "incremental_boundary_reached"
                    break
            else:
                unchanged_known_streak = 0
            published_values = [
                self._published_at_for_item(item) for _, item in identified_items
            ]
            batch_is_before_published_boundary = bool(identified_items) and all(
                value is not None and published_cutoff is not None and value <= published_cutoff
                for value in published_values
            )
            if (
                collection_mode == "incremental"
                and published_cutoff is not None
                and batch_is_before_published_boundary
            ):
                published_overlap_streak += 1
                if published_overlap_streak >= published_boundary_streak:
                    stop_reason = "published_overlap_boundary_reached"
                    break
            else:
                published_overlap_streak = 0
            if reported_total is not None and len(merged) >= reported_total:
                stop_reason = "reported_total_reached"
                break
            if len(merged) >= int(settings["max_records"]):
                stop_reason = "max_records_reached"
                break
            if requested_mode == "single_page":
                stop_reason = "single_page"
                break
            advanced, actual_mode, action_detail = self._advance_collection_page(
                page, requested_mode, settings
            )
            actual_modes.append(actual_mode)
            if not advanced:
                stop_reason = action_detail
                break
            before = len(merged)
            previous_ids = set(merged)
            next_items, _ = self._extract_items(source, page.content())
            next_ids = {self._external_id_for_item(item) for item in next_items}
            change_timeout_milliseconds = max(
                1_000,
                min(
                    int(
                        settings.get(
                            "change_timeout_milliseconds",
                            source.config.get("pagination_change_timeout_milliseconds", 5_000),
                        )
                    ),
                    15_000,
                ),
            )
            change_deadline = time.monotonic() + change_timeout_milliseconds / 1_000
            while next_ids.issubset(previous_ids) and time.monotonic() < change_deadline:
                self._wait_with_cancel(page, 250)
                next_items, _ = self._extract_items(source, page.content())
                next_ids = {self._external_id_for_item(item) for item in next_items}
            if next_ids.issubset(set(merged)) and len(merged) == before:
                stable_rounds += 1
                if stable_rounds >= int(settings["stable_rounds"]):
                    stop_reason = "no_more_items"
                    break
            else:
                stable_rounds = 0
        else:
            stop_reason = "max_batches_reached"

        result = list(merged.values())[: int(settings["max_records"])]
        self.report_progress(
            "job_discovery",
            status="completed",
            pages_loaded=batches_loaded,
            discovered=len(result),
            reported_total=reported_total,
            continuing=False,
            stop_reason=stop_reason,
        )
        effective_mode = next((item for item in actual_modes if item != "auto"), requested_mode)
        return result, "+".join(parser_modes) or "none", {
            "pagination_mode": effective_mode,
            "pagination_requested_mode": requested_mode,
            "collection_mode": collection_mode,
            "batches_loaded": batches_loaded,
            "reported_total": reported_total,
            "records_discovered": len(merged),
            "pagination_stop_reason": stop_reason,
            "pagination_action": action_detail,
            "max_records": int(settings["max_records"]),
            "known_checkpoint_size": len(known_ids),
            "known_content_hash_count": len(known_content_hashes),
            "known_batch_streak": require_known_batch_streak,
            "unchanged_known_streak": unchanged_known_streak,
            "published_high_watermark": (
                published_high_watermark.isoformat() if published_high_watermark else None
            ),
            "published_overlap_days": published_overlap_days,
            "published_boundary_cutoff": (
                published_cutoff.isoformat() if published_cutoff else None
            ),
            "published_boundary_streak": published_boundary_streak,
            "published_overlap_streak": published_overlap_streak,
        }

    def capture_repair_evidence(self, source: SourceDefinition) -> dict[str, object]:
        """Capture bounded public DOM structure for a declarative repair proposal.

        This intentionally excludes cookies, storage, headers and full HTML. The
        resulting evidence can be shown to an LLM without exposing browser
        credentials or allowing it to author executable code.
        """

        self.assert_live_collection_allowed(source)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AdapterTransportError(
                "Playwright 未安装，请安装 requirements-playwright.txt"
            ) from exc
        network_access = resolve_network_access(source.config.get("network_policy"))
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, **network_access.launch_options
                )
                context = browser.new_context(
                    user_agent="CareerGuardianMarketBot/1.0",
                    **network_access.context_options,
                )
                page = context.new_page()
                response = page.goto(
                    str(source.base_url),
                    wait_until=source.config.get("wait_until", "domcontentloaded"),
                    timeout=source.timeout_seconds * 1000,
                )
                page.wait_for_timeout(
                    min(int(source.config.get("settle_milliseconds", 1500)), 5_000)
                )
                structure = page.evaluate(
                    r"""
                    () => {
                      const clean = (value, limit = 160) =>
                        String(value || '').replace(/\s+/g, ' ').trim().slice(0, limit);
                      const visible = (node) => {
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                      };
                      const signatures = new Map();
                      for (const node of document.querySelectorAll('body *')) {
                        if (!visible(node)) continue;
                        const classes = Array.from(node.classList || []).slice(0, 4);
                        if (!classes.length) continue;
                        const key = `${node.tagName.toLowerCase()}.${classes.join('.')}`;
                        const row = signatures.get(key) || {tag: node.tagName.toLowerCase(), classes, count: 0, sample_text: ''};
                        row.count += 1;
                        if (!row.sample_text) row.sample_text = clean(node.innerText || node.textContent);
                        signatures.set(key, row);
                      }
                      const repeated = Array.from(signatures.values())
                        .filter((item) => item.count >= 2 && item.sample_text)
                        .sort((a, b) => b.count - a.count)
                        .slice(0, 16);
                      const controls = Array.from(document.querySelectorAll('button,a,[role="button"]'))
                        .filter(visible)
                        .map((node) => ({
                          tag: node.tagName.toLowerCase(),
                          text: clean(node.innerText || node.textContent, 80),
                          aria_label: clean(node.getAttribute('aria-label'), 80),
                          classes: Array.from(node.classList || []).slice(0, 4),
                        }))
                        .filter((item) => item.text || item.aria_label)
                        .slice(0, 30);
                      return {repeated_elements: repeated, interactive_controls: controls};
                    }
                    """
                )
                evidence = {
                    "page_title": str(page.title() or "")[:200],
                    "final_url": str(page.url)[:1000],
                    "http_status": response.status if response else None,
                    "existing_item_selectors": self._selector_candidates(source)[:20],
                    "existing_detail_selectors": self._detail_selector_candidates(source)[:20],
                    "network_mode": network_access.summary.get("mode", "direct"),
                    **(structure if isinstance(structure, dict) else {}),
                }
                context.close()
                browser.close()
                return evidence
        except Exception as exc:
            raise AdapterTransportError(
                f"采集修复证据失败（{type(exc).__name__}）：{exc}"
            ) from exc

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        self.throttle(source)
        self.raise_if_cancelled()
        self.report_progress(
            "entry_validation", status="opening", url=str(source.base_url)
        )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AdapterTransportError(
                "Playwright 未安装，请安装 requirements-playwright.txt"
            ) from exc

        selectors = self._selector_candidates(source)
        runtime = source.config.get("_runtime") or {}
        browser_mode = str(
            runtime.get("browser_mode") or source.config.get("browser_mode") or ""
        ).strip().lower()
        if browser_mode not in {"headless", "visible"}:
            browser_mode = "visible" if source.config.get("headless") is False else "headless"
        headless = browser_mode == "headless"
        network_access = resolve_network_access(source.config.get("network_policy"))
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=headless, **network_access.launch_options
                )
                context = browser.new_context(
                    user_agent="CareerGuardianMarketBot/1.0",
                    **network_access.context_options,
                )
                page = context.new_page()
                response = page.goto(
                    str(source.base_url),
                    wait_until=source.config.get("wait_until", "domcontentloaded"),
                    timeout=source.timeout_seconds * 1000,
                )
                self.raise_if_cancelled()
                if response is not None and response.status >= 400:
                    raise SourceEntryError(
                        f"采集入口返回 HTTP {response.status}，入口可能已失效：{page.url}"
                    )
                self.report_progress(
                    "entry_validation",
                    status="completed",
                    http_status=response.status if response else None,
                    final_url=str(page.url),
                )
                self._wait_with_cancel(
                    page, int(source.config.get("settle_milliseconds", 1500))
                )
                matched_selector, invalid_selectors = self._wait_for_any_selector(
                    page, selectors, source.timeout_seconds * 1000
                )
                platform_type = str(source.config.get("platform_type") or "").strip()
                items, parser_mode, pagination_metadata = self._collect_paginated_items(
                    page, source
                )
                empty_state = None
                if not items:
                    empty_state = self._detect_confirmed_empty_state(page, source)
                    if empty_state is None:
                        sample = ", ".join(selectors[:3]) or "未配置"
                        raise ListParseError(
                            f"页面已打开，但没有解析到岗位；平台={source.config.get('platform_type') or 'custom'}，"
                            f"候选规则={sample}"
                        )
                if platform_type == "zhiye":
                    self._retry_missing_zhiye_details(page, items)
                limit = max(1, min(int(source.config.get("max_records", 500)), 2_000))
                items = items[:limit]
                self.report_progress(
                    "detail_capture",
                    status="running",
                    total=len(items),
                    completed=0,
                    succeeded=0,
                    failed=0,
                    remaining=len(items),
                )
                final_url = page.url
                status = response.status if response else None
                detail_selectors = self._detail_selector_candidates(source)
                matched_detail_selectors: list[str] = []
                detail_interval_min, detail_interval_max = self._detail_pacing(source)
                detail_pause_total = 0
                for index, item in enumerate(items):
                    self.raise_if_cancelled()
                    if index:
                        pause_milliseconds = random.randint(
                            detail_interval_min, detail_interval_max
                        )
                        self._wait_with_cancel(page, pause_milliseconds)
                        detail_pause_total += pause_milliseconds
                    link = str(item.get("link") or item.get("url") or "").strip()
                    if not link:
                        templated_link = self._detail_url_from_template(source, item)
                        if templated_link:
                            link = templated_link
                            item["link"] = templated_link
                            item["_detail_navigation"] = "declarative_url_template"
                    if not link:
                        recovered_link = self._recover_detail_link_from_title(
                            page, str(final_url), item
                        )
                        if recovered_link:
                            link = recovered_link
                            item["link"] = recovered_link
                            item["_detail_navigation"] = "title_anchor_recovered"
                    detail_url = urljoin(final_url, link) if link else final_url
                    item["_source_url"] = detail_url
                    if link and not self._detail_url_allowed(source, detail_url):
                        item["_detail_warning"] = "detail_host_not_allowed"
                    elif link:
                        detail_page = context.new_page()
                        try:
                            detail_response = detail_page.goto(
                                detail_url,
                                wait_until=str(
                                    source.config.get("detail_wait_until") or "domcontentloaded"
                                ),
                                timeout=source.timeout_seconds * 1000,
                            )
                            self.raise_if_cancelled()
                            self._wait_with_cancel(
                                detail_page,
                                max(
                                    250,
                                    min(
                                        int(source.config.get("detail_settle_milliseconds", 1_500)),
                                        10_000,
                                    ),
                                ),
                            )
                            if detail_response is not None and detail_response.status >= 400:
                                item["_detail_warning"] = f"detail_http_{detail_response.status}"
                            else:
                                captured = self._capture_rendered_detail(
                                    detail_page, source, detail_selectors
                                )
                                self._apply_detail_capture(
                                    item, captured, matched_detail_selectors
                                )
                        except Exception as exc:
                            item["_detail_warning"] = type(exc).__name__
                        finally:
                            detail_page.close()
                    elif not str(item.get("_detail_text") or "").strip() and bool(
                        source.config.get("title_click_fallback", True)
                    ):
                        try:
                            captured, clicked_url = self._capture_detail_by_title_click(
                                page, context, source, item, detail_selectors
                            )
                            if captured is None:
                                item["_detail_warning"] = "detail_navigation_not_found"
                            else:
                                item["_detail_navigation"] = "title_click"
                                if clicked_url:
                                    item["_source_url"] = clicked_url
                                self._apply_detail_capture(
                                    item, captured, matched_detail_selectors
                                )
                        except Exception as exc:
                            item["_detail_warning"] = (
                                f"detail_title_click_failed:{type(exc).__name__}"
                            )
                    item["_record_index"] = index
                    detail_succeeded = sum(
                        bool(str(row.get("_detail_text") or "").strip())
                        or bool(row.get("responsibilities") or row.get("requirements"))
                        for row in items[: index + 1]
                    )
                    completed = index + 1
                    self.report_progress(
                        "detail_capture",
                        status="completed" if completed >= len(items) else "running",
                        total=len(items),
                        completed=completed,
                        succeeded=detail_succeeded,
                        failed=completed - detail_succeeded,
                        remaining=max(0, len(items) - completed),
                    )
                context.close()
                browser.close()
            detail_complete_count = sum(
                bool(item.get("responsibilities") and item.get("requirements")) for item in items
            )
            detail_partial_count = sum(
                bool(item.get("responsibilities") or item.get("requirements")) for item in items
            ) - detail_complete_count
            detail_missing_count = len(items) - detail_complete_count - detail_partial_count
            detail_capture_count = sum(
                bool(str(item.get("_detail_text") or "").strip())
                or bool(item.get("responsibilities") or item.get("requirements"))
                for item in items
            )
            detail_capture_modes: dict[str, int] = {}
            detail_warning_counts: dict[str, int] = {}
            for item in items:
                capture_mode = str(item.get("_detail_capture_mode") or "missing")
                detail_capture_modes[capture_mode] = detail_capture_modes.get(capture_mode, 0) + 1
                warning = str(item.get("_detail_warning") or "").strip()
                if warning:
                    detail_warning_counts[warning] = detail_warning_counts.get(warning, 0) + 1
            if (
                items
                and bool(source.config.get("detail_capture_required", True))
                and not detail_capture_count
            ):
                warning_summary = ", ".join(
                    f"{key}={value}" for key, value in sorted(detail_warning_counts.items())
                ) or "no_detail_evidence"
                if any(str(item.get("_detail_html") or "").strip() for item in items):
                    raise DetailContentError(
                        "详情视图已打开，但所有正文提取均失败；"
                        f"任务不会伪装成功；{warning_summary}"
                    )
                raise DetailNavigationError(
                    "列表岗位已发现，但所有详情导航均失败；"
                    f"任务不会伪装成功；{warning_summary}"
                )
            observed_detail_modes = {
                str(item.get("_detail_strategy") or "").strip()
                for item in items
                if str(item.get("_detail_strategy") or "").strip()
            }
            if {"detail_page", "title_click"} & observed_detail_modes:
                # Title-click navigation still opens a standalone detail view.
                # Keep the persisted declarative mode compatible with strategy-v1;
                # the exact fallback remains visible in detail_capture_modes.
                detail_mode = "detail_page"
            else:
                detail_mode = next(
                    (
                        mode
                        for mode in ("expanded_panel", "embedded_panel")
                        if mode in observed_detail_modes
                    ),
                    "missing",
                )
            return SourceSnapshot(
                source_url=final_url,
                content_type="application/json",
                content={"items": items},
                http_status=status,
                transport_metadata={
                    "attempt": 1,
                    "mode": "live",
                    "engine": "career-guardian-browser-v1",
                    "browser_mode": browser_mode,
                    "browser_mode_source": runtime.get("browser_mode_source", "channel_default"),
                    "network_policy": network_access.summary,
                    "strategy_version": runtime.get("strategy_version"),
                    "strategy_source": runtime.get("strategy_source", "runtime_discovery"),
                    "matched_selector": matched_selector,
                    "invalid_selector_count": len(invalid_selectors),
                    "parser_mode": parser_mode,
                    "detail_complete_count": detail_complete_count,
                    "detail_partial_count": detail_partial_count,
                    "detail_missing_count": detail_missing_count,
                    "detail_capture_count": detail_capture_count,
                    "detail_capture_missing_count": len(items) - detail_capture_count,
                    "detail_mode": detail_mode,
                    "detail_selectors": matched_detail_selectors,
                    "detail_capture_modes": detail_capture_modes,
                    "detail_warning_counts": detail_warning_counts,
                    "detail_interval_min_milliseconds": detail_interval_min,
                    "detail_interval_max_milliseconds": detail_interval_max,
                    "detail_pause_count": max(0, len(items) - 1),
                    "detail_pause_total_milliseconds": detail_pause_total,
                    "source_empty": bool(empty_state),
                    "source_empty_selector": empty_state.get("selector") if empty_state else None,
                    "source_empty_text": empty_state.get("text") if empty_state else None,
                    **pagination_metadata,
                },
            )
        except (AdapterParseError, AdapterTransportError):
            raise
        except Exception as exc:
            raise AdapterTransportError(
                f"职护浏览器采集失败（{type(exc).__name__}）：{exc}"
            ) from exc

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        content = snapshot.content
        items = content.get("items") if isinstance(content, dict) else None
        if not isinstance(items, list):
            raise AdapterParseError("公司渠道快照缺少岗位列表")
        if not items and snapshot.transport_metadata.get("source_empty"):
            return AdapterResult(
                adapter_type=self.adapter_type,
                adapter_version=self.version,
                source_code=source.code,
                records=[],
            )
        records: list[RawRecordInput] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            source_url = item.get("_source_url") or snapshot.source_url
            external_id = self._external_id_for_item(item)
            payload = dict(item)
            rendered_html = str(payload.pop("_detail_html", "") or "")
            records.append(
                RawRecordInput(
                    external_id=str(external_id)[:255],
                    source_url=source_url,
                    source_published_at=parse_datetime(item.get("publish_time")),
                    fetched_at=snapshot.fetched_at,
                    http_status=snapshot.http_status,
                    content_type="application/json",
                    raw_payload=payload,
                    raw_text=rendered_html or str(item.get("_detail_text") or "") or None,
                    transport_metadata=snapshot.transport_metadata,
                    schema_version=(
                        "school-announcement-v1"
                        if source.source_kind == "school_announcement"
                        else "company-channel-v1"
                    ),
                )
            )
        if not records:
            raise AdapterParseError("公司渠道解析器没有返回岗位")
        return AdapterResult(
            adapter_type=self.adapter_type,
            adapter_version=self.version,
            source_code=source.code,
            records=records,
        )
