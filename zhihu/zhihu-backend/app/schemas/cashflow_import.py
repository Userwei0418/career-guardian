from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.cashflow_validation import is_supported_financial_date


CashflowDirection = Literal["income", "expense", "transfer"]
CashflowNature = Literal["fixed", "flexible", "one_off", "reimbursable", "other"]
ImportOrigin = Literal["file", "ocr", "ai_text"]
ImportSourceHint = Literal["auto", "wechat", "alipay", "bank", "generic"]
ImportBatchStatus = Literal[
    "created",
    "processing",
    "mapping_required",
    "review_ready",
    "confirming",
    "completed",
    "failed",
    "cancelled",
]
ImportCandidateStatus = Literal[
    "ready",
    "needs_review",
    "exact_duplicate",
    "possible_duplicate",
    "invalid",
    "excluded",
    "confirmed",
]
ImportCandidateAction = Literal[
    "save",
    "exclude",
    "restore",
    "accept_review",
    "record_duplicate",
    "merge_evidence",
]

Money = Annotated[
    Decimal,
    Field(gt=Decimal("0"), le=Decimal("999999999999.99"), decimal_places=2),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ImportIssue(BaseModel):
    field: Optional[str] = None
    code: str
    message: str


class CashflowRecognitionSliceProgress(BaseModel):
    sequence_number: int = Field(ge=1)
    status: Literal["pending", "processing", "completed", "failed"]
    source_image_sequence: int = Field(default=1, ge=1)
    source_image_slice_sequence: int = Field(default=1, ge=1)
    source_image_slice_total: int = Field(default=1, ge=1)
    source_pixel_top: Optional[int] = None
    source_pixel_bottom: Optional[int] = None
    ocr_character_count: Optional[int] = Field(default=None, ge=0)
    ocr_processed_character_count: Optional[int] = Field(default=None, ge=0)
    ocr_chunk_count: Optional[int] = Field(default=None, ge=1)
    ocr_text_fully_processed: Optional[bool] = None
    program_candidate_count: Optional[int] = Field(default=None, ge=0)
    program_fallback_candidate_count: Optional[int] = Field(default=None, ge=0)
    ai_candidate_count: Optional[int] = Field(default=None, ge=0)
    ai_rejected_candidate_count: Optional[int] = Field(default=None, ge=0)
    ai_chunk_count: Optional[int] = Field(default=None, ge=0)
    expected_transaction_rows: Optional[int] = Field(default=None, ge=2)
    recognized_candidate_count: Optional[int] = Field(default=None, ge=0)
    missing_transaction_rows: Optional[int] = Field(default=None, ge=0)
    row_coverage_status: Literal[
        "unknown",
        "pending",
        "complete",
        "partial",
        "over_detected",
        "count_mismatch",
    ] = "unknown"
    row_detection_version: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class CashflowDuplicateImageProgress(BaseModel):
    image_sequence: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    slice_count: int = Field(default=0, ge=0)
    duplicate_of_image_sequence: int = Field(ge=1)


class CashflowRecognitionProgress(BaseModel):
    mode: Literal["segmented_image", "image_sequence"]
    submitted_images: int = Field(default=1, ge=0)
    unique_images: int = Field(default=1, ge=0)
    duplicate_images: list[CashflowDuplicateImageProgress] = Field(default_factory=list)
    total_slices: int = Field(ge=0)
    pending_slices: int = Field(ge=0)
    processing_slices: int = Field(ge=0)
    completed_slices: int = Field(ge=0)
    failed_slices: int = Field(ge=0)
    slices: list[CashflowRecognitionSliceProgress] = Field(default_factory=list)


class FinancialImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin_type: ImportOrigin
    source_type: str
    attachment_version_id: Optional[int] = None
    original_file_retained: bool = False
    resume_source: Literal[
        "legacy_original",
        "recognition_artifacts",
        "structured_candidates",
    ]
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    parser_version: str
    status: ImportBatchStatus
    column_mapping: dict[str, str] = Field(default_factory=dict)
    headers: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, str]] = Field(default_factory=list)
    recognition_progress: Optional[CashflowRecognitionProgress] = None
    supersedes_batch_id: Optional[int] = Field(default=None, ge=1)
    total_count: int
    ready_count: int
    review_count: int
    duplicate_count: int
    exact_duplicate_count: int
    possible_duplicate_count: int
    invalid_count: int
    excluded_count: int
    confirmed_count: int
    version: int
    parsed_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    reused: bool = False


