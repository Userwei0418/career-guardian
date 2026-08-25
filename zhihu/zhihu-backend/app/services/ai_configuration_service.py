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
    DEFAULT_IMAGE_LANDSCAPE_PROMPT,
    DEFAULT_IMAGE_SQUARE_PROMPT,
    DEFAULT_IMAGE_STYLE_PROMPT,
)
from app.models.user import User
from app.services.cashflow_tencent_ocr_service import (
    TENCENT_OCR_ENDPOINT,
    TENCENT_OCR_FEATURE,
    TENCENT_OCR_MODEL,
    TENCENT_OCR_PROVIDER,
    tencent_ocr_configured,
)
from app.schemas.ai_configuration import (
    AIInvocationLogItem,
    AIInvocationLogList,
    AISettingsUpdate,
    AISettingsView,
    AIUsageSummary,
    ServiceConfigurationAuditItem,
    ServiceConfigurationAuditList,
    TencentOCRServiceView,
)


FEATURE_LABELS: dict[str, str] = {
    "configuration_test": "服务配置·连接测试",
    "offer_extraction": "决策守护·Offer 信息提取",
    "opportunity_match": "机会守护·JD 与简历分析",
    "target_learning_plan": "机会守护·目标岗位能力路线",
    "target_plan_tts": "机会守护·能力路线语音解说",
    "resume_tailoring": "机会守护·目标岗位简历微调",
    "resume_parsing": "机会守护·简历解析",
    "major_direction_match": "机会守护·专业方向推荐",
    "mock_interview_realtime": "机会守护·模拟面试实时对话",
    "mock_interview_review": "机会守护·模拟面试复盘",
    "self_introduction_realtime": "机会守护·自我介绍专项练习",
    "self_introduction_review": "机会守护·自我介绍复盘",
    "market_strategy_repair_candidate": "数据采集·解析规则自动修复",
    "market_semantic_cleaning": "数据采集·岗位正文语义解析",
    "runtime_test": "服务配置·运行测试",
    "career_image_submit": "职业形象·提交前检查",
    "career_image_submit_landscape": "职业形象·提交横图生成",
    "career_image_submit_square": "职业形象·提交方图生成",
    "career_image_poll_landscape": "职业形象·查询横图结果",
    "career_image_poll_square": "职业形象·查询方图结果",
    "labor_contract_review": "权益守护·劳动合同审查",
    "labor_contract_follow_up": "权益守护·合同条款追问",
    "offer_contract_consistency": "权益守护·Offer 与合同核对",
    "cashflow_confirmed_ledger_qa": "收支守护·可信账本问询",
    "cashflow_import_candidate_duplicate_reasoning": "收支守护·导入候选重复判断",
    "cashflow_relation_reasoning": "收支守护·经济事实关系判断",
    "cashflow_same_fact_reasoning": "收支守护·同一经济事实判断",
    "cashflow_tencent_ocr": "收支守护·腾讯云票据识别",
    "cashflow_text_parse": "收支守护·自然语言记账解析",
    "cashflow_vision_parse": "收支守护·OCR 疑难交易解析",
    "growth_work_intake": "成长守护·当下工作整理",
}

CONFIGURATION_ACTION_LABELS: dict[str, str] = {
    "created": "创建模型服务配置",
    "updated": "更新模型服务配置",
    "connection_test_success": "连接测试成功",
    "connection_test_failed": "连接测试失败",
}


def feature_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature, "其他服务·未命名功能")


@dataclass(frozen=True)
class EffectiveAIConfiguration:
    setting_id: int | None
    provider_name: str
    base_url: str
    model: str
    tts_enabled: bool
    tts_model: str
    tts_voice_id: str
    realtime_enabled: bool
    realtime_model: str
    realtime_voice_id: str
    interview_agent_name: str
    interview_agent_prompt: str
    interview_greeting: str
    api_key: str
    source: str


