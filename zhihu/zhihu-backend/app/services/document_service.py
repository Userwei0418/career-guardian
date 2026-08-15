"""文档上传与文本提取服务。

支持 PDF 和图片文件，使用 PyMuPDF 提取文本。
参考: engineering-contract-ai-review/backend/app/services/contract_service.py
"""
import os
import uuid
import zipfile
from io import BytesIO
from xml.etree import ElementTree
from dataclasses import dataclass, field
from typing import Optional

import fitz  # PyMuPDF

from app.core.config import settings


@dataclass
class ExtractResult:
    raw_text: str = ""
    page_count: int = 0
    parse_mode: str = "text"  # "text" | "ocr" | "failed"
    parse_notice: str = ""


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def validate_upload(filename: str, content_type: str, file_size: int) -> Optional[str]:
    """校验上传文件，返回错误信息或 None"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"不支持的文件格式: {ext}，请上传 PDF、Word、TXT 或图片"
    if file_size > MAX_FILE_SIZE:
        return f"文件过大（{file_size / 1024 / 1024:.1f}MB），请上传 20MB 以内的文件"
    return None


def save_upload(file_bytes: bytes, filename: str) -> str:
    """保存上传文件到本地，返回文件路径"""
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    saved_name = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, saved_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return filepath


def extract_text_from_pdf(file_bytes: bytes) -> ExtractResult:
    """从 PDF 提取文本（PyMuPDF）"""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages_text.append(text)
        doc.close()

        raw_text = "\n\n".join(pages_text)
        if len(raw_text.strip()) < 50:
            return ExtractResult(
                raw_text=raw_text,
                page_count=len(pages_text),
                parse_mode="failed",
                parse_notice="这份没太看清，文字内容太少，建议换粘贴或手动填也一样",
            )
        return ExtractResult(raw_text=raw_text, page_count=len(pages_text))
    except Exception as e:
        return ExtractResult(parse_mode="failed", parse_notice=f"文件解析失败: {str(e)}")


def extract_text_from_image(file_bytes: bytes) -> ExtractResult:
    """从图片提取文本（PyMuPDF 渲染 + 简单 OCR 降级）

    注意：完整 OCR 需要 Tesseract，此处先用 PyMuPDF 的图片模式处理。
    后续可接入 Tesseract 做真正的 OCR。
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="png" if file_bytes[:4] == b"\x89PNG" else "jpeg")
        page = doc[0]
        text = page.get_text()
        doc.close()
        if text.strip():
            return ExtractResult(raw_text=text, page_count=1)
        return ExtractResult(
            parse_mode="failed",
            parse_notice="图片文字暂时没看清，建议换粘贴文字或手动输入",
        )
    except Exception as e:
        return ExtractResult(parse_mode="failed", parse_notice=f"图片解析失败: {str(e)}")


def extract_text(file_bytes: bytes, filename: str) -> ExtractResult:
    """根据文件类型选择提取方式"""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            text = "\n".join(
                value.strip()
                for value in root.itertext()
                if value and value.strip()
            )
            if len(text) < 50:
                return ExtractResult(raw_text=text, parse_mode="failed", parse_notice="Word 文档文字内容太少")
            return ExtractResult(raw_text=text, page_count=1)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            return ExtractResult(parse_mode="failed", parse_notice=f"Word 文档解析失败: {exc}")
    elif ext == ".txt":
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("gb18030", errors="replace")
        if len(text.strip()) < 50:
            return ExtractResult(raw_text=text, parse_mode="failed", parse_notice="文本内容太少")
        return ExtractResult(raw_text=text, page_count=1)
    elif ext in {".png", ".jpg", ".jpeg"}:
        return extract_text_from_image(file_bytes)
    return ExtractResult(parse_mode="failed", parse_notice="不支持的文件格式")
