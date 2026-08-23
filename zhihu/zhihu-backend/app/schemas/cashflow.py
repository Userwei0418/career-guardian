from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.cashflow_validation import is_supported_financial_date


Direction = Literal["income", "expense", "transfer"]
TransactionStatus = Literal["pending", "confirmed", "excluded"]
TransactionNature = Literal["fixed", "flexible", "one_off", "reimbursable", "other"]

# The persistence column is DECIMAL(14, 2): at most 12 integer digits and
# exactly two stored fractional places.  Validate that contract before values
# reach MySQL so the database never has to round or reject an amount for us.
MAX_TRANSACTION_AMOUNT = Decimal("999999999999.99")
TransactionAmount = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        le=MAX_TRANSACTION_AMOUNT,
        max_digits=14,
        decimal_places=2,
    ),
]
MoneyOutput = Annotated[Decimal, Field(decimal_places=2)]


class FinancialCategoryCreate(BaseModel):
    direction: Literal["income", "expense"]
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class FinancialCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: Literal["income", "expense"]
    name: str
    is_system: bool
    is_active: bool
    sort_order: int


class FinancialTransactionCreate(BaseModel):
    direction: Direction
    amount: TransactionAmount
    transaction_date: date
    category_id: Optional[int] = None
    merchant: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    nature: Optional[TransactionNature] = None
    status: TransactionStatus = "confirmed"

    @field_validator("merchant", "description")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("transaction_date")
    @classmethod
    def validate_transaction_date(cls, value: date) -> date:
        if not is_supported_financial_date(value):
            raise ValueError("交易日期超出支持范围")
        return value

    @model_validator(mode="after")
    def validate_direction_fields(self):
        if self.direction == "transfer" and self.category_id is not None:
            raise ValueError("转账不应设置收支分类")
        return self


class FinancialTransactionUpdate(BaseModel):
    direction: Optional[Direction] = None
    amount: Optional[TransactionAmount] = None
    transaction_date: Optional[date] = None
    category_id: Optional[int] = None
    merchant: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    nature: Optional[TransactionNature] = None
    status: Optional[TransactionStatus] = None
    excluded_reason: Optional[str] = Field(default=None, max_length=255)
    revision_reason: Optional[str] = Field(default=None, max_length=255)

    @field_validator("merchant", "description", "excluded_reason", "revision_reason")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
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
    def reject_null_required_fields(self):
        for field_name in ("direction", "amount", "transaction_date", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能设为空")
        return self


class FinancialTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: Direction
    amount: MoneyOutput
    currency: str
    transaction_date: date
    occurred_at: Optional[datetime] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    nature: Optional[TransactionNature] = None
    source_type: str
    source_ref: Optional[str] = None
    status: TransactionStatus
    confirmed_at: Optional[datetime] = None
    excluded_reason: Optional[str] = None
    economic_fact_id: Optional[int] = None
    economic_fact_role: Optional[Literal["primary", "corroborating", "split", "decomposed"]] = None
    counts_as_cashflow: bool = True
    allocated_to_other_facts: MoneyOutput = Decimal("0.00")
    effective_cashflow_amount: Optional[MoneyOutput] = None
    split_component_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class FinancialTransactionPage(BaseModel):
    items: list[FinancialTransactionResponse]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)


class FinancialTransactionRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: int
    transaction_revision: int = Field(ge=1)
    ledger_revision: int = Field(ge=1)
    operation: Literal["create", "update", "delete", "restore"]
    before_snapshot: Optional[dict] = None
    after_snapshot: Optional[dict] = None
    reason: Optional[str] = None
    created_at: datetime


class FinancialLedgerRevisionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_number: int = Field(ge=1)
    event_type: str
    entity_type: str
    entity_id: Optional[int] = None
    summary: str
    created_at: datetime


class DeletedFinancialTransaction(BaseModel):
    id: int
    direction: Direction
    amount: MoneyOutput
    currency: str
    transaction_date: date
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    nature: Optional[TransactionNature] = None
    source_type: str
    deleted_at: datetime