@dataclass(frozen=True)
class EffectiveImageConfiguration:
    setting_id: int | None
    provider_name: str
    base_url: str
    model: str
    landscape_size: str
    square_size: str
    poll_interval_seconds: int
    timeout_seconds: int
    style_prompt: str
    landscape_prompt: str
    square_prompt: str
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
            tts_enabled=stored.tts_enabled,
            tts_model=stored.tts_model,
            tts_voice_id=stored.tts_voice_id,
            realtime_enabled=stored.realtime_enabled,
            realtime_model=stored.realtime_model,
            realtime_voice_id=stored.realtime_voice_id,
            interview_agent_name=stored.interview_agent_name,
            interview_agent_prompt=stored.interview_agent_prompt,
            interview_greeting=stored.interview_greeting,
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
        tts_enabled=False,
        tts_model="senseaudio-tts-1.5-260319",
        tts_voice_id="female_0033_b",
        realtime_enabled=False,
        realtime_model="senseaudio-realtime-1.0",
        realtime_voice_id="f_y_0035_c",
        interview_agent_name="职护模拟面试官",
        interview_agent_prompt="你是一位专业、耐心、尊重候选人的面试官。",
        interview_greeting="你好，我是职护模拟面试官。准备好后，我们开始今天的模拟面试。",
        api_key=settings.LLM_API_KEY,
        source="environment",
    )


def effective_image_configuration(db: Session) -> EffectiveImageConfiguration | None:
    stored = _database_setting(db)
    if stored is not None:
        # 职业形象保留独立启停，但与文本能力复用同一服务地址和服务端密钥。
        if not stored.image_enabled or not stored.api_key_encrypted:
            return None
        return EffectiveImageConfiguration(
            setting_id=stored.id,
            provider_name=stored.provider_name,
            base_url=validate_base_url(stored.base_url),
            model=stored.image_model,
            landscape_size=stored.image_landscape_size,
            square_size=stored.image_square_size,
            poll_interval_seconds=stored.image_poll_interval_seconds,
            timeout_seconds=stored.image_timeout_seconds,
            style_prompt=stored.image_style_prompt or DEFAULT_IMAGE_STYLE_PROMPT,
            landscape_prompt=stored.image_landscape_prompt or DEFAULT_IMAGE_LANDSCAPE_PROMPT,
            square_prompt=stored.image_square_prompt or DEFAULT_IMAGE_SQUARE_PROMPT,
            api_key=decrypt_api_key(stored.api_key_encrypted),
            source="database",
        )
    if not settings.LLM_API_KEY or not settings.LLM_BASE_URL:
        return None
    return EffectiveImageConfiguration(
        setting_id=None,
        provider_name=_provider_from_url(settings.LLM_BASE_URL),
        base_url=validate_base_url(settings.LLM_BASE_URL),
        model=settings.IMAGE_MODEL,
        landscape_size=settings.IMAGE_LANDSCAPE_SIZE,
        square_size=settings.IMAGE_SQUARE_SIZE,
        poll_interval_seconds=settings.IMAGE_POLL_INTERVAL_SECONDS,
        timeout_seconds=settings.IMAGE_TIMEOUT_SECONDS,
        style_prompt=DEFAULT_IMAGE_STYLE_PROMPT,
        landscape_prompt=DEFAULT_IMAGE_LANDSCAPE_PROMPT,
        square_prompt=DEFAULT_IMAGE_SQUARE_PROMPT,
        api_key=settings.LLM_API_KEY,
        source="environment",
    )


def _masked(suffix: str, configured: bool) -> str:
    return f"已配置（尾号 {suffix}）" if configured and suffix else "未配置"


