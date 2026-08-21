from __future__ import annotations

from datetime import date


# MySQL DATE starts at year 1000. Keep one complete year below Python's upper
# boundary so a supported month always has a representable exclusive end.
MIN_FINANCIAL_DATE = date(1000, 1, 1)
MAX_FINANCIAL_DATE = date(9998, 12, 31)


def is_supported_financial_date(value: date | None) -> bool:
    return value is not None and MIN_FINANCIAL_DATE <= value <= MAX_FINANCIAL_DATE
