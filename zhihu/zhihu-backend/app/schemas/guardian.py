from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


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
