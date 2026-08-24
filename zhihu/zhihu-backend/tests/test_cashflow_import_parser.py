from __future__ import annotations

import hashlib
import unittest
import zipfile
from io import BytesIO
from unittest.mock import patch

from app.services import cashflow_import_parser as parser


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _minimal_xlsx(
    rows: list[list[str]],
    *,
    relationship_target: str = "worksheets/sheet1.xml",
    relationship_type: str = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    ),
    row_numbers: list[int] | None = None,
    date_1904: bool = False,
) -> bytes:
    def cell(column_index: int, row_index: int, value: str) -> str:
        quotient = column_index + 1
        letters = ""
        while quotient:
            quotient, remainder = divmod(quotient - 1, 26)
            letters = chr(ord("A") + remainder) + letters
        escaped = (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return (
            f'<c r="{letters}{row_index}" t="inlineStr">'
            f"<is><t>{escaped}</t></is></c>"
        )

    sheet_rows = []
    for sequence, values in enumerate(rows, start=1):
        row_index = row_numbers[sequence - 1] if row_numbers is not None else sequence
        cells = "".join(
            cell(column_index, row_index, str(value))
            for column_index, value in enumerate(values)
        )
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<workbookPr date1904="{1 if date_1904 else 0}"/>'
        '<sheets><sheet name="账单" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        f'Type="{relationship_type}" '
        f'Target="{relationship_target}"/>'
        "</Relationships>"
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )

    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def _replace_xlsx_member(content: bytes, name: str, replacement: str) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for info in source.infolist():
            target.writestr(info.filename, replacement if info.filename == name else source.read(info.filename))
    return output.getvalue()


def _remove_xlsx_member(content: bytes, name: str) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(content)) as source, zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target:
        for info in source.infolist():
            if info.filename != name:
                target.writestr(info.filename, source.read(info.filename))
    return output.getvalue()


