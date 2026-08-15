"""PDF document parser

Uses pypdf for text extraction with OCR fallback for scanned documents.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import settings
from app.services.ocr_service import OcrDependencyError, extract_text_with_ocr
from app.services.parsers.base import DocumentParser, ParseResult


class PdfParser(DocumentParser):
    """PDF parser with text layer extraction and OCR fallback"""

    def supports(self, filename: str) -> bool:
        return self._extension(filename) == "pdf"

    def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except PdfReadError as exc:
            return ParseResult(
                raw_text="", page_count=0, parse_status="failed", parse_mode="text",
                parse_error=f"Unable to read PDF: {exc}",
            )

        page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
        page_count = len(reader.pages)
        raw_text = "\n".join(text for text in page_texts if text).strip()

        if not raw_text:
            return self._parse_with_ocr(file_bytes, page_count)

        return ParseResult(
            raw_text=raw_text, page_count=page_count, parse_status="completed", parse_mode="text",
            parse_notice=f"Extracted {page_count} pages via text layer.",
        )

    def _parse_with_ocr(self, file_bytes: bytes, page_count: int) -> ParseResult:
        try:
            ocr_result = extract_text_with_ocr(file_bytes)
        except OcrDependencyError as exc:
            return ParseResult(
                raw_text="", page_count=page_count, parse_status="failed", parse_mode="ocr",
                parse_error=str(exc),
            )
        return ParseResult(
            raw_text=ocr_result.raw_text, page_count=ocr_result.page_count,
            parse_status="completed", parse_mode="ocr",
            parse_notice="Used OCR fallback for scanned document.",
        )