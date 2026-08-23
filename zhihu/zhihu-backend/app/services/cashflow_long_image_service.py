from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
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
    parse_ocr_text_intake_complete as parse_ocr_text_intake,
)
from app.services.cashflow_import_service import (
    _populate_candidates,
    get_owned_batch,
    import_error,
    refresh_batch_counts,
)
from app.services.cashflow_import_parser import (
    ParsedCandidate,
    build_candidate_fingerprint,
    duplicate_text_is_similar,
)
from app.services.cashflow_recognition_artifact_service import (
    persist_ocr_text_artifact,
)
from app.services.cashflow_service import lock_financial_ledger_owner
from app.services.cashflow_privacy import redact_cashflow_text
from app.services.personal_attachment_service import (
    resolve_attachment_path,
    save_personal_attachment,
)


LONG_IMAGE_PARSER_VERSION = "cashflow-long-image-v2"
NORMALIZED_IMAGE_WIDTH = 1440
MAX_IMAGE_UPSCALE = 1.5
MIN_NORMALIZED_IMAGE_WIDTH = 960
SLICE_HEIGHT = 2400
SLICE_OVERLAP = 320
MIN_TRAILING_SLICE_HEIGHT = 640
MAX_IMAGE_SLICES = 40
MAX_SEQUENCE_IMAGES = 10
MAX_SEQUENCE_TOTAL_BYTES = 90 * 1024 * 1024
MAX_SEQUENCE_TOTAL_SLICES = 80
STALE_SLICE_PROCESSING_SECONDS = 180


def _normalization_scale(width: int, height: int) -> float:
    scale = min(NORMALIZED_IMAGE_WIDTH / width, MAX_IMAGE_UPSCALE)
    adaptively_reduced = False
    maximum_normalized_height = SLICE_HEIGHT + (MAX_IMAGE_SLICES - 1) * (
        SLICE_HEIGHT - SLICE_OVERLAP
    )
    if round(height * scale) > maximum_normalized_height:
        scale = maximum_normalized_height / height
        adaptively_reduced = True
    if adaptively_reduced and width * scale < MIN_NORMALIZED_IMAGE_WIDTH:
        raise import_error(
            413,
            "cashflow_vision_too_tall_for_readable_slices",
            "截图过长，继续缩小会影响识别准确率；请把它分成两张连续截图，系统会自动处理交界重复记录",
        )
    return scale


def should_use_segmented_ocr(dimensions: tuple[int, int]) -> bool:
    width, height = dimensions
    scale = _normalization_scale(width, height)
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


