from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


GuardianDomain = Literal["opportunity", "decision", "rights", "income", "growth"]
GuardianState = Literal["empty", "active", "attention", "complete", "unavailable"]


class GuardianDomainState(BaseModel):
    domain: GuardianDomain
    label: str
    status: GuardianState
    title: str
    summary: str
    event_id: Optional[int] = None
    primary_action: str
    primary_action_href: str
    updated_at: Optional[datetime] = None


class GuardianStateResponse(BaseModel):
    generated_at: datetime
    domains: list[GuardianDomainState]
    primary_domain: Optional[GuardianDomain] = None


class DemoJourneyResponse(BaseModel):
    fixture_id: str
    data_mode: Literal["fixture"]
    created: bool
    event_ids: dict[str, int]
    offer_id: Optional[int] = None
    contract_id: Optional[int] = None
    payslip_id: Optional[int] = None
    message: str


class GrowthDraftRequest(BaseModel):
    job_family: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=8, ge=1, le=20)
    career_event_id: Optional[int] = None


class GrowthDraftResponse(BaseModel):
    availability: Literal["available", "insufficient_sample", "stale", "unavailable"]
    data_mode: Literal["live", "historical", "fixture", "unknown"]
    event_id: Optional[int] = None
    job_family: str
    confirmed_skills: list[str]
    market_skills: list[str]
    matched_skills: list[str]
    gaps: list[str]
    draft_actions: list[str]
    source_count: int
    note: Optional[str] = None