class DeletedFinancialTransactionPage(BaseModel):
    items: list[DeletedFinancialTransaction]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class CategoryAmount(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    amount: MoneyOutput
    count: int


class ExpenseNatureAmount(BaseModel):
    nature: TransactionNature
    amount: MoneyOutput
    count: int


class MerchantAmount(BaseModel):
    merchant_name: str
    amount: MoneyOutput
    count: int


class DailyAmount(BaseModel):
    date: date
    income: MoneyOutput
    expense: MoneyOutput


class CashflowSummaryResponse(BaseModel):
    month: str
    state: Literal["not_started", "recording", "needs_confirmation"]
    income: MoneyOutput
    expense: MoneyOutput
    net: MoneyOutput
    transfer_amount: MoneyOutput
    confirmed_count: int
    pending_count: int
    excluded_count: int
    income_categories: list[CategoryAmount]
    expense_categories: list[CategoryAmount]
    expense_natures: list[ExpenseNatureAmount]
    expense_merchants: list[MerchantAmount]
    daily: list[DailyAmount]


class FinancialBudgetUpsert(BaseModel):
    month: str
    category_id: Optional[int] = Field(default=None, gt=0)
    amount: TransactionAmount
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("month")
    @classmethod
    def validate_budget_month(cls, value: str) -> str:
        try:
            year_text, month_text = value.split("-", 1)
            month_start = date(int(year_text), int(month_text), 1)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("月份必须使用 YYYY-MM 格式") from None
        if value != f"{month_start.year:04d}-{month_start.month:02d}" or not is_supported_financial_date(month_start):
            raise ValueError("月份超出支持范围或格式不正确")
        return value


class FinancialBudgetResponse(BaseModel):
    id: int
    month: str
    scope: Literal["total", "category"]
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    amount: MoneyOutput
    spent_amount: MoneyOutput
    remaining_amount: MoneyOutput
    utilization_percent: float = Field(ge=0)
    execution_state: Literal["on_track", "near_limit", "over_budget"]
    status: Literal["active", "reversed"]
    version: int = Field(ge=1)
    confirmed_at: datetime
    reversed_at: Optional[datetime] = None


class CashflowMonthlyReportHighlight(BaseModel):
    level: Literal["positive", "info", "warning", "attention"]
    title: str
    detail: str


class CashflowMonthlyReportResponse(BaseModel):
    month: str
    ledger_revision: int = Field(ge=0)
    readiness: Literal["empty", "needs_confirmation", "partial", "ready"]
    income: MoneyOutput
    expense: MoneyOutput
    net: MoneyOutput
    savings_rate_percent: Optional[float] = None
    confirmed_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    top_expense_category: Optional[CategoryAmount] = None
    top_expense_merchant: Optional[MerchantAmount] = None
    subscription_count: int = Field(ge=0)
    fixed_expense_count: int = Field(ge=0)
    budget_alerts: list[FinancialBudgetResponse] = Field(default_factory=list)
    highlights: list[CashflowMonthlyReportHighlight] = Field(default_factory=list)
    generated_at: datetime


class FinancialMonthCloseCreate(BaseModel):
    month: str
    expected_ledger_revision: int = Field(ge=0)

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        try:
            year_text, month_text = value.split("-", 1)
            month_start = date(int(year_text), int(month_text), 1)
        except (TypeError, ValueError):
            raise ValueError("月份必须使用 YYYY-MM 格式") from None
        if value != f"{month_start.year:04d}-{month_start.month:02d}" or not is_supported_financial_date(month_start):
            raise ValueError("月份超出支持范围或格式不正确")
        return value


class FinancialMonthCloseResponse(BaseModel):
    id: int
    month: str
    version: int = Field(ge=1)
    ledger_revision: int = Field(ge=0)
    report_snapshot: CashflowMonthlyReportResponse
    pending_candidate_count: int = Field(ge=0)
    status: Literal["closed", "reopened"]
    is_current: bool
    is_stale: bool
    closed_at: datetime
    reopened_at: Optional[datetime] = None


class RecurringExpenseMonthAmount(BaseModel):
    month: str
    amount: MoneyOutput
    count: int = Field(ge=1)


RecurringExpenseDecisionType = Literal["subscription", "fixed_expense", "not_recurring"]


class RecurringExpenseDecisionUpsert(BaseModel):
    merchant_name: str = Field(min_length=1, max_length=120)
    decision_type: RecurringExpenseDecisionType
    note: Optional[str] = Field(default=None, max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("merchant_name", "note")
    @classmethod
    def normalize_recurring_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class RecurringExpenseDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_fingerprint: str
    merchant_name: str
    decision_type: RecurringExpenseDecisionType
    status: Literal["active", "reversed"]
    note: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)
    version: int = Field(ge=1)
    confirmed_at: datetime
    reversed_at: Optional[datetime] = None


class RecurringExpenseInsight(BaseModel):
    merchant_fingerprint: str
    merchant_name: str
    pattern_type: Literal["stable_monthly", "recurring_variable"]
    confidence_tier: Literal["high", "medium", "low"]
    months_seen: int = Field(ge=2)
    occurrence_count: int = Field(ge=2)
    average_amount: MoneyOutput
    minimum_amount: MoneyOutput
    maximum_amount: MoneyOutput
    variation_percent: float = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)
    monthly: list[RecurringExpenseMonthAmount] = Field(default_factory=list)
    user_decision: Optional[RecurringExpenseDecisionResponse] = None