def _render_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
    force_multiple: bool,
) -> list[dict[str, Any]]:
    width, height = dimensions
    scale = _normalization_scale(width, height)
    normalized_width = max(1, round(width * scale))
    normalized_height = max(1, round(height * scale))
    ranges = _slice_ranges(normalized_height)
    if force_multiple and len(ranges) < 2:
        if normalized_height < 2:
            raise import_error(
                400,
                "cashflow_vision_invalid_file",
                "图片高度过小，无法生成可恢复的 OCR 切片",
            )
        overlap = min(SLICE_OVERLAP, max(1, normalized_height // 5))
        midpoint = max(1, normalized_height // 2)
        first_bottom = min(normalized_height, midpoint + overlap // 2)
        second_top = max(0, midpoint - overlap // 2)
        ranges = [(0, first_bottom), (second_top, normalized_height)]

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
            overlap_pixels = 0
            if sequence_number > 1:
                previous_bottom = ranges[sequence_number - 2][1]
                overlap_pixels = max(0, previous_bottom - normalized_top)
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
                        "overlap_pixels": overlap_pixels,
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
            "截图无法稳定切片，请换一张清晰的 PNG、JPG 或 WebP 图片",
        ) from exc


def render_long_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
) -> list[dict[str, Any]]:
    parts = _render_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
        force_multiple=False,
    )
    if len(parts) < 2:
        raise ValueError("segmented OCR requires at least two slices")
    return parts


def render_sequence_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
) -> list[dict[str, Any]]:
    """Render recoverable derived slices without retaining a whole screenshot.

    A short screenshot is deliberately split into two overlapping regions so
    that a saved artifact is never just the original image under another name.
    """

    return _render_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
        force_multiple=True,
    )


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
                "source_image_sequence": locator.get("source_image_sequence", 1),
                "source_image_slice_sequence": locator.get("source_image_slice_sequence", artifact.sequence_number),
                "source_image_slice_total": locator.get("source_image_slice_total", len(artifacts)),
                "source_pixel_top": locator.get("source_pixel_top"),
                "source_pixel_bottom": locator.get("source_pixel_bottom"),
                "ocr_character_count": metadata.get("ocr_character_count"),
                "ocr_processed_character_count": metadata.get("ocr_processed_character_count"),
                "ocr_chunk_count": metadata.get("ocr_chunk_count"),
                "ocr_text_fully_processed": metadata.get("ocr_text_fully_processed"),
                "error_code": artifact.error_code if status == "failed" else None,
                "error_message": metadata.get("error_message") if status == "failed" else None,
            }
        )
    hints = batch.parse_hints if isinstance(batch.parse_hints, dict) else {}
    sequence_images = hints.get("sequence_images") if isinstance(hints.get("sequence_images"), list) else []
    duplicate_images = [
        item
        for item in sequence_images
        if isinstance(item, dict) and isinstance(item.get("duplicate_of_image_sequence"), int)
    ]
    submitted_images = len(sequence_images) or (1 if artifacts else 0)
    return {
        "mode": "image_sequence" if batch.source_type == "screenshot_sequence" else "segmented_image",
        "submitted_images": submitted_images,
        "unique_images": max(0, submitted_images - len(duplicate_images)),
        "duplicate_images": duplicate_images,
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
    dimensions = _validate_image_dimensions(content, detected_type, segmented=True)
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
    committed = False
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
            source_locator = {
                **item["source_locator"],
                "source_image_sequence": 1,
                "source_image_slice_sequence": sequence_number,
                "source_image_slice_total": len(rendered_slices),
            }
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
                    source_locator=source_locator,
                    artifact_metadata={
                        "contains_sensitive_source_image": True,
                        "ocr_status": "pending",
                    },
                )
            )
        db.flush()
        _store_progress(db, batch=batch)
        db.commit()
        committed = True
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
        if not committed:
            for path in created_paths:
                path.unlink(missing_ok=True)
        raise


