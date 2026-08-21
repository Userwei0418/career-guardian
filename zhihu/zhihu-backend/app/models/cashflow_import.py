from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.session import Base


class FinancialImportBatch(Base):
    """One user-owned parsing run shared by file, OCR, and AI text intake."""

    __tablename__ = "financial_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "origin_type",
            "source_type",
            "content_hash",
            "parser_version",
            name="uq_fin_import_batch_source_hash_parser",
        ),
        # The composite key lets candidates prove that their denormalized
        # user_id is the same owner as the parent batch.
        UniqueConstraint("id", "user_id", name="uq_fin_import_batch_id_owner"),
        CheckConstraint(
            "origin_type IN ('file', 'ocr', 'ai_text')",
            name="ck_fin_import_batch_origin_type",
        ),
        Index(
            "ix_financial_import_batches_owner_status",
            "user_id",
            "status",
            "created_at",
        ),
        Index("ix_financial_import_batches_attachment", "attachment_version_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    origin_type = Column(String(20), nullable=False)
    source_type = Column(String(50), nullable=False)
    attachment_version_id = Column(
        Integer,
        ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_filename = Column(String(255), nullable=True)
    content_type = Column(String(150), nullable=True)
    file_size = Column(Integer, nullable=True)
    content_hash = Column(String(64), nullable=False)
    parser_version = Column(String(80), nullable=False)
    status = Column(String(30), nullable=False, default="created", server_default="created")
    column_mapping = Column(JSON, nullable=False, default=dict)
    parse_hints = Column(JSON, nullable=False, default=dict)
    total_count = Column(Integer, nullable=False, default=0, server_default="0")
    ready_count = Column(Integer, nullable=False, default=0, server_default="0")
    review_count = Column(Integer, nullable=False, default=0, server_default="0")
    duplicate_count = Column(Integer, nullable=False, default=0, server_default="0")
    exact_duplicate_count = Column(Integer, nullable=False, default=0, server_default="0")
    possible_duplicate_count = Column(Integer, nullable=False, default=0, server_default="0")
    invalid_count = Column(Integer, nullable=False, default=0, server_default="0")
    excluded_count = Column(Integer, nullable=False, default=0, server_default="0")
    confirmed_count = Column(Integer, nullable=False, default=0, server_default="0")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    parsed_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __mapper_args__ = {"version_id_col": version}


class FinancialTransactionCandidate(Base):
    """A reviewable import row that is not yet part of the formal ledger."""

    __tablename__ = "financial_transaction_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["financial_import_batches.id", "financial_import_batches.user_id"],
            name="fk_fin_tx_candidate_batch_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "batch_id",
            "row_number",
            name="uq_fin_tx_candidate_batch_row",
        ),
        Index(
            "ix_fin_tx_candidates_batch_status_row",
            "batch_id",
            "status",
            "row_number",
        ),
        Index(
            "ix_fin_tx_candidates_owner_status",
            "user_id",
            "status",
            "created_at",
        ),
        Index("ix_fin_tx_candidates_fingerprint", "user_id", "fingerprint"),
        Index("ix_fin_tx_candidates_external_key", "user_id", "external_key"),
        Index("ix_fin_tx_candidates_category", "category_id"),
        Index("ix_fin_tx_candidates_duplicate_tx", "duplicate_transaction_id"),
        Index("ix_fin_tx_candidates_transaction", "transaction_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    batch_id = Column(Integer, nullable=False)
    row_number = Column(Integer, nullable=False)
    direction = Column(String(20), nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(3), nullable=True, default="CNY")
    transaction_date = Column(Date, nullable=True)
    occurred_at = Column(DateTime, nullable=True)
    category_id = Column(
        Integer,
        ForeignKey("financial_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    category_name = Column(String(80), nullable=True)
    merchant = Column(String(120), nullable=True)
    description = Column(String(500), nullable=True)
    nature = Column(String(30), nullable=True)
    status = Column(String(20), nullable=False, default="needs_review", server_default="needs_review")
    external_key = Column(String(160), nullable=True)
    fingerprint = Column(String(64), nullable=True)
    duplicate_transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_payload = Column(JSON, nullable=False)
    evidence = Column(JSON, nullable=False, default=dict)
    validation_errors = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __mapper_args__ = {"version_id_col": version}
