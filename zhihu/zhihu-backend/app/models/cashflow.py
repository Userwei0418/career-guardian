from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    JSON,
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


class FinancialLedgerRevisionEvent(Base):
    __tablename__ = "financial_ledger_revision_events"
    __table_args__ = (
        UniqueConstraint("user_id", "revision_number", name="uq_financial_ledger_revision_owner_number"),
        Index("ix_financial_ledger_revisions_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revision_number = Column(Integer, nullable=False)
    event_type = Column(String(40), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(Integer, nullable=True)
    summary = Column(String(255), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class FinancialTransactionRevision(Base):
    __tablename__ = "financial_transaction_revisions"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "transaction_revision",
            name="uq_financial_transaction_revision_number",
        ),
        Index("ix_financial_transaction_revisions_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_revision = Column(Integer, nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    operation = Column(String(30), nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    reason = Column(String(255), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class EconomicFactRelationRevision(Base):
    __tablename__ = "economic_fact_relation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "relation_id",
            "relation_revision",
            name="uq_economic_fact_relation_revision_number",
        ),
        Index(
            "ix_economic_fact_relation_revisions_owner_created",
            "user_id",
            "created_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    relation_id = Column(
        Integer,
        ForeignKey("economic_fact_relations.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_revision = Column(Integer, nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    operation = Column(String(20), nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=False)
    reason = Column(String(255), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class FinancialRecurringDecision(Base):
    __tablename__ = "financial_recurring_decisions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "merchant_fingerprint",
            name="uq_financial_recurring_decision_owner_merchant",
        ),
        Index(
            "ix_financial_recurring_decisions_owner_status",
            "user_id",
            "status",
            "decision_type",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    merchant_fingerprint = Column(String(64), nullable=False)
    merchant_name = Column(String(120), nullable=False)
    decision_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    note = Column(String(500), nullable=True)
    evidence = Column(JSON, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    reversed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class FinancialBudget(Base):
    __tablename__ = "financial_budgets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            "scope_key",
            name="uq_financial_budget_owner_month_scope",
        ),
        Index("ix_financial_budgets_owner_month", "user_id", "month", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)
    scope_key = Column(String(80), nullable=False)
    category_id = Column(
        Integer,
        ForeignKey("financial_categories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    amount = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    reversed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class FinancialMonthClose(Base):
    __tablename__ = "financial_month_closes"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            "version",
            name="uq_financial_month_close_owner_month_version",
        ),
        Index(
            "ix_financial_month_closes_owner_month",
            "user_id",
            "month",
            "status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)
    version = Column(Integer, nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    report_fingerprint = Column(String(64), nullable=False)
    report_snapshot = Column(JSON, nullable=False)
    pending_candidate_count = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="closed", server_default="closed")
    closed_at = Column(DateTime, nullable=False, server_default=func.now())
    reopened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class CashflowConversation(Base):
    __tablename__ = "cashflow_conversations"
    __table_args__ = (
        Index("ix_cashflow_conversations_owner_month", "user_id", "month", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    month = Column(String(7), nullable=False)
    title = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class CashflowConversationTurn(Base):
    __tablename__ = "cashflow_conversation_turns"
    __table_args__ = (
        Index("ix_cashflow_conversation_turns_conversation", "conversation_id", "id"),
        Index("ix_cashflow_conversation_turns_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(
        Integer,
        ForeignKey("cashflow_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    mode = Column(String(20), nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    data_start = Column(Date, nullable=False)
    data_end = Column(Date, nullable=False)
    transaction_count = Column(Integer, nullable=False)
    references = Column(JSON, nullable=False)
    payslip_references = Column(JSON, nullable=False)
    follow_up_questions = Column(JSON, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class EconomicFact(Base):
    __tablename__ = "economic_facts"
    __table_args__ = (
        UniqueConstraint("primary_transaction_id", name="uq_economic_fact_primary_transaction"),
        Index("ix_economic_facts_owner_date", "user_id", "occurred_date", "status", "fact_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    primary_transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=True,
    )
    fact_type = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    occurred_date = Column(Date, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="CNY", server_default="CNY")
    status = Column(String(20), nullable=False, default="confirmed", server_default="confirmed")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EconomicFactAllocation(Base):
    __tablename__ = "economic_fact_allocations"
    __table_args__ = (
        UniqueConstraint("fact_id", "transaction_id", name="uq_economic_fact_allocation"),
        Index("ix_economic_fact_allocations_transaction", "transaction_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_id = Column(Integer, ForeignKey("economic_facts.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(30), nullable=False, default="primary", server_default="primary")
    allocated_amount = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False, default="confirmed", server_default="confirmed")
    reasons = Column(JSON, nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    reversed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class EconomicFactRevision(Base):
    __tablename__ = "economic_fact_revisions"
    __table_args__ = (
        UniqueConstraint(
            "fact_id",
            "fact_revision",
            name="uq_economic_fact_revision_number",
        ),
        Index("ix_economic_fact_revisions_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fact_id = Column(
        Integer,
        ForeignKey("economic_facts.id", ondelete="CASCADE"),
        nullable=False,
    )
    fact_revision = Column(Integer, nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    operation = Column(String(30), nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=False)
    reason = Column(String(255), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class EconomicFactRelation(Base):
    __tablename__ = "economic_fact_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_fact_id",
            "target_fact_id",
            "relation_type",
            name="uq_economic_fact_relation_pair",
        ),
        Index("ix_economic_fact_relations_owner", "user_id", "status", "relation_type"),
        CheckConstraint("source_fact_id <> target_fact_id", name="ck_economic_fact_relation_distinct"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_fact_id = Column(Integer, ForeignKey("economic_facts.id", ondelete="CASCADE"), nullable=False)
    target_fact_id = Column(Integer, ForeignKey("economic_facts.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(30), nullable=False)
    allocated_amount = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False, default="confirmed", server_default="confirmed")
    detection_method = Column(String(20), nullable=False, default="manual", server_default="manual")
    reasons = Column(JSON, nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    reversed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
