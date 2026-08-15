from __future__ import annotations

import html
import json
import re
import time
from urllib.parse import urljoin

import httpx

from market_data.adapters.api import StructuredApiAdapter
from market_data.adapters.base import SourceAdapter
from market_data.adapters.utils import parse_datetime
from market_data.errors import AdapterParseError, AdapterTimeoutError, AdapterTransportError
from market_data.schemas import AdapterResult, RawRecordInput, SourceDefinition, SourceSnapshot


class HtmlAdapter(SourceAdapter):
    adapter_type = "html"

    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        if not isinstance(snapshot.content, str):
            raise AdapterParseError("HTML snapshot must contain text")
        mode = source.config.get("html_mode", "embedded_json")
        if mode == "embedded_json":
            result = self._parse_embedded_json(source, snapshot)
        elif mode == "job_cards":
            result = self._parse_job_cards(source, snapshot)
        else:
            raise AdapterParseError(f"unsupported html_mode: {mode}")
        return result

    def _parse_embedded_json(
        self, source: SourceDefinition, snapshot: SourceSnapshot
    ) -> AdapterResult:
        script_id = re.escape(source.config.get("script_id", "__NEXT_DATA__"))
        match = re.search(
            rf'<script[^>]+id=["\']{script_id}["\'][^>]*>(.*?)</script>',
            snapshot.content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not match:
            raise AdapterParseError(f"embedded JSON script #{script_id} not found")
        try:
            payload = json.loads(html.unescape(match.group(1)).strip())
        except json.JSONDecodeError as exc:
            raise AdapterParseError("embedded JSON is invalid") from exc
        api_snapshot = snapshot.model_copy(update={"content": payload})
        api_result = StructuredApiAdapter().parse(source, api_snapshot)
        return api_result.model_copy(update={"adapter_type": "html", "adapter_version": self.version})

    def _parse_job_cards(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        card_pattern = source.config.get(
            "card_pattern", r'<article\s+class="job-card"(?P<attrs>[^>]*)>(?P<body>.*?)</article>'
        )
        cards = list(re.finditer(card_pattern, snapshot.content, re.DOTALL | re.IGNORECASE))
        if not cards:
            raise AdapterParseError("no configured job cards were found")
        records: list[RawRecordInput] = []
        for card in cards:
            attrs = dict(re.findall(r'data-([\w-]+)=["\']([^"\']*)["\']', card.group("attrs")))
            external_id = attrs.get(source.config.get("card_id_attribute", "job-id"))
            relative_url = attrs.get(source.config.get("card_url_attribute", "url"), "")
            source_url = urljoin(str(snapshot.source_url), relative_url) if relative_url else snapshot.source_url
            records.append(
                RawRecordInput(
                    external_id=external_id,
                    source_url=source_url,
                    source_published_at=parse_datetime(
                        attrs.get(source.config.get("card_published_attribute", "published-at"))
                    ),
                    fetched_at=snapshot.fetched_at,
                    http_status=snapshot.http_status,
                    content_type="text/html",
                    raw_text=card.group(0).strip(),
                    transport_metadata=snapshot.transport_metadata,
                )
            )
        return AdapterResult(
            adapter_type="html",
            adapter_version=self.version,
            source_code=source.code,
            records=records,
        )

    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        self.assert_live_collection_allowed(source)
        last_error: Exception | None = None
        delays = [0.0, *self.retry_delays(source)]
        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=source.timeout_seconds, follow_redirects=False) as client:
                    response = client.get(
                        str(source.base_url), headers={"User-Agent": "CareerGuardianMarketBot/0.1"}
                    )
                response.raise_for_status()
                return SourceSnapshot(
                    source_url=str(response.url),
                    content_type=response.headers.get("content-type", "text/html"),
                    content=response.text,
                    http_status=response.status_code,
                    transport_metadata={"attempt": attempt + 1, "mode": "live"},
                )
            except httpx.TimeoutException as exc:
                last_error = AdapterTimeoutError(str(exc))
            except httpx.HTTPError as exc:
                last_error = AdapterTransportError(str(exc))
        assert last_error is not None
        raise last_error