def create_image_sequence_ocr_batch(
    db: Session,
    *,
    user_id: int,
    images: list[dict[str, Any]],
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    if len(images) < 2:
        raise import_error(400, "cashflow_vision_sequence_too_short", "连续截图至少选择 2 张")
    if len(images) > MAX_SEQUENCE_IMAGES:
        raise import_error(
            413,
            "cashflow_vision_sequence_too_many_images",
            f"一次最多选择 {MAX_SEQUENCE_IMAGES} 张连续截图",
        )

    total_bytes = sum(len(item.get("content") or b"") for item in images)
    if total_bytes > MAX_SEQUENCE_TOTAL_BYTES:
        raise import_error(413, "cashflow_vision_sequence_too_large", "连续截图总大小不能超过 90MB")

    sequence_hasher = hashlib.sha256(b"cashflow-image-sequence-v1\0")
    seen_hashes: dict[str, int] = {}
    sequence_images: list[dict[str, Any]] = []
    rendered_slices: list[dict[str, Any]] = []
    global_sequence = 1
    for image_sequence, image in enumerate(images, start=1):
        content = image.get("content")
        if not isinstance(content, bytes) or not content:
            raise import_error(400, "cashflow_vision_invalid_file", f"第 {image_sequence} 张图片内容为空")
        declared_type = str(image.get("content_type") or "application/octet-stream")
        detected_type = _validated_image_type(content, declared_type)
        dimensions = _validate_image_dimensions(content, detected_type, segmented=True)
        content_hash = hashlib.sha256(content).hexdigest()
        sequence_hasher.update(bytes.fromhex(content_hash))
        sequence_hasher.update(b"\0")
        duplicate_of = seen_hashes.get(content_hash)
        if duplicate_of is not None:
            sequence_images.append(
                {
                    "image_sequence": image_sequence,
                    "width": dimensions[0],
                    "height": dimensions[1],
                    "slice_count": 0,
                    "duplicate_of_image_sequence": duplicate_of,
                }
            )
            continue
        seen_hashes[content_hash] = image_sequence
        parts = render_sequence_image_slices(
            content,
            detected_type=detected_type,
            dimensions=dimensions,
        )
        if len(rendered_slices) + len(parts) > MAX_SEQUENCE_TOTAL_SLICES:
            raise import_error(
                413,
                "cashflow_vision_sequence_too_many_slices",
                f"连续截图合计需要超过 {MAX_SEQUENCE_TOTAL_SLICES} 个片段，请分成两个批次导入",
            )
        sequence_images.append(
            {
                "image_sequence": image_sequence,
                "width": dimensions[0],
                "height": dimensions[1],
                "slice_count": len(parts),
                "duplicate_of_image_sequence": None,
            }
        )
        for local_sequence, part in enumerate(parts, start=1):
            rendered_slices.append(
                {
                    **part,
                    "sequence_number": global_sequence,
                    "source_locator": {
                        **part["source_locator"],
                        "source_image_sequence": image_sequence,
                        "source_image_slice_sequence": local_sequence,
                        "source_image_slice_total": len(parts),
                    },
                }
            )
            global_sequence += 1

    content_hash = sequence_hasher.hexdigest()
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
        FinancialImportBatch.source_type == "screenshot_sequence",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
        FinancialImportBatch.status != "cancelled",
    ).first()
    if reusable is not None:
        return reusable, True

    created_paths: list[Path] = []
    committed = False
    try:
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type="ocr",
            source_type="screenshot_sequence",
            attachment_version_id=None,
            original_filename=f"连续账单截图（{len(images)} 张）",
            content_type="application/x-cashflow-image-sequence",
            file_size=total_bytes,
            content_hash=content_hash,
            parser_version=LONG_IMAGE_PARSER_VERSION,
            status="processing",
            column_mapping={},
            parse_hints={
                "intake": "ocr",
                "sequence_images": sequence_images,
            },
            parsed_at=None,
        )
        db.add(batch)
        db.flush()
        for item in rendered_slices:
            sequence_number = int(item["sequence_number"])
            locator = item["source_locator"]
            image_sequence = int(locator["source_image_sequence"])
            local_sequence = int(locator["source_image_slice_sequence"])
            local_total = int(locator["source_image_slice_total"])
            attachment = save_personal_attachment(
                db,
                user_id=user_id,
                document_type="cashflow_import",
                logical_key=f"cashflow-batch-{batch.id}-slice-{sequence_number}",
                display_name=f"连续截图 {image_sequence}/{len(images)} · 片段 {local_sequence}/{local_total}",
                original_filename=f"image-{image_sequence:03d}-slice-{local_sequence:03d}.png",
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
                    source_locator=locator,
                    artifact_metadata={
                        "contains_sensitive_source_image": True,
                        "ocr_status": "pending",
                        "source_image_sequence": image_sequence,
                    },
                )
            )
        db.flush()
        _store_progress(db, batch=batch)
        db.commit()
        committed = True
        db.refresh(batch)
        return batch, False
    except IntegrityError as exc:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        reusable = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == "ocr",
            FinancialImportBatch.source_type == "screenshot_sequence",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
            FinancialImportBatch.status != "cancelled",
        ).first()
        if reusable is not None:
            return reusable, True
        raise import_error(409, "cashflow_import_conflict", "相同连续截图正在识别，请刷新后继续") from exc
    except Exception:
        db.rollback()
        if not committed:
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


def _previous_slice_date_context(
    db: Session,
    *,
    batch: FinancialImportBatch,
    target_sequence: int,
    target_locator: dict[str, Any],
) -> dict[str, Any] | None:
    if target_sequence <= 1:
        return None
    previous = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == target_sequence - 1,
    ).first()
    if previous is None or _slice_status(previous) != "completed":
        return None
    previous_locator = previous.source_locator if isinstance(previous.source_locator, dict) else {}
    previous_image = previous_locator.get("source_image_sequence", 1)
    target_image = target_locator.get("source_image_sequence", 1)
    if not isinstance(previous_image, int) or not isinstance(target_image, int):
        return None
    if target_image not in {previous_image, previous_image + 1}:
        return None
    metadata = previous.artifact_metadata if isinstance(previous.artifact_metadata, dict) else {}
    raw_dates = metadata.get("recognized_transaction_dates")
    if not isinstance(raw_dates, list):
        return None
    parsed_dates: set[date] = set()
    for raw_date in raw_dates:
        if not isinstance(raw_date, str):
            continue
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        parsed_dates.add(parsed_date)
    if len(parsed_dates) != 1:
        return None
    transaction_date = next(iter(parsed_dates))
    return {
        "transaction_date": transaction_date,
        "source_slice_sequence": previous.sequence_number,
        "source_image_sequence": previous_image,
        "source_image_slice_sequence": previous_locator.get(
            "source_image_slice_sequence",
            previous.sequence_number,
        ),
    }


