from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_configuration import (
    AIConfigurationAudit,
    AIInvocationLog,
    AIProviderSetting,
)
from app.models.user import User
from app.schemas.ai_configuration import AISettingsUpdate, AISettingsView, AIUsageSummary


@dataclass(frozen=True)
class EffectiveAIConfiguration:
    setting_id: int | None
    provider_name: str
    base_url: str
    model: str
    api_key: str
    source: str


def _fernet() -> Fernet:
    secret = settings.AI_CONFIG_ENCRYPTION_KEY or settings.JWT_SECRET
    digest = hashlib.sha256(f"career-guardian-ai-config:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("AI 配置密钥无法解密，请由管理员重新填写 API Key") from exc


def _provider_from_url(base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    if host == "api.senseaudio.cn":
        return "SenseAudio"
    if host == "dashscope.aliyuncs.com":
        return "阿里云 DashScope"
    return host or "OpenAI 兼容服务"


def validate_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("AI 服务地址必须是完整的 HTTPS 地址")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("AI 服务地址不能包含账号、密码、查询参数或片段")
    allowed_hosts = {
        item.strip().lower()
        for item in settings.AI_ALLOWED_BASE_HOSTS.split(",")
        if item.strip()
    }
    if parsed.hostname.lower() not in allowed_hosts:
        raise ValueError("AI 服务域名不在服务端允许清单中")
    return normalized


def _database_setting(db: Session) -> AIProviderSetting | None:
    return db.query(AIProviderSetting).order_by(AIProviderSetting.id.desc()).first()


def effective_ai_configuration(db: Session) -> EffectiveAIConfiguration | None:
    stored = _database_setting(db)
    if stored is not None:
        if not stored.is_enabled:
            return None
        return EffectiveAIConfiguration(
            setting_id=stored.id,
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            api_key=decrypt_api_key(stored.api_key_encrypted),
            source="database",
        )
    if not settings.LLM_BASE_URL or not settings.LLM_API_KEY:
        return None
    base_url = validate_base_url(settings.LLM_BASE_URL)
    return EffectiveAIConfiguration(
        setting_id=None,
        provider_name=_provider_from_url(base_url),
        base_url=base_url,
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        source="environment",
    )


def _masked(suffix: str, configured: bool) -> str:
    return f"已配置（尾号 {suffix}）" if configured and suffix else "未配置"


def _usage_summary(db: Session) -> AIUsageSummary:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    total, success, tokens = db.query(
        func.count(AIInvocationLog.id),
        func.sum(case((AIInvocationLog.status == "success", 1), else_=0)),
        func.sum(AIInvocationLog.total_tokens),
    ).filter(AIInvocationLog.created_at >= since).one()
    total_calls = int(total or 0)
    successful_calls = int(success or 0)
    return AIUsageSummary(
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=max(0, total_calls - successful_calls),
        total_tokens=int(tokens or 0),
    )


def ai_settings_view(db: Session) -> AISettingsView:
    stored = _database_setting(db)
    if stored is not None:
        updater = db.get(User, stored.updated_by) if stored.updated_by else None
        return AISettingsView(
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            is_enabled=stored.is_enabled,
            api_key_configured=bool(stored.api_key_encrypted),
            api_key_masked=_masked(stored.api_key_suffix, bool(stored.api_key_encrypted)),
            source="database",
            updated_by=updater.username if updater else None,
            updated_at=stored.updated_at,
            last_test_status=stored.last_test_status,
            last_tested_at=stored.last_tested_at,
            usage=_usage_summary(db),
        )
    configured = bool(settings.LLM_API_KEY)
    suffix = settings.LLM_API_KEY[-4:] if settings.LLM_API_KEY else ""
    return AISettingsView(
        provider_name=_provider_from_url(settings.LLM_BASE_URL or ""),
        base_url=settings.LLM_BASE_URL or "",
        model=settings.LLM_MODEL,
        is_enabled=configured and bool(settings.LLM_BASE_URL),
        api_key_configured=configured,
        api_key_masked=_masked(suffix, configured),
        source="environment",
        usage=_usage_summary(db),
    )


def save_ai_settings(db: Session, request: AISettingsUpdate, admin: User) -> AISettingsView:
    base_url = validate_base_url(request.base_url)
    stored = _database_setting(db)
    is_new = stored is None
    key_changed = bool(request.api_key)
    if stored is None:
        fallback_key = settings.LLM_API_KEY or ""
        key = (request.api_key or fallback_key).strip()
        if not key:
            raise ValueError("首次保存 AI 配置时必须填写 API Key")
        stored = AIProviderSetting(
            provider_name=request.provider_name.strip(),
            base_url=base_url,
            model=request.model.strip(),
            api_key_encrypted=encrypt_api_key(key),
            api_key_suffix=key[-4:],
            is_enabled=request.is_enabled,
            updated_by=admin.id,
        )
        db.add(stored)
        db.flush()
        key_changed = True
    else:
        stored.provider_name = request.provider_name.strip()
        stored.base_url = base_url
        stored.model = request.model.strip()
        stored.is_enabled = request.is_enabled
        stored.updated_by = admin.id
        stored.last_test_status = None
        stored.last_tested_at = None
        if request.api_key:
            key = request.api_key.strip()
            stored.api_key_encrypted = encrypt_api_key(key)
            stored.api_key_suffix = key[-4:]
    db.add(
        AIConfigurationAudit(
            setting_id=stored.id,
            actor_user_id=admin.id,
            action="created" if is_new else "updated",
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            is_enabled=stored.is_enabled,
            key_changed=key_changed,
        )
    )
    db.commit()
    db.refresh(stored)
    return ai_settings_view(db)


def record_connection_test(db: Session, success: bool) -> None:
    stored = _database_setting(db)
    if stored is None:
        return
    stored.last_test_status = "success" if success else "failed"
    stored.last_tested_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        AIConfigurationAudit(
            setting_id=stored.id,
            actor_user_id=stored.updated_by,
            action="connection_test_success" if success else "connection_test_failed",
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            is_enabled=stored.is_enabled,
            key_changed=False,
        )
    )
    db.commit()


def record_ai_invocation(
    db: Session,
    configuration: EffectiveAIConfiguration,
    *,
    feature: str,
    status: str,
    latency_ms: int,
    usage: dict | None = None,
    error_code: str | None = None,
) -> None:
    usage = usage or {}
    db.add(
        AIInvocationLog(
            setting_id=configuration.setting_id,
            feature=feature[:100],
            provider_name=configuration.provider_name,
            model=configuration.model,
            status=status,
            latency_ms=max(0, latency_ms),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            error_code=error_code[:100] if error_code else None,
        )
    )
    db.commit()
