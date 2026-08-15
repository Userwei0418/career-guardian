"""Markdown and plain text parser
"""

from __future__ import annotations

from app.services.parsers.base import DocumentParser, ParseResult


class MarkdownParser(DocumentParser):
    """Markdown document parser"""

    def supports(self, filename: str) -> bool:
        return self._extension(filename) in ("md", "markdown", "mkd")

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("gbk", errors="replace")
        lines = [l for l in raw_text.split("\n") if l.strip()]
        return ParseResult(
            raw_text=raw_text, page_count=len(lines), parse_status="completed", parse_mode="markdown",
            parse_notice=f"Extracted {len(lines)} lines from Markdown.",
        )


class PlainTextParser(DocumentParser):
    """Plain text parser with encoding detection"""

    def supports(self, filename: str) -> bool:
        return self._extension(filename) in ("txt", "text", "csv", "json", "xml", "html", "htm")

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        for encoding in ("utf-8", "gbk", "gb2312", "gb18030", "big5"):
            try:
                raw_text = file_bytes.decode(encoding)
                lines = [l for l in raw_text.split("\n") if l.strip()]
                return ParseResult(
                    raw_text=raw_text, page_count=len(lines), parse_status="completed", parse_mode="text",
                    parse_notice=f"Extracted with encoding={encoding}, {len(lines)} lines.",
                    metadata={"encoding": encoding},
                )
            except UnicodeDecodeError:
                continue
        return ParseResult(
            raw_text="", page_count=0, parse_status="failed", parse_mode="text",
            parse_error="Unable to decode text file with supported encodings.",
        )