from datetime import datetime, timezone

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_configuration import (
    AIConnectionTestResult,
    AIInvocationLogList,
    AISettingsUpdate,
    AISettingsView,
    ServiceConfigurationAuditList,
)
from app.schemas.career_image import CareerImageAdminList
from app.services.ai_configuration_service import (
    ai_settings_view,
    list_ai_invocations,
    list_service_configuration_audits,
    record_connection_test,
    save_ai_settings,
)
from app.services.career_image_service import list_admin_generations
from app.services.assistant_service import _call_llm


router = APIRouter()


@router.get("/career-images", response_model=CareerImageAdminList)
def get_career_image_generations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: Optional[
        Literal["queued", "submitted", "generating", "completed", "partial", "failed"]
    ] = None,
    username: Optional[str] = Query(None, min_length=1, max_length=100),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_generations(
        db,
        page=page,
        page_size=page_size,
        status=status,
        username=username,
    )


@router.get("/invocations", response_model=AIInvocationLogList)
def get_ai_invocations(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    feature: Optional[str] = Query(None, min_length=1, max_length=100),
    status: Optional[Literal["success", "failed"]] = None,
    modality: Optional[Literal["text", "audio", "image", "video", "realtime"]] = None,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_ai_invocations(
        db,
        page=page,
        page_size=page_size,
        feature=feature,
        status=status,
        modality=modality,
    )


@router.get("/configuration-audits", response_model=ServiceConfigurationAuditList)
def get_service_configuration_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_service_configuration_audits(
        db,
        page=page,
        page_size=page_size,
    )


@router.get("/config", response_model=AISettingsView)
def get_ai_config(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ai_settings_view(db)


@router.put("/config", response_model=AISettingsView)
def update_ai_config(
    request: AISettingsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return save_ai_settings(db, request, admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/config/test", response_model=AIConnectionTestResult)
def test_ai_config(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tested_at = datetime.now(timezone.utc)
    output = _call_llm(
        "只回复 OK，不要输出其他内容。",
        feature="configuration_test",
        timeout=15,
        max_tokens=8,
        db=db,
        user_id=admin.id,
    )
    # Different compatible models may translate or wrap the requested marker.
    # A connection test only needs to prove that the configured endpoint can
    # return a non-empty completion; product-level quality is verified by the
    # real feature evaluation instead of this smoke check.
    success = bool(output and output.strip())
    record_connection_test(db, success, actor_user_id=admin.id)
    return AIConnectionTestResult(
        success=success,
        message="连接成功，当前配置可以调用" if success else "连接失败，请检查地址、模型、密钥和账户余额",
        tested_at=tested_at,
    )
