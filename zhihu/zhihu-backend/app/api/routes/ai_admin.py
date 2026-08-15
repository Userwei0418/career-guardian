from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.ai_configuration import (
    AIConnectionTestResult,
    AISettingsUpdate,
    AISettingsView,
)
from app.services.ai_configuration_service import (
    ai_settings_view,
    record_connection_test,
    save_ai_settings,
)
from app.services.assistant_service import _call_llm


router = APIRouter()


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
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tested_at = datetime.now(timezone.utc)
    output = _call_llm(
        "只回复 OK，不要输出其他内容。",
        feature="configuration_test",
        timeout=15,
        max_tokens=8,
        db=db,
    )
    success = bool(output and "OK" in output.upper())
    record_connection_test(db, success)
    return AIConnectionTestResult(
        success=success,
        message="连接成功，当前配置可以调用" if success else "连接失败，请检查地址、模型、密钥和账户余额",
        tested_at=tested_at,
    )
