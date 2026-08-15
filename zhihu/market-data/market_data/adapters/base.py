from __future__ import annotations

import time
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from market_data.errors import SourcePolicyError
from market_data.schemas import AdapterResult, SourceDefinition, SourceSnapshot


class SourceAdapter(ABC):
    adapter_type: str
    version = "1.0"

    def assert_live_collection_allowed(self, source: SourceDefinition) -> None:
        parsed = urlparse(str(source.base_url))
        allowed = {host.lower() for host in source.allowed_hosts}
        if not source.enabled or source.terms_review_status != "approved":
            raise SourcePolicyError(
                f"source {source.code} is not approved and enabled for live collection"
            )
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed:
            raise SourcePolicyError("live source must use HTTPS and an allow-listed host")

    def retry_delays(self, source: SourceDefinition) -> list[float]:
        return [min(source.min_interval_seconds * (2**attempt), 30) for attempt in range(source.max_retries)]

    @abstractmethod
    def parse(self, source: SourceDefinition, snapshot: SourceSnapshot) -> AdapterResult:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, source: SourceDefinition) -> SourceSnapshot:
        raise NotImplementedError

    def throttle(self, source: SourceDefinition) -> None:
        time.sleep(source.min_interval_seconds)
