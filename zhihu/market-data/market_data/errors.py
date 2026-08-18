class MarketDataError(Exception):
    code = "market_data_error"


class TaskCancellationRequested(MarketDataError):
    code = "task_cancelled"


class SourcePolicyError(MarketDataError):
    code = "source_policy_rejected"


class AdapterParseError(MarketDataError):
    code = "adapter_parse_failed"


class AdapterTransportError(MarketDataError):
    code = "adapter_transport_failed"


class AdapterTimeoutError(AdapterTransportError):
    code = "adapter_timeout"


class SourceEntryError(AdapterTransportError):
    code = "source_entry_invalid"


class ListParseError(AdapterParseError):
    code = "list_parse_failed"


class DetailNavigationError(AdapterParseError):
    code = "detail_navigation_failed"


class DetailContentError(AdapterParseError):
    code = "detail_content_failed"


class QualityGateError(MarketDataError):
    code = "quality_gate_quarantined"

    def __init__(self, reason_codes: list[str] | tuple[str, ...]):
        self.reason_codes = tuple(reason_codes)
        super().__init__("candidate did not pass Core quality gate: " + ",".join(self.reason_codes))
