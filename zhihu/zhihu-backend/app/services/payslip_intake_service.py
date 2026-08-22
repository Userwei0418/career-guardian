from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import httpx

from app.db.session import SessionLocal
from app.schemas.payslip import PayslipRecognitionCandidate, PayslipRecognitionResponse
from app.services.cashflow_ai_intake_service import (
    MAX_OCR_FILE_SIZE,
    SUPPORTED_IMAGE_TYPES,
    _local_ocr,
    _audit,
    _error_code,
    _validate_image_dimensions,
    _validated_image_type,
)
from app.services.ai_configuration_service import effective_ai_configuration
from app.services.cashflow_import_parser import (
    MAX_IMPORT_FILE_SIZE,
    CashflowImportError,
    read_import_table,
)
from app.services.cashflow_privacy import redact_cashflow_text


PARSER_VERSION = "payslip-recognition-v1"
MAX_PAYSLIP_ROWS = 200
MONEY_FIELDS = (
    "gross_salary",
    "base_salary",
    "performance",
    "bonus",
    "overtime_pay",
    "allowance",
    "social_insurance",
    "housing_fund",
    "individual_tax",
    "attendance_deductions",
    "meal_deductions",
    "other_deductions",
    "net_salary",
)
DEDUCTION_FIELDS = (
    "social_insurance",
    "housing_fund",
    "individual_tax",
    "attendance_deductions",
    "meal_deductions",
    "other_deductions",
)
KNOWN_FIELDS = (
    "employer_name",
    "pay_month",
    "pay_date",
    *MONEY_FIELDS,
)


def _normalized_header(value: str) -> str:
    return re.sub(r"[\s\-_/\\:：()（）\[\]【】]+", "", str(value or "")).strip().lower()


FIELD_ALIASES = {
    "employer_name": {"发薪单位", "单位名称", "公司名称", "企业名称", "雇主", "employer", "company"},
    "pay_month": {"工资月份", "工资所属月份", "薪资月份", "发薪月份", "月份", "paymonth", "salarymonth"},
    "pay_date": {"发薪日期", "发放日期", "实发日期", "到账日期", "paydate", "paymentdate"},
    "gross_salary": {"应发工资", "应发合计", "应发金额", "税前工资", "grosssalary", "grosspay"},
    "base_salary": {"基本工资", "基础工资", "岗位工资", "basesalary", "basepay"},
    "performance": {"绩效", "绩效工资", "绩效奖金", "performance", "performancepay"},
    "bonus": {"奖金", "月度奖金", "季度奖金", "年终奖", "bonus"},
    "overtime_pay": {"加班费", "加班工资", "overtime", "overtimepay"},
    "allowance": {"津贴", "补贴", "津贴补贴", "补助", "allowance", "subsidy"},
    "social_insurance": {"社保个人", "个人社保", "社会保险个人", "社保扣款", "socialinsurance"},
    "housing_fund": {"公积金个人", "个人公积金", "住房公积金个人", "公积金扣款", "housingfund"},
    "individual_tax": {"个税", "个人所得税", "所得税", "individualtax", "incometax"},
    "attendance_deductions": {"考勤扣款", "缺勤扣款", "迟到扣款", "请假扣款", "attendancededuction"},
    "meal_deductions": {"餐费扣款", "餐费", "伙食费", "mealdeduction"},
    "other_deductions": {"其他扣款", "其他扣除", "扣款其他", "otherdeductions"},
    "net_salary": {"实发工资", "实发合计", "实发金额", "到手工资", "netsalary", "netpay"},
}
FIELD_ALIASES = {
    field: {_normalized_header(alias) for alias in aliases}
    for field, aliases in FIELD_ALIASES.items()
}
FIELD_LABELS = {
    "employer_name": "发薪单位",
    "pay_month": "工资所属月份",
    "pay_date": "发薪日期",
    "gross_salary": "应发工资",
    "base_salary": "基本工资",
    "performance": "绩效",
    "bonus": "奖金",
    "overtime_pay": "加班费",
    "allowance": "津贴补贴",
    "social_insurance": "社保个人缴纳",
    "housing_fund": "公积金个人缴纳",
    "individual_tax": "个税",
    "attendance_deductions": "考勤扣款",
    "meal_deductions": "餐费扣款",
    "other_deductions": "其他扣款",
    "net_salary": "实发工资",
}


class PayslipRecognitionError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _mapping_for_headers(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = _normalized_header(header)
        for field, aliases in FIELD_ALIASES.items():
            if field not in mapping and normalized in aliases:
                mapping[field] = header
                break
    return mapping


def _clean_text(value: Any, limit: int = 255) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] or None


