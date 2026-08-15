from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ContractCreate(BaseModel):
    case_id: Optional[int] = None
    career_event_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    employer: Optional[str] = None
    contract_term: Optional[str] = None
    probation: Optional[str] = None
    salary_terms: Optional[str] = None
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    non_compete: Optional[str] = None
    penalty_terms: Optional[str] = None
    termination_terms: Optional[str] = None
    raw_text: Optional[str] = None


class ContractResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    career_event_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    employer: Optional[str] = None
    contract_term: Optional[str] = None
    probation: Optional[str] = None
    salary_terms: Optional[str] = None
    work_location: Optional[str] = None
    working_hours: Optional[str] = None
    non_compete: Optional[str] = None
    penalty_terms: Optional[str] = None
    termination_terms: Optional[str] = None
    raw_text: Optional[str] = None

    class Config:
        from_attributes = True


class ContractFinding(BaseModel):
    rule: str
    severity: str
    title: str
    explanation: str
    suggestion: str


class ContractReviewResponse(BaseModel):
    contract_id: int
    findings: List[Any]
    score: int
    total_risks: int
    high_risks: int


class ConsistencyDiff(BaseModel):
    field: str
    offer_value: Optional[str] = None
    contract_value: Optional[str] = None
    status: str
    note: Optional[str] = None


class ConsistencyResponse(BaseModel):
    contract_id: int
    offer_id: int
    diffs: List[Any]
    consistent_count: int
    issue_count: int


class ChecklistItem(BaseModel):
    priority: str
    title: str
    reason: str
    script: Optional[str] = None


class ChecklistResponse(BaseModel):
    contract_id: int
    checklist: List[Any]
