from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import func

from app.db.session import Base


class AIProviderSetting(Base):
    __tablename__ = "ai_provider_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)
    tts_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    tts_model = Column(String(200), nullable=False, default="senseaudio-tts-1.5-260319", server_default="senseaudio-tts-1.5-260319")
    tts_voice_id = Column(String(200), nullable=False, default="female_0033_b", server_default="female_0033_b")
    realtime_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    realtime_model = Column(String(200), nullable=False, default="senseaudio-realtime-1.0", server_default="senseaudio-realtime-1.0")
    realtime_voice_id = Column(String(200), nullable=False, default="f_y_0035_c", server_default="f_y_0035_c")
    interview_agent_name = Column(String(100), nullable=False, default="职护模拟面试官", server_default="职护模拟面试官")
    interview_agent_prompt = Column(Text, nullable=False, default="你是一位专业、耐心、尊重候选人的面试官。")
    interview_greeting = Column(Text, nullable=False, default="你好，我是职护模拟面试官。准备好后，我们开始今天的模拟面试。")
    image_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    image_base_url = Column(String(500), nullable=False, default="https://api.senseaudio.cn/v1", server_default="https://api.senseaudio.cn/v1")
    image_model = Column(String(200), nullable=False, default="senseaudio-image-2.0-260319", server_default="senseaudio-image-2.0-260319")
    image_landscape_size = Column(String(30), nullable=False, default="1536x864", server_default="1536x864")
    image_square_size = Column(String(30), nullable=False, default="1024x1024", server_default="1024x1024")
    image_poll_interval_seconds = Column(Integer, nullable=False, default=3, server_default="3")
    image_timeout_seconds = Column(Integer, nullable=False, default=240, server_default="240")
    image_api_key_encrypted = Column(Text, nullable=True)
    image_api_key_suffix = Column(String(8), nullable=True)
    api_key_encrypted = Column(Text, nullable=False)
    api_key_suffix = Column(String(8), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_test_status = Column(String(20), nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIInvocationLog(Base):
    __tablename__ = "ai_invocation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_id = Column(Integer, ForeignKey("ai_provider_settings.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    feature = Column(String(100), nullable=False)
    modality = Column(String(20), nullable=False, default="text", server_default="text")
    provider_name = Column(String(100), nullable=False)
    model = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0, server_default="0")
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    usage_amount = Column(Integer, nullable=True)
    usage_unit = Column(String(20), nullable=True)
    estimated_cost_microunits = Column(Integer, nullable=True)
    cost_currency = Column(String(10), nullable=True)
    error_code = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class AIConfigurationAudit(Base):
    __tablename__ = "ai_configuration_audits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_id = Column(Integer, ForeignKey("ai_provider_settings.id"), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)
    provider_name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)
    tts_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    tts_model = Column(String(200), nullable=False, default="senseaudio-tts-1.5-260319", server_default="senseaudio-tts-1.5-260319")
    realtime_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    realtime_model = Column(String(200), nullable=False, default="senseaudio-realtime-1.0", server_default="senseaudio-realtime-1.0")
    image_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    image_base_url = Column(String(500), nullable=False, default="https://api.senseaudio.cn/v1", server_default="https://api.senseaudio.cn/v1")
    image_model = Column(String(200), nullable=False, default="senseaudio-image-2.0-260319", server_default="senseaudio-image-2.0-260319")
    is_enabled = Column(Boolean, nullable=False)
    key_changed = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CareerImageGeneration(Base):
    __tablename__ = "career_image_generations"
    __table_args__ = (
        UniqueConstraint("user_id", "version_number", name="uq_career_image_user_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    setting_id = Column(Integer, ForeignKey("ai_provider_settings.id", ondelete="SET NULL"), nullable=True)
    version_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="queued", server_default="queued", index=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    is_stale = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    profile_summary = Column(JSON, nullable=False, default=dict)
    source_fingerprint = Column(String(64), nullable=False, index=True)
    style_version = Column(String(60), nullable=False, default="career-journey-editorial-v1")
    seed = Column(Integer, nullable=False)
    provider_name = Column(String(100), nullable=False)
    model = Column(String(200), nullable=False)
    landscape_size = Column(String(30), nullable=False)
    square_size = Column(String(30), nullable=False)
    landscape_task_id = Column(String(200), nullable=True, index=True)
    square_task_id = Column(String(200), nullable=True, index=True)
    landscape_status = Column(String(20), nullable=False, default="queued", server_default="queued")
    square_status = Column(String(20), nullable=False, default="queued", server_default="queued")
    landscape_image = Column(mysql.MEDIUMBLOB(), nullable=True)
    square_image = Column(mysql.MEDIUMBLOB(), nullable=True)
    landscape_content_type = Column(String(100), nullable=True)
    square_content_type = Column(String(100), nullable=True)
    landscape_prompt_hash = Column(String(64), nullable=False)
    square_prompt_hash = Column(String(64), nullable=False)
    landscape_error = Column(String(500), nullable=True)
    square_error = Column(String(500), nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