class CashflowDelimitedImportTest(unittest.TestCase):
    def test_utf8_bom_wechat_metadata_and_candidate_semantics(self):
        content = (
            "微信支付账单明细\n"
            "微信昵称：[收支守护测试]\n"
            "\n"
            "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号\n"
            '2026-08-01 09:30:00,商户消费,公司财务,八月工资,收入,"¥12,345.67",零钱,支付成功,wx-001\n'
            "2026-08-02 12:00:00,商户消费,午餐餐厅,工作餐,支出,25.80,零钱,支付成功,wx-002\n"
            "2026-08-03 18:00:00,零钱提现,微信零钱,提现到银行卡,不计收支,500.00,零钱,支付成功,wx-003\n"
            "2026-08-04 10:00:00,商户消费,关闭商户,失败订单,支出,66.00,零钱,交易关闭,wx-004\n"
            "2026-08-05 11:00:00,商户消费,退款商户,退货退款,支出,88.00,零钱,已全额退款,wx-005\n"
        ).encode("utf-8-sig")

        table = parser.read_import_table(content, "微信支付账单.csv")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual("wechat", table.source_type)
        self.assertEqual(4, table.header_row_number)
        self.assertFalse(table.mapping_required)
        self.assertEqual(5, len(candidates))
        self.assertEqual([5, 6, 7, 8, 9], [item.row_number for item in candidates])
        self.assertEqual(
            ["income", "expense", "transfer"],
            [item.direction for item in candidates[:3]],
        )
        self.assertEqual("12345.67", str(candidates[0].amount))
        self.assertEqual("工资", candidates[0].category_name)
        self.assertEqual("餐饮", candidates[1].category_name)
        self.assertIsNone(candidates[2].category_name)
        self.assertTrue(
            any(error["code"] == "SOURCE_NOT_COMPLETED" for error in candidates[3].validation_errors)
        )
        self.assertTrue(
            any(warning["code"] == "REFUND_REVIEW" for warning in candidates[4].warnings)
        )
        self.assertEqual("交易关闭", candidates[3].evidence["source_status"])

    def test_gb18030_bank_csv_accepts_common_single_character_debit_credit_markers(self):
        content = (
            "交易日期,借贷标志,交易金额,对方户名,摘要,流水号\n"
            "2026-08-06,贷,1000.00,某公司,劳务收入,bank-001\n"
            "2026-08-07,借,88.50,某超市,日常购物,bank-002\n"
        ).encode("gb18030")

        table = parser.read_import_table(content, "银行流水.csv")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual("bank", table.source_type)
        self.assertFalse(table.mapping_required)
        self.assertEqual(["income", "expense"], [item.direction for item in candidates])
        self.assertTrue(all(not item.validation_errors for item in candidates))

    def test_liability_principal_and_credit_repayments_do_not_become_consumption(self):
        content = (
            "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号\n"
            "2026-08-10 09:00:00,信用卡还款,某银行信用卡,本期还款,支出,3000.00,银行卡,支付成功,wx-credit-001\n"
            "2026-08-11 09:00:00,贷款本金,某银行,归还贷款本金,支出,2000.00,银行卡,支付成功,wx-loan-001\n"
            "2026-08-12 09:00:00,贷款利息,某银行,本月贷款利息,支出,80.00,银行卡,支付成功,wx-interest-001\n"
        ).encode("utf-8-sig")

        table = parser.read_import_table(content, "微信还款账单.csv")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual(["transfer", "transfer", "expense"], [item.direction for item in candidates])
        self.assertTrue(all(item.category_name is None for item in candidates[:2]))
        self.assertEqual("其他支出", candidates[2].category_name)
        self.assertTrue(
            all(
                any(warning["code"] == "LIABILITY_TRANSFER_REVIEW" for warning in item.warnings)
                for item in candidates[:2]
            )
        )
        self.assertFalse(
            any(warning["code"] == "LIABILITY_TRANSFER_REVIEW" for warning in candidates[2].warnings)
        )

    def test_generic_file_requires_mapping_then_uses_explicit_override(self):
        content = (
            "流水日,数额,流向值,对手方,附言,编号\n"
            "2026/08/08,42.50,支出,咖啡店,下午咖啡,generic-001\n"
        ).encode("utf-8")

        unmapped = parser.read_import_table(content, "custom.csv", source_hint="generic")
        self.assertTrue(unmapped.mapping_required)

        mapped = parser.read_import_table(
            content,
            "custom.csv",
            source_hint="generic",
            mapping_override={
                "transaction_date": "流水日",
                "amount": "数额",
                "direction": "流向值",
                "merchant": "对手方",
                "description": "附言",
                "external_id": "编号",
            },
        )
        candidates = parser.parse_candidate_rows(mapped, content_hash=_content_hash(content))

        self.assertFalse(mapped.mapping_required)
        self.assertEqual("expense", candidates[0].direction)
        self.assertEqual("42.50", str(candidates[0].amount))
        self.assertEqual("咖啡店", candidates[0].merchant)
        self.assertFalse(candidates[0].validation_errors)

    def test_mapping_override_rejects_a_column_that_is_not_in_the_file(self):
        content = "日期,金额,方向\n2026-08-08,12.00,收入\n".encode("utf-8")

        with self.assertRaisesRegex(parser.CashflowImportError, "不存在的列"):
            parser.read_import_table(
                content,
                "custom.csv",
                mapping_override={
                    "transaction_date": "日期",
                    "amount": "金额",
                    "direction": "没有这一列",
                },
            )

    def test_duplicate_external_id_produces_the_same_idempotency_key(self):
        content = (
            "交易日期,收支,金额,交易对方,交易单号\n"
            "2026-08-09,支出,10.00,甲商户,same-id\n"
            "2026-08-10,支出,20.00,乙商户,same-id\n"
        ).encode("utf-8")

        table = parser.read_import_table(content, "duplicate.csv", source_hint="wechat")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual(candidates[0].external_key, candidates[1].external_key)
        self.assertNotEqual(candidates[0].fingerprint, candidates[1].fingerprint)

    def test_non_finite_amount_is_invalid_instead_of_raising(self):
        content = (
            "交易日期,收支,金额,交易对方,交易单号\n"
            "2026-08-09,收入,NaN,异常来源,nan-001\n"
        ).encode("utf-8")

        table = parser.read_import_table(content, "non-finite.csv", source_hint="wechat")
        candidate = parser.parse_candidate_rows(
            table,
            content_hash=_content_hash(content),
        )[0]

        self.assertIsNone(candidate.amount)
        self.assertIn(
            "AMOUNT_INVALID",
            {issue["code"] for issue in candidate.validation_errors},
        )

    def test_negative_amount_cannot_silently_reverse_explicit_income(self):
        content = (
            "交易日期,收支,金额,交易对方,交易单号\n"
            "2026-08-09,收入,-100.00,异常来源,negative-income-001\n"
        ).encode("utf-8")

        table = parser.read_import_table(content, "negative-income.csv", source_hint="wechat")
        candidate = parser.parse_candidate_rows(
            table,
            content_hash=_content_hash(content),
        )[0]

        self.assertEqual("income", candidate.direction)
        self.assertEqual("100.00", str(candidate.amount))
        self.assertIn(
            "SIGN_DIRECTION_CONFLICT",
            {issue["code"] for issue in candidate.validation_errors},
        )

    def test_negative_split_income_and_expense_amounts_require_review(self):
        content = (
            "交易日期,贷方金额,借方金额,对方户名,流水号\n"
            "2026-08-09,-100.00,,异常收入,split-negative-income\n"
            "2026-08-10,,-88.00,异常支出,split-negative-expense\n"
        ).encode("utf-8")

        table = parser.read_import_table(content, "split-negative.csv", source_hint="bank")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual(["income", "expense"], [item.direction for item in candidates])
        self.assertEqual(["100.00", "88.00"], [str(item.amount) for item in candidates])
        self.assertTrue(all(
            "SIGN_DIRECTION_CONFLICT" in {issue["code"] for issue in item.validation_errors}
            for item in candidates
        ))

    def test_date_only_values_never_invent_midnight_occurrence(self):
        for value in ("2026-08-01", "2026/08/01", "46235", "46235.0"):
            with self.subTest(value=value):
                transaction_date, occurred_at = parser._parse_datetime(value)
                self.assertIsNotNone(transaction_date)
                self.assertIsNone(occurred_at)

        _transaction_date, explicit_time = parser._parse_datetime("46235.5")
        self.assertIsNotNone(explicit_time)
        self.assertEqual(12, explicit_time.hour)

    def test_mapped_blank_currency_is_invalid_but_absent_currency_defaults_to_cny(self):
        with_currency = (
            "交易日期,收支,金额,币种,交易对方\n"
            "2026-08-01,收入,1000,,境外公司\n"
        ).encode()
        candidate = parser.parse_candidate_rows(
            parser.read_import_table(with_currency, "currency.csv"),
            content_hash=_content_hash(with_currency),
        )[0]
        self.assertEqual("UNK", candidate.currency)
        self.assertIn("CURRENCY_REQUIRED", {item["code"] for item in candidate.validation_errors})

        without_currency = "交易日期,收支,金额\n2026-08-01,收入,1000\n".encode()
        defaulted = parser.parse_candidate_rows(
            parser.read_import_table(without_currency, "cny.csv"),
            content_hash=_content_hash(without_currency),
        )[0]
        self.assertEqual("CNY", defaulted.currency)

    def test_explicit_direction_cannot_conflict_with_split_amount_column(self):
        content = "日期,方向,数额\n2026-08-01,支出,100.00\n".encode()
        table = parser.read_import_table(
            content,
            "direction-conflict.csv",
            mapping_override={
                "transaction_date": "日期",
                "direction": "方向",
                "income_amount": "数额",
            },
        )
        candidate = parser.parse_candidate_rows(table, content_hash=_content_hash(content))[0]
        self.assertIn(
            "DIRECTION_COLUMN_CONFLICT",
            {item["code"] for item in candidate.validation_errors},
        )

    def test_placeholder_and_long_external_ids_never_collide_as_hard_identity(self):
        placeholder = (
            "交易日期,收支,金额,交易对方,交易单号\n"
            "2026-08-01,支出,10.00,甲,-\n"
            "2026-08-02,支出,20.00,乙,-\n"
        ).encode()
        candidates = parser.parse_candidate_rows(
            parser.read_import_table(placeholder, "placeholder.csv", source_hint="wechat"),
            content_hash=_content_hash(placeholder),
        )
        self.assertNotEqual(candidates[0].external_key, candidates[1].external_key)

        for placeholder_id in ("UNKNOWN", "xxxxxxxx", "00000000x", "not available"):
            with self.subTest(placeholder_id=placeholder_id):
                low_information = (
                    "交易日期,收支,金额,交易对方,交易单号\n"
                    f"2026-08-01,支出,10.00,甲,{placeholder_id}\n"
                    f"2026-08-02,收入,20.00,乙,{placeholder_id}\n"
                ).encode()
                placeholder_candidates = parser.parse_candidate_rows(
                    parser.read_import_table(
                        low_information,
                        "low-information.csv",
                        source_hint="wechat",
                    ),
                    content_hash=_content_hash(low_information),
                )
                self.assertNotEqual(
                    placeholder_candidates[0].external_key,
                    placeholder_candidates[1].external_key,
                )
                self.assertEqual(
                    ["file_row", "file_row"],
                    [item.evidence["external_key_scope"] for item in placeholder_candidates],
                )

        prefix = "x" * 200
        long_ids = (
            "交易日期,收支,金额,交易对方,交易单号\n"
            f"2026-08-01,支出,10.00,甲,{prefix}A\n"
            f"2026-08-02,支出,20.00,乙,{prefix}B\n"
        ).encode()
        long_candidates = parser.parse_candidate_rows(
            parser.read_import_table(long_ids, "long-id.csv", source_hint="wechat"),
            content_hash=_content_hash(long_ids),
        )
        self.assertNotEqual(long_candidates[0].external_key, long_candidates[1].external_key)

    def test_mysql_unsupported_date_becomes_single_invalid_candidate(self):
        content = "交易日期,收支,金额\n0001-01-01,收入,100.00\n".encode()
        candidate = parser.parse_candidate_rows(
            parser.read_import_table(content, "old-date.csv"),
            content_hash=_content_hash(content),
        )[0]
        self.assertIsNone(candidate.transaction_date)
        self.assertIn("DATE_OUT_OF_RANGE", {item["code"] for item in candidate.validation_errors})