class RecurringExpenseResponse(BaseModel):
    start_month: str
    end_month: str
    months_analyzed: int = Field(ge=2, le=12)
    items: list[RecurringExpenseInsight] = Field(default_factory=list)


EconomicRelationType = Literal["refunds", "reimburses", "transfer_pair"]


class EconomicFactResponse(BaseModel):
    id: int
    primary_transaction_id: Optional[int] = None
    fact_type: str
    title: str
    occurred_date: date
    amount: MoneyOutput
    currency: str
    category_id: Optional[int] = None
    nature: Optional[TransactionNature] = None
    description: Optional[str] = None
    status: Literal["confirmed", "reversed", "superseded"]


class EconomicFactRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fact_id: int
    fact_revision: int = Field(ge=1)
    ledger_revision: int = Field(ge=1)
    operation: str
    before_snapshot: Optional[dict[str, object]] = None
    after_snapshot: dict[str, object]
    reason: Optional[str] = None
    actor_user_id: int
    created_at: datetime


class EconomicFactMember(BaseModel):
    transaction_id: int
    role: Literal["primary", "corroborating", "split_component"]
    allocated_amount: MoneyOutput
    direction: Direction
    amount: MoneyOutput
    transaction_date: date
    title: str
    source_type: str
    counts_as_cashflow: bool


class EconomicFactPayslipEvidence(BaseModel):
    payslip_id: int
    pay_month: Optional[str] = None
    employer_name: Optional[str] = None
    gross_salary: Optional[MoneyOutput] = None
    net_salary: Optional[MoneyOutput] = None
    allocated_amount: MoneyOutput
    transaction_ids: list[int] = Field(default_factory=list)
    role: Literal["entitlement"] = "entitlement"
    counts_as_cashflow: Literal[False] = False


class EconomicFactMergeSuggestion(BaseModel):
    primary_transaction_id: int
    evidence_transaction_id: int
    primary_fact_id: int
    evidence_fact_id: int
    primary_amount: MoneyOutput
    evidence_amount: MoneyOutput
    primary_date: date
    evidence_date: date
    primary_title: str
    evidence_title: str
    primary_source_type: str
    evidence_source_type: str
    allocated_amount: MoneyOutput
    score: int = Field(ge=0, le=100)
    confidence_tier: Literal["high", "medium", "low"]
    reasons: list[str] = Field(default_factory=list)
    ai_status: Literal["not_needed", "completed", "unavailable"] = "not_needed"
    ai_assessment: Optional[Literal["likely", "unlikely", "uncertain"]] = None
    ai_reason: Optional[str] = None


