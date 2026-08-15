class MarketDataError(Exception):
    code = "market_data_error"


class SourcePolicyError(MarketDataError):
    code = "source_policy_rejected"


class AdapterParseError(MarketDataError):
    code = "adapter_parse_failed"


class AdapterTransportError(MarketDataError):
    code = "adapter_transport_failed"


class AdapterTimeoutError(AdapterTransportError):
    code = "adapter_timeout"