def _usage_summary(db: Session) -> AIUsageSummary:
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    total, success, prompt_tokens, completion_tokens, tokens = db.query(
        func.count(AIInvocationLog.id),
        func.sum(case((AIInvocationLog.status == "success", 1), else_=0)),
        func.sum(AIInvocationLog.prompt_tokens),
        func.sum(AIInvocationLog.completion_tokens),
        func.sum(AIInvocationLog.total_tokens),
    ).filter(AIInvocationLog.created_at >= since).one()
    total_calls = int(total or 0)
    successful_calls = int(success or 0)
    modality_counts = {name: 0 for name in ("text", "audio", "image", "video", "realtime")}
    for modality, count in (
        db.query(AIInvocationLog.modality, func.count(AIInvocationLog.id))
        .filter(AIInvocationLog.created_at >= since)
        .group_by(AIInvocationLog.modality)
        .all()
    ):
        modality_counts[str(modality or "text")] = int(count or 0)
    usage_breakdown = [
        {
            "modality": str(modality or "text"),
            "usage_unit": str(usage_unit),
            "amount": int(amount or 0),
        }
        for modality, usage_unit, amount in (
            db.query(
                AIInvocationLog.modality,
                AIInvocationLog.usage_unit,
                func.sum(AIInvocationLog.usage_amount),
            )
            .filter(
                AIInvocationLog.created_at >= since,
                AIInvocationLog.usage_amount.isnot(None),
                AIInvocationLog.usage_unit.isnot(None),
            )
            .group_by(AIInvocationLog.modality, AIInvocationLog.usage_unit)
            .order_by(AIInvocationLog.modality.asc(), AIInvocationLog.usage_unit.asc())
            .all()
        )
    ]
    top_users = [
        {"username": username or "未记录用户", "calls": int(count or 0)}
        for username, count in (
            db.query(User.username, func.count(AIInvocationLog.id))
            .outerjoin(User, AIInvocationLog.user_id == User.id)
            .filter(AIInvocationLog.created_at >= since)
            .group_by(User.username)
            .order_by(func.count(AIInvocationLog.id).desc())
            .limit(5)
            .all()
        )
    ]
    return AIUsageSummary(
        total_calls=total_calls,
        successful_calls=successful_calls,
        failed_calls=max(0, total_calls - successful_calls),
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(tokens or 0),
        usage_breakdown=usage_breakdown,
        modality_counts=modality_counts,
        top_users=top_users,
    )


def _tencent_ocr_service_view(db: Session) -> TencentOCRServiceView:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    month_start = datetime(now.year, now.month, 1)
    monthly_calls = int(
        db.query(func.sum(AIInvocationLog.usage_amount))
        .filter(
            AIInvocationLog.feature == TENCENT_OCR_FEATURE,
            AIInvocationLog.created_at >= month_start,
            AIInvocationLog.usage_amount.isnot(None),
        )
        .scalar()
        or 0
    )
    last_call = (
        db.query(AIInvocationLog)
        .filter(AIInvocationLog.feature == TENCENT_OCR_FEATURE)
        .order_by(AIInvocationLog.created_at.desc(), AIInvocationLog.id.desc())
        .first()
    )
    included_quota = max(0, int(settings.TENCENT_OCR_MONTHLY_INCLUDED_QUOTA))
    soft_limit = max(0, int(settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT))
    return TencentOCRServiceView(
        provider_name=TENCENT_OCR_PROVIDER,
        model=TENCENT_OCR_MODEL,
        endpoint=TENCENT_OCR_ENDPOINT,
        region=settings.TENCENT_OCR_REGION.strip() or "ap-guangzhou",
        enabled=bool(settings.TENCENT_OCR_ENABLED),
        configured=tencent_ocr_configured(),
        request_timeout_seconds=max(5, int(settings.TENCENT_OCR_REQUEST_TIMEOUT_SECONDS)),
        max_calls_per_batch=max(0, int(settings.TENCENT_OCR_MAX_CALLS_PER_BATCH)),
        monthly_included_quota=included_quota,
        monthly_soft_limit=soft_limit,
        monthly_calls=monthly_calls,
        remaining_included_quota=max(0, included_quota - monthly_calls) if included_quota else 0,
        remaining_before_soft_limit=max(0, soft_limit - monthly_calls) if soft_limit else 0,
        safety_reserve_calls=max(0, included_quota - soft_limit),
        fallback_to_tesseract=bool(settings.TENCENT_OCR_FALLBACK_TO_TESSERACT),
        last_call_status=last_call.status if last_call is not None else None,
        last_called_at=last_call.created_at if last_call is not None else None,
    )


