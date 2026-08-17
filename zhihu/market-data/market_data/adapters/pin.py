from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from urllib.parse import urljoin

from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime
from market_data.errors import AdapterParseError, AdapterTransportError
from market_data.schemas import AdapterResult, RawRecordInput, SourceDefinition, SourceSnapshot


class PinChannelAdapter(SourceAdapter):
    """Compatibility adapter for Pin's generated company-channel parsers.

    It deliberately reuses only parser/config assets. Pin's old task service and
    database writes are not called: records always return to market_raw first.
    """

    adapter_type = "pin"
    version = "2.0"

    def _parser_path(self, source: SourceDefinition) -> Path:
        configured_root = source.config.get("parser_root")
        root = Path(configured_root) if configured_root else Path(__file__).resolve().parents[4] / "Pin" / "crawler" / "auto_gen_com" / "gen"
        function_name = str(source.config.get("parser_function") or "").strip()
        if not function_name or not function_name.replace("_", "").isalnum():
            raise AdapterParseError("Pin channel has no valid generated parser function")
        path = (root / f"{function_name}.py").resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise AdapterParseError(f"Pin generated parser is unavailable: {function_name}")
        return path

    def validate_configuration(self, source: SourceDefinition) -> None:
        """Validate local parser availability without issuing a network request."""
        self._parser_path(source)

    def _extract_items(self, source: SourceDefinition, html: str) -> list[dict]:
        path = self._parser_path(source)
        spec = importlib.util.spec_from_file_location(f"career_guardian_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise AdapterParseError(f"cannot load Pin generated parser: {path.stem}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        parser = getattr(module, "extract_table_from_html", None)
        if not callable(parser):
            raise AdapterParseError(f"Pin parser has no extract_table_from_html: {path.stem}")
        with tempfile.NamedTemporaryFile(suffix=".json") as output:
            parser(html, output.name)
            output.seek(0)
            try:
                payload = json.load(output)
            except json.JSONDecodeError as exc:
                raise AdapterParseError(f"Pin parser returned invalid JSON: {path.stem}") from exc
        if not isinstance(payload, list):
            raise AdapterParseError("Pin parser result must be a list")
        return [item for item in payload if isinstance(item, dict)]

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        self.throttle(source)
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AdapterTransportError(
                "Playwright extra is not installed; install requirements-playwright.txt"
            ) from exc
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent="CareerGuardianMarketBot/0.2")
                response = page.goto(
                    str(source.base_url),
                    wait_until=source.config.get("wait_until", "domcontentloaded"),
                    timeout=source.timeout_seconds * 1000,
                )
                ready_selector = source.config.get("table_selector")
                if ready_selector:
                    page.wait_for_selector(str(ready_selector), timeout=source.timeout_seconds * 1000)
                page.wait_for_timeout(int(source.config.get("settle_milliseconds", 1500)))
                items = self._extract_items(source, page.content())
                limit = max(1, min(int(source.config.get("max_records", 100)), 500))
                items = items[:limit]
                final_url = page.url
                status = response.status if response else None
                detail_selector = source.config.get("detail_selector")
                for index, item in enumerate(items):
                    link = str(item.get("link") or item.get("url") or "").strip()
                    detail_url = urljoin(final_url, link) if link else final_url
                    item["_source_url"] = detail_url
                    if link and detail_selector:
                        detail_page = browser.new_page(user_agent="CareerGuardianMarketBot/0.2")
                        try:
                            detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=source.timeout_seconds * 1000)
                            detail_page.wait_for_selector(str(detail_selector), timeout=source.timeout_seconds * 1000)
                            item["_detail_text"] = detail_page.locator(str(detail_selector)).inner_text().strip()
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
                transport_metadata={"attempt": 1, "mode": "live", "engine": "pin-compatible-v2"},
            )
        except PlaywrightTimeoutError as exc:
            raise AdapterTransportError(f"Pin-compatible Playwright timed out: {exc}") from exc
        except AdapterParseError:
            raise
        except Exception as exc:
            raise AdapterTransportError(f"Pin-compatible collection failed: {exc}") from exc

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        content = snapshot.content
        items = content.get("items") if isinstance(content, dict) else None
        if not isinstance(items, list):
            raise AdapterParseError("Pin-compatible snapshot has no item list")
        records: list[RawRecordInput] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            source_url = item.get("_source_url") or snapshot.source_url
            external_id = item.get("id") or item.get("job_id") or item.get("announcement_id")
            if not external_id:
                external_id = f"{source.code}:{index}:{item.get('announcement_name', '')}"
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
                    schema_version="pin-channel-v2",
                )
            )
        if not records:
            raise AdapterParseError("Pin-compatible parser found no jobs")
        return AdapterResult(
            adapter_type="pin",
            adapter_version=self.version,
            source_code=source.code,
            records=records,
        )
