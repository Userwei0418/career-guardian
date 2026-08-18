from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


CareerImageStatus = Literal["queued", "submitted", "generating", "completed", "partial", "failed"]
VariantStatus = Literal["queued", "submitted", "generating", "completed", "failed"]


class CareerImageGenerationView(BaseModel):
    id: int
    version_number: int
    status: CareerImageStatus
    is_current: bool
    is_stale: bool
    profile_summary: dict
    style_version: str
    model: str
    landscape_size: str
    square_size: str
    landscape_status: VariantStatus
    square_status: VariantStatus
    landscape_ready: bool
    square_ready: bool
    landscape_error: Optional[str] = None
    square_error: Optional[str] = None
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class CareerImageCurrentView(BaseModel):
    current: Optional[CareerImageGenerationView] = None
    pending: Optional[CareerImageGenerationView] = None
    can_generate: bool
    source_ready: bool
    source_message: str
    poll_interval_seconds: int = Field(3, ge=1, le=30)


class CareerImageVersionList(BaseModel):
    items: list[CareerImageGenerationView] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    total_pages: int


class CareerImageAdminItem(CareerImageGenerationView):
    user_id: int
    username: str
    provider_name: str


class CareerImageAdminList(BaseModel):
    items: list[CareerImageAdminItem]
    total: int
    page: int
    page_size: int
    total_pages: int
