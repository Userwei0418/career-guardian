from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.session import Base


class FinancialCategory(Base):
    __tablename__ = "financial_categories"
    __table_args__ = (
        UniqueConstraint("user_id", "direction", "name", name="uq_financial_category_owner_direction_name"),
        Index("ix_financial_categories_owner_direction", "user_id", "direction", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    direction = Column(String(20), nullable=False)
    name = Column(String(50), nullable=False)
    is_system = Column(Boolean, nullable=False, default=False, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_type",
            "external_key",
            name="uq_financial_transaction_source_key",
        ),
        Index(
            "ix_financial_transactions_monthly",
            "user_id",
            "transaction_date",
            "status",
            "direction",
        ),
        Index("ix_financial_transactions_category_id", "category_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(
        Integer,
        ForeignKey("financial_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    direction = Column(String(20), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY", server_default="CNY")
    transaction_date = Column(Date, nullable=False)
    occurred_at = Column(DateTime, nullable=True)
    merchant = Column(String(120), nullable=True)
    description = Column(String(500), nullable=True)
    nature = Column(String(30), nullable=True)
    source_type = Column(String(30), nullable=False, default="manual", server_default="manual")
    source_ref = Column(String(255), nullable=True)
    external_key = Column(String(160), nullable=True)
    status = Column(String(20), nullable=False, default="confirmed", server_default="confirmed")
    confirmed_at = Column(DateTime, nullable=True)
    excluded_reason = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