class EconomicRelationSuggestion(BaseModel):
    source_transaction_id: int
    target_transaction_id: int
    source_fact_id: int
    target_fact_id: int
    source_direction: Direction
    target_direction: Direction
    source_amount: MoneyOutput
    target_amount: MoneyOutput
    source_date: date
    target_date: date
    source_title: str
    target_title: str
    relation_type: EconomicRelationType
    allocated_amount: MoneyOutput
    score: int = Field(ge=0, le=100)
    confidence_tier: Literal["high", "medium", "low"]
    reasons: list[str] = Field(default_factory=list)
    ai_status: Literal["not_needed", "completed", "unavailable"] = "not_needed"
    ai_assessment: Optional[Literal["likely", "unlikely", "uncertain"]] = None
    ai_reason: Optional[str] = None


class EconomicFactSplitComponentResponse(BaseModel):
    fact_id: int
    source_transaction_id: int
    amount: MoneyOutput
    category_id: int
    category_name: str
    title: str
    description: Optional[str] = None
    nature: Optional[TransactionNature] = None
    status: Literal["confirmed"] = "confirmed"


class EconomicRelationSuggestionResponse(BaseModel):
    transaction: FinancialTransactionResponse
    fact: EconomicFactResponse
    fact_members: list[EconomicFactMember] = Field(default_factory=list)
    payslip_evidence: list[EconomicFactPayslipEvidence] = Field(default_factory=list)
    split_components: list[EconomicFactSplitComponentResponse] = Field(default_factory=list)
    merge_suggestions: list[EconomicFactMergeSuggestion] = Field(default_factory=list)
    suggestions: list[EconomicRelationSuggestion] = Field(default_factory=list)


class EconomicFactMergeConfirmRequest(BaseModel):
    primary_transaction_id: int
    evidence_transaction_id: int
    allocated_amount: TransactionAmount
    reasons: list[str] = Field(default_factory=list, max_length=12)
    detection_method: Literal["program", "ai", "manual"] = "manual"


class EconomicFactMergeBatchItem(BaseModel):
    evidence_transaction_id: int
    allocated_amount: TransactionAmount
    reasons: list[str] = Field(default_factory=list, max_length=12)
    detection_method: Literal["program", "ai", "manual"] = "manual"


class EconomicFactMergeBatchConfirmRequest(BaseModel):
    primary_transaction_id: int
    allocations: list[EconomicFactMergeBatchItem] = Field(min_length=1, max_length=20)

    @field_validator("allocations")
    @classmethod
    def ensure_distinct_evidence(cls, value: list[EconomicFactMergeBatchItem]):
        evidence_ids = [item.evidence_transaction_id for item in value]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("同一条证据记录不能在一次批量分配中重复出现")
        return value


class EconomicFactMembershipResponse(BaseModel):
    fact: EconomicFactResponse
    members: list[EconomicFactMember] = Field(default_factory=list)


class EconomicFactSplitComponentInput(BaseModel):
    amount: TransactionAmount
    category_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    nature: Optional[TransactionNature] = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: Optional[str]) -> Optional[str]:
        normalized = (value or "").strip()
        return normalized or None


class EconomicFactSplitConfirmRequest(BaseModel):
    components: list[EconomicFactSplitComponentInput] = Field(min_length=2, max_length=20)
    reason: Optional[str] = Field(default=None, max_length=255)


class EconomicFactSplitResponse(BaseModel):
    transaction_id: int
    original_amount: MoneyOutput
    allocated_amount: MoneyOutput
    remaining_amount: MoneyOutput
    components: list[EconomicFactSplitComponentResponse] = Field(default_factory=list)
    ledger_revision: int