def _parse_money(value: Any) -> tuple[Decimal | None, str | None]:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "/", "未知", "无"}:
        return None, None
    normalized = re.sub(r"[￥¥元,，\s]", "", text)
    normalized = normalized.strip("()（）")
    try:
        amount = Decimal(normalized).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None, f"无法把“{text[:30]}”识别为金额"
    if abs(amount) > Decimal("999999999999.99"):
        return None, "金额超过可支持范围"
    return abs(amount), None


def _parse_month(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"((?:19|20)\d{2})\s*[年./-]\s*(1[0-2]|0?[1-9])", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    compact = re.fullmatch(r"((?:19|20)\d{2})(1[0-2]|0[1-9])", re.sub(r"\s+", "", text))
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}"
    return None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = re.sub(r"[年./]", "-", text).replace("月", "-").replace("日", "").strip("-")
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized, pattern).date()
        except ValueError:
            continue
    return None


def _candidate(
    values: Mapping[str, Any],
    *,
    row_number: int,
    evidence: Mapping[str, str] | None = None,
    custom_items: list[dict[str, str]] | None = None,
    warnings: list[str] | None = None,
    model_confidence: float | None = None,
) -> PayslipRecognitionCandidate:
    parsed: dict[str, Any] = {
        "row_number": row_number,
        "employer_name": _clean_text(values.get("employer_name")),
        "pay_month": _parse_month(values.get("pay_month")),
        "pay_date": _parse_date(values.get("pay_date")),
        "custom_items": (custom_items or [])[:80],
        "evidence": dict(evidence or {}),
    }
    result_warnings = list(warnings or [])
    quality_warning_count = 0
    for field in MONEY_FIELDS:
        amount, warning = _parse_money(values.get(field))
        parsed[field] = amount
        if warning:
            result_warnings.append(f"{FIELD_LABELS[field]}：{warning}")
            quality_warning_count += 1
    if parsed["pay_month"] is None and parsed["pay_date"] is not None:
        parsed["pay_month"] = parsed["pay_date"].strftime("%Y-%m")

    missing_required = [
        field for field in ("pay_month", "gross_salary", "net_salary")
        if parsed.get(field) is None
    ]
    if missing_required:
        result_warnings.append("仍需补充：" + "、".join(FIELD_LABELS[field] for field in missing_required))
        quality_warning_count += 1

    if all(parsed.get(field) is not None for field in DEDUCTION_FIELDS) and parsed.get("gross_salary") is not None and parsed.get("net_salary") is not None:
        deduction_total = sum((parsed[field] for field in DEDUCTION_FIELDS), Decimal("0"))
        arithmetic_diff = parsed["net_salary"] - (parsed["gross_salary"] - deduction_total)
        if abs(arithmetic_diff) > Decimal("1.00"):
            result_warnings.append(f"应发减已识别扣款与实发相差 {abs(arithmetic_diff):.2f} 元")
            quality_warning_count += 1

    confidence = model_confidence if model_confidence is not None else 0.96
    if missing_required:
        confidence = min(confidence, 0.58 if len(missing_required) >= 2 else 0.72)
    if quality_warning_count and not missing_required:
        confidence = min(confidence, 0.84)
    confidence = max(0.0, min(1.0, confidence))
    tier = "high" if confidence >= 0.9 else "medium" if confidence >= 0.65 else "low"
    reasons = {
        "high": ["工资月份、应发和实发字段完整，可载入后快速核对"],
        "medium": ["核心数字大部分可读，但仍有字段或算术需要人工确认"],
        "low": ["核心字段缺失或识别证据较弱，必须逐项人工核对"],
    }[tier]
    parsed.update({
        "confidence": confidence,
        "confidence_tier": tier,
        "reasons": reasons,
        "warnings": result_warnings,
        "unknown_fields": [field for field in KNOWN_FIELDS if parsed.get(field) is None],
    })
    return PayslipRecognitionCandidate.model_validate(parsed)


