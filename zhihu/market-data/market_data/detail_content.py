from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


RESPONSIBILITY_HEADINGS = (
    "工作职责",
    "岗位职责",
    "职位职责",
    "主要职责",
    "工作内容",
    "岗位内容",
    "职位描述",
)
REQUIREMENT_HEADINGS = (
    "任职要求",
    "任职资格",
    "岗位要求",
    "职位要求",
    "任职条件",
    "资格要求",
)
BENEFIT_HEADINGS = ("福利待遇", "薪酬福利", "我们提供", "岗位福利")
ALL_HEADINGS = RESPONSIBILITY_HEADINGS + REQUIREMENT_HEADINGS + BENEFIT_HEADINGS


def clean_detail_text(value: Any) -> str:
    text = str(value or "").replace("\u00a0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_detail_text(html: str) -> str:
    """Convert captured rendered HTML into conservative visible source text."""

    soup = BeautifulSoup(str(html or ""), "html.parser")
    for node in soup.select("script,style,noscript,svg,template"):
        node.decompose()
    return clean_detail_text(soup.get_text("\n", strip=True))


def _section_pattern() -> re.Pattern[str]:
    headings = "|".join(re.escape(item) for item in sorted(ALL_HEADINGS, key=len, reverse=True))
    return re.compile(rf"(?P<heading>{headings})\s*[:\uff1a]?\s*", re.IGNORECASE)


SECTION_PATTERN = _section_pattern()


def split_detail_sections(detail_text: str) -> dict[str, str]:
    """Split only explicit source headings; never infer facts absent from the page."""

    text = clean_detail_text(detail_text)
    matches = list(SECTION_PATTERN.finditer(text))
    if not matches:
        return {}
    sections: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = clean_detail_text(text[start:end]).strip(" -\uff0d|\uff5c")
        if not value:
            continue
        heading = match.group("heading")
        if heading in RESPONSIBILITY_HEADINGS:
            key = "responsibilities"
        elif heading in REQUIREMENT_HEADINGS:
            key = "requirements"
        else:
            key = "benefits"
        sections.setdefault(key, []).append(value)
    return {key: "\n".join(values) for key, values in sections.items() if values}
