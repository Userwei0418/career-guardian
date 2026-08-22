"""Add versioned user month-close snapshots.

Revision ID: 20260823_0041
Revises: 20260823_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0041"
down_revision = "20260823_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_month_closes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("report_snapshot", sa.JSON(), nullable=False),
        sa.Column("pending_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="closed"),
        sa.Column("closed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reopened_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "month",
            "version",
            name="uq_financial_month_close_owner_month_version",
        ),
    )
    op.create_index(
        "ix_financial_month_closes_owner_month",
        "financial_month_closes",
        ["user_id", "month", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_month_closes_owner_month",
        table_name="financial_month_closes",
    )
    op.drop_table("financial_month_closes")
