"""Add reversible user decisions for recurring expense candidates.

Revision ID: 20260823_0038
Revises: 20260823_0037
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0038"
down_revision = "20260823_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_recurring_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("merchant_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("merchant_name", sa.String(length=120), nullable=False),
        sa.Column("decision_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "merchant_fingerprint",
            name="uq_financial_recurring_decision_owner_merchant",
        ),
    )
    op.create_index(
        "ix_financial_recurring_decisions_owner_status",
        "financial_recurring_decisions",
        ["user_id", "status", "decision_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_recurring_decisions_owner_status",
        table_name="financial_recurring_decisions",
    )
    op.drop_table("financial_recurring_decisions")