def _apply_previous_slice_date_context(
    parsed: list[ParsedCandidate],
    *,
    date_context: dict[str, Any] | None,
    content_hash: str,
) -> list[ParsedCandidate]:
    if date_context is None:
        return parsed
    inherited_date = date_context["transaction_date"]
    contextualized: list[ParsedCandidate] = []
    for index, candidate in enumerate(parsed, start=1):
        missing_date = any(
            issue.get("code") == "DATE_INVALID"
            for issue in candidate.validation_errors
        )
        if candidate.transaction_date is not None or not missing_date:
            contextualized.append(candidate)
            continue
        fingerprint = build_candidate_fingerprint(
            direction=candidate.direction,
            amount=candidate.amount,
            transaction_date=inherited_date,
            merchant=candidate.merchant,
            description=candidate.description,
        )
        key_digest = hashlib.sha256(
            f"ocr|{content_hash}|{index}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        warning = {
            "field": "transaction_date",
            "code": "DATE_CONTEXT_INHERITED",
            "message": (
                f"本片没有识别到独立日期，程序沿用上一相邻片段的唯一日期 "
                f"{inherited_date.isoformat()}，请确认后再记录"
            ),
        }
        contextualized.append(
            replace(
                candidate,
                transaction_date=inherited_date,
                external_key=f"ocr:{key_digest}",
                fingerprint=fingerprint,
                evidence={
                    **candidate.evidence,
                    "date_context_inherited": True,
                    "date_context": {
                        **date_context,
                        "transaction_date": inherited_date.isoformat(),
                    },
                },
                validation_errors=[
                    issue
                    for issue in candidate.validation_errors
                    if issue.get("code") != "DATE_INVALID"
                ],
                warnings=[warning, *candidate.warnings],
            )
        )
    return contextualized


def _adjacent_candidate_source(
    evidence: dict[str, Any],
    *,
    candidate_sequence: int | None,
) -> dict[str, Any] | None:
    source_slices = list(evidence.get("source_slices") or [])
    if not source_slices and isinstance(evidence.get("slice_sequence"), int):
        source_slices.append(
            {
                "slice_sequence": evidence["slice_sequence"],
                "source_locator": evidence.get("source_locator") or {},
            }
        )
    return next(
        (
            source
            for source in reversed(source_slices)
            if isinstance(source, dict)
            and isinstance(source.get("slice_sequence"), int)
            and isinstance(candidate_sequence, int)
            and abs(source["slice_sequence"] - candidate_sequence) == 1
        ),
        None,
    )


def _cross_image_overlap_cases(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: list[ParsedCandidate],
) -> list[dict[str, Any]]:
    existing = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.batch_id == batch.id,
        FinancialTransactionCandidate.status.in_({"ready", "needs_review", "possible_duplicate"}),
    ).all()
    cases: list[dict[str, Any]] = []
    for candidate in parsed:
        candidate_sequence = candidate.evidence.get("slice_sequence")
        candidate_locator = candidate.evidence.get("source_locator")
        if not isinstance(candidate_locator, dict):
            continue
        candidate_image = candidate_locator.get("source_image_sequence", 1)
        for row in existing:
            row_evidence = dict(row.evidence or {})
            adjacent_source = _adjacent_candidate_source(
                row_evidence,
                candidate_sequence=candidate_sequence if isinstance(candidate_sequence, int) else None,
            )
            if adjacent_source is None:
                continue
            row_locator = adjacent_source.get("source_locator")
            if not isinstance(row_locator, dict):
                row_locator = {}
            row_image = row_locator.get("source_image_sequence", 1)
            if row_image == candidate_image:
                continue
            if (
                row.direction != candidate.direction
                or row.amount != candidate.amount
                or row.transaction_date != candidate.transaction_date
                or row.amount is None
                or row.transaction_date is None
            ):
                continue
            if not duplicate_text_is_similar(
                row.merchant,
                row.description,
                merchant_b=candidate.merchant,
                description_b=candidate.description,
            ):
                continue
            row_merchant = _normalized_overlap_text(row.merchant)
            row_description = _normalized_overlap_text(row.description)
            candidate_merchant = _normalized_overlap_text(candidate.merchant)
            candidate_description = _normalized_overlap_text(candidate.description)
            row_quote = _normalized_overlap_text(row_evidence.get("evidence_quote"))
            candidate_quote = _normalized_overlap_text(candidate.evidence.get("evidence_quote"))
            merchant_conflicts = bool(
                row_merchant and candidate_merchant and row_merchant != candidate_merchant
            )
            description_conflicts = bool(
                row_description and candidate_description and row_description != candidate_description
            )
            exact_business_text = bool(
                (row_merchant and row_merchant == candidate_merchant)
                or (row_description and row_description == candidate_description)
            )
            exact_quote = bool(row_quote and row_quote == candidate_quote)
            if exact_business_text and exact_quote and not merchant_conflicts and not description_conflicts:
                continue
            cases.append(
                {
                    "current_row_number": candidate.row_number,
                    "prior_candidate_id": row.id,
                    "direction": candidate.direction,
                    "amount": format(candidate.amount, "f") if candidate.amount is not None else None,
                    "transaction_date": candidate.transaction_date.isoformat() if candidate.transaction_date else None,
                    "current_merchant": redact_cashflow_text(candidate.merchant or "", max_length=120),
                    "current_description": redact_cashflow_text(candidate.description or "", max_length=200),
                    "prior_merchant": redact_cashflow_text(row.merchant or "", max_length=120),
                    "prior_description": redact_cashflow_text(row.description or "", max_length=200),
                    "program_reason": "相邻截图交界处日期、金额和方向相同，交易文本相似但不完全一致",
                }
            )
            if len(cases) >= 20:
                return cases
    return cases


