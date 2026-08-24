from __future__ import annotations

from pathlib import Path
import shutil
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.cashflow_import import (
    CashflowImportCapabilitiesResponse,
    CashflowRecognitionSliceDetailResponse,
    FinancialImportBatchDeleteResponse,
    FinancialImportBatchListResponse,
    FinancialImportBatchReviewResolutionRequest,
    FinancialImportBatchReviewResolutionResponse,
    FinancialImportBatchResponse,
    FinancialImportCandidateEvidenceResponse,
    FinancialImportCandidatePage,
    FinancialImportCandidateGroupMergeRequest,
    FinancialImportCandidateGroupMergeResponse,
    FinancialImportCandidateMergeRequest,
    FinancialImportCandidateMergeResponse,
    FinancialImportCandidateMergeUndoRequest,
    FinancialImportCandidateUpdate,
    FinancialImportConfirmRequest,
    FinancialImportConfirmReport,
    FinancialImportDuplicateAIReviewResponse,
    FinancialImportDuplicateRefreshResponse,
    FinancialImportMappingUpdate,
    FinancialTransactionCandidateResponse,
    CashflowTextCandidateCreate,
)
from app.services.ai_configuration_service import effective_ai_configuration
from app.services.cashflow_ai_intake_service import (
    MAX_OCR_FILE_SIZE,
    _validate_image_dimensions,
    _validated_image_type,
    parse_text_intake,
    parse_vision_intake,
)
from app.services.cashflow_import_parser import (
    MAX_IMPORT_FILE_SIZE,
    CashflowImportError,
)
from app.services.cashflow_import_service import (
    apply_mapping,
    batch_payload,
    candidate_payload,
    candidate_payloads,
    confirm_candidates,
    create_generated_import,
    create_file_import,
    delete_import_batch,
    get_owned_batch,
    import_error,
    list_owned_batches,
    list_owned_candidates,
    merge_candidate_group_into_fact,
    merge_duplicate_candidates,
    refresh_duplicate_candidates,
    review_candidate_duplicate_candidates_with_ai,
    review_formal_duplicate_candidates_with_ai,
    update_candidate,
    undo_duplicate_candidate_merge,
)
from app.services.cashflow_long_image_service import (
    MAX_SEQUENCE_IMAGES,
    MAX_SEQUENCE_TOTAL_BYTES,
    apply_batch_review_resolutions,
    create_image_sequence_ocr_batch,
    create_segmented_ocr_batch,
    get_candidate_evidence_payload,
    get_candidate_evidence_slice,
    get_ocr_slice_detail_payload,
    get_ocr_slice_image,
    process_ocr_slice,
    should_use_segmented_ocr,
)
from app.services.cashflow_tencent_ocr_service import tencent_ocr_configured


def _ocr_consent_message() -> str:
    if settings.TENCENT_OCR_ENABLED:
        return (
            "请先确认：识别所需的派生图片切片会发送至腾讯云 OCR；"
            "返回文字经本地规则处理，疑难文字才会发送至职护当前 AI，确认后才入账"
        )
    return "请先确认：图片仅在本地 OCR，脱敏后的文字将发送至当前 AI 服务进行结构化识别"


router = APIRouter()

SourceHint = Literal["auto", "wechat", "alipay", "bank", "generic"]
CandidateStatus = Literal[
    "ready",
    "needs_review",
    "exact_duplicate",
    "possible_duplicate",
    "invalid",
    "excluded",
    "confirmed",
]


