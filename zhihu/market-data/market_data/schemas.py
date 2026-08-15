from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


AdapterType = Literal["api", "html", "playwright"]


class SourceDefinition(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=200)
    adapter_type: AdapterType
    base_url: HttpUrl
    allowed_hosts: list[str] = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    terms_review_status: Literal["pending", "approved", "rejected"] = "pending"
    enabled: bool = False
    min_interval_seconds: int = Field(default=5, ge=1, le=3600)
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)


class SourceSnapshot(BaseModel):
    source_url: HttpUrl
    content_type: str
    content: dict[str, Any] | list[Any] | str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    http_status: int | None = None
    transport_metadata: dict[str, Any] = Field(default_factory=dict)


class RawRecordInput(BaseModel):
    external_id: str | None = None
    source_url: HttpUrl
    source_published_at: datetime | None = None
    fetched_at: datetime
    http_status: int | None = None
    content_type: str
    raw_payload: dict[str, Any] | list[Any] | None = None
    raw_text: str | None = None
    transport_metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = "raw-v1"

    @model_validator(mode="after")
    def require_content(self) -> "RawRecordInput":
        if self.raw_payload is None and self.raw_text is None:
            raise ValueError("raw_payload or raw_text is required")
        return self


class AdapterResult(BaseModel):
    adapter_type: AdapterType
    adapter_version: str
    source_code: str
    records: list[RawRecordInput]
    warnings: list[str] = Field(default_factory=list)


class CorePromotionInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    company_website_url: str | None = None
    title: str = Field(min_length=1, max_length=255)
    normalized_title: str | None = None
    location_text: str | None = None
    description: str | None = None
    requirements: str | None = None
    published_at: datetime | None = None
    raw_record_id: int = Field(gt=0)
    data_source_id: int = Field(gt=0)
    source_job_id: str | None = None
    source_url: HttpUrl
    content_hash: str = Field(min_length=64, max_length=64)
    fetched_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