def _table_candidates(content: bytes, filename: str) -> list[PayslipRecognitionCandidate]:
    try:
        table = read_import_table(content, filename, source_hint="generic")
    except CashflowImportError as exc:
        raise PayslipRecognitionError(
            413 if "10MB" in str(exc) or "过大" in str(exc) else 400,
            "payslip_file_invalid",
            str(exc).replace("账单", "工资条"),
        ) from exc
    if len(table.rows) > MAX_PAYSLIP_ROWS:
        raise PayslipRecognitionError(413, "payslip_rows_too_many", f"单次最多识别 {MAX_PAYSLIP_ROWS} 行工资条")
    mapping = _mapping_for_headers(table.headers)
    if not mapping:
        raise PayslipRecognitionError(400, "payslip_headers_unrecognized", "没有识别到工资月份、应发、实发或工资构成列")
    mapped_headers = set(mapping.values())
    candidates: list[PayslipRecognitionCandidate] = []
    for index, row in enumerate(table.rows):
        values = {field: row.get(header, "") for field, header in mapping.items()}
        evidence = {field: str(row.get(header, ""))[:160] for field, header in mapping.items() if str(row.get(header, "")).strip()}
        custom_items = [
            {"name": header[:80], "value": str(row.get(header, ""))[:200]}
            for header in table.headers
            if header not in mapped_headers and str(row.get(header, "")).strip()
        ]
        candidates.append(_candidate(
            values,
            row_number=table.row_numbers[index] if index < len(table.row_numbers) else index + 2,
            evidence=evidence,
            custom_items=custom_items,
        ))
    return candidates


def _json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def _call_payslip_llm(
    prompt: str,
    *,
    user_id: int,
    expected_data_epoch: int | None,
    feature: str = "payslip_ocr_structure",
    max_tokens: int = 2200,
) -> str | None:
    try:
        with SessionLocal() as configuration_db:
            configuration = effective_ai_configuration(configuration_db)
    except Exception as exc:
        _audit(None, feature=feature, modality="text", user_id=user_id, status="failed", error_code=_error_code(exc), expected_data_epoch=expected_data_epoch)
        return None
    if configuration is None:
        _audit(None, feature=feature, modality="text", user_id=user_id, status="failed", error_code="AIConfigurationUnavailable", expected_data_epoch=expected_data_epoch)
        return None
    started = time.monotonic()
    try:
        response = httpx.post(
            f"{configuration.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {configuration.api_key}", "Content-Type": "application/json"},
            json={
                "model": configuration.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": max_tokens,
            },
            timeout=httpx.Timeout(connect=10, read=75, write=20, pool=10),
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
        choice = body["choices"][0]
        if choice.get("finish_reason") not in {None, "stop"}:
            raise ValueError(f"ModelFinishReason:{choice.get('finish_reason')}")
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("ModelResponseInvalidJSON")
        _audit(configuration, feature=feature, modality="text", user_id=user_id, status="success", latency_ms=round((time.monotonic() - started) * 1000), usage=body.get("usage") if isinstance(body, dict) else None, expected_data_epoch=expected_data_epoch)
        return content
    except Exception as exc:
        _audit(configuration, feature=feature, modality="text", user_id=user_id, status="failed", latency_ms=round((time.monotonic() - started) * 1000), error_code=_error_code(exc), expected_data_epoch=expected_data_epoch)
        return None


def _ai_ocr_candidates(ocr_text: str, *, user_id: int, expected_data_epoch: int | None = None) -> list[PayslipRecognitionCandidate]:
    redacted = redact_cashflow_text(re.sub(r"\s+", " ", ocr_text).strip(), max_length=8000)
    prompt = """你是收支守护的工资条结构化识别器。只提取文字中明确出现的工资事实，缺失字段必须输出 null，绝不填 0、绝不猜测。金额保留原币种数值；扣款即使带负号也输出绝对值。输出严格 JSON，不要 markdown：
{"payslips":[{"employer_name":null,"pay_month":"YYYY-MM或null","pay_date":"YYYY-MM-DD或null","gross_salary":null,"base_salary":null,"performance":null,"bonus":null,"overtime_pay":null,"allowance":null,"social_insurance":null,"housing_fund":null,"individual_tax":null,"attendance_deductions":null,"meal_deductions":null,"other_deductions":null,"net_salary":null,"custom_items":[{"name":"其他项目名","value":"原值"}],"confidence":0.0,"evidence":{"字段名":"原文短句"}}]}
这是本地 OCR 并脱敏后的工资条文字，方括号隐藏内容不得猜测：
---
{text}
---""".replace("{text}", redacted)
    output = _call_payslip_llm(prompt, user_id=user_id, expected_data_epoch=expected_data_epoch)
    payload = _json_object(output or "")
    rows = payload.get("payslips") if payload else None
    if not isinstance(rows, list):
        return []
    candidates: list[PayslipRecognitionCandidate] = []
    for index, item in enumerate(rows[:20], start=1):
        if not isinstance(item, dict):
            continue
        raw_custom = item.get("custom_items")
        custom_items = []
        if isinstance(raw_custom, list):
            for custom in raw_custom[:80]:
                if isinstance(custom, dict) and _clean_text(custom.get("name"), 80):
                    custom_items.append({
                        "name": _clean_text(custom.get("name"), 80) or "其他项目",
                        "value": _clean_text(custom.get("value"), 200) or "",
                    })
        raw_evidence = item.get("evidence")
        if not isinstance(raw_evidence, dict):
            raw_evidence = {}
        evidence = {
            str(key)[:80]: str(value)[:160]
            for key, value in raw_evidence.items()
            if isinstance(value, (str, int, float))
        }
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        candidates.append(_candidate(
            item,
            row_number=index,
            evidence=evidence,
            custom_items=custom_items,
            warnings=["这是 AI 结构化候选，保存前仍需核对原文依据"],
            model_confidence=confidence,
        ))
    return candidates


