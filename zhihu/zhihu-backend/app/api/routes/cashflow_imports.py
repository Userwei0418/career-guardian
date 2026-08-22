from __future__ import annotations

from pathlib import Path
import shutil
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.cashflow_import import (
    CashflowImportCapabilitiesResponse,
    FinancialImportBatchListResponse,
    FinancialImportBatchResponse,
    FinancialImportCandidatePage,
    FinancialImportCandidateUpdate,
    FinancialImportConfirmRequest,
    FinancialImportConfirmReport,
    FinancialImportMappingUpdate,
    FinancialTransactionCandidateResponse,
    CashflowTextCandidateCreate,
)
from app.services.ai_configuration_service import effective_ai_configuration
from app.services.cashflow_ai_intake_service import parse_text_intake, parse_vision_intake
from app.services.cashflow_import_parser import (
    MAX_IMPORT_FILE_SIZE,
    CashflowImportError,
)
from app.services.cashflow_import_service import (
    apply_mapping,
    batch_payload,
    confirm_candidates,
    create_generated_import,
    create_file_import,
    get_owned_batch,
    import_error,
    list_owned_batches,
    list_owned_candidates,
    update_candidate,
)


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


def _read_upload_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = file.file.read(min(1024 * 1024, MAX_IMPORT_FILE_SIZE + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_IMPORT_FILE_SIZE:
            raise import_error(413, "cashflow_import_too_large", "账单文件不能超过 10MB")
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
    if local_ocr_configured and ai_configured:
        ocr_message = "已检测到本机 OCR 与职护当前 AI 配置；远端模型连通性将在提交时校验"
    elif not local_ocr_configured and not ai_configured:
        ocr_message = "本机 OCR 与职护当前 AI 配置均尚未就绪"
    elif not local_ocr_configured:
        ocr_message = "本机 OCR 尚未就绪"
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
            "enabled": local_ocr_configured and ai_configured,
            "state": "configured" if local_ocr_configured and ai_configured else "unavailable",
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
            "请先确认：图片仅在本地 OCR，脱敏后的文字将发送至当前 AI 服务进行结构化识别",
        )
    user_id = user.id
    data_epoch = user.business_data_epoch
    db.rollback()
    content = _read_upload_limited(file)
    # This is a synchronous FastAPI route, so local OCR, the current text-model
    # call and candidate persistence all run in the framework worker pool
    # instead of blocking the async event loop.
    result = parse_vision_intake(
        user_id=user_id,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        expected_data_epoch=data_epoch,
    )
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[result.content_type]
    original_name = Path(file.filename or "receipt").name
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
        expected_data_epoch=data_epoch,
    )
    return batch_payload(batch, reused=reused)


@router.get("/{batch_id}", response_model=FinancialImportBatchResponse)
def get_cashflow_import(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return batch_payload(get_owned_batch(db, user_id=user.id, batch_id=batch_id))


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
    return {"items": rows, "total": total, "offset": offset, "limit": limit}


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
    return candidate


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