class FinancialImportBatchListResponse(BaseModel):
    items: list[FinancialImportBatchResponse]
    total: int


class FinancialImportBatchDeleteResponse(BaseModel):
    """Result of retiring one recognition batch without touching formal facts."""

    batch_id: int = Field(ge=1)
    deleted_candidate_count: int = Field(ge=0)
    deleted_artifact_count: int = Field(ge=0)
    deleted_attachment_count: int = Field(ge=0)
    preserved_transaction_count: int = Field(ge=0)
    cleanup_job_ids: list[int] = Field(default_factory=list)
    cleanup_completed_ids: list[int] = Field(default_factory=list)
    cleanup_failed_ids: list[int] = Field(default_factory=list)
    physical_cleanup_status: Literal[
        "not_needed",
        "completed",
        "retry_pending",
    ]


CashflowImportCapabilityState = Literal["available", "configured", "unavailable"]


class CashflowImportCapability(BaseModel):
    enabled: bool
    state: CashflowImportCapabilityState
    message: str


class CashflowImportCapabilitiesResponse(BaseModel):
    file: CashflowImportCapability
    text: CashflowImportCapability
    ocr: CashflowImportCapability


class FinancialTransactionCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    row_number: int
    direction: Optional[CashflowDirection] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    transaction_date: Optional[date] = None
    occurred_at: Optional[datetime] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    nature: Optional[CashflowNature] = None
    status: ImportCandidateStatus
    duplicate_transaction_id: Optional[int] = None
    duplicate_matches: list["FinancialImportDuplicateMatch"] = Field(default_factory=list)
    duplicate_candidate_matches: list["FinancialImportCandidateDuplicateMatch"] = Field(default_factory=list)
    transaction_id: Optional[int] = None
    original_payload: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
    version: int
    confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FinancialImportDuplicateMatch(BaseModel):
    transaction_id: int = Field(ge=1)
    economic_fact_id: Optional[int] = Field(default=None, ge=1)
    direction: CashflowDirection
    amount: Decimal
    available_amount: Decimal
    currency: str
    transaction_date: date
    merchant: Optional[str] = None
    description: Optional[str] = None
    source_type: str
    can_merge_as_evidence: bool
    merge_block_reason: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    ai_status: Literal["not_requested", "completed", "unavailable"] = "not_requested"
    ai_assessment: Optional[Literal["likely", "unlikely", "uncertain"]] = None
    ai_reason: Optional[str] = None


class FinancialImportCandidateDuplicateMatch(BaseModel):
    candidate_id: int = Field(ge=1)
    batch_id: int = Field(ge=1)
    row_number: int = Field(ge=1)
    direction: Optional[CashflowDirection] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    transaction_date: Optional[date] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    source_type: str
    status: ImportCandidateStatus
    reasons: list[str] = Field(default_factory=list)
    ai_status: Literal["not_requested", "completed", "unavailable"] = "not_requested"
    ai_assessment: Optional[Literal["likely", "unlikely", "uncertain"]] = None
    ai_reason: Optional[str] = None


class FinancialImportDuplicateAIReviewResponse(BaseModel):
    batch_id: int = Field(ge=1)
    eligible_candidate_count: int = Field(ge=0)
    reviewed_candidate_count: int = Field(ge=0)
    completed_assessment_count: int = Field(ge=0)
    unavailable_candidate_count: int = Field(ge=0)
    remaining_candidate_count: int = Field(ge=0)


class FinancialImportCandidatePage(BaseModel):
    items: list[FinancialTransactionCandidateResponse]
    total: int
    offset: int
    limit: int


