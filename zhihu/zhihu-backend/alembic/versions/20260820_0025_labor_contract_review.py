"""Add labor contract source and review snapshots.

Revision ID: 20260820_0025
Revises: 20260820_0024
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0025"
down_revision = "20260820_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch_op:
        batch_op.add_column(sa.Column("source_attachment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("display_name", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("document_kind", sa.String(length=30), server_default="labor_contract", nullable=False)
        )
        batch_op.add_column(
            sa.Column("status", sa.String(length=30), server_default="active", nullable=False)
        )
        batch_op.add_column(
            sa.Column("parse_status", sa.String(length=30), server_default="ready", nullable=False)
        )
        batch_op.add_column(sa.Column("parse_mode", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("parse_notice", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("page_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_contracts_source_attachment_id", ["source_attachment_id"], unique=False)
        batch_op.create_index("ix_contracts_status", ["status"], unique=False)
        batch_op.create_foreign_key(
            "fk_contract_source_attachment",
            "personal_attachment_versions",
            ["source_attachment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "contract_review_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("attachment_version_id", sa.Integer(), nullable=True),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("review_mode", sa.String(length=30), server_default="rules", nullable=False),
        sa.Column("rule_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["attachment_version_id"], ["personal_attachment_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "review_number", name="uq_contract_review_number"),
    )
    op.create_index("ix_contract_review_attachment", "contract_review_snapshots", ["attachment_version_id"], unique=False)
    op.create_index("ix_contract_review_contract", "contract_review_snapshots", ["contract_id"], unique=False)
    op.create_index("ix_contract_review_hash", "contract_review_snapshots", ["document_hash"], unique=False)


def downgrade() -> None:
    op.drop_table("contract_review_snapshots")
    with op.batch_alter_table("contracts") as batch_op:
        batch_op.drop_constraint("fk_contract_source_attachment", type_="foreignkey")
        batch_op.drop_index("ix_contracts_status")
        batch_op.drop_index("ix_contracts_source_attachment_id")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("page_count")
        batch_op.drop_column("parse_notice")
        batch_op.drop_column("parse_mode")
        batch_op.drop_column("parse_status")
        batch_op.drop_column("status")
        batch_op.drop_column("document_kind")
        batch_op.drop_column("display_name")
        batch_op.drop_column("source_attachment_id")
