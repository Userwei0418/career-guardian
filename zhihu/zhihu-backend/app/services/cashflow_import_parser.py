from __future__ import annotations

import csv
import hashlib
import json
import posixpath
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
from typing import Iterable, Mapping
from xml.etree import ElementTree

from app.services.cashflow_privacy import redact_cashflow_text
from app.cashflow_validation import is_supported_financial_date


MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_COLUMNS = 80
MAX_XLSX_UNCOMPRESSED_SIZE = 32 * 1024 * 1024
MAX_XLSX_WORKSHEET_SIZE = 24 * 1024 * 1024
MAX_XLSX_SHARED_STRINGS_SIZE = 8 * 1024 * 1024
MAX_XLSX_SHARED_STRING_COUNT = 100_000
MAX_XLSX_METADATA_SIZE = 1024 * 1024
MAX_XLSX_SHARED_STRING_XML_NODES = 500_000
MAX_XLSX_WORKSHEET_XML_NODES = 1_500_000
ALLOWED_IMPORT_EXTENSIONS = {".csv", ".tsv", ".xlsx"}
PARSER_VERSION = "cashflow-tabular-v3"
MAX_TRANSACTION_AMOUNT = Decimal("999999999999.99")
MAX_XLSX_SHARED_STRING_TEXT_NODES = 256
MAX_XLSX_CELL_TEXT_NODES = 64
MAX_XLSX_XML_DEPTH = 64


class CashflowImportError(ValueError):
    pass


@dataclass(frozen=True)
class ImportTable:
    source_type: str
    headers: list[str]
    rows: list[dict[str, str]]
    mapping: dict[str, str]
    header_row_number: int
    row_numbers: list[int]
    mapping_required: bool
    excel_date_1904: bool = False


@dataclass(frozen=True)
class ParsedCandidate:
    row_number: int
    direction: str | None
    amount: Decimal | None
    currency: str
    transaction_date: date | None
    occurred_at: datetime | None
    category_name: str | None
    merchant: str | None
    description: str | None
    nature: str | None
    external_key: str
    fingerprint: str
    original_payload: dict[str, str]
    evidence: dict
    validation_errors: list[dict[str, str]]
    warnings: list[dict[str, str]]


def _normalized_header(value: str) -> str:
    return re.sub(r"[\s\-_/\\:：()（）\[\]【】]+", "", str(value or "")).strip().lower()


FIELD_ALIASES = {
    "transaction_date": {
        "交易时间", "交易日期", "记账日期", "发生日期", "付款时间", "入账时间",
        "日期", "时间", "transactiondate", "datetime", "date", "time",
    },
    "direction": {
        "收支", "收支类型", "资金方向", "资金流向", "方向", "借贷标志", "借贷方向",
        "direction", "inout",
    },
    "amount": {
        "金额", "金额元", "交易金额", "交易金额元", "发生金额", "amount", "money",
    },
    "income_amount": {"收入", "收入金额", "贷方金额", "贷方发生额", "credit", "income"},
    "expense_amount": {"支出", "支出金额", "借方金额", "借方发生额", "debit", "expense"},
    "merchant": {
        "交易对方", "交易对象", "商户", "商家", "收付款方", "对方户名", "对方名称",
        "merchant", "counterparty", "payee", "payer",
    },
    "description": {
        "商品", "商品名称", "商品说明", "摘要", "交易摘要", "备注", "交易备注", "用途",
        "description", "memo", "note",
    },
    "category": {"分类", "交易分类", "类别", "category"},
    "nature": {"支出性质", "性质", "nature"},
    "external_id": {
        "交易单号", "交易号", "流水号", "业务流水号", "订单号", "商户单号",
        "transactionid", "tradeno", "orderno", "reference",
    },
    "source_account": {
        "本方账号", "本人账号", "交易账号", "交易卡号", "银行卡号", "卡号", "账号",
        "account", "accountnumber", "cardnumber",
    },
    "currency": {"币种", "货币", "交易币种", "currency", "ccy"},
    "transaction_type": {"交易类型", "业务类型", "类型", "transactiontype", "businesstype"},
    "source_status": {"当前状态", "交易状态", "资金状态", "状态", "status"},
}
FIELD_ALIASES = {
    field: {_normalized_header(alias) for alias in aliases}
    for field, aliases in FIELD_ALIASES.items()
}


def validate_import_file(filename: str, content: bytes) -> str:
    safe_name = Path(filename or "").name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_IMPORT_EXTENSIONS:
        if extension == ".xls":
            raise CashflowImportError("暂不读取旧版 .xls，请另存为 .xlsx、.csv 或 .tsv 后再上传")
        raise CashflowImportError("仅支持 .csv、.tsv 和 .xlsx 账单文件")
    if not content:
        raise CashflowImportError("账单文件为空")
    if len(content) > MAX_IMPORT_FILE_SIZE:
        raise CashflowImportError("账单文件不能超过 10MB")
    if extension == ".xlsx" and not content.startswith(b"PK"):
        raise CashflowImportError("文件内容不是有效的 .xlsx 工作簿")
    return extension


