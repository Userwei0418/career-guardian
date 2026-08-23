"""Build a user-owned export containing confirmed structured cashflow data only."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
import json
import re
from typing import Iterable, Mapping
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


TRANSACTION_HEADERS = ["流水ID", "发生日期", "方向", "金额", "币种", "分类", "商户或来源", "备注", "支出性质", "来源类型", "外部交易键", "关联经济事实IDs", "经济事实类型", "事实角色", "是否计入收支", "分配至其他事实", "本笔计入金额", "确认时间"]
FACT_HEADERS = ["经济事实ID", "事实类型", "事实名称", "发生日期", "金额", "币种", "主流水ID", "创建时间", "更新时间"]
RELATION_HEADERS = ["关系ID", "关系类型", "分配金额", "来源流水ID", "来源事实", "目标流水ID", "目标事实", "判断来源", "确认理由", "确认时间"]
PAYSLIP_HEADERS = ["工资条ID", "版本状态", "上一版工资条ID", "工资所属月份", "工资条发薪日", "约定发薪日", "单位", "应发工资", "基本工资", "绩效", "奖金", "加班费", "津贴补贴", "社保个人", "公积金个人", "个税", "考勤扣款", "餐费扣款", "其他扣款", "实发工资", "自定义项目", "来源类型", "识别置信度", "关联Offer IDs", "关联合同 IDs", "实际到账流水ID及分配金额", "创建时间"]


@dataclass(frozen=True)
class _SheetSpec:
    name: str
    title: str
    description: str
    headers: list[str]
    rows: list[list[object]]
    column_kinds: Mapping[int, str]


@dataclass(frozen=True)
class _PreparedExport:
    manifest: dict
    sheets: list[_SheetSpec]


def _safe_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime,)):
        text = value.isoformat()
    elif hasattr(value, "isoformat"):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = format(value, "f")
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    # Prevent spreadsheet formula execution when a CSV is opened directly.
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv_bytes(headers: list[str], rows: Iterable[Iterable[object]]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe_cell(value) for value in row])
    return b"\xef\xbb\xbf" + stream.getvalue().encode("utf-8")


def _excel_column(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(value, (date, datetime)):
        text = value.isoformat()
    elif isinstance(value, Decimal):
        text = format(value, "f")
    else:
        text = str(value)
    # XML 1.0 forbids these control characters even when escaped.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def _excel_serial(value: date | datetime) -> str:
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=None)
        epoch = datetime(1899, 12, 30)
        return format(Decimal(str((normalized - epoch).total_seconds())) / Decimal("86400"), "f")
    return str((value - date(1899, 12, 30)).days)


def _xlsx_cell(reference: str, value: object, *, kind: str | None = None, style: int = 0) -> str:
    if value is None:
        return f'<c r="{reference}" s="{style}"/>'
    if kind == "date" and isinstance(value, (date, datetime)):
        return f'<c r="{reference}" s="4"><v>{_excel_serial(value)}</v></c>'
    if kind == "datetime" and isinstance(value, (date, datetime)):
        return f'<c r="{reference}" s="5"><v>{_excel_serial(value)}</v></c>'
    if kind in {"currency", "percentage", "number"} and isinstance(value, (Decimal, int, float)):
        number = format(value, "f") if isinstance(value, Decimal) else str(value)
        number_style = {"currency": 3, "percentage": 6, "number": 0}[kind]
        return f'<c r="{reference}" s="{number_style}"><v>{number}</v></c>'
    if kind == "text" and style == 0:
        style = 8
    text = _xml_text(value)
    preserve = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t{preserve}>{escape(text)}</t></is></c>'


def _sheet_xml(spec: _SheetSpec) -> str:
    last_column = _excel_column(len(spec.headers))
    last_row = max(3, len(spec.rows) + 3)
    widths: list[float] = []
    for index, header in enumerate(spec.headers):
        values = [_safe_cell(row[index]) if index < len(row) else "" for row in spec.rows[:300]]
        longest = max([len(header), *(len(value) for value in values)], default=len(header))
        widths.append(float(min(36, max(10, longest + 2))))
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    row_xml = [
        f'<row r="1" ht="28" customHeight="1">{_xlsx_cell("A1", spec.title, style=1)}</row>',
        f'<row r="2" ht="32" customHeight="1">{_xlsx_cell("A2", spec.description, style=7)}</row>',
        '<row r="3" ht="24" customHeight="1">'
        + "".join(
            _xlsx_cell(f"{_excel_column(index)}3", header, style=2)
            for index, header in enumerate(spec.headers, start=1)
        )
        + "</row>",
    ]
    for row_number, row in enumerate(spec.rows, start=4):
        cells = []
        for column_index, value in enumerate(row, start=1):
            cells.append(
                _xlsx_cell(
                    f"{_excel_column(column_index)}{row_number}",
                    value,
                    kind=spec.column_kinds.get(column_index - 1),
                )
            )
        row_xml.append(f'<row r="{row_number}">' + "".join(cells) + "</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0">'
        '<pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/>'
        f'<cols>{columns}</cols><sheetData>{"".join(row_xml)}</sheetData>'
        f'<mergeCells count="2"><mergeCell ref="A1:{last_column}1"/><mergeCell ref="A2:{last_column}2"/></mergeCells>'
        f'<autoFilter ref="A3:{last_column}{last_row}"/>'
        '<pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        '</worksheet>'
    )


def _xlsx_styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="4"><numFmt numFmtId="164" formatCode="¥#,##0.00;[Red]-¥#,##0.00"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd"/><numFmt numFmtId="166" formatCode="yyyy-mm-dd hh:mm:ss"/><numFmt numFmtId="167" formatCode="0.0%"/></numFmts>
  <fonts count="4"><font><sz val="11"/><color rgb="FF24332F"/><name val="Aptos"/><family val="2"/></font><font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/><family val="2"/></font><font><b/><sz val="11"/><color rgb="FF173F37"/><name val="Aptos"/><family val="2"/></font><font><sz val="10"/><color rgb="FF60706B"/><name val="Aptos"/><family val="2"/></font></fonts>
  <fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2F7569"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFDCECE7"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FFC9D8D3"/></bottom><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="9"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right"/></xf><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def _workbook_bytes(prepared: _PreparedExport, *, generated_at: datetime) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(prepared.sheets) + 1)
        )
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>' + overrides + '</Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
        sheets_xml = "".join(
            f'<sheet name="{escape(spec.name, {chr(34): "&quot;"})}" sheetId="{index}" r:id="rId{index}"/>'
            for index, spec in enumerate(prepared.sheets, start=1)
        )
        archive.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets>' + sheets_xml + '</sheets><calcPr calcId="0" fullCalcOnLoad="1"/></workbook>')
        relationships = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(prepared.sheets) + 1)
        )
        relationships += f'<Relationship Id="rId{len(prepared.sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        archive.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + relationships + '</Relationships>')
        archive.writestr("xl/styles.xml", _xlsx_styles())
        for index, spec in enumerate(prepared.sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(spec))
        timestamp = generated_at.replace(microsecond=0).isoformat() + "Z"
        archive.writestr("docProps/core.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>收支守护数据导出</dc:title><dc:creator>职护</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">' + timestamp + '</dcterms:created></cp:coreProperties>')
        archive.writestr("docProps/app.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>职护收支守护</Application></Properties>')
    return output.getvalue()


def _prepare_export(
    *,
    generated_at: datetime,
    business_data_epoch: int,
    ledger_revision: int,
    transactions: list,
    category_names: Mapping[int, str],
    facts: list,
    allocations: list,
    relations: list,
    payslips: list,
    material_links: list,
    arrival_links: list,
) -> _PreparedExport:
    fact_by_id = {item.id: item for item in facts}
    fact_by_transaction = {item.primary_transaction_id: item for item in facts if item.primary_transaction_id is not None}
    allocations_by_transaction: dict[int, list] = {}
    for allocation in allocations:
        if allocation.status == "confirmed" and allocation.fact_id in fact_by_id:
            allocations_by_transaction.setdefault(allocation.transaction_id, []).append(allocation)
    links_by_payslip: dict[int, dict[str, list[str]]] = {}
    for link in material_links:
        bucket = links_by_payslip.setdefault(link.payslip_id, {"offers": [], "contracts": []})
        if link.offer_id is not None:
            bucket["offers"].append(str(link.offer_id))
        if link.contract_id is not None:
            bucket["contracts"].append(str(link.contract_id))
    arrivals_by_payslip: dict[int, list[str]] = {}
    for link in arrival_links:
        arrivals_by_payslip.setdefault(link.payslip_id, []).append(f"{link.transaction_id}:{format(Decimal(link.allocated_amount), 'f')}")

    transaction_rows = []
    for item in transactions:
        transaction_allocations = allocations_by_transaction.get(item.id, [])
        primary_fact = fact_by_transaction.get(item.id)
        corroborating = [allocation for allocation in transaction_allocations if allocation.role == "corroborating"]
        allocated_to_other_facts = min(
            Decimal(item.amount),
            sum((Decimal(allocation.allocated_amount) for allocation in corroborating), Decimal("0.00")),
        )
        effective_amount = max(Decimal("0.00"), Decimal(item.amount) - allocated_to_other_facts)
        related_facts = [
            fact_by_id[allocation.fact_id]
            for allocation in transaction_allocations
            if allocation.fact_id in fact_by_id
        ]
        if primary_fact is not None and all(fact.id != primary_fact.id for fact in related_facts):
            related_facts.insert(0, primary_fact)
        if allocated_to_other_facts <= Decimal("0.00"):
            role = "primary"
        elif effective_amount <= Decimal("0.00"):
            role = "corroborating"
        else:
            role = "split"
        fact_ids = ";".join(str(fact.id) for fact in related_facts)
        fact_types = ";".join(dict.fromkeys(fact.fact_type for fact in related_facts)) or item.direction
        transaction_rows.append([item.id, item.transaction_date, item.direction, item.amount, item.currency, category_names.get(item.category_id, "") if item.category_id is not None else "", item.merchant, item.description, item.nature, item.source_type, item.external_key, fact_ids, fact_types, role, "是" if effective_amount > Decimal("0.00") else "否", allocated_to_other_facts, effective_amount, item.confirmed_at])
    fact_rows = [[item.id, item.fact_type, item.title, item.occurred_date, item.amount, item.currency, item.primary_transaction_id, item.created_at, item.updated_at] for item in facts]
    relation_rows = []
    for item in relations:
        source = fact_by_id.get(item.source_fact_id)
        target = fact_by_id.get(item.target_fact_id)
        relation_rows.append([item.id, item.relation_type, item.allocated_amount, source.primary_transaction_id if source is not None else None, source.title if source is not None else None, target.primary_transaction_id if target is not None else None, target.title if target is not None else None, item.detection_method, item.reasons, item.confirmed_at])
    payslip_rows = []
    for item in payslips:
        links = links_by_payslip.get(item.id, {"offers": [], "contracts": []})
        payslip_rows.append([item.id, item.record_status, item.supersedes_payslip_id, item.pay_month, item.pay_date, item.agreed_pay_date, item.employer_name, item.gross_salary, item.base_salary, item.performance, item.bonus, item.overtime_pay, item.allowance, item.social_insurance, item.housing_fund, item.individual_tax, item.attendance_deductions, item.meal_deductions, item.other_deductions, item.net_salary, item.custom_items, item.source_type, item.recognition_confidence, ";".join(links["offers"]), ";".join(links["contracts"]), ";".join(arrivals_by_payslip.get(item.id, [])), item.created_at])

    manifest = {
        "product": "收支守护",
        "generated_at": generated_at.isoformat(),
        "business_data_epoch": business_data_epoch,
        "ledger_revision": ledger_revision,
        "timezone": "UTC",
        "scope": "当前账户中已确认、未删除、未撤销的结构化数据",
        "contains_original_files": False,
        "contains_ocr_text_or_slices": False,
        "counts": {"transactions": len(transaction_rows), "economic_facts": len(fact_rows), "economic_relations": len(relation_rows), "payslips": len(payslip_rows)},
    }
    description = f"生成于 {generated_at.isoformat()} UTC · 账本修订 r{ledger_revision} · 仅已确认结构化数据，不含原文件、OCR 原文或切片"
    summary_rows = [["产品", manifest["product"]], ["生成时间", generated_at], ["时区", manifest["timezone"]], ["账本修订", f"r{ledger_revision}"], ["业务数据代次", str(business_data_epoch)], ["数据范围", manifest["scope"]], ["已确认流水", len(transaction_rows)], ["经济事实", len(fact_rows)], ["经济关系", len(relation_rows)], ["工资条版本", len(payslip_rows)], ["包含原文件", "否"], ["包含 OCR 原文或切片", "否"]]
    return _PreparedExport(
        manifest=manifest,
        sheets=[
            _SheetSpec("导出说明", "收支守护数据导出", description, ["项目", "内容"], summary_rows, {1: "text", 0: "text"}),
            _SheetSpec("可信账本", "可信账本", description, TRANSACTION_HEADERS, transaction_rows, {0: "text", 1: "date", 3: "currency", 10: "text", 11: "text", 15: "currency", 16: "currency", 17: "datetime"}),
            _SheetSpec("经济事实", "统一经济事实", description, FACT_HEADERS, fact_rows, {0: "text", 3: "date", 4: "currency", 6: "text", 7: "datetime", 8: "datetime"}),
            _SheetSpec("经济关系", "经济事实关系", description, RELATION_HEADERS, relation_rows, {0: "text", 2: "currency", 3: "text", 5: "text", 9: "datetime"}),
            _SheetSpec("工资条", "工资条与关联证据", description, PAYSLIP_HEADERS, payslip_rows, {0: "text", 2: "text", 4: "date", 5: "date", **{index: "currency" for index in range(7, 20)}, 22: "percentage", 23: "text", 24: "text", 25: "text", 26: "datetime"}),
        ],
    )


def build_cashflow_export_workbook(
    *,
    generated_at: datetime,
    business_data_epoch: int,
    ledger_revision: int,
    transactions: list,
    category_names: Mapping[int, str],
    facts: list,
    allocations: list,
    relations: list,
    payslips: list,
    material_links: list,
    arrival_links: list,
) -> bytes:
    prepared = _prepare_export(generated_at=generated_at, business_data_epoch=business_data_epoch, ledger_revision=ledger_revision, transactions=transactions, category_names=category_names, facts=facts, allocations=allocations, relations=relations, payslips=payslips, material_links=material_links, arrival_links=arrival_links)
    return _workbook_bytes(prepared, generated_at=generated_at)


def build_cashflow_export_bundle(
    *,
    generated_at: datetime,
    business_data_epoch: int,
    ledger_revision: int,
    transactions: list,
    category_names: Mapping[int, str],
    facts: list,
    allocations: list,
    relations: list,
    payslips: list,
    material_links: list,
    arrival_links: list,
) -> bytes:
    prepared = _prepare_export(generated_at=generated_at, business_data_epoch=business_data_epoch, ledger_revision=ledger_revision, transactions=transactions, category_names=category_names, facts=facts, allocations=allocations, relations=relations, payslips=payslips, material_links=material_links, arrival_links=arrival_links)
    transaction_sheet, fact_sheet, relation_sheet, payslip_sheet = prepared.sheets[1:]
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(prepared.manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr("cashflow-guardian.xlsx", _workbook_bytes(prepared, generated_at=generated_at))
        archive.writestr("confirmed-transactions.csv", _csv_bytes(transaction_sheet.headers, transaction_sheet.rows))
        archive.writestr("economic-facts.csv", _csv_bytes(fact_sheet.headers, fact_sheet.rows))
        archive.writestr("economic-relations.csv", _csv_bytes(relation_sheet.headers, relation_sheet.rows))
        archive.writestr("payslips.csv", _csv_bytes(payslip_sheet.headers, payslip_sheet.rows))
    return output.getvalue()