def ai_settings_view(db: Session) -> AISettingsView:
    stored = _database_setting(db)
    if stored is not None:
        updater = db.get(User, stored.updated_by) if stored.updated_by else None
        return AISettingsView(
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            tts_enabled=stored.tts_enabled,
            tts_model=stored.tts_model,
            tts_voice_id=stored.tts_voice_id,
            realtime_enabled=stored.realtime_enabled,
            realtime_model=stored.realtime_model,
            realtime_voice_id=stored.realtime_voice_id,
            interview_agent_name=stored.interview_agent_name,
            interview_agent_prompt=stored.interview_agent_prompt,
            interview_greeting=stored.interview_greeting,
            image_enabled=stored.image_enabled,
            image_base_url=stored.image_base_url,
            image_model=stored.image_model,
            image_landscape_size=stored.image_landscape_size,
            image_square_size=stored.image_square_size,
            image_poll_interval_seconds=stored.image_poll_interval_seconds,
            image_timeout_seconds=stored.image_timeout_seconds,
            image_style_prompt=stored.image_style_prompt or DEFAULT_IMAGE_STYLE_PROMPT,
            image_landscape_prompt=stored.image_landscape_prompt or DEFAULT_IMAGE_LANDSCAPE_PROMPT,
            image_square_prompt=stored.image_square_prompt or DEFAULT_IMAGE_SQUARE_PROMPT,
            image_api_key_configured=bool(stored.api_key_encrypted),
            image_api_key_masked=_masked(stored.api_key_suffix or "", bool(stored.api_key_encrypted)),
            is_enabled=stored.is_enabled,
            api_key_configured=bool(stored.api_key_encrypted),
            api_key_masked=_masked(stored.api_key_suffix, bool(stored.api_key_encrypted)),
            source="database",
            updated_by=updater.username if updater else None,
            updated_at=stored.updated_at,
            last_test_status=stored.last_test_status,
            last_tested_at=stored.last_tested_at,
            usage=_usage_summary(db),
            tencent_ocr=_tencent_ocr_service_view(db),
        )
    configured = bool(settings.LLM_API_KEY)
    suffix = settings.LLM_API_KEY[-4:] if settings.LLM_API_KEY else ""
    return AISettingsView(
        provider_name=_provider_from_url(settings.LLM_BASE_URL or ""),
        base_url=settings.LLM_BASE_URL or "",
        model=settings.LLM_MODEL,
        tts_enabled=False,
        tts_model="senseaudio-tts-1.5-260319",
        tts_voice_id="female_0033_b",
        realtime_enabled=False,
        realtime_model="senseaudio-realtime-1.0",
        realtime_voice_id="f_y_0035_c",
        interview_agent_name="职护模拟面试官",
        interview_agent_prompt="你是一位专业、耐心、尊重候选人的面试官。",
        interview_greeting="你好，我是职护模拟面试官。准备好后，我们开始今天的模拟面试。",
        image_enabled=bool(settings.LLM_API_KEY and settings.LLM_BASE_URL),
        image_base_url=settings.LLM_BASE_URL or "",
        image_model=settings.IMAGE_MODEL,
        image_landscape_size=settings.IMAGE_LANDSCAPE_SIZE,
        image_square_size=settings.IMAGE_SQUARE_SIZE,
        image_poll_interval_seconds=settings.IMAGE_POLL_INTERVAL_SECONDS,
        image_timeout_seconds=settings.IMAGE_TIMEOUT_SECONDS,
        image_style_prompt=DEFAULT_IMAGE_STYLE_PROMPT,
        image_landscape_prompt=DEFAULT_IMAGE_LANDSCAPE_PROMPT,
        image_square_prompt=DEFAULT_IMAGE_SQUARE_PROMPT,
        image_api_key_configured=configured,
        image_api_key_masked=_masked(suffix, configured),
        is_enabled=configured and bool(settings.LLM_BASE_URL),
        api_key_configured=configured,
        api_key_masked=_masked(suffix, configured),
        source="environment",
        usage=_usage_summary(db),
        tencent_ocr=_tencent_ocr_service_view(db),
    )


