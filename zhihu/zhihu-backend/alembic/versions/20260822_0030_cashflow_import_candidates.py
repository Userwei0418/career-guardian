"""Add shared import batches and reviewable transaction candidates.

Revision ID: 20260822_0030
Revises: 20260822_0029
"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_0030"
down_revision = "20260822_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "business_data_epoch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "personal_attachment_cleanup_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_path", name="uq_attachment_cleanup_storage_path"),
    )
    op.create_index(
        "ix_attachment_cleanup_user",
        "personal_attachment_cleanup_jobs",
        ["user_id", "status", "id"],
    )
    op.create_index(
        "ix_attachment_cleanup_status",
        "personal_attachment_cleanup_jobs",
        ["status", "updated_at"],
    )
    op.create_table(
        "financial_import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("origin_type", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("attachment_version_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("column_mapping", sa.JSON(), nullable=False),
        sa.Column("parse_hints", sa.JSON(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exact_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("possible_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parsed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "origin_type IN ('file', 'ocr', 'ai_text')",
            name="ck_fin_import_batch_origin_type",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_version_id"],
            ["personal_attachment_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "user_id", name="uq_fin_import_batch_id_owner"),
        sa.UniqueConstraint(
            "user_id",
            "origin_type",
            "source_type",
            "content_hash",
            "parser_version",
            name="uq_fin_import_batch_source_hash_parser",
        ),
    )
    op.create_index(
        "ix_financial_import_batches_owner_status",
        "financial_import_batches",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_financial_import_batches_attachment",
        "financial_import_batches",
        ["attachment_version_id"],
    )

    op.create_table(
        "financial_transaction_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_name", sa.String(length=80), nullable=True),
        sa.Column("merchant", sa.String(length=120), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("nature", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="needs_review"),
        sa.Column("external_key", sa.String(length=160), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("duplicate_transaction_id", sa.Integer(), nullable=True),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("original_payload", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["financial_import_batches.id", "financial_import_batches.user_id"],
            name="fk_fin_tx_candidate_batch_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["financial_categories.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_transaction_id"],
            ["financial_transactions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["financial_transactions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_fin_tx_candidate_batch_row"),
    )
    op.create_index(
        "ix_fin_tx_candidates_batch_status_row",
        "financial_transaction_candidates",
        ["batch_id", "status", "row_number"],
    )
    op.create_index(
        "ix_fin_tx_candidates_owner_status",
        "financial_transaction_candidates",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_fin_tx_candidates_fingerprint",
        "financial_transaction_candidates",
        ["user_id", "fingerprint"],
    )
    op.create_index(
        "ix_fin_tx_candidates_external_key",
        "financial_transaction_candidates",
        ["user_id", "external_key"],
    )
    op.create_index(
        "ix_fin_tx_candidates_category",
        "financial_transaction_candidates",
        ["category_id"],
    )
    op.create_index(
        "ix_fin_tx_candidates_duplicate_tx",
        "financial_transaction_candidates",
        ["duplicate_transaction_id"],
    )
    op.create_index(
        "ix_fin_tx_candidates_transaction",
        "financial_transaction_candidates",
        ["transaction_id"],
    )


def downgrade() -> None:
    # Dropping a table removes its indexes and foreign keys atomically. Avoid
    # dropping FK-supporting indexes first: MySQL can reject that order with
    # "needed in a foreign key constraint" when an explicit index replaced the
    # automatically-created FK index.
    op.drop_table("financial_transaction_candidates")
    op.drop_table("financial_import_batches")
    op.drop_table("personal_attachment_cleanup_jobs")
    op.drop_column("users", "business_data_epoch")
