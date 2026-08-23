"""Persist resumable payslip recognition candidates without original files.

Revision ID: 20260823_0047
Revises: 20260823_0046
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0047"
down_revision = "20260823_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payslip_recognition_candidate_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence_tier", sa.String(20), nullable=False),
        sa.Column("candidate_payload", sa.JSON(), nullable=False),
        sa.Column("payslip_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("excluded_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'excluded')",
            name="ck_payslip_recognition_draft_status",
        ),
        sa.CheckConstraint(
            "confidence_tier IN ('high', 'medium', 'low')",
            name="ck_payslip_recognition_draft_tier",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["financial_import_batches.id", "financial_import_batches.user_id"],
            name="fk_payslip_recognition_draft_batch_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["payslip_id"], ["payslips.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "row_number",
            name="uq_payslip_recognition_draft_row",
        ),
    )
    op.create_index(
        "ix_payslip_recognition_drafts_owner_status",
        "payslip_recognition_candidate_drafts",
        ["user_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_payslip_recognition_drafts_batch_status",
        "payslip_recognition_candidate_drafts",
        ["batch_id", "status", "row_number"],
    )
    op.create_index(
        "ix_payslip_recognition_drafts_payslip",
        "payslip_recognition_candidate_drafts",
        ["payslip_id"],
    )


def downgrade() -> None:
    op.drop_table("payslip_recognition_candidate_drafts")
