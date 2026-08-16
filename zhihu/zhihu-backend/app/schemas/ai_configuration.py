from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field


class AIUsageSummary(BaseModel):
    period_days: int = 30
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    usage_breakdown: list[dict[str, Union[int, str]]] = Field(default_factory=list)
    modality_counts: dict[str, int] = Field(default_factory=dict)
    top_users: list[dict[str, Union[int, str]]] = Field(default_factory=list)


class AISettingsView(BaseModel):
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
    tts_enabled: bool = True
    tts_model: str = Field(default="senseaudio-tts-1.5-260319", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    tts_voice_id: str = Field(default="female_0033_b", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    realtime_enabled: bool = False
    realtime_model: str = Field(default="senseaudio-realtime-1.0", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    realtime_voice_id: str = Field(default="f_y_0035_c", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    interview_agent_name: str = Field(default="职护模拟面试官", min_length=1, max_length=100)
    interview_agent_prompt: str = Field(default="你是一位专业、耐心、尊重候选人的面试官。", min_length=10, max_length=4000)
    interview_greeting: str = Field(default="你好，我是职护模拟面试官。准备好后，我们开始今天的模拟面试。", min_length=4, max_length=500)
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
    modality: str
    status: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usage_amount: Optional[int] = None
    usage_unit: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime


class AIInvocationLogList(BaseModel):
    items: list[AIInvocationLogItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    features: list[str]
    modalities: list[str]
