from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class ContractCreate(BaseModel):
    case_id: Optional[int] = None
    career_event_id: Optional[int] = None
    source_action_id: Optional[int] = None
    linked_offer_id: Optional[int] = None
    source_attachment_id: Optional[int] = None
    display_name: Optional[str] = None
    document_kind: str = "labor_contract"
    status: str = "active"
    parse_status: str = "ready"
    parse_mode: Optional[str] = None
    parse_notice: Optional[str] = None
    parse_error_code: Optional[str] = None
    page_count: Optional[int] = None
    text_page_count: Optional[int] = None
    ocr_page_count: Optional[int] = None
    parse_quality: dict[str, Any] = Field(default_factory=dict)
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
    source_attachment_id: Optional[int] = None
    display_name: Optional[str] = None
    document_kind: str = "labor_contract"
    status: str = "active"
    parse_status: str = "ready"
    parse_mode: Optional[str] = None
    parse_notice: Optional[str] = None
    parse_error_code: Optional[str] = None
    page_count: Optional[int] = None
    text_page_count: Optional[int] = None
    ocr_page_count: Optional[int] = None
    parse_quality: dict[str, Any] = Field(default_factory=dict)
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
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContractPasteCreate(BaseModel):
    text: str
    display_name: Optional[str] = None
    document_kind: str = "auto"
    linked_offer_id: Optional[int] = None
    career_event_id: Optional[int] = None
    source_action_id: Optional[int] = None
    auto_review: bool = True


class ContractUpdate(BaseModel):
    display_name: Optional[str] = None
    document_kind: Optional[str] = None
    linked_offer_id: Optional[int] = None
    status: Optional[str] = None


class ContractReviewSnapshotResponse(BaseModel):
    id: int
    contract_id: int
    attachment_version_id: Optional[int] = None
    review_number: int
    extracted_fields: dict[str, Any]
    findings: List[Any]
    summary: str
    review_mode: str
    rule_version: str
    clause_segments: List[Any] = Field(default_factory=list)
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    redaction_version: Optional[str] = None
    ai_status: str = "not_requested"
    ai_input_clause_count: int = 0
    ai_batch_count: int = 0
    ai_completed_batch_count: int = 0
    redaction_report: dict[str, Any] = Field(default_factory=dict)
    coverage_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class ContractLinkedOfferSummary(BaseModel):
    id: int
    name: Optional[str] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None


class ContractDetailResponse(ContractResponse):
    latest_review: Optional[ContractReviewSnapshotResponse] = None
    review_count: int = 0
    linked_offer: Optional[ContractLinkedOfferSummary] = None
    linked_offer_contract_count: int = 0
    linked_offer_contract_index: Optional[int] = None


class ContractReviewResponse(BaseModel):
    contract_id: int
    snapshot_id: int
    review_number: int
    findings: List[Any]
    extracted_fields: dict[str, Any]
    summary: str
    important_count: int
    review_count: int
    reused: bool = False
    reviewed_at: datetime
    synced_finding_count: int = 0
    synced_action_count: int = 0


class ContractFollowUpMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=800)


class ContractFollowUpRequest(BaseModel):
    clause_id: str = Field(min_length=1, max_length=100)
    finding_code: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=2, max_length=600)
    history: List[ContractFollowUpMessage] = Field(default_factory=list, max_length=6)


class ContractFollowUpResponse(BaseModel):
    answer: str
    evidence_quote: Optional[str] = None
    limits: str
    provider_name: str
    model_name: str
    prompt_version: str
    redaction_version: str
    review_method: str


class ContractFollowUpHistoryItem(BaseModel):
    id: int
    turn_number: int
    question: str
    answer: str
    evidence_quote: Optional[str] = None
    limits: str
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    redaction_version: Optional[str] = None
    review_method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContractFollowUpHistoryResponse(BaseModel):
    contract_id: int
    review_snapshot_id: int
    clause_id: str
    finding_code: str
    items: List[ContractFollowUpHistoryItem] = Field(default_factory=list)


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
    synced_finding_count: int = 0
    synced_action_count: int = 0
    review_mode: str = "rules_only"
    model_status: str = "not_requested"
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    redaction_version: Optional[str] = None


class ChecklistItem(BaseModel):
    priority: str
    title: str
    reason: str
    script: Optional[str] = None


class ChecklistResponse(BaseModel):
    contract_id: int
    checklist: List[Any]
    synced_action_count: int = 0
