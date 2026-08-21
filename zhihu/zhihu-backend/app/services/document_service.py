"""文档上传与本地文本提取。

原件只在本地保存和解析。质量报告保留页级计数与偏移，不复制合同正文。
"""
from __future__ import annotations

import math
import os
import re
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Optional
from xml.etree import ElementTree


def _configure_local_tessdata() -> str | None:
    """让 PyMuPDF 在常见本机安装位置找到 OCR 语言数据。"""

    configured = os.environ.get("TESSDATA_PREFIX")
    if configured and os.path.isfile(os.path.join(configured, "chi_sim.traineddata")):
        return configured
    for candidate in (
        "/opt/homebrew/share/tessdata",
        "/usr/local/share/tessdata",
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
    ):
        if os.path.isfile(os.path.join(candidate, "chi_sim.traineddata")):
            os.environ["TESSDATA_PREFIX"] = candidate
            return candidate
    return None


_TESSDATA_PATH = _configure_local_tessdata()

import fitz

from app.core.config import settings


@dataclass
class ExtractResult:
    raw_text: str = ""
    page_count: int = 0
    text_page_count: int = 0
    ocr_page_count: int = 0
    parse_mode: str = "text"  # text | hybrid | partial_text | ocr | failed
    parse_notice: str = ""
    parse_error_code: str | None = None
    parse_quality: dict[str, Any] = field(default_factory=dict)


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 20 * 1024 * 1024
_MIN_PAGE_TEXT = 20
EXTRACTOR_VERSION = "employment-document-local-v2"


