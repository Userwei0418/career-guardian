from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
)
from app.services.cashflow_import_parser import ImportTable


TABULAR_ROWS_PER_ARTIFACT = 250


class CashflowRecognitionArtifactError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_artifact(
    *,
    batch: FinancialImportBatch,
    artifact_type: str,
    sequence_number: int,
    content: dict[str, Any],
    source_locator: dict[str, Any] | None = None,
    artifact_metadata: dict[str, Any] | None = None,
) -> FinancialRecognitionArtifact:
    encoded = _canonical_json_bytes(content)
    return FinancialRecognitionArtifact(
        user_id=batch.user_id,
        batch_id=batch.id,
        artifact_type=artifact_type,
        sequence_number=sequence_number,
        status="ready",
        content_json=content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        content_type="application/json",
        byte_size=len(encoded),
        source_locator=source_locator or {},
        artifact_metadata=artifact_metadata or {},
    )


def _verified_json_content(
    artifact: FinancialRecognitionArtifact,
) -> dict[str, Any]:
    content = artifact.content_json
    if not isinstance(content, dict):
        raise CashflowRecognitionArtifactError("corrupt", "识别产物内容损坏")
    encoded = _canonical_json_bytes(content)
    if (
        hashlib.sha256(encoded).hexdigest() != artifact.content_hash
        or len(encoded) != artifact.byte_size
    ):
        raise CashflowRecognitionArtifactError("corrupt", "识别产物完整性校验失败")
    return content


