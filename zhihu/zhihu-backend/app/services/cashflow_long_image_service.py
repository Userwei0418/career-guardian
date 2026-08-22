from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import fitz
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.services.cashflow_ai_intake_service import (
    _local_ocr,
    _validate_image_dimensions,
    _validated_image_type,
    parse_ocr_text_intake,
)
from app.services.cashflow_import_service import (
    _populate_candidates,
    get_owned_batch,
    import_error,
    refresh_batch_counts,
)
from app.services.cashflow_import_parser import ParsedCandidate
from app.services.cashflow_recognition_artifact_service import (
    persist_ocr_text_artifact,
)
from app.services.cashflow_service import lock_financial_ledger_owner
from app.services.personal_attachment_service import (
    resolve_attachment_path,
    save_personal_attachment,
)


LONG_IMAGE_PARSER_VERSION = "cashflow-long-image-v1"
NORMALIZED_IMAGE_WIDTH = 1440
MAX_IMAGE_UPSCALE = 1.5
SLICE_HEIGHT = 2400
SLICE_OVERLAP = 320
MIN_TRAILING_SLICE_HEIGHT = 640
MAX_IMAGE_SLICES = 40
STALE_SLICE_PROCESSING_SECONDS = 180


def should_use_segmented_ocr(dimensions: tuple[int, int]) -> bool:
    width, height = dimensions
    scale = min(NORMALIZED_IMAGE_WIDTH / width, MAX_IMAGE_UPSCALE)
    return round(height * scale) > SLICE_HEIGHT


def _slice_ranges(normalized_height: int) -> list[tuple[int, int]]:
    if normalized_height <= SLICE_HEIGHT:
        return [(0, normalized_height)]
    step = SLICE_HEIGHT - SLICE_OVERLAP
    starts = list(range(0, normalized_height, step))
    if normalized_height - starts[-1] < MIN_TRAILING_SLICE_HEIGHT:
        starts[-1] = max(0, normalized_height - SLICE_HEIGHT)
    starts = list(dict.fromkeys(starts))
    ranges = [(start, min(normalized_height, start + SLICE_HEIGHT)) for start in starts]
    if len(ranges) > MAX_IMAGE_SLICES:
        raise import_error(
            413,
            "cashflow_vision_too_many_slices",
            f"长截图需要拆成超过 {MAX_IMAGE_SLICES} 个片段，请分成两张截图后再导入",
        )
    return ranges


def render_long_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
) -> list[dict[str, Any]]:
    width, height = dimensions
    scale = min(NORMALIZED_IMAGE_WIDTH / width, MAX_IMAGE_UPSCALE)
    normalized_width = max(1, round(width * scale))
    normalized_height = max(1, round(height * scale))
    ranges = _slice_ranges(normalized_height)
    if len(ranges) < 2:
        raise ValueError("segmented OCR requires at least two slices")

    filetype = {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/webp": "webp",
    }[detected_type]
    try:
        document = fitz.open(stream=content, filetype=filetype)
        page = document[0]
        render_scale = normalized_width / page.rect.width
        page_y_per_source_pixel = page.rect.height / height
        slices: list[dict[str, Any]] = []
        for sequence_number, (normalized_top, normalized_bottom) in enumerate(ranges, start=1):
            source_top = normalized_top / scale
            source_bottom = min(float(height), normalized_bottom / scale)
            clip = fitz.Rect(
                page.rect.x0,
                page.rect.y0 + source_top * page_y_per_source_pixel,
                page.rect.x1,
                page.rect.y0 + source_bottom * page_y_per_source_pixel,
            )
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(render_scale, render_scale),
                clip=clip,
                colorspace=fitz.csRGB,
                alpha=False,
            )
            png = pixmap.tobytes("png")
            slices.append(
                {
                    "sequence_number": sequence_number,
                    "content": png,
                    "content_hash": hashlib.sha256(png).hexdigest(),
                    "byte_size": len(png),
                    "source_locator": {
                        "source_pixel_top": round(source_top),
                        "source_pixel_bottom": round(source_bottom),
                        "source_pixel_width": width,
                        "source_pixel_height": height,
                        "normalized_top": normalized_top,
                        "normalized_bottom": normalized_bottom,
                        "normalized_width": pixmap.width,
                        "normalized_height": pixmap.height,
                        "overlap_pixels": SLICE_OVERLAP if sequence_number > 1 else 0,
                    },
                }
            )
        document.close()
        return slices
    except HTTPException:
        raise
    except Exception as exc:
        raise import_error(
            422,
            "cashflow_vision_slice_failed",
            "长截图无法稳定切片，请换一张清晰的 PNG、JPG 或 WebP 图片",
        ) from exc


