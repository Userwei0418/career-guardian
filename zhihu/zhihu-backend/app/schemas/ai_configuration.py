from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field, model_validator

from app.models.ai_configuration import (
    DEFAULT_IMAGE_LANDSCAPE_PROMPT,
    DEFAULT_IMAGE_SQUARE_PROMPT,
    DEFAULT_IMAGE_STYLE_PROMPT,
)


IMAGE_MODELS = {
    "senseaudio-image-2.0-260319": {
        "1024x1024", "1536x864", "864x1536", "2016x864", "864x2016",
        "2048x1024", "1024x2048", "2048x1152", "1152x2048",
        "2688x1152", "1152x2688", "2688x1344", "1344x2688",
        "3840x1648", "1648x3840", "3840x1920", "1920x3840",
        "3840x2160", "2160x3840",
    },
    "senseaudio-image-1.0-260319": {
        "1664x928", "928x1664", "1584x1056", "1056x1584",
        "1472x1140", "1140x1472", "1328x1328",
    },
    "doubao-seedream-5-0-260128": {
        "2304x1728", "1728x2304", "2496x1664", "1664x2496",
        "2048x2048", "3136x1344", "2848x1600", "1600x2848",
        "3456x2592", "2592x3456", "2496x3744", "3744x2496",
        "4096x2304", "2304x4096", "3072x3072", "4704x2016",
    },
    "sensenova-u1-fast": {
        "1664x2496", "2496x1664", "1760x2368", "2368x1760",
        "1824x2272", "2272x1824", "2048x2048", "2752x1536",
        "1536x2752", "3072x1376", "1344x3136",
    },
}


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
    image_enabled: bool
    image_base_url: str
    image_model: str
    image_landscape_size: str
    image_square_size: str
    image_poll_interval_seconds: int
    image_timeout_seconds: int
    image_style_prompt: str
    image_landscape_prompt: str
    image_square_prompt: str
    image_api_key_configured: bool
    image_api_key_masked: str
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
    image_enabled: bool = False
    image_base_url: str = Field(default="https://api.senseaudio.cn/v1", min_length=8, max_length=500)
    image_model: str = Field(default="senseaudio-image-2.0-260319", min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:/-]+$")
    image_landscape_size: str = Field(default="1536x864", min_length=7, max_length=30, pattern=r"^[0-9]+x[0-9]+$")
    image_square_size: str = Field(default="1024x1024", min_length=7, max_length=30, pattern=r"^[0-9]+x[0-9]+$")
    image_poll_interval_seconds: int = Field(default=3, ge=2, le=30)
    image_timeout_seconds: int = Field(default=900, ge=60, le=1800)
    image_style_prompt: str = Field(default=DEFAULT_IMAGE_STYLE_PROMPT, min_length=10, max_length=3000)
    image_landscape_prompt: str = Field(default=DEFAULT_IMAGE_LANDSCAPE_PROMPT, min_length=10, max_length=2000)
    image_square_prompt: str = Field(default=DEFAULT_IMAGE_SQUARE_PROMPT, min_length=10, max_length=2000)
    api_key: Optional[str] = Field(default=None, min_length=8, max_length=1000)
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_image_model_sizes(self):
        sizes = IMAGE_MODELS.get(self.image_model)
        if sizes is None:
            raise ValueError("图片模型不在当前支持清单中")
        if self.image_landscape_size not in sizes or self.image_square_size not in sizes:
            raise ValueError("图片尺寸与所选模型不匹配")
        return self


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
    provider_name: str
    model: str
    status: str
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usage_amount: Optional[int] = None
    usage_unit: Optional[str] = None
    estimated_cost_microunits: Optional[int] = None
    cost_currency: Optional[str] = None
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
