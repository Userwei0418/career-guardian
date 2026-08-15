from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


class AIProviderSetting(Base):
    __tablename__ = "ai_provider_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(100), nullable=False)
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)
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
    provider_name = Column(String(100), nullable=False)
    model = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Integer, nullable=False, default=0, server_default="0")
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
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
    is_enabled = Column(Boolean, nullable=False)
    key_changed = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