class CashflowXlsxImportTest(unittest.TestCase):
    def test_minimal_xlsx_uses_first_sheet_and_inline_strings(self):
        content = _minimal_xlsx(
            [
                ["交易日期", "收支", "金额", "交易对方", "交易单号"],
                ["2026-08-11", "收入", "888.00", "项目客户", "xlsx-001"],
            ]
        )

        table = parser.read_import_table(content, "账单.xlsx")
        candidates = parser.parse_candidate_rows(table, content_hash=_content_hash(content))

        self.assertEqual(1, table.header_row_number)
        self.assertFalse(table.mapping_required)
        self.assertEqual(1, len(candidates))
        self.assertEqual("income", candidates[0].direction)
        self.assertEqual("888.00", str(candidates[0].amount))
        self.assertEqual("项目客户", candidates[0].merchant)

    def test_xlsx_rejects_too_many_zip_members_before_parsing_xml(self):
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index in range(501):
                archive.writestr(f"xl/dummy/{index}.xml", "")

        with self.assertRaisesRegex(parser.CashflowImportError, "解压后过大"):
            parser.read_import_table(output.getvalue(), "many-members.xlsx")

    def test_xlsx_rejects_excessive_uncompressed_size(self):
        content = _minimal_xlsx(
            [
                ["交易日期", "收支", "金额"],
                ["2026-08-12", "支出", "18.00"],
            ]
        )

        with patch.object(parser, "MAX_XLSX_UNCOMPRESSED_SIZE", 64):
            with self.assertRaisesRegex(parser.CashflowImportError, "解压后过大"):
                parser.read_import_table(content, "oversized.xlsx")

    def test_xlsx_rejects_pk_prefixed_non_zip_payload(self):
        with self.assertRaisesRegex(parser.CashflowImportError, "无法读取"):
            parser.read_import_table(b"PK-not-a-zip", "broken.xlsx")

    def test_xlsx_preserves_sparse_physical_row_number(self):
        content = _minimal_xlsx(
            [
                ["交易日期", "收支", "金额"],
                ["2026-08-12", "支出", "18.00"],
            ],
            row_numbers=[1, 100],
        )
        table = parser.read_import_table(content, "sparse.xlsx")
        candidate = parser.parse_candidate_rows(table, content_hash=_content_hash(content))[0]
        self.assertEqual([100], table.row_numbers)
        self.assertEqual(100, candidate.row_number)
        self.assertEqual(100, candidate.evidence["source_row"])

    def test_xlsx_1904_dates_require_valid_workbook_metadata(self):
        content = _minimal_xlsx(
            [
                ["交易日期", "收支", "金额"],
                ["44783", "收入", "18.00"],
            ],
            date_1904=True,
        )
        table = parser.read_import_table(content, "1904.xlsx")
        candidate = parser.parse_candidate_rows(table, content_hash=_content_hash(content))[0]
        self.assertTrue(table.excel_date_1904)
        self.assertEqual("2026-08-11", candidate.transaction_date.isoformat())

        malformed_workbook = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<workbookPr date1904="1"/><sheets>'
        )
        corrupted = _replace_xlsx_member(
            content,
            "xl/workbook.xml",
            malformed_workbook,
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "元数据"):
            parser.read_import_table(corrupted, "broken-1904.xlsx")

    def test_xlsx_rejects_missing_or_invalid_first_sheet_relationship(self):
        content = _minimal_xlsx([["交易日期", "收支", "金额"], ["2026-08-11", "收入", "18.00"]])

        without_relationships = _remove_xlsx_member(
            content,
            "xl/_rels/workbook.xml.rels",
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "缺少"):
            parser.read_import_table(without_relationships, "missing-rels.xlsx")

        missing_target = _minimal_xlsx(
            [["交易日期", "收支", "金额"], ["2026-08-11", "收入", "18.00"]],
            relationship_target="worksheets/missing.xml",
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "路径"):
            parser.read_import_table(missing_target, "missing-sheet.xlsx")

        wrong_type = _minimal_xlsx(
            [["交易日期", "收支", "金额"], ["2026-08-11", "收入", "18.00"]],
            relationship_type=(
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chartsheet"
            ),
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "关系类型"):
            parser.read_import_table(wrong_type, "wrong-type.xlsx")

    def test_xlsx_rejects_repeated_cells_and_excessive_depth_while_streaming(self):
        base = _minimal_xlsx([["交易日期"], ["2026-08-12"]])
        repeated_cells = "".join('<c r="A1"><v>1</v></c>' for _ in range(81))
        repeated_sheet = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="1">{repeated_cells}</row></sheetData></worksheet>'
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "80"):
            parser.read_import_table(
                _replace_xlsx_member(base, "xl/worksheets/sheet1.xml", repeated_sheet),
                "repeated.xlsx",
            )

        nested = "<x>" * 65 + "</x>" * 65
        deep_sheet = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{nested}</worksheet>"
        )
        with self.assertRaisesRegex(parser.CashflowImportError, "嵌套过深"):
            parser.read_import_table(
                _replace_xlsx_member(base, "xl/worksheets/sheet1.xml", deep_sheet),
                "deep.xlsx",
            )


