from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
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
    version = "1.0"

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
                }
            )
        return items

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
                html = page.content()
                items, parser_mode = self._extract_items(source, html)
                if not items:
                    sample = ", ".join(selectors[:3]) or "未配置"
                    raise AdapterParseError(
                        f"页面已打开，但没有解析到岗位；平台={source.config.get('platform_type') or 'custom'}，"
                        f"候选规则={sample}"
                    )
                limit = max(1, min(int(source.config.get("max_records", 100)), 500))
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