def _enrich_cross_image_overlap_with_ai(
    parsed: list[ParsedCandidate],
    *,
    cases: list[dict[str, Any]],
    user_id: int,
    expected_data_epoch: int,
) -> list[ParsedCandidate]:
    if not cases:
        return parsed
    from app.services.payslip_intake_service import _call_payslip_llm

    prompt = """你是收支守护的跨截图重复判断助手。程序已经先按截图顺序、日期、金额、方向和文本找到相似候选。
你只能评议是否可能为同一笔交易，不能合并、不能写账、不能代替用户确认。信息不足必须输出 uncertain。
只输出严格 JSON：{"assessments":[{"current_row_number":3001,"prior_candidate_id":12,"assessment":"likely_same|likely_different|uncertain","reason":"一句可核对理由"}]}
候选：
{cases}
""".replace("{cases}", json.dumps(cases, ensure_ascii=False))
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_cross_image_duplicate_reasoning",
        max_tokens=1600,
    )
    assessments_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    if output:
        text = output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            payload = None
        raw_assessments = payload.get("assessments") if isinstance(payload, dict) else None
        allowed_pairs = {
            (item["current_row_number"], item["prior_candidate_id"])
            for item in cases
        }
        if isinstance(raw_assessments, list):
            for item in raw_assessments[:20]:
                if not isinstance(item, dict):
                    continue
                key = (item.get("current_row_number"), item.get("prior_candidate_id"))
                verdict = item.get("assessment")
                if key not in allowed_pairs or verdict not in {"likely_same", "likely_different", "uncertain"}:
                    continue
                reason = re.sub(r"\s+", " ", str(item.get("reason") or "")).strip()[:240]
                assessments_by_pair[(int(key[0]), int(key[1]))] = {
                    "prior_candidate_id": int(key[1]),
                    "assessment": verdict,
                    "reason": reason or "AI 未提供可核对理由",
                    "ai_status": "completed",
                }

    contextualized: list[ParsedCandidate] = []
    cases_by_row: dict[int, list[dict[str, Any]]] = {}
    for item in cases:
        cases_by_row.setdefault(int(item["current_row_number"]), []).append(item)
    for candidate in parsed:
        row_cases = cases_by_row.get(candidate.row_number)
        if not row_cases:
            contextualized.append(candidate)
            continue
        assessments = [
            assessments_by_pair.get(
                (candidate.row_number, int(item["prior_candidate_id"])),
                {
                    "prior_candidate_id": int(item["prior_candidate_id"]),
                    "assessment": "uncertain",
                    "reason": "AI 未返回可用判断，需要人工核对",
                    "ai_status": "unavailable",
                },
            )
            for item in row_cases
        ]
        primary = next(
            (item for item in assessments if item["assessment"] == "likely_same"),
            assessments[0],
        )
        verdict_copy = {
            "likely_same": "AI 认为较可能是同一笔",
            "likely_different": "AI 认为较可能不是同一笔",
            "uncertain": "AI 仍无法确定是否同一笔",
        }[primary["assessment"]]
        warning = {
            "field": "fingerprint",
            "code": "CROSS_IMAGE_DUPLICATE_AI_REVIEW",
            "message": (
                f"程序发现相邻截图交界处的疑似同笔交易；{verdict_copy}："
                f"{primary['reason']}。系统不会自动合并或入账，请人工确认"
            ),
        }
        contextualized.append(
            replace(
                candidate,
                evidence={
                    **candidate.evidence,
                    "cross_image_duplicate_assessments": assessments,
                },
                warnings=[warning, *candidate.warnings],
            )
        )
    return contextualized


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
        matched_source_locator: dict[str, Any] = {}
        for row in existing:
            row_evidence = dict(row.evidence or {})
            candidate_sequence = candidate.evidence.get("slice_sequence")
            adjacent_source = _adjacent_candidate_source(
                row_evidence,
                candidate_sequence=candidate_sequence if isinstance(candidate_sequence, int) else None,
            )
            if adjacent_source is None:
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
                matched_source_locator = (
                    adjacent_source.get("source_locator")
                    if isinstance(adjacent_source.get("source_locator"), dict)
                    else {}
                )
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
        candidate_locator = candidate.evidence.get("source_locator") if isinstance(candidate.evidence.get("source_locator"), dict) else {}
        same_source_image = matched_source_locator.get("source_image_sequence", 1) == candidate_locator.get("source_image_sequence", 1)
        next_reason = (
            "同一截图相邻片段的日期、金额、方向和交易文本完全一致"
            if same_source_image
            else "相邻截图交界处的日期、金额、方向和交易文本完全一致"
        )
        current_reason = evidence.get("overlap_merge_reason")
        if current_reason is None or not same_source_image:
            evidence["overlap_merge_reason"] = next_reason
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
    if batch.origin_type != "ocr" or batch.source_type not in {"long_screenshot", "screenshot_sequence"}:
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
        # The slice bytes are now in memory. Release the attachment lookup
        # transaction before local OCR and either model call.
        db.rollback()
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

        context_batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
        date_context = _previous_slice_date_context(
            db,
            batch=context_batch,
            target_sequence=target_sequence,
            target_locator=source_locator,
        )
        row_start = target_sequence * 1000
        parsed = [
            replace(
                candidate,
                row_number=row_start + index,
                evidence={
                    **candidate.evidence,
                    "slice_sequence": target_sequence,
                    "slice_candidate_index": index,
                    "source_image_sequence": source_locator.get("source_image_sequence", 1),
                    "source_image_slice_sequence": source_locator.get("source_image_slice_sequence", target_sequence),
                    "source_locator": source_locator,
                    "source_slices": [
                        {
                            "slice_sequence": target_sequence,
                            "source_image_sequence": source_locator.get("source_image_sequence", 1),
                            "source_image_slice_sequence": source_locator.get("source_image_slice_sequence", target_sequence),
                            "source_locator": source_locator,
                        }
                    ],
                },
            )
            for index, candidate in enumerate(result.parsed, start=1)
        ]
        parsed = _apply_previous_slice_date_context(
            parsed,
            date_context=date_context,
            content_hash=slice_hash,
        )
        cross_image_cases = _cross_image_overlap_cases(
            db,
            batch=context_batch,
            parsed=parsed,
        )
        db.rollback()
        parsed = _enrich_cross_image_overlap_with_ai(
            parsed,
            cases=cross_image_cases,
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
        )
        recognized_candidate_count = len(parsed)
        recognized_transaction_dates = sorted(
            {
                candidate.transaction_date.isoformat()
                for candidate in parsed
                if candidate.transaction_date is not None
            }
        )
        date_context_inherited_count = sum(
            1
            for candidate in parsed
            if candidate.evidence.get("date_context_inherited") is True
        )
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
        parsed = _merge_exact_overlap_candidates(db, batch=batch, parsed=parsed)
        _populate_candidates(db, batch=batch, parsed=parsed)
        metadata = dict(target.artifact_metadata or {})
        metadata.update(
            {
                "ocr_status": "completed",
                "ocr_character_count": len(ocr_text),
                "ocr_processed_character_count": result.ocr_processed_characters or len(ocr_text),
                "ocr_chunk_count": result.ocr_chunk_count or 1,
                "ocr_text_fully_processed": (result.ocr_processed_characters or len(ocr_text)) == len(ocr_text),
                "recognized_candidate_count": recognized_candidate_count,
                "new_candidate_count": len(parsed),
                "overlap_merge_count": recognized_candidate_count - len(parsed),
                "recognized_transaction_dates": recognized_transaction_dates,
                "date_context_inherited_count": date_context_inherited_count,
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
