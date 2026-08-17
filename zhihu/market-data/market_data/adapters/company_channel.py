from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime
from market_data.company_channel_catalog import COMPAT_PARSER_ROOT
from market_data.errors import AdapterParseError, AdapterTransportError
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
        '[aria-label*="下一页"]',
        'button[aria-label*="Next"]',
        'a[aria-label*="Next"]',
        '.next:not(.disabled)',
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
        if mode not in {"auto", "single_page", "infinite_scroll", "load_more", "next_button"}:
            raise AdapterParseError(f"不支持的页面采集模式：{mode}")
        max_records = max(
            1,
            min(int(pagination.get("max_records", source.config.get("max_records", 500))), 2_000),
        )
        max_batches = max(
            1,
            min(
                int(
                    pagination.get(
                        "max_batches",
                        pagination.get(
                            "max_pages",
                            pagination.get(
                                "max_rounds",
                                source.config.get("max_scroll_rounds", 30),
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
            items, parser_mode = self._extract_items(source, page.content())
            if not items and batch_index == 0:
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
                page.wait_for_timeout(int(source.config.get("settle_milliseconds", 1500)))
                matched_selector, invalid_selectors = self._wait_for_any_selector(
                    page, selectors, source.timeout_seconds * 1000
                )
                platform_type = str(source.config.get("platform_type") or "").strip()
                items, parser_mode, pagination_metadata = self._collect_paginated_items(
                    page, source
                )
                if not items:
                    sample = ", ".join(selectors[:3]) or "未配置"
                    raise AdapterParseError(
                        f"页面已打开，但没有解析到岗位；平台={source.config.get('platform_type') or 'custom'}，"
                        f"候选规则={sample}"
                    )
                if platform_type == "zhiye":
                    self._retry_missing_zhiye_details(page, items)
                limit = max(1, min(int(source.config.get("max_records", 500)), 2_000))
                items = items[:limit]
                final_url = page.url
                status = response.status if response else None
                detail_selectors = self._detail_selector_candidates(source)
                matched_detail_selectors: list[str] = []
                for index, item in enumerate(items):
                    link = str(item.get("link") or item.get("url") or "").strip()
                    detail_url = urljoin(final_url, link) if link else final_url
                    item["_source_url"] = detail_url
                    if link and detail_selectors:
                        detail_page = context.new_page()
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
                                if detail_selector not in matched_detail_selectors:
                                    matched_detail_selectors.append(detail_selector)
                                item["_detail_strategy"] = "detail_page"
                            else:
                                item["_detail_warning"] = "detail_selector_not_found"
                        except Exception as exc:
                            item["_detail_warning"] = type(exc).__name__
                        finally:
                            detail_page.close()
                    item["_record_index"] = index
                context.close()
                browser.close()
            detail_complete_count = sum(
                bool(item.get("responsibilities") and item.get("requirements")) for item in items
            )
            detail_partial_count = sum(
                bool(item.get("responsibilities") or item.get("requirements")) for item in items
            ) - detail_complete_count
            detail_missing_count = len(items) - detail_complete_count - detail_partial_count
            observed_detail_modes = {
                str(item.get("_detail_strategy") or "").strip()
                for item in items
                if str(item.get("_detail_strategy") or "").strip()
            }
            detail_mode = next(
                (
                    mode
                    for mode in ("detail_page", "expanded_panel", "embedded_panel")
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
                    "detail_mode": detail_mode,
                    "detail_selectors": matched_detail_selectors,
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
            external_id = self._external_id_for_item(item)
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