class EconomicRelationConfirmRequest(BaseModel):
    source_transaction_id: Optional[int] = Field(default=None, gt=0)
    target_transaction_id: Optional[int] = Field(default=None, gt=0)
    source_fact_id: Optional[int] = Field(default=None, gt=0)
    target_fact_id: Optional[int] = Field(default=None, gt=0)
    relation_type: EconomicRelationType
    allocated_amount: TransactionAmount
    reasons: list[str] = Field(default_factory=list, max_length=12)
    detection_method: Literal["program", "ai", "manual"] = "manual"

    @model_validator(mode="after")
    def require_fact_or_transaction_for_each_side(self):
        if self.source_transaction_id is None and self.source_fact_id is None:
            raise ValueError("来源端必须指定流水或经济事实")
        if self.target_transaction_id is None and self.target_fact_id is None:
            raise ValueError("目标端必须指定流水或经济事实")
        if (
            self.source_transaction_id is not None
            and self.target_transaction_id is not None
            and self.source_transaction_id == self.target_transaction_id
            and self.source_fact_id == self.target_fact_id
        ):
            raise ValueError("不能把同一个经济事实关联给自己")
        return self


class EconomicRelationBatchReverseRequest(BaseModel):
    relation_ids: list[int] = Field(min_length=1, max_length=50)
    reason: Optional[str] = Field(default=None, max_length=255)

    @field_validator("relation_ids")
    @classmethod
    def normalize_relation_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("关系 ID 必须大于 0")
        return list(dict.fromkeys(value))

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class EconomicRelationResponse(BaseModel):
    id: int
    source_fact_id: int
    target_fact_id: int
    source_transaction_id: int
    target_transaction_id: int
    source_title: str
    target_title: str
    source_amount: MoneyOutput
    target_amount: MoneyOutput
    source_date: date
    target_date: date
    relation_type: EconomicRelationType
    allocated_amount: MoneyOutput
    status: Literal["confirmed", "reversed"]
    detection_method: Literal["program", "ai", "manual"]
    reasons: list[str] = Field(default_factory=list)
    confirmed_at: datetime
    reversed_at: Optional[datetime] = None


class EconomicRelationRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relation_id: int
    relation_revision: int = Field(ge=1)
    ledger_revision: int = Field(ge=1)
    operation: Literal["confirm", "reverse"]
    before_snapshot: Optional[dict] = None
    after_snapshot: dict
    reason: Optional[str] = None
    created_at: datetime


class CashflowChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)

    @field_validator("content")
    @classmethod
    def normalize_chat_content(cls, value: str) -> str:
        return value.strip()


class CashflowAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    month: Optional[str] = None
    conversation_id: Optional[int] = Field(default=None, gt=0)
    history: list[CashflowChatMessage] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return value.strip()


class CashflowAnswerReference(BaseModel):
    transaction_id: int
    transaction_date: date
    direction: Direction
    amount: MoneyOutput
    title: str
    category_name: Optional[str] = None
    fact_type: str


class CashflowPayslipReference(BaseModel):
    payslip_id: int
    pay_month: Optional[str] = None
    employer_name: Optional[str] = None
    gross_salary: Optional[MoneyOutput] = None
    net_salary: Optional[MoneyOutput] = None
    attention_count: int = Field(default=0, ge=0)
    unverified_count: int = Field(default=0, ge=0)


class CashflowAskResponse(BaseModel):
    conversation_id: int
    turn_id: int
    answer: str
    mode: Literal["ai", "program"]
    ledger_revision: int = Field(ge=0)
    data_start: date
    data_end: date
    transaction_count: int
    references: list[CashflowAnswerReference] = Field(default_factory=list)
    payslip_references: list[CashflowPayslipReference] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    generated_at: datetime


class CashflowConversationSummaryResponse(BaseModel):
    id: int
    month: str
    title: str
    status: Literal["active", "archived"]
    turn_count: int = Field(ge=0)
    latest_ledger_revision: Optional[int] = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime


class CashflowConversationTurnResponse(BaseModel):
    question: str
    response: CashflowAskResponse


class CashflowConversationDetailResponse(CashflowConversationSummaryResponse):
    turns: list[CashflowConversationTurnResponse] = Field(default_factory=list)
