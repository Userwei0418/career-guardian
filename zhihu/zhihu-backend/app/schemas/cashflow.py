from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Direction = Literal["income", "expense", "transfer"]
TransactionStatus = Literal["pending", "confirmed", "excluded"]
TransactionNature = Literal["fixed", "flexible", "one_off", "reimbursable", "other"]


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
    amount: float = Field(gt=0, le=999_999_999_999.99)
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

    @model_validator(mode="after")
    def validate_direction_fields(self):
        if self.direction == "transfer" and self.category_id is not None:
            raise ValueError("转账不应设置收支分类")
        return self


class FinancialTransactionUpdate(BaseModel):
    direction: Optional[Direction] = None
    amount: Optional[float] = Field(default=None, gt=0, le=999_999_999_999.99)
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
    amount: float
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


class CategoryAmount(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    amount: float
    count: int


class DailyAmount(BaseModel):
    date: date
    income: float
    expense: float


class CashflowSummaryResponse(BaseModel):
    month: str
    state: Literal["not_started", "recording", "needs_confirmation"]
    income: float
    expense: float
    net: float
    transfer_amount: float
    confirmed_count: int
    pending_count: int
    excluded_count: int
    income_categories: list[CategoryAmount]
    expense_categories: list[CategoryAmount]
    daily: list[DailyAmount]
