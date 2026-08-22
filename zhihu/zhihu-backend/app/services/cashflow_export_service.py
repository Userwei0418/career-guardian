"""Build a user-owned export containing confirmed structured cashflow data only."""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import BytesIO, StringIO
import json
from typing import Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile


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


def build_cashflow_export_bundle(
    *,
    generated_at: datetime,
    business_data_epoch: int,
    transactions: list,
    category_names: Mapping[int, str],
    facts: list,
    relations: list,
    payslips: list,
    material_links: list,
    arrival_links: list,
) -> bytes:
    fact_by_id = {item.id: item for item in facts}
    fact_by_transaction = {
        item.primary_transaction_id: item
        for item in facts
        if item.primary_transaction_id is not None
    }
    links_by_payslip: dict[int, dict[str, list[str]]] = {}
    for link in material_links:
        bucket = links_by_payslip.setdefault(link.payslip_id, {"offers": [], "contracts": []})
        if link.offer_id is not None:
            bucket["offers"].append(str(link.offer_id))
        if link.contract_id is not None:
            bucket["contracts"].append(str(link.contract_id))
    arrivals_by_payslip: dict[int, list[str]] = {}
    for link in arrival_links:
        arrivals_by_payslip.setdefault(link.payslip_id, []).append(
            f"{link.transaction_id}:{format(Decimal(link.allocated_amount), 'f')}"
        )

    transaction_rows = []
    for item in transactions:
        fact = fact_by_transaction.get(item.id)
        transaction_rows.append(
            [
                item.id,
                item.transaction_date,
                item.direction,
                item.amount,
                item.currency,
                category_names.get(item.category_id, "") if item.category_id is not None else "",
                item.merchant,
                item.description,
                item.nature,
                item.source_type,
                item.external_key,
                fact.id if fact is not None else None,
                fact.fact_type if fact is not None else item.direction,
                item.confirmed_at,
            ]
        )
    relation_rows = []
    for item in relations:
        source = fact_by_id.get(item.source_fact_id)
        target = fact_by_id.get(item.target_fact_id)
        relation_rows.append(
            [
                item.id,
                item.relation_type,
                item.allocated_amount,
                source.primary_transaction_id if source is not None else None,
                source.title if source is not None else None,
                target.primary_transaction_id if target is not None else None,
                target.title if target is not None else None,
                item.detection_method,
                item.reasons,
                item.confirmed_at,
            ]
        )
    payslip_rows = []
    for item in payslips:
        links = links_by_payslip.get(item.id, {"offers": [], "contracts": []})
        payslip_rows.append(
            [
                item.id,
                item.pay_month,
                item.pay_date,
                item.agreed_pay_date,
                item.employer_name,
                item.gross_salary,
                item.base_salary,
                item.performance,
                item.bonus,
                item.overtime_pay,
                item.allowance,
                item.social_insurance,
                item.housing_fund,
                item.individual_tax,
                item.attendance_deductions,
                item.meal_deductions,
                item.other_deductions,
                item.net_salary,
                item.custom_items,
                item.source_type,
                item.recognition_confidence,
                ";".join(links["offers"]),
                ";".join(links["contracts"]),
                ";".join(arrivals_by_payslip.get(item.id, [])),
                item.created_at,
            ]
        )

    manifest = {
        "product": "收支守护",
        "generated_at": generated_at.isoformat(),
        "business_data_epoch": business_data_epoch,
        "scope": "当前账户中已确认、未删除、未撤销的结构化数据",
        "contains_original_files": False,
        "contains_ocr_text_or_slices": False,
        "counts": {
            "transactions": len(transaction_rows),
            "economic_relations": len(relation_rows),
            "payslips": len(payslip_rows),
        },
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        archive.writestr(
            "confirmed-transactions.csv",
            _csv_bytes(
                ["流水ID", "发生日期", "方向", "金额", "币种", "分类", "商户或来源", "备注", "支出性质", "来源类型", "外部交易键", "经济事实ID", "经济事实类型", "确认时间"],
                transaction_rows,
            ),
        )
        archive.writestr(
            "economic-relations.csv",
            _csv_bytes(
                ["关系ID", "关系类型", "分配金额", "来源流水ID", "来源事实", "目标流水ID", "目标事实", "判断来源", "确认理由", "确认时间"],
                relation_rows,
            ),
        )
        archive.writestr(
            "payslips.csv",
            _csv_bytes(
                ["工资条ID", "工资所属月份", "工资条发薪日", "约定发薪日", "单位", "应发工资", "基本工资", "绩效", "奖金", "加班费", "津贴补贴", "社保个人", "公积金个人", "个税", "考勤扣款", "餐费扣款", "其他扣款", "实发工资", "自定义项目", "来源类型", "识别置信度", "关联Offer IDs", "关联合同 IDs", "实际到账流水ID及分配金额", "创建时间"],
                payslip_rows,
            ),
        )
    return output.getvalue()