def _decode_delimited(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CashflowImportError("无法识别表格文字编码，请转换为 UTF-8 CSV 后重试")


def _delimited_rows(content: bytes, extension: str) -> list[list[str]]:
    text = _decode_delimited(content)
    sample = text[:8192]
    delimiter = "\t" if extension == ".tsv" else ","
    if extension != ".tsv":
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
        except csv.Error:
            counts = {candidate: sample.count(candidate) for candidate in (",", "\t", ";")}
            delimiter = max(counts, key=counts.get)
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    rows: list[list[str]] = []
    for row in reader:
        if len(row) > MAX_IMPORT_COLUMNS:
            raise CashflowImportError(f"账单列数不能超过 {MAX_IMPORT_COLUMNS} 列")
        rows.append([str(value or "").strip()[:500] for value in row[:MAX_IMPORT_COLUMNS]])
        if len(rows) > MAX_IMPORT_ROWS + 100:
            break
    return rows


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        info = archive.getinfo("xl/sharedStrings.xml")
    except KeyError:
        return []
    if info.file_size > MAX_XLSX_SHARED_STRINGS_SIZE:
        raise CashflowImportError("工作簿共享文字过大，已停止读取")
    values: list[str] = []
    current_parts: list[str] | None = None
    current_text_nodes = 0
    node_count = 0
    stack: list[ElementTree.Element] = []
    try:
        with archive.open(info) as stream:
            for event, item in ElementTree.iterparse(stream, events=("start", "end")):
                tag = item.tag.rsplit("}", 1)[-1]
                if event == "start":
                    stack.append(item)
                    if len(stack) > MAX_XLSX_XML_DEPTH:
                        raise CashflowImportError("工作簿共享文字 XML 嵌套过深，已停止读取")
                    node_count += 1
                    if node_count > MAX_XLSX_SHARED_STRING_XML_NODES:
                        raise CashflowImportError("工作簿共享文字 XML 结构过于复杂，已停止读取")
                    if tag == "si":
                        current_parts = []
                        current_text_nodes = 0
                    continue
                if event == "end" and tag == "t" and current_parts is not None:
                    current_text_nodes += 1
                    if current_text_nodes > MAX_XLSX_SHARED_STRING_TEXT_NODES:
                        raise CashflowImportError("工作簿单个共享文字结构过于复杂，已停止读取")
                    remaining = 500 - sum(len(part) for part in current_parts)
                    if remaining > 0:
                        current_parts.append((item.text or "")[:remaining])
                elif event == "end" and tag == "si":
                    values.append("".join(current_parts or []))
                    current_parts = None
                    if len(values) > MAX_XLSX_SHARED_STRING_COUNT:
                        raise CashflowImportError("工作簿共享文字条目过多，已停止读取")
                # Clearing alone leaves empty child objects attached to a huge
                # parent. Detach every completed element so unknown tags and
                # rich-text wrappers cannot accumulate an in-memory DOM.
                if len(stack) >= 2:
                    try:
                        stack[-2].remove(item)
                    except ValueError:
                        pass
                item.clear()
                if stack:
                    stack.pop()
    except ElementTree.ParseError as exc:
        raise CashflowImportError("无法读取 .xlsx 共享文字") from exc
    return values


def _column_index(cell_reference: str) -> int:
    reference = str(cell_reference or "")
    if not reference:
        return 0
    match = re.fullmatch(r"([A-Za-z]{1,3})(?:[1-9]\d{0,6})?", reference)
    if match is None:
        raise CashflowImportError("工作簿单元格坐标无效")
    result = 0
    for character in match.group(1).upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return max(0, result - 1)


def _workbook_info(archive: zipfile.ZipFile) -> tuple[str, bool]:
    names = set(archive.namelist())
    try:
        workbook_info = archive.getinfo("xl/workbook.xml")
        relationships_info = archive.getinfo("xl/_rels/workbook.xml.rels")
    except KeyError as exc:
        raise CashflowImportError("工作簿缺少必需的元数据或工作表关系") from exc
    if (
        workbook_info.file_size > MAX_XLSX_METADATA_SIZE
        or relationships_info.file_size > MAX_XLSX_METADATA_SIZE
    ):
        raise CashflowImportError("工作簿元数据过大，已停止读取")

    try:
        workbook = ElementTree.fromstring(archive.read(workbook_info))
        relationships = ElementTree.fromstring(archive.read(relationships_info))
    except ElementTree.ParseError as exc:
        # Never guess sheet1 after malformed workbook metadata. In particular,
        # losing workbookPr/date1904 would shift every numeric date by 1,462
        # days while still producing superficially valid financial facts.
        raise CashflowImportError("无法读取 .xlsx 工作簿元数据") from exc

    workbook_properties = workbook.find(".//{*}workbookPr")
    raw_date_system = (
        ""
        if workbook_properties is None
        else str(workbook_properties.attrib.get("date1904", "")).strip().lower()
    )
    if raw_date_system in {"", "0", "false"}:
        date_1904 = False
    elif raw_date_system in {"1", "true"}:
        date_1904 = True
    else:
        raise CashflowImportError("工作簿日期系统标记无效")

    first_sheet = workbook.find(".//{*}sheet")
    if first_sheet is None:
        raise CashflowImportError("工作簿中没有可读取的工作表")
    relation_id = next(
        (
            value
            for key, value in first_sheet.attrib.items()
            if key.endswith("}id") or key == "r:id"
        ),
        None,
    )
    if not relation_id:
        raise CashflowImportError("工作簿首个工作表缺少关系标识")

    matching_relationships = [
        relationship
        for relationship in relationships.findall(".//{*}Relationship")
        if relationship.attrib.get("Id") == relation_id
    ]
    if len(matching_relationships) != 1:
        raise CashflowImportError("工作簿首个工作表关系无效")
    relationship = matching_relationships[0]
    if relationship.attrib.get("Type") not in {
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
        "http://purl.oclc.org/ooxml/officeDocument/relationships/worksheet",
    }:
        raise CashflowImportError("工作簿首个工作表关系类型无效")
    if str(relationship.attrib.get("TargetMode", "")).strip().lower() == "external":
        raise CashflowImportError("工作簿不能引用外部工作表")

    target = str(relationship.attrib.get("Target", "")).strip()
    if (
        not target
        or "\\" in target
        or "\x00" in target
        or "?" in target
        or "#" in target
        or target.startswith("//")
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
    ):
        raise CashflowImportError("工作簿首个工作表路径无效")
    candidate = posixpath.normpath(
        target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
    )
    if (
        not candidate.startswith("xl/worksheets/")
        or candidate not in names
    ):
        raise CashflowImportError("工作簿首个工作表路径不存在或超出允许范围")
    return candidate, date_1904


def _xlsx_rows(content: bytes) -> tuple[list[list[str]], list[int], bool]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > 500 or sum(item.file_size for item in infos) > MAX_XLSX_UNCOMPRESSED_SIZE:
                raise CashflowImportError("工作簿解压后过大，已停止读取")
            shared_strings = _xlsx_shared_strings(archive)
            worksheet_path, date_1904 = _workbook_info(archive)
            worksheet_info = archive.getinfo(worksheet_path)
            if worksheet_info.file_size > MAX_XLSX_WORKSHEET_SIZE:
                raise CashflowImportError("工作簿交易工作表过大，已停止读取")

            rows: list[list[str]] = []
            row_numbers: list[int] = []
            seen_row_numbers: set[int] = set()
            last_row_number = 0
            current_row_number = 0
            current_values: dict[int, str] | None = None
            current_cell_count = 0
            current_cell_index = 0
            current_cell_type: str | None = None
            current_cell_value = ""
            current_cell_text_parts: list[str] = []
            current_cell_text_nodes = 0
            worksheet_node_count = 0
            stack: list[ElementTree.Element] = []
            with archive.open(worksheet_info) as stream:
                for event, item in ElementTree.iterparse(stream, events=("start", "end")):
                    tag = item.tag.rsplit("}", 1)[-1]
                    if event == "start":
                        stack.append(item)
                        if len(stack) > MAX_XLSX_XML_DEPTH:
                            raise CashflowImportError("工作簿 XML 嵌套过深，已停止读取")
                        worksheet_node_count += 1
                        if worksheet_node_count > MAX_XLSX_WORKSHEET_XML_NODES:
                            raise CashflowImportError("工作簿 XML 结构过于复杂，已停止读取")
                        if tag == "row":
                            if current_values is not None:
                                raise CashflowImportError("工作簿行结构无效")
                            current_values = {}
                            current_cell_count = 0
                            raw_row_number = str(item.attrib.get("r", "")).strip()
                            if raw_row_number:
                                if re.fullmatch(r"[1-9]\d{0,6}", raw_row_number) is None:
                                    raise CashflowImportError("工作簿行号无效")
                                current_row_number = int(raw_row_number)
                                if current_row_number > 1_048_576:
                                    raise CashflowImportError("工作簿行号超出 Excel 范围")
                            else:
                                current_row_number = last_row_number + 1
                            if current_row_number in seen_row_numbers:
                                raise CashflowImportError("工作簿存在重复行号")
                            seen_row_numbers.add(current_row_number)
                            last_row_number = current_row_number
                        elif tag == "c":
                            if current_values is None:
                                raise CashflowImportError("工作簿单元格不属于任何数据行")
                            current_cell_count += 1
                            if current_cell_count > MAX_IMPORT_COLUMNS:
                                raise CashflowImportError(f"账单列数不能超过 {MAX_IMPORT_COLUMNS} 列")
                            current_cell_index = _column_index(item.attrib.get("r", ""))
                            if current_cell_index >= MAX_IMPORT_COLUMNS:
                                raise CashflowImportError(f"账单列数不能超过 {MAX_IMPORT_COLUMNS} 列")
                            current_cell_type = item.attrib.get("t")
                            current_cell_value = ""
                            current_cell_text_parts = []
                            current_cell_text_nodes = 0
                        continue
                    if tag == "v" and current_values is not None:
                        current_cell_value = (item.text or "")[:500]
                    elif tag == "t" and current_values is not None:
                        current_cell_text_nodes += 1
                        if current_cell_text_nodes > MAX_XLSX_CELL_TEXT_NODES:
                            raise CashflowImportError("工作簿单元格文字结构过于复杂")
                        remaining = 500 - sum(len(part) for part in current_cell_text_parts)
                        if remaining > 0:
                            current_cell_text_parts.append((item.text or "")[:remaining])
                    elif tag == "c" and current_values is not None:
                        value = (
                            "".join(current_cell_text_parts)
                            if current_cell_type == "inlineStr"
                            else current_cell_value
                        )
                        if current_cell_type == "s" and value:
                            try:
                                value = shared_strings[int(value)]
                            except (IndexError, ValueError):
                                value = ""
                        current_values[current_cell_index] = str(value or "").strip()[:500]
                    elif tag == "row":
                        values = current_values or {}
                        if values:
                            width = min(max(values) + 1, MAX_IMPORT_COLUMNS)
                            rows.append([values.get(index, "") for index in range(width)])
                        else:
                            rows.append([])
                        row_numbers.append(current_row_number)
                        current_values = None
                        if len(rows) > MAX_IMPORT_ROWS + 100:
                            # Finish detaching this row before stopping the
                            # parser; no later XML is needed for the row cap.
                            if len(stack) >= 2:
                                try:
                                    stack[-2].remove(item)
                                except ValueError:
                                    pass
                            item.clear()
                            if stack:
                                stack.pop()
                            break
                    if len(stack) >= 2:
                        try:
                            stack[-2].remove(item)
                        except ValueError:
                            pass
                    item.clear()
                    if stack:
                        stack.pop()
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
        raise CashflowImportError("无法读取 .xlsx 工作簿") from exc
    return rows, row_numbers, date_1904


def _mapping_for_headers(headers: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = _normalized_header(header)
        for field, aliases in FIELD_ALIASES.items():
            if field not in mapping and normalized in aliases:
                mapping[field] = header
                break
    return mapping


def _mapping_complete(mapping: Mapping[str, str]) -> bool:
    has_amount = "amount" in mapping or "income_amount" in mapping or "expense_amount" in mapping
    has_direction = "direction" in mapping or (
        "income_amount" in mapping and "expense_amount" in mapping
    )
    return "transaction_date" in mapping and has_amount and has_direction


def _detect_source(headers: Iterable[str], source_hint: str) -> str:
    if source_hint in {"wechat", "alipay", "bank", "generic"}:
        return source_hint
    normalized = {_normalized_header(header) for header in headers}
    if {"交易单号", "收支", "支付方式"}.issubset(normalized):
        return "wechat"
    if "交易号" in normalized and ("资金状态" in normalized or "交易来源地" in normalized):
        return "alipay"
    if normalized.intersection({"借方金额", "贷方金额", "对方户名", "借贷标志"}):
        return "bank"
    return "generic"


def read_import_table(
    content: bytes,
    filename: str,
    *,
    source_hint: str = "auto",
    mapping_override: Mapping[str, str] | None = None,
) -> ImportTable:
    extension = validate_import_file(filename, content)
    if extension == ".xlsx":
        rows, raw_row_numbers, excel_date_1904 = _xlsx_rows(content)
    else:
        rows = _delimited_rows(content, extension)
        raw_row_numbers = list(range(1, len(rows) + 1))
        excel_date_1904 = False
    nonempty = [index for index, row in enumerate(rows) if any(str(value).strip() for value in row)]
    if not nonempty:
        raise CashflowImportError("账单文件中没有可读取的行")

    best_index = nonempty[0]
    best_mapping: dict[str, str] = {}
    best_score = -1
    for index in nonempty[:81]:
        headers = [str(value or "").strip() for value in rows[index]]
        mapping = _mapping_for_headers(headers)
        score = len(mapping) + (3 if _mapping_complete(mapping) else 0)
        if score > best_score:
            best_index, best_mapping, best_score = index, mapping, score
    # A single accidental alias inside a data row (for example a cell whose
    # value is just “支出”) is not enough evidence that the row is a header.
    # Known provider exports expose several recognizable columns; generic
    # tables fall back to their first non-empty row and can then be mapped by
    # the user.
    if best_score < 2:
        best_index = nonempty[0]
        best_mapping = _mapping_for_headers(rows[best_index])
    headers = [str(value or "").strip() or f"未命名列{index + 1}" for index, value in enumerate(rows[best_index])]
    if not headers:
        raise CashflowImportError("账单文件缺少表头")
    normalized_headers = [_normalized_header(header) for header in headers]
    if len(set(normalized_headers)) != len(normalized_headers):
        raise CashflowImportError("账单表头存在重复列，请重命名后再上传")

    if mapping_override is not None:
        available = set(headers)
        invalid = [value for value in mapping_override.values() if value not in available]
        if invalid:
            raise CashflowImportError(f"字段映射引用了不存在的列：{invalid[0]}")
        best_mapping = {key: value for key, value in mapping_override.items() if key in FIELD_ALIASES}

    data_row_entries = [
        (raw_row_numbers[index], values)
        for index, values in enumerate(rows[best_index + 1:], start=best_index + 1)
        if any(str(value).strip() for value in values)
    ]
    data_rows = [values for _row_number, values in data_row_entries]
    if len(data_rows) > MAX_IMPORT_ROWS:
        raise CashflowImportError(f"单个账单最多支持 {MAX_IMPORT_ROWS} 条交易记录")
    normalized_rows: list[dict[str, str]] = []
    for values in data_rows:
        normalized_rows.append({
            header: (str(values[index]).strip()[:500] if index < len(values) else "")
            for index, header in enumerate(headers)
        })
    if not normalized_rows:
        raise CashflowImportError("账单文件只有表头，没有交易记录")
    return ImportTable(
        source_type=_detect_source(headers, source_hint),
        headers=headers,
        rows=normalized_rows,
        mapping=best_mapping,
        header_row_number=raw_row_numbers[best_index],
        row_numbers=[row_number for row_number, _values in data_row_entries],
        mapping_required=not _mapping_complete(best_mapping),
        excel_date_1904=excel_date_1904,
    )


def _value(row: Mapping[str, str], mapping: Mapping[str, str], field: str) -> str:
    header = mapping.get(field)
    return "" if header is None else str(row.get(header, "") or "").strip()


def _parse_decimal(value: str) -> tuple[Decimal | None, bool]:
    token = str(value or "").strip().replace("，", ",")
    parenthesized = token.startswith("(") and token.endswith(")")
    if token.startswith("(") != token.endswith(")"):
        return None, False
    if parenthesized:
        token = token[1:-1].strip()
    token = re.sub(r"^[¥￥]\s*", "", token)
    token = re.sub(r"\s*元$", "", token)
    token = token.strip()
    negative = parenthesized or token.startswith("-")
    if token[:1] in {"+", "-"}:
        token = token[1:]
    token = token.strip()
    if not token:
        return None, negative
    ungrouped = r"(?:\d+(?:\.\d+)?|\.\d+)"
    grouped = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    if re.fullmatch(f"(?:{ungrouped}|{grouped})", token) is None:
        return None, negative
    try:
        parsed = Decimal(token.replace(",", ""))
        # Decimal accepts lexical values such as NaN and Infinity, but they
        # are not financial facts and comparisons against them may raise.
        return (parsed, negative) if parsed.is_finite() else (None, negative)
    except InvalidOperation:
        return None, negative


def _parse_datetime(
    value: str,
    *,
    excel_date_1904: bool = False,
) -> tuple[date | None, datetime | None]:
    normalized = str(value or "").strip()
    if not normalized:
        return None, None
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        serial_decimal = Decimal(normalized)
        if Decimal("20000") <= serial_decimal <= Decimal("80000"):
            base = datetime(1904, 1, 1) if excel_date_1904 else datetime(1899, 12, 30)
            parsed = base + timedelta(days=float(serial_decimal))
            has_explicit_time = serial_decimal != serial_decimal.to_integral_value()
            return parsed.date(), parsed if has_explicit_time else None
    normalized = normalized.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    normalized = re.sub(r"\s+", " ", normalized)
    iso_value = normalized.replace("/", "-")
    # Python accepts a date-only ISO value as midnight. Keep the distinction
    # between a source-provided time and an invented 00:00:00 timestamp.
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", iso_value):
        try:
            return datetime.strptime(iso_value, "%Y-%m-%d").date(), None
        except ValueError:
            return None, None
    try:
        parsed = datetime.fromisoformat(iso_value)
        return parsed.date(), parsed
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized.replace("/", "-"), pattern)
            return parsed.date(), parsed if "%H" in pattern else None
        except ValueError:
            continue
    return None, None


def _direction_and_amount(
    row: Mapping[str, str],
    mapping: Mapping[str, str],
    source_type: str,
) -> tuple[str | None, Decimal | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    direction_value = _value(row, mapping, "direction").strip().lower()
    transaction_type = _value(row, mapping, "transaction_type").strip().lower()
    income_amount, income_negative = _parse_decimal(_value(row, mapping, "income_amount"))
    expense_amount, expense_negative = _parse_decimal(_value(row, mapping, "expense_amount"))

    explicit_direction: str | None = None
    if direction_value == "贷" or any(token in direction_value for token in ("收入", "入账", "贷方", "credit")):
        explicit_direction = "income"
    elif direction_value == "借" or any(token in direction_value for token in ("支出", "付款", "借方", "debit")):
        explicit_direction = "expense"
    elif direction_value in {"/", "其他", "中性", "不计收支", "transfer", "转账"}:
        explicit_direction = "transfer"

    direction: str | None = None
    amount: Decimal | None = None
    if income_amount is not None and income_amount > 0:
        direction, amount = "income", income_amount
        if income_negative:
            errors.append({
                "field": "amount",
                "code": "SIGN_DIRECTION_CONFLICT",
                "message": "贷方收入列金额为负数，请核对原始账单",
            })
    if expense_amount is not None and expense_amount > 0:
        if direction is not None:
            errors.append({"field": "amount", "code": "BOTH_SIDES_HAVE_AMOUNT", "message": "同一行同时存在收入和支出金额"})
        else:
            direction, amount = "expense", expense_amount
        if expense_negative:
            errors.append({
                "field": "amount",
                "code": "SIGN_DIRECTION_CONFLICT",
                "message": "借方支出列金额为负数，请核对原始账单",
            })

    if direction is not None and explicit_direction is not None and direction != explicit_direction:
        errors.append({
            "field": "direction",
            "code": "DIRECTION_COLUMN_CONFLICT",
            "message": "收支方向列与收入/支出金额列矛盾，请核对源账单",
        })
    if direction is None:
        direction = explicit_direction

    raw_amount = _value(row, mapping, "amount")
    parsed_amount, negative = _parse_decimal(raw_amount)
    if amount is None:
        amount = parsed_amount
    if direction is None and parsed_amount is not None:
        if negative:
            direction = "expense"
        elif source_type == "bank" and raw_amount.strip().startswith("+"):
            direction = "income"
    # Internal money movement must not inflate either income or expense even
    # when a provider also labels it as “收入/支出”.
    if any(token in transaction_type for token in ("提现", "充值", "账户转账")):
        direction = "transfer"

    if direction is None:
        errors.append({"field": "direction", "code": "DIRECTION_REQUIRED", "message": "无法判断收入、支出或转账"})
    if amount is None:
        errors.append({"field": "amount", "code": "AMOUNT_INVALID", "message": "金额无法识别"})
    else:
        if negative and direction == "income":
            errors.append({
                "field": "amount",
                "code": "SIGN_DIRECTION_CONFLICT",
                "message": "来源标记为收入但金额为负数，请核对方向和金额",
            })
        amount = abs(amount)
        if amount <= 0:
            errors.append({"field": "amount", "code": "AMOUNT_NOT_POSITIVE", "message": "金额必须大于 0"})
        if amount > MAX_TRANSACTION_AMOUNT:
            errors.append({"field": "amount", "code": "AMOUNT_TOO_LARGE", "message": "金额超出支持范围"})
        if -amount.as_tuple().exponent > 2:
            errors.append({"field": "amount", "code": "AMOUNT_SCALE", "message": "金额最多保留两位小数"})
    return direction, amount, errors


def _suggest_category(
    direction: str | None,
    category_hint: str,
    merchant: str,
    description: str,
    transaction_type: str,
) -> str | None:
    if direction not in {"income", "expense"}:
        return None
    text = " ".join((category_hint, merchant, description, transaction_type)).lower()
    if direction == "income":
        rules = (
            ("工资", ("工资", "薪资", "salary")),
            ("奖金", ("奖金", "年终奖", "bonus")),
            ("兼职副业", ("兼职", "稿费", "副业")),
            ("投资收益", ("利息", "分红", "理财", "投资")),
            ("报销", ("报销",)),
            ("退款", ("退款", "退货")),
            ("补贴", ("补贴", "津贴")),
        )
        fallback = "其他收入"
    else:
        rules = (
            ("住房", ("房租", "租金", "物业", "水费", "电费", "燃气")),
            ("餐饮", ("餐饮", "外卖", "餐厅", "饭店", "咖啡", "奶茶", "美团")),
            ("交通", ("地铁", "公交", "打车", "滴滴", "高铁", "机票", "加油", "停车")),
            ("医疗", ("医院", "药房", "医疗", "挂号", "体检")),
            ("学习", ("课程", "培训", "书店", "学费", "考试")),
            ("家庭", ("家庭", "家人", "育儿", "母婴")),
            ("购物", ("购物", "超市", "淘宝", "京东", "拼多多")),
            ("娱乐", ("电影", "游戏", "娱乐", "会员")),
            ("人情", ("红包", "礼金", "人情")),
        )
        fallback = "其他支出"
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category
    return category_hint.strip()[:80] or fallback


LIABILITY_TRANSFER_TOKENS = (
    "信用卡还款",
    "花呗还款",
    "白条还款",
    "贷款本金",
    "归还贷款本金",
    "偿还本金",
    "本金还款",
)


def _suggest_nature(direction: str | None, category_name: str | None, text: str) -> str | None:
    if direction != "expense":
        return None
    if category_name == "住房" or any(keyword in text for keyword in ("房租", "订阅", "月费")):
        return "fixed"
    if any(keyword in text for keyword in ("报销", "垫付")):
        return "reimbursable"
    return "flexible"


def build_candidate_fingerprint(
    *,
    direction: str | None,
    amount: Decimal | None,
    transaction_date: date | None,
    merchant: str | None,
    description: str | None,
) -> str:
    normalized_merchant = _normalize_duplicate_text(merchant)
    normalized_description = _normalize_duplicate_text(description)
    payload = {
        "rule": "cashflow-fuzzy-v2",
        "direction": direction,
        "amount": format(amount.quantize(Decimal("0.01")), "f") if amount is not None else None,
        "date": transaction_date.isoformat() if transaction_date else None,
        # Merchant identity is deliberately primary. Provider exports often
        # omit a memo in one file and add one in another; the same merchant,
        # direction, day and amount must therefore enter explicit review.
        "text_identity": normalized_merchant or normalized_description,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_DUPLICATE_CHANNEL_AFFIXES = (
    "微信支付",
    "支付宝",
    "财付通",
    "云闪付",
    "银联",
    "快捷支付",
    "扫码支付",
    "二维码支付",
    "付款给",
    "转账给",
    "收款来自",
    "商户消费",
    "消费",
    "付款",
    "收款",
    "交易",
)


def _normalize_duplicate_text(value: str | None) -> str:
    normalized = re.sub(
        r"[^0-9a-z\u4e00-\u9fff]+",
        "",
        str(value or "").strip().lower(),
    )
    # Remove only common channel wrappers at the edges. Business words inside
    # the merchant name remain intact, which keeps the rule deterministic and
    # avoids turning unrelated merchants into an automatic hard duplicate.
    changed = True
    while changed and normalized:
        changed = False
        for affix in _DUPLICATE_CHANNEL_AFFIXES:
            if normalized.startswith(affix) and len(normalized) - len(affix) >= 2:
                normalized = normalized[len(affix):]
                changed = True
            if normalized.endswith(affix) and len(normalized) - len(affix) >= 2:
                normalized = normalized[:-len(affix)]
                changed = True
    return normalized


def duplicate_text_signature(
    merchant: str | None,
    description: str | None,
) -> tuple[str, ...]:
    return tuple(sorted({
        value[:120]
        for value in (
            _normalize_duplicate_text(merchant),
            _normalize_duplicate_text(description),
        )
        if value
    }))


def duplicate_signatures_are_similar(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> bool:
    if not left or not right:
        return True
    for left_value in left:
        for right_value in right:
            if left_value == right_value:
                return True
            if min(len(left_value), len(right_value)) >= 3 and (
                left_value in right_value or right_value in left_value
            ):
                return True
    return False


def duplicate_text_is_similar(
    merchant_a: str | None,
    description_a: str | None,
    merchant_b: str | None,
    description_b: str | None,
) -> bool:
    """Conservative, versioned text rule used only to require review.

    It never suppresses a row. Equal normalized merchants/descriptions,
    containment after channel-wrapper removal, or missing text on either side
    all count as a possible duplicate after direction/date/amount already
    match. Low-information rows are intentionally reviewed rather than silently
    admitted.
    """

    return duplicate_signatures_are_similar(
        duplicate_text_signature(merchant_a, description_a),
        duplicate_text_signature(merchant_b, description_b),
    )


def _normalized_currency(
    value: str,
    *,
    column_mapped: bool,
) -> tuple[str, dict[str, str] | None]:
    raw = str(value or "").strip()
    normalized = re.sub(r"[\s._/-]+", "", raw).upper()
    if not normalized:
        if not column_mapped:
            return "CNY", None
        return "UNK", {
            "field": "currency",
            "code": "CURRENCY_REQUIRED",
            "message": "源文件已声明币种列，但该行币种为空，请修正源文件后再入账",
        }
    if normalized in {"CNY", "RMB", "人民币", "人民币元", "¥", "￥"}:
        return "CNY", None
    currency = normalized if re.fullmatch(r"[A-Z]{3}", normalized) else "UNK"
    return currency, {
        "field": "currency",
        "code": "UNSUPPORTED_CURRENCY",
        "message": f"当前仅支持人民币，源文件币种“{redact_cashflow_text(raw, max_length=20)}”不能直接入账",
    }


def _file_scoped_external_key(
    *,
    source_type: str,
    content_hash: str,
    row_number: int,
    row: Mapping[str, str],
) -> str:
    row_digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    digest = hashlib.sha256(
        f"{content_hash}|{row_number}|{row_digest}".encode("utf-8")
    ).hexdigest()
    return f"{source_type}:{digest}"


def _stable_source_account(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw or re.search(r"(?:尾号|末\s*\d|后四位|last|[*＊xX?？•·])", raw, re.I):
        return None
    normalized = re.sub(r"[\s\-_/]", "", raw)
    # For the currently supported CNY bank/generic exports, only a complete
    # numeric account/card identifier is strong enough for hard idempotency.
    # Short aliases and masked suffixes fall back to file-row identity plus
    # fuzzy review so they can never permanently suppress another account.
    return normalized if re.fullmatch(r"\d{12,32}", normalized) else None


def _stable_external_id(value: str, *, source_type: str) -> str | None:
    raw = str(value or "").strip()
    lowered = re.sub(r"\s+", "", raw).lower()
    if lowered in {
        "", "-", "--", "/", "n/a", "na", "none", "null", "unknown",
        "pending", "unavailable", "notavailable", "notprovided", "tbd",
        "无", "暂无", "未知", "不适用", "待定", "待处理", "未提供", "不可用",
    }:
        return None
    information = re.sub(r"[^0-9a-z]+", "", lowered)
    if len(information) < 6:
        return None
    if re.fullmatch(
        r"(?:unknown|pending|unavailable|notavailable|notprovided|none|null|tbd)\d*",
        information,
    ):
        return None
    character_counts = Counter(information)
    dominant_ratio = max(character_counts.values()) / len(information)
    repeated_unit = re.fullmatch(r"(.{1,4})\1+", information)
    if dominant_ratio >= 0.8 or repeated_unit is not None:
        return None
    if source_type in {"bank", "generic"} and information.isdigit() and len(information) < 12:
        # Short numeric bank sequence numbers commonly reset by day/month and
        # are not safe as a cross-file hard identity even with an account.
        return None
    return raw


def parse_candidate_rows(
    table: ImportTable,
    *,
    content_hash: str,
) -> list[ParsedCandidate]:
    candidates: list[ParsedCandidate] = []
    for index, row in zip(table.row_numbers, table.rows):
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        direction, amount, amount_errors = _direction_and_amount(row, table.mapping, table.source_type)
        errors.extend(amount_errors)
        transaction_date, occurred_at = _parse_datetime(
            _value(row, table.mapping, "transaction_date"),
            excel_date_1904=table.excel_date_1904,
        )
        if transaction_date is not None and not is_supported_financial_date(transaction_date):
            errors.append({
                "field": "transaction_date",
                "code": "DATE_OUT_OF_RANGE",
                "message": "交易日期超出支持范围",
            })
            transaction_date = None
            occurred_at = None
        elif transaction_date is None:
            errors.append({"field": "transaction_date", "code": "DATE_INVALID", "message": "交易日期无法识别"})

        source_status = redact_cashflow_text(
            _value(row, table.mapping, "source_status"),
            max_length=500,
        )
        normalized_status = source_status.lower()
        if any(token in normalized_status for token in ("关闭", "失败", "取消", "已撤销", "failed", "cancelled", "canceled", "closed")):
            errors.append({"field": "source_status", "code": "SOURCE_NOT_COMPLETED", "message": f"源交易状态为“{source_status}”，默认不准入"})
        if any(token in normalized_status for token in ("退款", "退回", "refund", "refunded")):
            warnings.append({"field": "source_status", "code": "REFUND_REVIEW", "message": f"源交易状态为“{source_status}”，请核对退款口径"})

        merchant = redact_cashflow_text(
            _value(row, table.mapping, "merchant"),
            max_length=120,
        ).strip() or None
        description = redact_cashflow_text(
            _value(row, table.mapping, "description"),
            max_length=500,
        ).strip() or None
        transaction_type = redact_cashflow_text(
            _value(row, table.mapping, "transaction_type"),
            max_length=500,
        )
        liability_text = " ".join((transaction_type, merchant or "", description or "")).lower()
        if any(token in liability_text for token in LIABILITY_TRANSFER_TOKENS):
            direction = "transfer"
            warnings.append({
                "field": "direction",
                "code": "LIABILITY_TRANSFER_REVIEW",
                "message": "识别为信用账户还款或贷款本金，已先按账户/负债变化处理；请确认利息和手续费是否需要另行记为支出",
            })
        category_hint = redact_cashflow_text(
            _value(row, table.mapping, "category"),
            max_length=500,
        )
        category_name = _suggest_category(
            direction,
            category_hint,
            merchant or "",
            description or "",
            transaction_type,
        )
        nature_hint = _value(row, table.mapping, "nature").lower()
        nature_map = {"固定": "fixed", "日常弹性": "flexible", "弹性": "flexible", "一次性": "one_off", "可报销": "reimbursable", "其他": "other"}
        nature = nature_map.get(nature_hint) or _suggest_nature(
            direction,
            category_name,
            " ".join((merchant or "", description or "", transaction_type)),
        )

        currency, currency_error = _normalized_currency(
            _value(row, table.mapping, "currency"),
            column_mapped="currency" in table.mapping,
        )
        if currency_error is not None:
            errors.append(currency_error)

        raw_external_id = _value(row, table.mapping, "external_id")
        external_id = _stable_external_id(
            raw_external_id,
            source_type=table.source_type,
        )
        source_account = _stable_source_account(
            _value(row, table.mapping, "source_account")
        )
        external_key_scope = "file_row"
        if external_id and table.source_type in {"wechat", "alipay"}:
            external_digest = hashlib.sha256(
                f"{table.source_type}|{external_id}".encode("utf-8")
            ).hexdigest()
            external_key = f"{table.source_type}:{external_digest}"
            external_key_scope = "provider_transaction"
        elif external_id and source_account:
            account_digest = hashlib.sha256(
                re.sub(r"\s+", "", source_account).lower().encode("utf-8")
            ).hexdigest()
            external_digest = hashlib.sha256(
                f"{table.source_type}|{account_digest}|{external_id}".encode("utf-8")
            ).hexdigest()
            external_key = f"{table.source_type}:{external_digest}"
            external_key_scope = "account_transaction"
        else:
            external_key = _file_scoped_external_key(
                source_type=table.source_type,
                content_hash=content_hash,
                row_number=index,
                row=row,
            )
            if raw_external_id:
                warnings.append({
                    "field": "external_id",
                    "code": "EXTERNAL_ID_SCOPE_UNKNOWN",
                    "message": "源流水号为占位/低信息值，或缺少可验证的账户范围；本次只作为文件内幂等依据，跨文件由疑似重复复核保护",
                })
        fingerprint_amount = (
            None
            if any(issue.get("field") == "amount" for issue in errors)
            else amount
        )
        fingerprint = build_candidate_fingerprint(
            direction=direction,
            amount=fingerprint_amount,
            transaction_date=transaction_date,
            merchant=merchant,
            description=description,
        )
        safe_amount = (
            format(amount, "f")
            if amount is not None
            and not any(issue.get("field") == "amount" for issue in errors)
            else ""
        )
        normalized_payload_values = {
            "transaction_date": transaction_date.isoformat() if transaction_date else "",
            "direction": direction or "",
            "amount": safe_amount,
            "income_amount": safe_amount if direction == "income" else "",
            "expense_amount": safe_amount if direction == "expense" else "",
            "currency": currency,
            "merchant": merchant or "",
            "description": description or "",
            "category": category_name or "",
            "nature": nature or "",
            "transaction_type": transaction_type,
            "source_status": source_status,
        }
        safe_original_payload: dict[str, str] = {}
        for field in (
                "transaction_date",
                "direction",
                "amount",
                "income_amount",
                "expense_amount",
                "currency",
                "merchant",
                "description",
                "category",
                "nature",
                "transaction_type",
                "source_status",
        ):
            if field not in table.mapping:
                continue
            # Never copy an arbitrary source cell into candidate/API JSON.
            # Use the already validated/normalized fact and apply the shared
            # redactor again as defense against dirty or malicious mappings.
            safe_original_payload[field] = redact_cashflow_text(
                normalized_payload_values[field],
                max_length=500,
            )
        candidates.append(ParsedCandidate(
            row_number=index,
            direction=direction,
            amount=amount,
            currency=currency,
            transaction_date=transaction_date,
            occurred_at=occurred_at,
            category_name=category_name,
            merchant=merchant,
            description=description,
            nature=nature,
            external_key=external_key,
            fingerprint=fingerprint,
            # Keep only business fields used for review. Account/card columns and
            # provider transaction ids stay in the private source file; the
            # latter is represented by the irreversible external_key above.
            original_payload=safe_original_payload,
            evidence={
                "source_row": index,
                "source_status": source_status or None,
                "external_key_scope": external_key_scope,
                "excel_date_system": "1904" if table.excel_date_1904 else "1900",
            },
            validation_errors=errors,
            warnings=warnings,
        ))
    return candidates