def list_ai_invocations(
    db: Session,
    *,
    page: int,
    page_size: int,
    feature: str | None = None,
    status: str | None = None,
    modality: str | None = None,
) -> AIInvocationLogList:
    query = db.query(AIInvocationLog, User.username).outerjoin(User, AIInvocationLog.user_id == User.id)
    if feature:
        query = query.filter(AIInvocationLog.feature == feature)
    if status:
        query = query.filter(AIInvocationLog.status == status)
    if modality:
        query = query.filter(AIInvocationLog.modality == modality)
    total = query.count()
    rows = (
        query.order_by(AIInvocationLog.created_at.desc(), AIInvocationLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    features = [
        value
        for (value,) in db.query(AIInvocationLog.feature)
        .distinct()
        .order_by(AIInvocationLog.feature.asc())
        .all()
    ]
    modalities = [
        value
        for (value,) in db.query(AIInvocationLog.modality)
        .distinct()
        .order_by(AIInvocationLog.modality.asc())
        .all()
    ]
    return AIInvocationLogList(
        items=[
            AIInvocationLogItem(
                id=row.id,
                user_id=row.user_id,
                username=username,
                feature=row.feature,
                feature_label=feature_label(row.feature),
                modality=row.modality,
                provider_name=row.provider_name,
                model=row.model,
                status=row.status,
                latency_ms=row.latency_ms,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
                usage_amount=row.usage_amount,
                usage_unit=row.usage_unit,
                estimated_cost_microunits=row.estimated_cost_microunits,
                cost_currency=row.cost_currency,
                error_code=row.error_code,
                created_at=row.created_at,
            )
            for row, username in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        features=features,
        feature_options=[
            {"value": value, "label": feature_label(value)}
            for value in sorted(features, key=lambda item: (feature_label(item), item))
        ],
        modalities=modalities,
    )


def list_service_configuration_audits(
    db: Session,
    *,
    page: int,
    page_size: int,
) -> ServiceConfigurationAuditList:
    query = (
        db.query(AIConfigurationAudit, User.username)
        .outerjoin(User, AIConfigurationAudit.actor_user_id == User.id)
    )
    total = query.count()
    rows = (
        query.order_by(AIConfigurationAudit.created_at.desc(), AIConfigurationAudit.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ServiceConfigurationAuditList(
        items=[
            ServiceConfigurationAuditItem(
                id=row.id,
                actor_user_id=row.actor_user_id,
                actor_username=username,
                action=row.action,
                action_label=CONFIGURATION_ACTION_LABELS.get(row.action, "其他配置操作"),
                service_name="AI 模型服务",
                provider_name=row.provider_name,
                model=row.model,
                is_enabled=row.is_enabled,
                key_changed=row.key_changed,
                created_at=row.created_at,
            )
            for row, username in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
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
            tts_enabled=request.tts_enabled,
            tts_model=request.tts_model.strip(),
            tts_voice_id=request.tts_voice_id.strip(),
            realtime_enabled=request.realtime_enabled,
            realtime_model=request.realtime_model.strip(),
            realtime_voice_id=request.realtime_voice_id.strip(),
            interview_agent_name=request.interview_agent_name.strip(),
            interview_agent_prompt=request.interview_agent_prompt.strip(),
            interview_greeting=request.interview_greeting.strip(),
            image_enabled=request.image_enabled,
            image_base_url=base_url,
            image_model=request.image_model.strip(),
            image_landscape_size=request.image_landscape_size,
            image_square_size=request.image_square_size,
            image_poll_interval_seconds=request.image_poll_interval_seconds,
            image_timeout_seconds=request.image_timeout_seconds,
            image_style_prompt=request.image_style_prompt.strip(),
            image_landscape_prompt=request.image_landscape_prompt.strip(),
            image_square_prompt=request.image_square_prompt.strip(),
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
        stored.tts_enabled = request.tts_enabled
        stored.tts_model = request.tts_model.strip()
        stored.tts_voice_id = request.tts_voice_id.strip()
        stored.realtime_enabled = request.realtime_enabled
        stored.realtime_model = request.realtime_model.strip()
        stored.realtime_voice_id = request.realtime_voice_id.strip()
        stored.interview_agent_name = request.interview_agent_name.strip()
        stored.interview_agent_prompt = request.interview_agent_prompt.strip()
        stored.interview_greeting = request.interview_greeting.strip()
        stored.image_enabled = request.image_enabled
        stored.image_base_url = base_url
        stored.image_model = request.image_model.strip()
        stored.image_landscape_size = request.image_landscape_size
        stored.image_square_size = request.image_square_size
        stored.image_poll_interval_seconds = request.image_poll_interval_seconds
        stored.image_timeout_seconds = request.image_timeout_seconds
        stored.image_style_prompt = request.image_style_prompt.strip()
        stored.image_landscape_prompt = request.image_landscape_prompt.strip()
        stored.image_square_prompt = request.image_square_prompt.strip()
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
            tts_enabled=stored.tts_enabled,
            tts_model=stored.tts_model,
            realtime_enabled=stored.realtime_enabled,
            realtime_model=stored.realtime_model,
            image_enabled=stored.image_enabled,
            image_base_url=stored.image_base_url,
            image_model=stored.image_model,
            is_enabled=stored.is_enabled,
            key_changed=key_changed,
        )
    )
    db.commit()
    db.refresh(stored)
    return ai_settings_view(db)


def record_connection_test(db: Session, success: bool, *, actor_user_id: int) -> None:
    stored = _database_setting(db)
    if stored is None:
        return
    stored.last_test_status = "success" if success else "failed"
    stored.last_tested_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(
        AIConfigurationAudit(
            setting_id=stored.id,
            actor_user_id=actor_user_id,
            action="connection_test_success" if success else "connection_test_failed",
            provider_name=stored.provider_name,
            base_url=stored.base_url,
            model=stored.model,
            tts_enabled=stored.tts_enabled,
            tts_model=stored.tts_model,
            realtime_enabled=stored.realtime_enabled,
            realtime_model=stored.realtime_model,
            image_enabled=stored.image_enabled,
            image_base_url=stored.image_base_url,
            image_model=stored.image_model,
            is_enabled=stored.is_enabled,
            key_changed=False,
        )
    )
    db.commit()


def record_ai_invocation(
    db: Session,
    configuration: EffectiveAIConfiguration | EffectiveImageConfiguration,
    *,
    feature: str,
    status: str,
    latency_ms: int,
    usage: dict | None = None,
    error_code: str | None = None,
    user_id: int | None = None,
    modality: str = "text",
    model: str | None = None,
    usage_amount: int | None = None,
    usage_unit: str | None = None,
    estimated_cost_microunits: int | None = None,
    cost_currency: str | None = None,
) -> None:
    usage = usage or {}
    if estimated_cost_microunits is None:
        raw_microunits = usage.get("cost_microunits")
        raw_cost = usage.get("cost")
        if isinstance(raw_microunits, (int, float)) and not isinstance(raw_microunits, bool):
            estimated_cost_microunits = max(0, int(round(raw_microunits)))
        elif isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
            estimated_cost_microunits = max(0, int(round(raw_cost * 1_000_000)))
    if cost_currency is None and estimated_cost_microunits is not None and usage.get("currency"):
        cost_currency = str(usage["currency"])[:10]
    db.add(
        AIInvocationLog(
            setting_id=configuration.setting_id,
            user_id=user_id,
            feature=feature[:100],
            modality=modality[:20],
            provider_name=configuration.provider_name,
            model=(model or configuration.model)[:200],
            status=status,
            latency_ms=max(0, latency_ms),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            usage_amount=usage_amount if usage_amount is not None else usage.get("total_tokens"),
            usage_unit=usage_unit or ("tokens" if usage.get("total_tokens") is not None else None),
            estimated_cost_microunits=estimated_cost_microunits,
            cost_currency=cost_currency[:10] if cost_currency else None,
            error_code=error_code[:100] if error_code else None,
        )
    )
    db.commit()


def record_unavailable_ai_invocation(
    db: Session,
    *,
    feature: str,
    error_code: str,
    user_id: int | None = None,
    modality: str = "text",
    provider_name: str = "unconfigured",
    model: str = "unconfigured",
) -> None:
    """Audit an attempted call even when no provider configuration is usable."""

    db.add(
        AIInvocationLog(
            setting_id=None,
            user_id=user_id,
            feature=feature[:100],
            modality=modality[:20],
            provider_name=provider_name[:100],
            model=model[:200],
            status="failed",
            latency_ms=0,
            error_code=error_code[:100],
        )
    )
    db.commit()
