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

    @field_validator("merchant", "description", "excluded_reason")
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
    created_at: datetime
    updated_at: datetime


class FinancialTransactionPage(BaseModel):
    items: list[FinancialTransactionResponse]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)


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
    status: Literal["confirmed", "reversed", "superseded"]


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


class EconomicRelationSuggestionResponse(BaseModel):
    transaction: FinancialTransactionResponse
    fact: EconomicFactResponse
    suggestions: list[EconomicRelationSuggestion] = Field(default_factory=list)


class EconomicRelationConfirmRequest(BaseModel):
    source_transaction_id: int
    target_transaction_id: int
    relation_type: EconomicRelationType
    allocated_amount: TransactionAmount
    reasons: list[str] = Field(default_factory=list, max_length=12)
    detection_method: Literal["program", "ai", "manual"] = "manual"


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
    answer: str
    mode: Literal["ai", "program"]
    data_start: date
    data_end: date
    transaction_count: int
    references: list[CashflowAnswerReference] = Field(default_factory=list)
    payslip_references: list[CashflowPayslipReference] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    generated_at: datetime