def persist_import_table_artifacts(
    db: Session,
    *,
    batch: FinancialImportBatch,
    table: ImportTable,
) -> list[FinancialRecognitionArtifact]:
    """Persist a bounded manifest and row chunks, never the uploaded bytes."""

    existing = db.query(FinancialRecognitionArtifact.id).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type.in_(
            {"tabular_manifest", "normalized_rows"}
        ),
    ).first()
    if existing is not None:
        return []

    manifest = _json_artifact(
        batch=batch,
        artifact_type="tabular_manifest",
        sequence_number=1,
        content={
            "schema_version": 1,
            "source_type": table.source_type,
            "headers": list(table.headers),
            "mapping": dict(table.mapping),
            "header_row_number": table.header_row_number,
            "mapping_required": table.mapping_required,
            "excel_date_1904": table.excel_date_1904,
            "row_count": len(table.rows),
            "chunk_size": TABULAR_ROWS_PER_ARTIFACT,
        },
        artifact_metadata={"contains_sensitive_source_text": True},
    )
    artifacts = [manifest]
    for offset in range(0, len(table.rows), TABULAR_ROWS_PER_ARTIFACT):
        rows = [
            {
                "row_number": table.row_numbers[index],
                "values": dict(table.rows[index]),
            }
            for index in range(
                offset,
                min(offset + TABULAR_ROWS_PER_ARTIFACT, len(table.rows)),
            )
        ]
        artifacts.append(
            _json_artifact(
                batch=batch,
                artifact_type="normalized_rows",
                sequence_number=(offset // TABULAR_ROWS_PER_ARTIFACT) + 1,
                content={"schema_version": 1, "rows": rows},
                source_locator={
                    "first_row_number": rows[0]["row_number"] if rows else None,
                    "last_row_number": rows[-1]["row_number"] if rows else None,
                },
                artifact_metadata={"contains_sensitive_source_text": True},
            )
        )
    db.add_all(artifacts)
    db.flush()
    return artifacts


def load_import_table_artifact(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
) -> ImportTable:
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.status == "ready",
        FinancialRecognitionArtifact.artifact_type.in_(
            {"tabular_manifest", "normalized_rows"}
        ),
    ).order_by(
        FinancialRecognitionArtifact.artifact_type.asc(),
        FinancialRecognitionArtifact.sequence_number.asc(),
    ).all()
    manifests = [row for row in artifacts if row.artifact_type == "tabular_manifest"]
    row_chunks = [row for row in artifacts if row.artifact_type == "normalized_rows"]
    if len(manifests) != 1:
        code = "missing" if not manifests else "corrupt"
        raise CashflowRecognitionArtifactError(code, "表格识别清单缺失或重复")
    if manifests[0].sequence_number != 1:
        raise CashflowRecognitionArtifactError("corrupt", "表格识别清单序号损坏")
    manifest = _verified_json_content(manifests[0])
    if manifest.get("schema_version") != 1:
        raise CashflowRecognitionArtifactError("corrupt", "表格识别清单版本不受支持")

    rows: list[dict[str, str]] = []
    row_numbers: list[int] = []
    expected_count = int(manifest.get("row_count") or 0)
    chunk_size = int(manifest.get("chunk_size") or 0)
    if chunk_size <= 0:
        raise CashflowRecognitionArtifactError("corrupt", "表格识别清单分片信息损坏")
    expected_sequences = list(range(1, ((expected_count + chunk_size - 1) // chunk_size) + 1))
    actual_sequences = sorted(row.sequence_number for row in row_chunks)
    if actual_sequences != expected_sequences:
        raise CashflowRecognitionArtifactError("missing", "规范化表格行分片不完整")

    for chunk in sorted(row_chunks, key=lambda row: row.sequence_number):
        content = _verified_json_content(chunk)
        if content.get("schema_version") != 1 or not isinstance(content.get("rows"), list):
            raise CashflowRecognitionArtifactError("corrupt", "规范化表格行损坏")
        for item in content["rows"]:
            if not isinstance(item, dict) or not isinstance(item.get("values"), dict):
                raise CashflowRecognitionArtifactError("corrupt", "规范化表格行损坏")
            try:
                row_number = int(item["row_number"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CashflowRecognitionArtifactError("corrupt", "规范化表格行号损坏") from exc
            row_numbers.append(row_number)
            rows.append({str(key): str(value or "") for key, value in item["values"].items()})

    if expected_count != len(rows) or len(row_numbers) != len(set(row_numbers)):
        raise CashflowRecognitionArtifactError("corrupt", "规范化表格行不完整")
    headers = manifest.get("headers")
    mapping = manifest.get("mapping")
    if not isinstance(headers, list) or not isinstance(mapping, dict):
        raise CashflowRecognitionArtifactError("corrupt", "表格识别清单字段损坏")
    normalized_headers = [str(value) for value in headers]
    if any(set(row) - set(normalized_headers) for row in rows):
        raise CashflowRecognitionArtifactError("corrupt", "规范化表格列与清单不一致")
    return ImportTable(
        source_type=str(manifest.get("source_type") or "generic"),
        headers=normalized_headers,
        rows=rows,
        mapping={str(key): str(value) for key, value in mapping.items()},
        header_row_number=int(manifest.get("header_row_number") or 1),
        row_numbers=row_numbers,
        mapping_required=bool(manifest.get("mapping_required")),
        excel_date_1904=bool(manifest.get("excel_date_1904")),
    )


def persist_ocr_text_artifact(
    db: Session,
    *,
    batch: FinancialImportBatch,
    ocr_text: str,
    sequence_number: int = 1,
    source_locator: dict[str, Any] | None = None,
    artifact_metadata: dict[str, Any] | None = None,
) -> FinancialRecognitionArtifact | None:
    existing = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "ocr_text",
        FinancialRecognitionArtifact.sequence_number == sequence_number,
    ).first()
    if existing is not None:
        return None
    encoded = ocr_text.encode("utf-8")
    artifact = FinancialRecognitionArtifact(
        user_id=batch.user_id,
        batch_id=batch.id,
        artifact_type="ocr_text",
        sequence_number=sequence_number,
        status="ready",
        content_text=ocr_text,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        content_type="text/plain; charset=utf-8",
        byte_size=len(encoded),
        source_locator={
            "ocr_provider": "local-tesseract",
            **(source_locator or {}),
        },
        artifact_metadata={
            "contains_sensitive_source_text": True,
            "sent_to_model": False,
            **(artifact_metadata or {}),
        },
    )
    db.add(artifact)
    db.flush()
    return artifact


def load_ocr_text_artifact(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
) -> str:
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "ocr_text",
        FinancialRecognitionArtifact.status == "ready",
    ).all()
    if len(artifacts) != 1:
        code = "missing" if not artifacts else "corrupt"
        raise CashflowRecognitionArtifactError(code, "OCR 文字识别产物缺失或重复")
    artifact = artifacts[0]
    if artifact.sequence_number != 1 or not isinstance(artifact.content_text, str):
        raise CashflowRecognitionArtifactError("corrupt", "OCR 文字识别产物损坏")
    encoded = artifact.content_text.encode("utf-8")
    if (
        hashlib.sha256(encoded).hexdigest() != artifact.content_hash
        or len(encoded) != artifact.byte_size
    ):
        raise CashflowRecognitionArtifactError("corrupt", "OCR 文字识别产物完整性校验失败")
    return artifact.content_text


def recognition_artifact_counts(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
) -> dict[str, int]:
    return dict(
        Counter(
            artifact_type
            for (artifact_type,) in db.query(
                FinancialRecognitionArtifact.artifact_type
            ).filter(
                FinancialRecognitionArtifact.user_id == user_id,
                FinancialRecognitionArtifact.batch_id == batch_id,
            ).all()
        )
    )
