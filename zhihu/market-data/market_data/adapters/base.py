from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from urllib.parse import urlparse

from market_data.errors import SourcePolicyError, TaskCancellationRequested
from market_data.schemas import AdapterResult, SourceDefinition, SourceSnapshot


class SourceAdapter(ABC):
    adapter_type: str
    version = "1.0"

    def set_cancel_check(self, callback: Callable[[], bool] | None) -> None:
        self._cancel_check = callback

    def set_progress_callback(
        self, callback: Callable[[str, dict], None] | None
    ) -> None:
        self._progress_callback = callback

    def report_progress(self, stage: str, **metrics: object) -> None:
        callback = getattr(self, "_progress_callback", None)
        if callback is not None:
            callback(stage, dict(metrics))

    def raise_if_cancelled(self) -> None:
        callback = getattr(self, "_cancel_check", None)
        if callback is not None and callback():
            raise TaskCancellationRequested("任务已由管理员终止")

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
        deadline = time.monotonic() + source.min_interval_seconds
        while time.monotonic() < deadline:
            self.raise_if_cancelled()
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        self.raise_if_cancelled()
