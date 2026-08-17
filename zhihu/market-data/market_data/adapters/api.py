from __future__ import annotations

import copy
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime, value_at_path
from market_data.errors import AdapterParseError, AdapterTimeoutError, AdapterTransportError
from market_data.schemas import AdapterResult, RawRecordInput, SourceDefinition, SourceSnapshot


class StructuredApiAdapter(SourceAdapter):
    adapter_type = "api"

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        if not isinstance(snapshot.content, (dict, list)):
            raise AdapterParseError("structured API snapshot must contain JSON")
        try:
            items = value_at_path(snapshot.content, source.config.get("items_path"))
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterParseError("configured items_path was not found") from exc
        if not isinstance(items, list):
            raise AdapterParseError("configured items_path must resolve to a list")

        id_field = source.config.get("id_field", "id")
        url_field = source.config.get("url_field", "url")
        published_field = source.config.get("published_field", "published_at")
        url_template = source.config.get("url_template")
        records: list[RawRecordInput] = []
        for item in items:
            if not isinstance(item, dict):
                raise AdapterParseError("each API record must be an object")
            external_id = item.get(id_field)
            source_url = item.get(url_field)
            if not source_url and url_template and external_id is not None:
                source_url = url_template.format(id=external_id)
            if not source_url:
                source_url = str(snapshot.source_url)
            records.append(
                RawRecordInput(
                    external_id=str(external_id) if external_id is not None else None,
                    source_url=source_url,
                    source_published_at=parse_datetime(item.get(published_field)),
                    fetched_at=snapshot.fetched_at,
                    http_status=snapshot.http_status,
                    content_type="application/json",
                    raw_payload=item,
                    transport_metadata=snapshot.transport_metadata,
                )
            )
        return AdapterResult(
            adapter_type="api",
            adapter_version=self.version,
            source_code=source.code,
            records=records,
        )

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        method = str(source.config.get("method", "GET")).upper()
        headers = self._headers(source)
        pagination = source.config.get("pagination")
        if not isinstance(pagination, dict):
            self.throttle(source)
            response, attempt = self._request(
                source,
                method,
                source.config.get("params"),
                source.config.get("json_body"),
                headers,
            )
            return self._snapshot(response, attempt=attempt, pages=1)

        if pagination.get("mode") != "json_body":
            raise AdapterParseError("only json_body API pagination is supported")
        body = copy.deepcopy(source.config.get("json_body") or {})
        if not isinstance(body, dict):
            raise AdapterParseError("paginated API json_body must be an object")
        page_field = str(pagination.get("page_index_field", "PageIndex"))
        size_field = str(pagination.get("page_size_field", "PageSize"))
        start_page = int(pagination.get("start_page", 0))
        page_size = int(pagination.get("page_size", 100))
        max_pages = int(pagination.get("max_pages", 20))
        if page_size < 1 or page_size > 500 or max_pages < 1 or max_pages > 100:
            raise AdapterParseError("pagination limits are outside the safe range")

        items_path = str(source.config.get("items_path") or "")
        total_path = pagination.get("total_path")
        merged_content: dict[str, Any] | None = None
        merged_items: list[Any] = []
        total_attempts = 0
        response = None
        collection = source.config.get("_collection")
        collection_runtime = dict(collection) if isinstance(collection, dict) else {}
        collection_mode = str(collection_runtime.get("mode") or "full")
        known_ids = {
            str(item)
            for item in (collection_runtime.get("known_external_ids") or [])
            if item is not None
        }
        id_field = str(source.config.get("id_field", "id"))
        stop_reason = "max_pages_reached"
        for offset in range(max_pages):
            if offset:
                time.sleep(source.min_interval_seconds)
            request_body = copy.deepcopy(body)
            request_body[page_field] = start_page + offset
            request_body[size_field] = page_size
            response, attempt = self._request(
                source,
                method,
                source.config.get("params"),
                request_body,
                headers,
            )
            total_attempts += attempt
            page_content = response.json()
            self._assert_success(source, page_content)
            try:
                page_items = value_at_path(page_content, items_path)
            except (KeyError, IndexError, TypeError) as exc:
                raise AdapterParseError("configured items_path was not found") from exc
            if not isinstance(page_items, list):
                raise AdapterParseError("configured items_path must resolve to a list")
            if merged_content is None:
                if not isinstance(page_content, dict):
                    raise AdapterParseError("paginated API response must be an object")
                merged_content = copy.deepcopy(page_content)
            merged_items.extend(page_items)
            page_ids = {
                str(item.get(id_field))
                for item in page_items
                if isinstance(item, dict) and item.get(id_field) is not None
            }
            total = None
            if total_path:
                try:
                    total = int(value_at_path(page_content, str(total_path)))
                except (KeyError, IndexError, TypeError, ValueError):
                    total = None
            if collection_mode == "incremental" and known_ids and page_ids and page_ids.issubset(known_ids):
                stop_reason = "incremental_boundary_reached"
                break
            if not page_items:
                stop_reason = "empty_page"
                break
            if len(page_items) < page_size:
                stop_reason = "short_page"
                break
            if total is not None and len(merged_items) >= total:
                stop_reason = "reported_total_reached"
                break
        assert response is not None and merged_content is not None
        self._set_value_at_path(merged_content, items_path, merged_items)
        return self._snapshot(
            response,
            content=merged_content,
            attempt=total_attempts,
            pages=offset + 1,
            records=len(merged_items),
            extra_metadata={
                "collection_mode": collection_mode,
                "pagination_stop_reason": stop_reason,
                "known_checkpoint_size": len(known_ids),
            },
        )

    @staticmethod
    def _headers(source: SourceDefinition) -> dict[str, str]:
        headers = {"User-Agent": "CareerGuardianMarketBot/0.2"}
        configured = source.config.get("headers") or {}
        allowed = {"accept", "content-type", "origin", "referer", "x-requested-with"}
        if not isinstance(configured, dict):
            raise AdapterParseError("API headers must be an object")
        for name, value in configured.items():
            if str(name).lower() not in allowed:
                raise AdapterParseError(f"API header is not allowed: {name}")
            if str(name).lower() in {"origin", "referer"}:
                parsed = urlparse(str(value))
                if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
                    host.lower() for host in source.allowed_hosts
                }:
                    raise AdapterParseError(f"API header host is not allowed: {name}")
            headers[str(name)] = str(value)
        return headers

    @staticmethod
    def _assert_success(source: SourceDefinition, content: Any) -> None:
        success_path = source.config.get("success_path")
        if not success_path:
            return
        try:
            actual = value_at_path(content, str(success_path))
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterParseError("configured success_path was not found") from exc
        if actual != source.config.get("success_value"):
            raise AdapterTransportError("upstream API returned an unsuccessful payload")

    def _request(
        self,
        source: SourceDefinition,
        method: str,
        params: Any,
        json_body: Any,
        headers: dict[str, str],
    ) -> tuple[httpx.Response, int]:
        last_error: Exception | None = None
        delays = [0.0, *self.retry_delays(source)]
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=source.timeout_seconds, follow_redirects=False) as client:
                    response = client.request(
                        method,
                        str(source.base_url),
                        params=params,
                        json=json_body,
                        headers=headers,
                    )
                response.raise_for_status()
                content = response.json()
                self._assert_success(source, content)
                return response, attempt + 1
            except httpx.TimeoutException as exc:
                last_error = AdapterTimeoutError(str(exc))
            except (httpx.HTTPError, ValueError) as exc:
                last_error = AdapterTransportError(str(exc))
        assert last_error is not None
        raise last_error

    @staticmethod
    def _snapshot(
        response: httpx.Response,
        *,
        content: Any | None = None,
        attempt: int,
        pages: int,
        records: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SourceSnapshot:
        metadata = {"attempt": attempt, "mode": "live", "pages": pages}
        if records is not None:
            metadata["records"] = records
        if extra_metadata:
            metadata.update(extra_metadata)
        return SourceSnapshot(
            source_url=str(response.url),
            content_type=response.headers.get("content-type", "application/json"),
            content=response.json() if content is None else content,
            http_status=response.status_code,
            transport_metadata=metadata,
        )

    @staticmethod
    def _set_value_at_path(content: dict[str, Any], path: str, value: list[Any]) -> None:
        parts = path.split(".") if path else []
        if not parts:
            raise AdapterParseError("paginated API requires an items_path")
        current: Any = content
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                raise AdapterParseError("configured items_path was not found")
            current = current[part]
        if not isinstance(current, dict):
            raise AdapterParseError("configured items_path cannot be replaced")
        current[parts[-1]] = value
