"""Abstract base class for document parsers

Defines the interface that all document parsers must implement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath


@dataclass
class ParseResult:
    """Unified parse result across all document types"""
    raw_text: str
    page_count: int
    parse_status: str  # completed | processing | failed
    parse_mode: str    # text | ocr | hybrid | office | markdown
    parse_notice: str | None = None
    parse_error: str | None = None
    metadata: dict | None = None  # Document-specific metadata


class DocumentParser:
    """Abstract base class for document parsers"""

    def supports(self, filename: str) -> bool:
        """Check if this parser supports the given file type"""
        raise NotImplementedError

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        """Parse the document and return extracted text"""
        raise NotImplementedError

    @staticmethod
    def _extension(filename: str) -> str:
        """Extract lowercase extension from filename"""
        return PurePath(filename).suffix.lower().lstrip(".")