def _slice_status(artifact: FinancialRecognitionArtifact) -> str:
    metadata = artifact.artifact_metadata if isinstance(artifact.artifact_metadata, dict) else {}
    status = metadata.get("ocr_status")
    return status if status in {"pending", "processing", "completed", "failed"} else "pending"


def _recognition_progress(
    db: Session,
    *,
    batch: FinancialImportBatch,
) -> dict[str, Any]:
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
    slices: list[dict[str, Any]] = []
    counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for artifact in artifacts:
        metadata = artifact.artifact_metadata if isinstance(artifact.artifact_metadata, dict) else {}
        status = _slice_status(artifact)
        counts[status] += 1
        locator = artifact.source_locator if isinstance(artifact.source_locator, dict) else {}
        slices.append(
            {
                "sequence_number": artifact.sequence_number,
                "status": status,
                "source_pixel_top": locator.get("source_pixel_top"),
                "source_pixel_bottom": locator.get("source_pixel_bottom"),
                "error_code": artifact.error_code if status == "failed" else None,
                "error_message": metadata.get("error_message") if status == "failed" else None,
            }
        )
    return {
        "mode": "segmented_image",
        "total_slices": len(artifacts),
        "pending_slices": counts["pending"],
        "processing_slices": counts["processing"],
        "completed_slices": counts["completed"],
        "failed_slices": counts["failed"],
        "slices": slices,
    }


def _store_progress(db: Session, *, batch: FinancialImportBatch) -> dict[str, Any]:
    progress = _recognition_progress(db, batch=batch)
    hints = dict(batch.parse_hints or {})
    hints["recognition_progress"] = progress
    batch.parse_hints = hints
    return progress


def create_segmented_ocr_batch(
    db: Session,
    *,
    user_id: int,
    content: bytes,
    content_type: str,
    original_filename: str,
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    detected_type = _validated_image_type(content, content_type)
    dimensions = _validate_image_dimensions(content, detected_type)
    if not should_use_segmented_ocr(dimensions):
        raise ValueError("image does not require segmented OCR")
    rendered_slices = render_long_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
    )
    content_hash = hashlib.sha256(content).hexdigest()

    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if expected_data_epoch is not None and owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "切片期间账户数据已被清空，本次结果未保存，请重新导入",
        )
    reusable = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == "ocr",
        FinancialImportBatch.source_type == "long_screenshot",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
        FinancialImportBatch.status != "cancelled",
    ).first()
    if reusable is not None:
        return reusable, True

    created_paths: list[Path] = []
    try:
        safe_name = Path(original_filename or "long-screenshot.png").name[:255]
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            attachment_version_id=None,
            original_filename=safe_name,
            content_type=detected_type,
            file_size=len(content),
            content_hash=content_hash,
            parser_version=LONG_IMAGE_PARSER_VERSION,
            status="processing",
            column_mapping={},
            parse_hints={"intake": "ocr", "image_dimensions": {"width": dimensions[0], "height": dimensions[1]}},
            parsed_at=None,
        )
        db.add(batch)
        db.flush()
        for item in rendered_slices:
            sequence_number = int(item["sequence_number"])
            attachment = save_personal_attachment(
                db,
                user_id=user_id,
                document_type="cashflow_import",
                logical_key=f"cashflow-batch-{batch.id}-slice-{sequence_number}",
                display_name=f"长截图识别片段 {sequence_number}/{len(rendered_slices)}",
                original_filename=f"slice-{sequence_number:03d}.png",
                content_type="image/png",
                content=item["content"],
            )
            created_paths.append(resolve_attachment_path(attachment))
            db.add(
                FinancialRecognitionArtifact(
                    user_id=user_id,
                    batch_id=batch.id,
                    artifact_type="image_slice",
                    sequence_number=sequence_number,
                    status="ready",
                    attachment_version_id=attachment.id,
                    content_hash=item["content_hash"],
                    content_type="image/png",
                    byte_size=item["byte_size"],
                    source_locator=item["source_locator"],
                    artifact_metadata={
                        "contains_sensitive_source_image": True,
                        "ocr_status": "pending",
                    },
                )
            )
        db.flush()
        _store_progress(db, batch=batch)
        db.commit()
        db.refresh(batch)
        return batch, False
    except IntegrityError as exc:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        reusable = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == "ocr",
            FinancialImportBatch.source_type == "long_screenshot",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
            FinancialImportBatch.status != "cancelled",
        ).first()
        if reusable is not None:
            return reusable, True
        raise import_error(409, "cashflow_import_conflict", "相同长截图正在识别，请刷新后继续") from exc
    except Exception:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise


def _safe_processing_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return (
            str(exc.detail.get("code") or "cashflow_vision_slice_failed")[:100],
            str(exc.detail.get("message") or "该片段识别失败，请重试")[:240],
        )
    if isinstance(exc, FileNotFoundError):
        return "cashflow_vision_slice_missing", "识别片段缺失，请删除该批次后重新上传长截图"
    return "cashflow_vision_slice_failed", "该片段识别失败，请重试"


