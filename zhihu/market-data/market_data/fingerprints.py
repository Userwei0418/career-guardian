from __future__ import annotations

import hashlib
import json
from typing import Any


COLLECTOR_ONLY_KEYS = {"_record_index", "_source_url", "_detail_warning"}


def _business_value(value: Any) -> Any:
    """Remove collector-only fields before comparing one upstream job over time."""

    if isinstance(value, dict):
        return {
            str(key): _business_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in COLLECTOR_ONLY_KEYS
        }
    if isinstance(value, list):
        return [_business_value(item) for item in value]
    return value


def business_payload_hash(payload: Any) -> str:
    content = json.dumps(
        _business_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()