def validate_upload(filename: str, content_type: str, file_size: int) -> Optional[str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"不支持的文件格式: {ext}，请上传 PDF、Word、TXT 或图片"
    if file_size > MAX_FILE_SIZE:
        return f"文件过大（{file_size / 1024 / 1024:.1f}MB），请上传 20MB 以内的文件"
    return None


def save_upload(file_bytes: bytes, filename: str) -> str:
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    filepath = os.path.join(upload_dir, f"{uuid.uuid4().hex}{ext}")
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return filepath


def _normalized_repeated_block(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    return re.sub(r"\d+", "#", compact)[:240]


def _join_positioned_words(words: list[tuple]) -> str:
    """Rebuild one visual line, including text drawn in separate overlay blocks.

    Many electronic labor-contract PDFs contain a static template and draw the
    entered dates / role / city as independent text blocks on top of its blank
    slots.  PyMuPDF's block order then places those values before or after the
    clause even though they are on the same visual line.  Joining by page
    coordinates keeps the visible relationship without guessing any value.
    """

    ordered = sorted(words, key=lambda word: (float(word[0]), float(word[1])))
    pieces: list[str] = []
    previous_x1: float | None = None
    previous_height = 0.0
    for word in ordered:
        value = str(word[4] or "").strip()
        if not value:
            continue
        x0, y0, x1, y1 = map(float, word[:4])
        if pieces and previous_x1 is not None:
            gap = x0 - previous_x1
            if gap > max(2.0, previous_height * 0.22):
                pieces.append(" ")
        pieces.append(value)
        previous_x1 = max(previous_x1 or x1, x1)
        previous_height = max(1.0, y1 - y0)
    return "".join(pieces).strip()


def _page_text_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    """Return visual lines rather than PDF content-stream block order."""

    words = [tuple(word) for word in page.get_text("words", sort=False) if len(word) >= 8 and str(word[4] or "").strip()]
    visual_lines: list[dict[str, Any]] = []
    # Cluster by vertical overlap so overlay values from a different PDF block
    # rejoin the template line they visibly occupy.
    for word in sorted(words, key=lambda item: ((float(item[1]) + float(item[3])) / 2, float(item[0]))):
        center = (float(word[1]) + float(word[3])) / 2
        height = max(1.0, float(word[3]) - float(word[1]))
        target = next(
            (
                line
                for line in reversed(visual_lines[-6:])
                if abs(center - float(line["center"])) <= max(2.5, min(height, float(line["height"])) * 0.38)
            ),
            None,
        )
        if target is None:
            visual_lines.append({"center": center, "height": height, "words": [word]})
        else:
            target["words"].append(word)
            count = len(target["words"])
            target["center"] = (float(target["center"]) * (count - 1) + center) / count
            target["height"] = max(float(target["height"]), height)

    blocks: list[dict[str, Any]] = []
    height = max(float(page.rect.height), 1.0)
    for line in sorted(visual_lines, key=lambda item: (float(item["center"]), min(float(word[0]) for word in item["words"]))):
        line_words = line["words"]
        text = _join_positioned_words(line_words)
        if not text:
            continue
        y0 = min(float(word[1]) for word in line_words)
        y1 = max(float(word[3]) for word in line_words)
        edge = "top" if y1 <= height * 0.14 else "bottom" if y0 >= height * 0.86 else "body"
        blocks.append({"text": text, "edge": edge, "key": _normalized_repeated_block(text)})
    return blocks


def _repeated_edge_keys(pages: list[list[dict[str, Any]]]) -> set[str]:
    counter: Counter[str] = Counter()
    for blocks in pages:
        counter.update({block["key"] for block in blocks if block["edge"] != "body" and len(block["key"]) >= 2})
    threshold = max(3, math.ceil(len(pages) * 0.25))
    return {key for key, count in counter.items() if count >= threshold}


def _ocr_page_text(page: fitz.Page) -> str:
    """仅在本地 OCR；未安装 Tesseract 时由调用方降级。"""
    text_page = page.get_textpage_ocr(
        language="chi_sim+eng",
        dpi=200,
        full=True,
        tessdata=_TESSDATA_PATH,
    )
    return _normalize_ocr_text(page.get_text("text", textpage=text_page, sort=True))


def _normalize_ocr_text(text: str) -> str:
    """修复 OCR 把中文词和“第…条”标题误拆成多行的常见情况。"""

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    repaired: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "第" and index + 1 < len(lines) and re.match(r"^[一二三四五六七八九十百零〇0-9]+[章节条款]", lines[index + 1]):
            repaired.append(line + lines[index + 1])
            index += 2
            continue
        repaired.append(line)
        index += 1

    heading = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+[章节条款]")
    normalized: list[str] = []
    for line in repaired:
        if not normalized or heading.match(line) or normalized[-1].endswith(("。", "；", ";", "！", "？", ":", "：")):
            normalized.append(line)
            continue
        if re.search(r"[\u3400-\u9fff]$", normalized[-1]) and re.match(r"^[\u3400-\u9fff]", line):
            normalized[-1] += line
        else:
            normalized.append(line)
    return "\n".join(normalized).strip()


def extract_text_from_pdf(file_bytes: bytes) -> ExtractResult:
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        return ExtractResult(parse_mode="failed", parse_notice="PDF 文件暂时无法读取，请确认文件未损坏后重试。", parse_error_code="pdf_open_failed")

    try:
        page_count = len(doc)
        page_blocks = [_page_text_blocks(page) for page in doc]
        repeated_keys = _repeated_edge_keys(page_blocks)
        page_texts: list[dict[str, Any]] = []
        ocr_available = True
        ocr_attempted = 0
        for index, (page, blocks) in enumerate(zip(doc, page_blocks), start=1):
            kept = [b["text"] for b in blocks if not (b["edge"] != "body" and b["key"] in repeated_keys)]
            text = "\n".join(kept).strip()
            source_mode = "text"
            if len(re.sub(r"\s+", "", text)) < _MIN_PAGE_TEXT and ocr_available:
                ocr_attempted += 1
                try:
                    ocr_text = _ocr_page_text(page)
                    if len(re.sub(r"\s+", "", ocr_text)) > len(re.sub(r"\s+", "", text)):
                        text, source_mode = ocr_text, "ocr"
                except Exception:
                    ocr_available = False
            page_texts.append({"page": index, "text": text, "source_mode": source_mode})

        raw_parts: list[str] = []
        spans: list[dict[str, Any]] = []
        cursor = 0
        for item in page_texts:
            text = item["text"]
            if not text:
                spans.append({"page": item["page"], "start": cursor, "end": cursor, "character_count": 0, "source_mode": "empty"})
                continue
            if raw_parts:
                raw_parts.append("\n\n")
                cursor += 2
            start = cursor
            raw_parts.append(text)
            cursor += len(text)
            spans.append({"page": item["page"], "start": start, "end": cursor, "character_count": len(text), "source_mode": item["source_mode"]})

        raw_text = "".join(raw_parts)
        text_pages = sum(s["character_count"] >= _MIN_PAGE_TEXT and s["source_mode"] == "text" for s in spans)
        ocr_pages = sum(s["character_count"] >= _MIN_PAGE_TEXT and s["source_mode"] == "ocr" for s in spans)
        empty_pages = sum(s["character_count"] == 0 for s in spans)
        low_pages = sum(0 < s["character_count"] < _MIN_PAGE_TEXT for s in spans)
        readable_pages = text_pages + ocr_pages
        quality = {
            "extractor_version": EXTRACTOR_VERSION,
            "actual_page_count": page_count,
            "text_page_count": text_pages,
            "ocr_page_count": ocr_pages,
            "empty_page_count": empty_pages,
            "low_quality_page_count": low_pages,
            "repeated_block_count": len(repeated_keys),
            "character_count": len(raw_text),
            "ocr_attempted_page_count": ocr_attempted,
            "ocr_available": ocr_available or ocr_attempted == 0,
            "pages": spans,
        }
        if len(raw_text.strip()) < 50:
            return ExtractResult(
                raw_text=raw_text, page_count=page_count, text_page_count=text_pages, ocr_page_count=ocr_pages,
                parse_mode="failed", parse_notice="原件已保留，但这份 PDF 暂时没有可靠读出文字，可以改用粘贴文字继续。",
                parse_error_code="ocr_unavailable" if ocr_attempted and not ocr_available else "no_readable_text",
                parse_quality=quality,
            )
        incomplete = readable_pages < page_count
        mode = "hybrid" if ocr_pages and incomplete else "ocr" if ocr_pages else "partial_text" if incomplete else "text"
        notice = f"已读出 {readable_pages}/{page_count} 页文字；未读出的页面不会生成审查结论。" if incomplete else ""
        return ExtractResult(
            raw_text=raw_text, page_count=page_count, text_page_count=text_pages, ocr_page_count=ocr_pages,
            parse_mode=mode, parse_notice=notice, parse_error_code="partial_pages" if incomplete else None,
            parse_quality=quality,
        )
    finally:
        doc.close()


def extract_text_from_image(file_bytes: bytes) -> ExtractResult:
    try:
        filetype = "png" if file_bytes[:4] == b"\x89PNG" else "jpeg"
        doc = fitz.open(stream=file_bytes, filetype=filetype)
        page = doc[0]
        text = page.get_text("text", sort=True).strip()
        if len(text) < 50:
            try:
                text = _ocr_page_text(page)
            except Exception:
                text = ""
        doc.close()
        if len(text.strip()) >= 50:
            length = len(text)
            return ExtractResult(
                raw_text=text, page_count=1, ocr_page_count=1, parse_mode="ocr",
                parse_quality={"actual_page_count": 1, "text_page_count": 0, "ocr_page_count": 1, "empty_page_count": 0,
                               "extractor_version": EXTRACTOR_VERSION,
                               "low_quality_page_count": 0, "repeated_block_count": 0, "character_count": length,
                               "pages": [{"page": 1, "start": 0, "end": length, "character_count": length, "source_mode": "ocr"}]},
            )
        return ExtractResult(
            page_count=1, parse_mode="failed", parse_notice="原件已保留，但图片文字暂时没有可靠读出，请改用粘贴文字。",
            parse_error_code="ocr_unavailable",
            parse_quality={"actual_page_count": 1, "text_page_count": 0, "ocr_page_count": 0, "empty_page_count": 1,
                           "extractor_version": EXTRACTOR_VERSION,
                           "low_quality_page_count": 0, "repeated_block_count": 0, "character_count": 0, "pages": []},
        )
    except Exception:
        return ExtractResult(parse_mode="failed", parse_notice="图片暂时无法读取。", parse_error_code="image_open_failed")


def _single_text_result(text: str, *, kind: str) -> ExtractResult:
    if len(text.strip()) < 50:
        return ExtractResult(raw_text=text, page_count=1, parse_mode="failed", parse_notice=f"{kind} 文字内容太少", parse_error_code="text_too_short")
    length = len(text)
    return ExtractResult(
        raw_text=text, page_count=1, text_page_count=1, parse_mode="text",
        parse_quality={"actual_page_count": 1, "text_page_count": 1, "ocr_page_count": 0, "empty_page_count": 0,
                       "extractor_version": EXTRACTOR_VERSION,
                       "low_quality_page_count": 0, "repeated_block_count": 0, "character_count": length,
                       "pages": [{"page": 1, "start": 0, "end": length, "character_count": length, "source_mode": "text"}]},
    )


def extract_text(file_bytes: bytes, filename: str) -> ExtractResult:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            return _single_text_result("\n".join(v.strip() for v in root.itertext() if v and v.strip()), kind="Word 文档")
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            return ExtractResult(parse_mode="failed", parse_notice="Word 文档暂时无法读取。", parse_error_code="docx_open_failed")
    if ext == ".txt":
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("gb18030", errors="replace")
        return _single_text_result(text, kind="文本")
    if ext in {".png", ".jpg", ".jpeg"}:
        return extract_text_from_image(file_bytes)
    return ExtractResult(parse_mode="failed", parse_notice="不支持的文件格式", parse_error_code="unsupported_file_type")