def _normalized_overlap_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").lower())


def _merge_exact_overlap_candidates(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: list[ParsedCandidate],
) -> list[ParsedCandidate]:
    """Collapse only deterministic cross-slice repeats and retain both proofs.

    Similar-but-not-identical rows deliberately remain for the normal fuzzy
    duplicate gate. This helper never turns an uncertain match into an
    automatic merge.
    """

    existing = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.batch_id == batch.id,
        FinancialTransactionCandidate.status.in_({"ready", "needs_review", "possible_duplicate"}),
    ).all()
    remaining = []
    for candidate in parsed:
        candidate_merchant = _normalized_overlap_text(candidate.merchant)
        candidate_description = _normalized_overlap_text(candidate.description)
        match = None
        for row in existing:
            row_evidence = dict(row.evidence or {})
            row_sequence = row_evidence.get("slice_sequence")
            candidate_sequence = candidate.evidence.get("slice_sequence")
            if (
                not isinstance(row_sequence, int)
                or not isinstance(candidate_sequence, int)
                or abs(row_sequence - candidate_sequence) != 1
            ):
                continue
            if (
                row.direction != candidate.direction
                or row.amount != candidate.amount
                or row.transaction_date != candidate.transaction_date
            ):
                continue
            row_merchant = _normalized_overlap_text(row.merchant)
            row_description = _normalized_overlap_text(row.description)
            row_quote = _normalized_overlap_text(row_evidence.get("evidence_quote"))
            candidate_quote = _normalized_overlap_text(candidate.evidence.get("evidence_quote"))
            merchant_conflicts = bool(row_merchant and candidate_merchant and row_merchant != candidate_merchant)
            description_conflicts = bool(
                row_description and candidate_description and row_description != candidate_description
            )
            exact_business_text = bool(
                (row_merchant and row_merchant == candidate_merchant)
                or (row_description and row_description == candidate_description)
            )
            exact_quote = bool(row_quote and row_quote == candidate_quote)
            if exact_business_text and exact_quote and not merchant_conflicts and not description_conflicts:
                match = row
                break
        if match is None:
            remaining.append(candidate)
            continue
        evidence = dict(match.evidence or {})
        sources = list(evidence.get("source_slices") or [])
        if not sources and isinstance(evidence.get("slice_sequence"), int):
            sources.append(
                {
                    "slice_sequence": evidence["slice_sequence"],
                    "source_locator": evidence.get("source_locator") or {},
                }
            )
        next_source = {
            "slice_sequence": candidate.evidence.get("slice_sequence"),
            "source_locator": candidate.evidence.get("source_locator") or {},
        }
        if next_source not in sources:
            sources.append(next_source)
        evidence["source_slices"] = sources
        evidence["overlap_merge_reason"] = "日期、金额、方向和交易文本完全一致"
        match.evidence = evidence
    return remaining


def _finalize_batch_state(db: Session, *, batch: FinancialImportBatch) -> dict[str, Any]:
    progress = _store_progress(db, batch=batch)
    unfinished = progress["pending_slices"] + progress["processing_slices"]
    if unfinished:
        batch.status = "processing"
        batch.parsed_at = None
    else:
        refresh_batch_counts(db, batch)
        if batch.total_count == 0:
            batch.status = "failed"
        batch.parsed_at = datetime.utcnow()
    batch.updated_at = datetime.utcnow()
    return progress


def _reset_stale_processing_slices(db: Session, *, batch: FinancialImportBatch) -> None:
    stale_before = datetime.utcnow() - timedelta(seconds=STALE_SLICE_PROCESSING_SECONDS)
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    ).all()
    for artifact in artifacts:
        metadata = dict(artifact.artifact_metadata or {})
        if metadata.get("ocr_status") != "processing":
            continue
        raw_started = metadata.get("processing_started_at")
        try:
            started = datetime.fromisoformat(str(raw_started))
        except (TypeError, ValueError):
            started = datetime.min
        if started <= stale_before:
            metadata["ocr_status"] = "pending"
            metadata.pop("processing_started_at", None)
            artifact.artifact_metadata = metadata