def _read_upload_limited(
    file: UploadFile,
    *,
    max_size: int = MAX_IMPORT_FILE_SIZE,
    too_large_message: str = "账单文件不能超过 10MB",
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = file.file.read(min(1024 * 1024, max_size + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > max_size:
            raise import_error(413, "cashflow_import_too_large", too_large_message)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=FinancialImportBatchResponse)
def upload_cashflow_import(
    file: Annotated[UploadFile, File(...)],
    source_hint: Annotated[SourceHint, Form()] = "auto",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    data_epoch = user.business_data_epoch
    # Authentication performed a read on this request Session. End that
    # snapshot before CPU-heavy parsing so the connection returns to the pool.
    db.rollback()
    content = _read_upload_limited(file)
    try:
        batch, reused = create_file_import(
            db,
            user_id=user_id,
            filename=file.filename or "cashflow.csv",
            content=content,
            source_hint=source_hint,
            expected_data_epoch=data_epoch,
        )
    except CashflowImportError as exc:
        message = str(exc)
        status_code = 413 if "10MB" in message or "最多支持" in message or "过大" in message else 400
        code = "cashflow_import_too_large" if status_code == 413 else "cashflow_import_invalid_file"
        raise import_error(status_code, code, message) from exc
    return batch_payload(batch, reused=reused)


@router.get("", response_model=FinancialImportBatchListResponse)
def list_cashflow_imports(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    unfinished_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = list_owned_batches(
        db,
        user_id=user.id,
        offset=offset,
        limit=limit,
        unfinished_only=unfinished_only,
    )
    return {"items": [batch_payload(row) for row in rows], "total": total}


@router.get("/capabilities", response_model=CashflowImportCapabilitiesResponse)
def get_cashflow_import_capabilities(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        # Verify the branch code and its import tables are both active. This
        # deliberately reads no candidate payload and creates no data.
        list_owned_batches(db, user_id=user.id, offset=0, limit=1)
    except Exception:
        db.rollback()
        unavailable = {
            "enabled": False,
            "state": "unavailable",
            "message": "导入批次存储尚未就绪，请联系管理员完成迁移或恢复数据库服务",
        }
        return {"file": unavailable, "text": unavailable, "ocr": unavailable}

    try:
        ai_configured = effective_ai_configuration(db) is not None
        ai_message = (
            "已检测到职护当前 AI 配置；远端模型连通性将在提交时校验"
            if ai_configured
            else "职护当前 AI 配置尚未启用"
        )
    except Exception:
        ai_configured = False
        ai_message = "职护当前 AI 配置暂时无法读取"

    local_ocr_configured = shutil.which("tesseract") is not None
    cloud_ocr_configured = tencent_ocr_configured()
    ocr_engine_configured = cloud_ocr_configured or local_ocr_configured
    if cloud_ocr_configured and local_ocr_configured:
        ocr_message = "腾讯云高精度 OCR 已配置，本机 OCR 可在失败或额度不足时降级"
    elif cloud_ocr_configured:
        ocr_message = "腾讯云高精度 OCR 已配置；派生图片切片会发送至腾讯云"
    elif local_ocr_configured and ai_configured:
        ocr_message = "腾讯云 OCR 未启用，当前使用本机 OCR 与职护 AI"
    elif not ocr_engine_configured and not ai_configured:
        ocr_message = "腾讯云和本机 OCR 均尚未就绪，职护当前 AI 也未启用"
    elif not ocr_engine_configured:
        ocr_message = "腾讯云和本机 OCR 均尚未就绪"
    else:
        ocr_message = ai_message

    return {
        "file": {
            "enabled": True,
            "state": "available",
            "message": "文件解析、批次和候选接口已启用；具体文件仍会按类型与内容校验",
        },
        "text": {
            "enabled": ai_configured,
            "state": "configured" if ai_configured else "unavailable",
            "message": ai_message,
        },
        "ocr": {
            "enabled": ocr_engine_configured and ai_configured,
            "state": "configured" if ocr_engine_configured and ai_configured else "unavailable",
            "message": ocr_message,
        },
    }


@router.post("/text", response_model=FinancialImportBatchResponse)
def create_cashflow_text_candidates(
    data: CashflowTextCandidateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    data_epoch = user.business_data_epoch
    # Do not hold the authentication transaction/connection across a remote
    # model call. The same Session begins a fresh short business transaction
    # only when candidate persistence starts.
    db.rollback()
    result = parse_text_intake(
        user_id=user_id,
        text=data.text,
        expected_data_epoch=data_epoch,
    )
    batch, reused = create_generated_import(
        db,
        user_id=user_id,
        origin_type="ai_text",
        source_type="ai_text",
        content_hash=result.content_hash,
        parser_version=result.parser_version,
        parsed=result.parsed,
        expected_data_epoch=data_epoch,
    )
    return batch_payload(batch, reused=reused)


@router.post("/ocr", response_model=FinancialImportBatchResponse)
def create_cashflow_ocr_candidates(
    file: Annotated[UploadFile, File(...)],
    confirm_external_processing: Annotated[bool, Form()] = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not confirm_external_processing:
        raise import_error(
            400,
            "cashflow_vision_consent_required",
            _ocr_consent_message(),
        )
    user_id = user.id
    data_epoch = user.business_data_epoch
    db.rollback()
    content = _read_upload_limited(
        file,
        max_size=MAX_OCR_FILE_SIZE,
        too_large_message="OCR 图片不能超过 30MB",
    )
    declared_content_type = file.content_type or "application/octet-stream"
    detected_type = _validated_image_type(content, declared_content_type)
    dimensions = _validate_image_dimensions(content, detected_type, segmented=True)
    original_name = Path(file.filename or "receipt").name
    if should_use_segmented_ocr(dimensions):
        batch, reused = create_segmented_ocr_batch(
            db,
            user_id=user_id,
            content=content,
            content_type=declared_content_type,
            original_filename=original_name,
            expected_data_epoch=data_epoch,
        )
        return batch_payload(batch, reused=reused)
    # This is a synchronous FastAPI route, so local OCR, the current text-model
    # call and candidate persistence all run in the framework worker pool
    # instead of blocking the async event loop.
    result = parse_vision_intake(
        user_id=user_id,
        content=content,
        content_type=declared_content_type,
        expected_data_epoch=data_epoch,
    )
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[result.content_type]
    if Path(original_name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        original_name = f"receipt{suffix}"
    batch, reused = create_generated_import(
        db,
        user_id=user_id,
        origin_type="ocr",
        source_type="receipt",
        content_hash=result.content_hash,
        parser_version=result.parser_version,
        parsed=result.parsed,
        original_filename=original_name,
        original_content_type=result.content_type,
        original_file_size=len(content),
        ocr_text=result.ocr_text,
        ocr_source_locator=result.ocr_source_locator,
        ocr_artifact_metadata=result.ocr_artifact_metadata,
        expected_data_epoch=data_epoch,
    )
    return batch_payload(batch, reused=reused)


@router.post("/ocr/sequence", response_model=FinancialImportBatchResponse)
def create_cashflow_screenshot_sequence_candidates(
    files: Annotated[list[UploadFile], File(...)],
    confirm_external_processing: Annotated[bool, Form()] = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not confirm_external_processing:
        raise import_error(
            400,
            "cashflow_vision_consent_required",
            _ocr_consent_message(),
        )
    if len(files) < 2:
        raise import_error(400, "cashflow_vision_sequence_too_short", "连续截图至少选择 2 张")
    if len(files) > MAX_SEQUENCE_IMAGES:
        raise import_error(
            413,
            "cashflow_vision_sequence_too_many_images",
            f"一次最多选择 {MAX_SEQUENCE_IMAGES} 张连续截图",
        )

    data_epoch = user.business_data_epoch
    db.rollback()
    images: list[dict[str, object]] = []
    total_size = 0
    for index, file in enumerate(files, start=1):
        content = _read_upload_limited(
            file,
            max_size=MAX_OCR_FILE_SIZE,
            too_large_message=f"第 {index} 张 OCR 图片不能超过 30MB",
        )
        total_size += len(content)
        if total_size > MAX_SEQUENCE_TOTAL_BYTES:
            raise import_error(413, "cashflow_vision_sequence_too_large", "连续截图总大小不能超过 90MB")
        images.append(
            {
                "content": content,
                "content_type": file.content_type or "application/octet-stream",
                "original_filename": Path(file.filename or f"screenshot-{index}.png").name,
            }
        )
    batch, reused = create_image_sequence_ocr_batch(
        db,
        user_id=user.id,
        images=images,
        expected_data_epoch=data_epoch,
    )
    return batch_payload(batch, reused=reused)


@router.post("/{batch_id}/ocr/process-next", response_model=FinancialImportBatchResponse)
def process_next_cashflow_ocr_slice(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    batch = process_ocr_slice(
        db,
        user_id=user.id,
        batch_id=batch_id,
    )
    return batch_payload(batch)


@router.post(
    "/{batch_id}/ocr/slices/{sequence_number}/retry",
    response_model=FinancialImportBatchResponse,
)
def retry_cashflow_ocr_slice(
    batch_id: int,
    sequence_number: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if sequence_number < 1:
        raise import_error(400, "cashflow_vision_invalid_slice", "识别片段序号无效")
    db.rollback()
    batch = process_ocr_slice(
        db,
        user_id=user.id,
        batch_id=batch_id,
        sequence_number=sequence_number,
        retry_failed=True,
    )
    return batch_payload(batch)


@router.get("/{batch_id}", response_model=FinancialImportBatchResponse)
def get_cashflow_import(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return batch_payload(get_owned_batch(db, user_id=user.id, batch_id=batch_id))


@router.delete("/{batch_id}", response_model=FinancialImportBatchDeleteResponse)
def delete_cashflow_import(
    batch_id: int,
    expected_version: int = Query(ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Authentication opened a read transaction.  Start a fresh transaction so
    # the user ledger lock and expected-version check observe current state.
    db.rollback()
    return delete_import_batch(
        db,
        user_id=user.id,
        batch_id=batch_id,
        expected_version=expected_version,
    )


@router.get("/{batch_id}/candidates", response_model=FinancialImportCandidatePage)
def get_cashflow_import_candidates(
    batch_id: int,
    candidate_status: Optional[CandidateStatus] = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows, total = list_owned_candidates(
        db,
        user_id=user.id,
        batch_id=batch_id,
        status=candidate_status,
        offset=offset,
        limit=limit,
    )
    batch = get_owned_batch(db, user_id=user.id, batch_id=batch_id)
    return {
        "items": candidate_payloads(db, batch=batch, candidates=rows),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post(
    "/{batch_id}/review-resolutions",
    response_model=FinancialImportBatchReviewResolutionResponse,
)
def resolve_cashflow_import_batch_reviews(
    batch_id: int,
    data: FinancialImportBatchReviewResolutionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Batch versioning is the concurrency boundary for this intentionally
    # all-or-nothing acknowledgement.  It changes candidate review state only;
    # no formal transaction or economic fact is created here.
    db.rollback()
    return apply_batch_review_resolutions(
        db,
        user_id=user.id,
        batch_id=batch_id,
        data=data,
    )


@router.get(
    "/{batch_id}/candidates/{candidate_id}/evidence",
    response_model=FinancialImportCandidateEvidenceResponse,
)
def get_cashflow_import_candidate_evidence(
    batch_id: int,
    candidate_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_candidate_evidence_payload(
        db,
        user_id=user.id,
        batch_id=batch_id,
        candidate_id=candidate_id,
    )


@router.get(
    "/{batch_id}/candidates/{candidate_id}/evidence/slices/{sequence_number}",
)
def get_cashflow_import_candidate_evidence_slice(
    batch_id: int,
    candidate_id: int,
    sequence_number: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if sequence_number < 1:
        raise import_error(400, "cashflow_vision_invalid_slice", "识别片段序号无效")
    path, media_type, filename = get_candidate_evidence_slice(
        db,
        user_id=user.id,
        batch_id=batch_id,
        candidate_id=candidate_id,
        sequence_number=sequence_number,
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/{batch_id}/ocr/slices/{sequence_number}",
    response_model=CashflowRecognitionSliceDetailResponse,
)
def get_cashflow_import_ocr_slice_detail(
    batch_id: int,
    sequence_number: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if sequence_number < 1:
        raise import_error(400, "cashflow_vision_invalid_slice", "识别片段序号无效")
    return get_ocr_slice_detail_payload(
        db,
        user_id=user.id,
        batch_id=batch_id,
        sequence_number=sequence_number,
    )


@router.get("/{batch_id}/ocr/slices/{sequence_number}/image")
def get_cashflow_import_ocr_slice_image(
    batch_id: int,
    sequence_number: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if sequence_number < 1:
        raise import_error(400, "cashflow_vision_invalid_slice", "识别片段序号无效")
    path, media_type, filename = get_ocr_slice_image(
        db,
        user_id=user.id,
        batch_id=batch_id,
        sequence_number=sequence_number,
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{batch_id}/duplicate-ai-review",
    response_model=FinancialImportDuplicateAIReviewResponse,
)
def review_cashflow_import_duplicates(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Authentication starts a read transaction.  Capture the deletion epoch,
    # then let the service release the transaction before its external model
    # call and revalidate everything under the ledger lock before persisting.
    user_id = user.id
    expected_data_epoch = user.business_data_epoch
    db.rollback()
    formal_report = review_formal_duplicate_candidates_with_ai(
        db,
        user_id=user_id,
        batch_id=batch_id,
        expected_data_epoch=expected_data_epoch,
    )
    candidate_report = review_candidate_duplicate_candidates_with_ai(
        db,
        user_id=user_id,
        batch_id=batch_id,
        expected_data_epoch=expected_data_epoch,
    )
    return {
        "batch_id": batch_id,
        "eligible_candidate_count": formal_report["eligible_candidate_count"] + candidate_report["eligible_candidate_count"],
        "reviewed_candidate_count": formal_report["reviewed_candidate_count"] + candidate_report["reviewed_candidate_count"],
        "completed_assessment_count": formal_report["completed_assessment_count"] + candidate_report["completed_assessment_count"],
        "unavailable_candidate_count": formal_report["unavailable_candidate_count"] + candidate_report["unavailable_candidate_count"],
        "remaining_candidate_count": formal_report["remaining_candidate_count"] + candidate_report["remaining_candidate_count"],
    }


@router.post(
    "/{batch_id}/duplicate-refresh",
    response_model=FinancialImportDuplicateRefreshResponse,
)
def refresh_cashflow_import_duplicates(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Resuming a draft must compare it with the ledger as it exists now, not
    # only with the snapshot that existed when OCR/import first ran.
    user_id = user.id
    db.rollback()
    return refresh_duplicate_candidates(
        db,
        user_id=user_id,
        batch_id=batch_id,
    )


@router.put("/{batch_id}/mapping", response_model=FinancialImportBatchResponse)
def update_cashflow_import_mapping(
    batch_id: int,
    data: FinancialImportMappingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        batch = apply_mapping(
            db,
            user_id=user.id,
            batch_id=batch_id,
            expected_batch_version=data.expected_batch_version,
            mapping=data.mapping,
        )
    except CashflowImportError as exc:
        raise import_error(400, "cashflow_import_invalid_mapping", str(exc)) from exc
    return batch_payload(batch)


@router.patch(
    "/{batch_id}/candidates/{candidate_id}",
    response_model=FinancialTransactionCandidateResponse,
)
def patch_cashflow_import_candidate(
    batch_id: int,
    candidate_id: int,
    data: FinancialImportCandidateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    candidate, _batch = update_candidate(
        db,
        user_id=user_id,
        batch_id=batch_id,
        candidate_id=candidate_id,
        data=data,
    )
    return candidate_payload(db, batch=_batch, candidate=candidate)


@router.post(
    "/{batch_id}/candidate-group-merge",
    response_model=FinancialImportCandidateGroupMergeResponse,
)
def merge_cashflow_import_candidate_group(
    batch_id: int,
    data: FinancialImportCandidateGroupMergeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    return merge_candidate_group_into_fact(
        db,
        user_id=user_id,
        batch_id=batch_id,
        data=data,
    )


@router.post(
    "/{batch_id}/candidate-merge",
    response_model=FinancialImportCandidateMergeResponse,
)
def merge_cashflow_import_duplicate_candidates(
    batch_id: int,
    data: FinancialImportCandidateMergeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    return merge_duplicate_candidates(
        db,
        user_id=user.id,
        batch_id=batch_id,
        data=data,
    )


@router.post(
    "/{batch_id}/candidate-merges/{merged_candidate_id}/undo",
    response_model=FinancialImportCandidateMergeResponse,
)
def undo_cashflow_import_duplicate_candidate_merge(
    batch_id: int,
    merged_candidate_id: int,
    data: FinancialImportCandidateMergeUndoRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    return undo_duplicate_candidate_merge(
        db,
        user_id=user.id,
        batch_id=batch_id,
        merged_candidate_id=merged_candidate_id,
        data=data,
    )


@router.post("/{batch_id}/confirm", response_model=FinancialImportConfirmReport)
def confirm_cashflow_import(
    batch_id: int,
    data: FinancialImportConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    # Authentication performed a consistent read. Start a fresh transaction so
    # the per-user ledger lock is followed by a current duplicate snapshot.
    db.rollback()
    return confirm_candidates(
        db,
        user_id=user_id,
        batch_id=batch_id,
        data=data,
    )
