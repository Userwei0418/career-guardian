"""Unified document parser service

Strategy-pattern based document parsing that routes files to the
appropriate parser based on file extension.
"""

from __future__ import annotations

import logging

from app.services.parsers.base import DocumentParser, ParseResult
from app.services.parsers.pdf_parser import PdfParser
from app.services.parsers.office_parser import OfficeParser
from app.services.parsers.markdown_parser import MarkdownParser, PlainTextParser

logger = logging.getLogger(__name__)


class DocumentParserService:
    """Unified document parser that routes to specialized parsers"""

    def __init__(self):
        self._parsers: list[DocumentParser] = []

    def register_parser(self, parser: DocumentParser) -> None:
        """Register a new document parser"""
        self._parsers.append(parser)
        logger.info(f"Registered parser: {parser.__class__.__name__}")

    def get_parser(self, filename: str) -> DocumentParser | None:
        "Find a parser that supports the given file type"
        for parser in self._parsers:
            if parser.supports(filename):
                return parser
        return None

    def parse_document(self, file_bytes: bytes, filename: str) -> ParseResult:
        """Parse a document using the appropriate parser"""
        parser = self.get_parser(filename)
        if parser is None:
            return ParseResult(
                raw_text="", page_count=0, parse_status="failed", parse_mode="unknown",
                parse_error=f"Unsupported file type: {filename}",
            )
        logger.info(f"Parsing {filename} with {parser.__class__.__name__}")
        return parser.parse(file_bytes, filename)

    def supported_extensions(self) -> list[str]:
        """List all supported file extensions"""
        exts = []
        for parser in self._parsers:
            if hasattr(parser, "SUPPORTED_EXTENSIONS"):
                exts.extend(parser.SUPPORTED_EXTENSIONS)
            elif isinstance(parser, PdfParser):
                exts.append("pdf")
            elif isinstance(parser, MarkdownParser):
                exts.extend(["md", "markdown", "mkd"])
        return sorted(set(exts))


# Singleton instance
_parser_service: DocumentParserService | None = None


def get_document_parser_service() -> DocumentParserService:
    """Get the singleton document parser service instance"""
    global _parser_service
    if _parser_service is None:
        _parser_service = DocumentParserService()
        _parser_service.register_parser(PdfParser())
        _parser_service.register_parser(OfficeParser())
        _parser_service.register_parser(MarkdownParser())
        _parser_service.register_parser(PlainTextParser())
    return _parser_service