def process_ocr_slice(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    sequence_number: int | None = None,
    retry_failed: bool = False,
) -> FinancialImportBatch:
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    expected_data_epoch = owner.business_data_epoch
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.origin_type != "ocr" or batch.source_type != "long_screenshot":
        raise import_error(409, "cashflow_vision_not_segmented", "该批次不是长截图分片识别任务")
    _reset_stale_processing_slices(db, batch=batch)
    query = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    )
    if sequence_number is not None:
        query = query.filter(FinancialRecognitionArtifact.sequence_number == sequence_number)
    artifacts = query.order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
    target = None
    for artifact in artifacts:
        status = _slice_status(artifact)
        if status == "pending" or (retry_failed and status == "failed"):
            target = artifact
            break
    if target is None:
        _finalize_batch_state(db, batch=batch)
        db.commit()
        db.refresh(batch)
        return batch
    if target.attachment_version_id is None:
        raise import_error(409, "cashflow_vision_slice_missing", "识别片段缺失，请重新上传长截图")
    metadata = dict(target.artifact_metadata or {})
    metadata["ocr_status"] = "processing"
    metadata["processing_started_at"] = datetime.utcnow().isoformat()
    metadata.pop("error_message", None)
    target.artifact_metadata = metadata
    target.error_code = None
    batch.status = "processing"
    _store_progress(db, batch=batch)
    attachment_id = target.attachment_version_id
    target_sequence = target.sequence_number
    source_locator = dict(target.source_locator or {})
    slice_hash = target.content_hash
    db.commit()

    try:
        attachment = db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.id == attachment_id,
            PersonalAttachmentVersion.user_id == user_id,
        ).first()
        if attachment is None:
            raise FileNotFoundError("slice attachment missing")
        slice_content = resolve_attachment_path(attachment).read_bytes()
        if hashlib.sha256(slice_content).hexdigest() != slice_hash:
            raise FileNotFoundError("slice attachment corrupt")
        ocr_text = _local_ocr(
            user_id=user_id,
            content=slice_content,
            detected_type="image/png",
            expected_data_epoch=expected_data_epoch,
        )
        result = parse_ocr_text_intake(
            user_id=user_id,
            ocr_text=ocr_text,
            content_hash=slice_hash,
            expected_data_epoch=expected_data_epoch,
        )

        db.rollback()
        owner = lock_financial_ledger_owner(db, user_id=user_id)
        if owner.business_data_epoch != expected_data_epoch:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_data_cleared",
                "识别期间账户数据已被清空，本片段结果未保存",
            )
        batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
        target = db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "image_slice",
            FinancialRecognitionArtifact.sequence_number == target_sequence,
        ).with_for_update().first()
        if target is None:
            raise import_error(409, "cashflow_import_data_cleared", "识别批次已被删除，本片段结果未保存")
        row_start = target_sequence * 1000
        db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.batch_id == batch_id,
            FinancialTransactionCandidate.row_number > row_start,
            FinancialTransactionCandidate.row_number < row_start + 1000,
            FinancialTransactionCandidate.status != "confirmed",
        ).delete(synchronize_session="fetch")
        db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "ocr_text",
            FinancialRecognitionArtifact.sequence_number == target_sequence,
        ).delete(synchronize_session="fetch")
        persist_ocr_text_artifact(
            db,
            batch=batch,
            ocr_text=ocr_text,
            sequence_number=target_sequence,
            source_locator={"slice_sequence": target_sequence, **source_locator},
        )
        parsed = [
            replace(
                candidate,
                row_number=row_start + index,
                evidence={
                    **candidate.evidence,
                    "slice_sequence": target_sequence,
                    "slice_candidate_index": index,
                    "source_locator": source_locator,
                    "source_slices": [
                        {
                            "slice_sequence": target_sequence,
                            "source_locator": source_locator,
                        }
                    ],
                },
            )
            for index, candidate in enumerate(result.parsed, start=1)
        ]
        recognized_candidate_count = len(parsed)
        parsed = _merge_exact_overlap_candidates(db, batch=batch, parsed=parsed)
        _populate_candidates(db, batch=batch, parsed=parsed)
        metadata = dict(target.artifact_metadata or {})
        metadata.update(
            {
                "ocr_status": "completed",
                "ocr_character_count": len(ocr_text),
                "recognized_candidate_count": recognized_candidate_count,
                "new_candidate_count": len(parsed),
                "overlap_merge_count": recognized_candidate_count - len(parsed),
                "model": result.model,
                "parser_version": result.parser_version,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        metadata.pop("processing_started_at", None)
        metadata.pop("error_message", None)
        target.artifact_metadata = metadata
        target.error_code = None
        _finalize_batch_state(db, batch=batch)
        db.commit()
        db.refresh(batch)
        return batch
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("code") == "cashflow_import_data_cleared":
            raise
        error_code, error_message = _safe_processing_error(exc)
    except Exception as exc:
        error_code, error_message = _safe_processing_error(exc)

    db.rollback()
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    target = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == target_sequence,
    ).with_for_update().first()
    if target is not None:
        metadata = dict(target.artifact_metadata or {})
        metadata["ocr_status"] = "failed"
        metadata["error_message"] = error_message
        metadata.pop("processing_started_at", None)
        target.artifact_metadata = metadata
        target.error_code = error_code
    _finalize_batch_state(db, batch=batch)
    db.commit()
    db.refresh(batch)
    return batch
