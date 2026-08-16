from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
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
    is_enabled = Column(Boolean, nullable=False)
    key_changed = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
