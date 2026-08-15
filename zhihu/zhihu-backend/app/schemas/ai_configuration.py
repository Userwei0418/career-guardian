from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AIUsageSummary(BaseModel):
    period_days: int = 30
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_tokens: int = 0


class AISettingsView(BaseModel):
    provider_name: str
    base_url: str
    model: str
    is_enabled: bool
    api_key_configured: bool
    api_key_masked: str
    source: str
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    usage: AIUsageSummary


class AISettingsUpdate(BaseModel):
    provider_name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    api_key: Optional[str] = Field(default=None, min_length=8, max_length=1000)
    is_enabled: bool = True


class AIConnectionTestResult(BaseModel):
    success: bool
    message: str
    tested_at: datetime


class AIInvocationLogItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    feature: str
    status: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error_code: Optional[str] = None
    created_at: datetime


class AIInvocationLogList(BaseModel):
    items: list[AIInvocationLogItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    features: list[str]
