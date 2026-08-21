from __future__ import annotations

import re


EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
FORMATTED_CN_MOBILE_PATTERN = re.compile(
    r"(?<!\d)1[3-9](?:[ \t\u3000·•-]?\d){9}(?![ \t\u3000·•-]?\d)"
)
ACCOUNT_NUMBER_PATTERN = re.compile(
    r"(?<!\d)(?:\d[ \t\u3000·•-]?){12,19}(?!\d)"
)
LONG_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{7,}(?!\d)")

SENSITIVE_VALUE_PATTERNS = (
    EMAIL_PATTERN,
    FORMATTED_CN_MOBILE_PATTERN,
    ACCOUNT_NUMBER_PATTERN,
)


def redact_cashflow_text(value: str, *, max_length: int | None = None) -> str:
    """Redact contact/account identifiers before duplicating text into cashflow rows.

    The private source attachment remains the evidence of record. Candidate
    columns and API payloads only need the business-facing text and must not
    become a second copy of card numbers, phone numbers, email addresses or
    other long numeric identifiers.
    """

    redacted = str(value or "")
    redacted = EMAIL_PATTERN.sub("[邮箱已隐藏]", redacted)
    redacted = FORMATTED_CN_MOBILE_PATTERN.sub("[手机号已隐藏]", redacted)
    redacted = ACCOUNT_NUMBER_PATTERN.sub("[账号已隐藏]", redacted)
    redacted = LONG_NUMBER_PATTERN.sub("[长数字已隐藏]", redacted)
    return redacted[:max_length] if max_length is not None else redacted
