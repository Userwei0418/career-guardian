from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "职护 API"
    APP_VERSION: str = "0.2.0"
    APP_ENV: str = "development"
    DEBUG: bool = False

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72

    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4o-mini"
    AI_CONFIG_ENCRYPTION_KEY: Optional[str] = None
    AI_ALLOWED_BASE_HOSTS: str = "api.senseaudio.cn,dashscope.aliyuncs.com"
    IMAGE_API_BASE_URL: str = "https://api.senseaudio.cn/v1"
    IMAGE_API_KEY: Optional[str] = None
    IMAGE_MODEL: str = "senseaudio-image-2.0-260319"
    IMAGE_LANDSCAPE_SIZE: str = "1536x864"
    IMAGE_SQUARE_SIZE: str = "1024x1024"
    IMAGE_POLL_INTERVAL_SECONDS: int = 3
    IMAGE_TIMEOUT_SECONDS: int = 240
    IMAGE_MAX_DOWNLOAD_BYTES: int = 16 * 1024 * 1024

    MARKET_API_URL: str = "http://127.0.0.1:8100"
    MARKET_API_TIMEOUT_SECONDS: float = 8.0
    MARKET_INTERNAL_TOKEN: Optional[str] = None
    MARKET_STRATEGY_AUTO_REPAIR_ENABLED: bool = True
    MARKET_STRATEGY_AUTO_REPAIR_INTERVAL_SECONDS: float = 8.0
    MARKET_STRATEGY_AUTO_REPAIR_LEASE_SECONDS: int = 180
    MARKET_STRATEGY_AUTO_REPAIR_MAX_ATTEMPTS: int = 3
    MARKET_STRATEGY_AUTO_REPAIR_RETRY_DELAY_SECONDS: int = 30

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 20 * 1024 * 1024

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_runtime_security(self):
        environment = self.APP_ENV.strip().lower()
        if environment in {"staging", "production"}:
            if self.DEBUG:
                raise ValueError("staging/production 环境不能启用 DEBUG")
            if len(self.JWT_SECRET) < 32 or self.JWT_SECRET == "zhihu-dev-secret-change-in-production":
                raise ValueError("staging/production 环境必须配置独立的强 JWT_SECRET")
        return self


settings = Settings()
