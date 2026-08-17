from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime
from market_data.company_channel_catalog import COMPAT_PARSER_ROOT
from market_data.errors import AdapterParseError, AdapterTransportError
from market_data.schemas import AdapterResult, RawRecordInput, SourceDefinition, SourceSnapshot


PLATFORM_LIST_SELECTORS = {
    "zhiye": [
        '[class*="STJobList-editor"]',
        '[class*="STListItem-editor"]',
    ],
}

SAFE_COMPAT_IMPORTS = {"json", "bs4", "re", "urllib.parse", "datetime"}


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
    version = "1.1"

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
        root = COMPAT_PARSER_ROOT.resolve()
        path = (root / f"{function_name}.py").resolve()
        if root not in path.parents or not path.is_file():
            raise AdapterParseError(f"职护内置兼容解析器不可用：{function_name}")
        validate_compat_parser_source(path)
        return path

    def validate_configuration(self, source: SourceDefinition) -> None:
        platform_type = str(source.config.get("platform_type") or "").strip()
        if platform_type in PLATFORM_LIST_SELECTORS:
            return
        if self._compat_parser_path(source) is None:
            raise AdapterParseError("该渠道既没有平台解析规则，也没有职护内置兼容解析器")

    def _selector_candidates(self, source: SourceDefinition) -> list[str]:
        result: list[str] = []
        platform_type = str(source.config.get("platform_type") or "").strip()
        for selector in [
            *PLATFORM_LIST_SELECTORS.get(platform_type, []),
            *_as_selector_list(source.config.get("list_selectors")),
            *_as_selector_list(source.config.get("table_selectors")),
            *_as_selector_list(source.config.get("table_selector")),
        ]:
            if selector not in result:
                result.append(selector)
        return result

    @staticmethod
    def _wait_for_any_selector(page, selectors: list[str], timeout_milliseconds: int) -> tuple[str | None, list[str]]:
        deadline = time.monotonic() + timeout_milliseconds / 1000
        invalid: list[str] = []
        while time.monotonic() < deadline:
            for selector in selectors:
                if selector in invalid:
                    continue
                try:
                    locator = page.locator(selector)
                    if locator.count() and locator.first.is_visible():
                        return selector, invalid
                except Exception:
                    invalid.append(selector)
            page.wait_for_timeout(250)
        return None, invalid

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

    def _extract_items(self, source: SourceDefinition, html: str) -> tuple[list[dict], str]:
        platform_type = str(source.config.get("platform_type") or "").strip()
        if platform_type == "zhiye":
            items = self._extract_zhiye(html)
            if items:
                return items, "platform:zhiye"
        items = self._extract_compat_items(source, html)
        if items:
            return items, "compat"
        return [], "none"

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        self.throttle(source)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AdapterTransportError(
                "Playwright 未安装，请安装 requirements-playwright.txt"
            ) from exc

        selectors = self._selector_candidates(source)
        headless = bool(source.config.get("headless", True))
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=headless)
                page = browser.new_page(user_agent="CareerGuardianMarketBot/1.0")
                response = page.goto(
                    str(source.base_url),
                    wait_until=source.config.get("wait_until", "domcontentloaded"),
                    timeout=source.timeout_seconds * 1000,
                )
                page.wait_for_timeout(int(source.config.get("settle_milliseconds", 1500)))
                matched_selector, invalid_selectors = self._wait_for_any_selector(
                    page, selectors, source.timeout_seconds * 1000
                )
                platform_type = str(source.config.get("platform_type") or "").strip()
                pagination_metadata: dict[str, object] = {
                    "pagination_mode": "single_page",
                    "batches_loaded": 1,
                    "reported_total": None,
                    "records_discovered": 0,
                    "pagination_stop_reason": "pagination_not_supported",
                }
                if platform_type == "zhiye":
                    pagination_metadata = self._load_all_zhiye_items(page, source)
                html = page.content()
                items, parser_mode = self._extract_items(source, html)
                if not items:
                    sample = ", ".join(selectors[:3]) or "未配置"
                    raise AdapterParseError(
                        f"页面已打开，但没有解析到岗位；平台={source.config.get('platform_type') or 'custom'}，"
                        f"候选规则={sample}"
                    )
                if platform_type == "zhiye":
                    self._retry_missing_zhiye_details(page, items)
                limit = max(1, min(int(source.config.get("max_records", 500)), 500))
                items = items[:limit]
                final_url = page.url
                status = response.status if response else None
                detail_selectors = _as_selector_list(source.config.get("detail_selectors"))
                for index, item in enumerate(items):
                    link = str(item.get("link") or item.get("url") or "").strip()
                    detail_url = urljoin(final_url, link) if link else final_url
                    item["_source_url"] = detail_url
                    if link and detail_selectors:
                        detail_page = browser.new_page(user_agent="CareerGuardianMarketBot/1.0")
                        try:
                            detail_page.goto(
                                detail_url,
                                wait_until="domcontentloaded",
                                timeout=min(source.timeout_seconds, 15) * 1000,
                            )
                            detail_selector, _ = self._wait_for_any_selector(
                                detail_page, detail_selectors, min(source.timeout_seconds, 10) * 1000
                            )
                            if detail_selector:
                                item["_detail_text"] = detail_page.locator(detail_selector).first.inner_text().strip()
                            else:
                                item["_detail_warning"] = "detail_selector_not_found"
                        except Exception as exc:
                            item["_detail_warning"] = type(exc).__name__
                        finally:
                            detail_page.close()
                    item["_record_index"] = index
                browser.close()
            detail_complete_count = sum(
                bool(item.get("responsibilities") and item.get("requirements")) for item in items
            )
            detail_partial_count = sum(
                bool(item.get("responsibilities") or item.get("requirements")) for item in items
            ) - detail_complete_count
            detail_missing_count = len(items) - detail_complete_count - detail_partial_count
            return SourceSnapshot(
                source_url=final_url,
                content_type="application/json",
                content={"items": items},
                http_status=status,
                transport_metadata={
                    "attempt": 1,
                    "mode": "live",
                    "engine": "career-guardian-browser-v1",
                    "browser_mode": "headless" if headless else "visible",
                    "matched_selector": matched_selector,
                    "invalid_selector_count": len(invalid_selectors),
                    "parser_mode": parser_mode,
                    "detail_complete_count": detail_complete_count,
                    "detail_partial_count": detail_partial_count,
                    "detail_missing_count": detail_missing_count,
                    **pagination_metadata,
                },
            )
        except AdapterParseError:
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
        records: list[RawRecordInput] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            source_url = item.get("_source_url") or snapshot.source_url
            external_id = item.get("id") or item.get("job_id") or item.get("announcement_id")
            if not external_id:
                identity = "|".join(
                    str(item.get(key) or "")
                    for key in ("announcement_name", "hd_loc", "hd_dept", "link")
                )
                external_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()
            records.append(
                RawRecordInput(
                    external_id=str(external_id)[:255],
                    source_url=source_url,
                    source_published_at=parse_datetime(item.get("publish_time")),
                    fetched_at=snapshot.fetched_at,
                    http_status=snapshot.http_status,
                    content_type="application/json",
                    raw_payload=item,
                    raw_text=str(item.get("_detail_text") or "") or None,
                    transport_metadata=snapshot.transport_metadata,
                    schema_version="company-channel-v1",
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