class CashflowCategorySuggestionTest(unittest.TestCase):
    def _suggest(
        self,
        source_text: str,
        *,
        direction: str = "expense",
        merchant: str = "",
    ) -> parser.CategorySuggestion:
        suggestion = parser._category_suggestion(
            direction,
            source_text,
            merchant,
            source_text,
            "",
        )
        self.assertIsNotNone(suggestion)
        assert suggestion is not None
        return suggestion

    def test_exact_provider_labels_map_directly_without_confirmation(self):
        cases = (
            ("2026-08-13 娱乐 12:12| Apple -11.00", "expense", "娱乐"),
            ("发红包 12:25|微信红包 -200.00", "expense", "人情"),
            ("收红包 12:39|微信红包-来自某用户 +0.10", "income", "赠与红包"),
            ("购物 15:25|拼多多平台商户 -25.90", "expense", "购物"),
        )
        for source_text, direction, expected in cases:
            with self.subTest(source_text=source_text):
                suggestion = self._suggest(source_text, direction=direction)
                self.assertEqual(expected, suggestion.category_name)
                self.assertEqual("source_label", suggestion.source)
                self.assertFalse(suggestion.requires_confirmation)

    def test_life_payment_requires_a_specific_counterparty_semantic(self):
        phone = self._suggest("生活缴费 21:19|中国移动 -20.00")
        power = self._suggest("生活缴费 08:30|国家电网电费 -86.20")
        unknown = self._suggest("生活缴费 12:53| -30.00")

        self.assertEqual(("通讯", False), (phone.category_name, phone.requires_confirmation))
        self.assertEqual(("住房", False), (power.category_name, power.requires_confirmation))
        self.assertEqual("fallback", unknown.source)

    def test_non_equivalent_source_labels_become_groupable_proposals(self):
        travel = self._suggest("旅行 01:10 -753.00")
        insurance = self._suggest("保险 21:12|国信同源 -100.00")
        cloud = self._suggest("服务 16:06|iCloud由云上贵州运营 -21.00")

        self.assertEqual(("交通", True), (travel.category_name, travel.requires_confirmation))
        self.assertEqual(("其他支出", True), (insurance.category_name, insurance.requires_confirmation))
        self.assertEqual(("其他支出", True), (cloud.category_name, cloud.requires_confirmation))
        self.assertEqual("source_label_mapping", travel.source)

    def test_platform_rules_are_specific_and_do_not_blanket_all_meituan_rows(self):
        cases = (
            ("服务 19:04|美团平台商户 -88.00", "餐饮"),
            ("服务 19:04|美团单车 -1.50", "交通"),
            ("服务 19:04|美团买药 -36.00", "医疗"),
            ("服务 19:04|美团优选 -42.00", "购物"),
        )
        for source_text, expected in cases:
            with self.subTest(source_text=source_text):
                suggestion = self._suggest(source_text)
                self.assertEqual(expected, suggestion.category_name)
                self.assertEqual("program_rule", suggestion.source)
                self.assertTrue(suggestion.requires_confirmation)

        ambiguous = self._suggest("服务 19:04|美团商户 -88.00")
        self.assertEqual("fallback", ambiguous.source)
        self.assertNotEqual("餐饮", ambiguous.category_name)

    def test_generic_source_label_uses_merchant_semantics_but_stays_reviewable(self):
        dining = self._suggest("其他 13:19|北京爽可维餐饮中心 -258.00")
        unknown = self._suggest("其他 21:47|复兴壹号 -5.00")

        self.assertEqual("餐饮", dining.category_name)
        self.assertTrue(dining.requires_confirmation)
        self.assertEqual("fallback", unknown.source)

    def test_standalone_custom_category_with_digit_is_preserved_for_tabular_import(self):
        suggestion = self._suggest("3C数码")

        self.assertEqual("3C数码", suggestion.category_name)
        self.assertEqual("source_label", suggestion.source)
        self.assertTrue(suggestion.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