def _regex_ocr_candidate(ocr_text: str) -> PayslipRecognitionCandidate:
    values: dict[str, Any] = {}
    evidence: dict[str, str] = {}
    lines = [re.sub(r"\s+", " ", line).strip() for line in ocr_text.splitlines() if line.strip()]
    for field, aliases in FIELD_ALIASES.items():
        label_candidates = sorted((alias for alias in aliases if re.search(r"[\u4e00-\u9fff]", alias)), key=len, reverse=True)
        for line in lines:
            normalized = _normalized_header(line)
            alias = next((item for item in label_candidates if item in normalized), None)
            if alias is None:
                continue
            if field == "employer_name":
                value = re.sub(r"^(发薪单位|单位名称|公司名称|企业名称|雇主)\s*[:：]?\s*", "", line).strip()
            elif field in {"pay_month", "pay_date"}:
                value = line
            else:
                money_match = re.search(r"[-+]?\s*[￥¥]?\s*\d[\d,，]*(?:\.\d{1,2})?", line)
                value = money_match.group(0) if money_match else ""
            if value:
                values[field] = value
                evidence[field] = line[:160]
                break
    if "pay_month" not in values:
        month_match = re.search(r"(?:19|20)\d{2}\s*[年./-]\s*(?:1[0-2]|0?[1-9])", ocr_text)
        if month_match:
            values["pay_month"] = month_match.group(0)
            evidence["pay_month"] = month_match.group(0)
    return _candidate(
        values,
        row_number=1,
        evidence=evidence,
        warnings=["AI 当前未返回可用结构，已保留本机 OCR 的规则识别结果"],
        model_confidence=0.62,
    )


def recognize_payslip_upload(
    *,
    user_id: int,
    filename: str,
    content: bytes,
    content_type: str,
    confirm_external_processing: bool,
    expected_data_epoch: int | None = None,
) -> PayslipRecognitionResponse:
    safe_name = Path(filename or "payslip").name
    extension = Path(safe_name).suffix.lower()
    if extension in {".csv", ".tsv", ".xlsx"}:
        if len(content) > MAX_IMPORT_FILE_SIZE:
            raise PayslipRecognitionError(413, "payslip_file_too_large", "工资条表格不能超过 10MB")
        candidates = _table_candidates(content, safe_name)
        return PayslipRecognitionResponse(
            source_type="file",
            original_filename=safe_name,
            original_file_retained=False,
            candidates=candidates,
        )

    declared_type = content_type or "application/octet-stream"
    if declared_type not in SUPPORTED_IMAGE_TYPES and extension not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise PayslipRecognitionError(400, "payslip_file_type_unsupported", "仅支持 CSV、TSV、XLSX 或 PNG/JPG/WebP 工资条")
    if not confirm_external_processing:
        raise PayslipRecognitionError(400, "payslip_ocr_consent_required", "请先确认：图片仅在本机 OCR，脱敏后的文字将发送至职护当前 AI 进行结构化识别")
    if not content:
        raise PayslipRecognitionError(400, "payslip_image_empty", "工资条图片为空")
    if len(content) > MAX_OCR_FILE_SIZE:
        raise PayslipRecognitionError(413, "payslip_image_too_large", "工资条图片不能超过 30MB")
    detected_type = _validated_image_type(content, declared_type)
    _validate_image_dimensions(content, detected_type)
    ocr_text = _local_ocr(
        user_id=user_id,
        content=content,
        detected_type=detected_type,
        expected_data_epoch=expected_data_epoch,
    )
    candidates = _ai_ocr_candidates(ocr_text, user_id=user_id, expected_data_epoch=expected_data_epoch)
    if not candidates:
        candidates = [_regex_ocr_candidate(ocr_text)]
    return PayslipRecognitionResponse(
        source_type="ocr",
        original_filename=safe_name,
        original_file_retained=False,
        raw_text=ocr_text[:100_000],
        candidates=candidates,
    )
