from __future__ import annotations

import time
from typing import Any

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
        self.throttle(source)
        method = str(source.config.get("method", "GET")).upper()
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
                        params=source.config.get("params"),
                        json=source.config.get("json_body"),
                        headers={"User-Agent": "CareerGuardianMarketBot/0.1"},
                    )
                response.raise_for_status()
                return SourceSnapshot(
                    source_url=str(response.url),
                    content_type=response.headers.get("content-type", "application/json"),
                    content=response.json(),
                    http_status=response.status_code,
                    transport_metadata={"attempt": attempt + 1, "mode": "live"},
                )
            except httpx.TimeoutException as exc:
                last_error = AdapterTimeoutError(str(exc))
            except (httpx.HTTPError, ValueError) as exc:
                last_error = AdapterTransportError(str(exc))
        assert last_error is not None
        raise last_error