class FinancialImportMappingUpdate(BaseModel):
    expected_batch_version: int = Field(ge=1)
    mapping: dict[str, ShortText]

    @field_validator("mapping")
    @classmethod
    def validate_mapping_keys(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {
            "transaction_date",
            "direction",
            "amount",
            "income_amount",
            "expense_amount",
            "merchant",
            "description",
            "category",
            "nature",
            "external_id",
            "source_account",
            "currency",
            "transaction_type",
            "source_status",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"不支持的映射字段：{unknown[0]}")
        if "transaction_date" not in value:
            raise ValueError("必须映射交易日期")
        if not ({"amount", "income_amount", "expense_amount"} & set(value)):
            raise ValueError("必须映射金额")
        if "direction" not in value and not {"income_amount", "expense_amount"}.issubset(value):
            raise ValueError("必须映射收支方向，或同时映射收入金额与支出金额")
        if len(set(value.values())) != len(value.values()):
            raise ValueError("同一源列不能映射到多个字段")
        return value


class FinancialImportCandidateUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    action: ImportCandidateAction = "save"
    direction: Optional[CashflowDirection] = None
    amount: Optional[Money] = None
    transaction_date: Optional[date] = None
    category_id: Optional[int] = Field(default=None, ge=1)
    merchant: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    nature: Optional[CashflowNature] = None
    duplicate_override_reason: Optional[str] = Field(default=None, min_length=2, max_length=200)
    target_transaction_id: Optional[int] = Field(default=None, ge=1)
    allocated_amount: Optional[Money] = None
    evidence_merge_reason: Optional[str] = Field(default=None, min_length=2, max_length=200)

    @field_validator(
        "merchant",
        "description",
        "duplicate_override_reason",
        "evidence_merge_reason",
    )
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("transaction_date")
    @classmethod
    def validate_transaction_date(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and not is_supported_financial_date(value):
            raise ValueError("交易日期超出支持范围")
        return value

    @model_validator(mode="after")
    def require_change_for_save(self):
        editable = {
            "direction",
            "amount",
            "transaction_date",
            "category_id",
            "merchant",
            "description",
            "nature",
        }
        if self.action == "save" and not (self.model_fields_set & editable):
            raise ValueError("请至少修改一个候选字段")
        if self.action == "record_duplicate" and not self.duplicate_override_reason:
            raise ValueError("请说明为什么仍要记录这笔精确重复交易")
        if self.action == "merge_evidence":
            if self.target_transaction_id is None:
                raise ValueError("请选择要并入的已有流水")
            if self.allocated_amount is None:
                raise ValueError("请输入作为同一事实证据的金额")
            if not self.evidence_merge_reason:
                raise ValueError("请说明为什么这是同一经济事实的另一份证据")
        return self


class FinancialImportConfirmationItem(BaseModel):
    candidate_id: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class FinancialImportConfirmRequest(BaseModel):
    expected_batch_version: int = Field(ge=1)
    # A file may contain 5,000 rows, but formal writes are deliberately
    # committed in bounded chunks so one request cannot hold the per-user ledger
    # lock through thousands of savepoints. The frontend chains these chunks
    # using the batch version returned by the previous response.
    candidates: list[FinancialImportConfirmationItem] = Field(min_length=1, max_length=500)

    @field_validator("candidates")
    @classmethod
    def reject_duplicate_candidate_ids(
        cls,
        value: list[FinancialImportConfirmationItem],
    ) -> list[FinancialImportConfirmationItem]:
        ids = [item.candidate_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("确认列表中存在重复候选")
        return value


class FinancialImportConfirmReport(BaseModel):
    batch: FinancialImportBatchResponse
    confirmed_candidate_ids: list[int] = Field(default_factory=list)
    transaction_ids: list[int] = Field(default_factory=list)
    duplicate_candidate_ids: list[int] = Field(default_factory=list)
    independent_candidate_ids: list[int] = Field(default_factory=list)
    corroborating_candidate_ids: list[int] = Field(default_factory=list)
    corroborating_fact_ids: list[int] = Field(default_factory=list)
    confirmed_count: int
    duplicate_count: int
    independent_count: int = 0
    corroborating_count: int = 0


class CashflowTextCandidateCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("请输入要识别的收支描述")
        return normalized
