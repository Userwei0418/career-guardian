"""Add reversible total and category monthly budgets.

Revision ID: 20260823_0039
Revises: 20260823_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0039"
down_revision = "20260823_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_budgets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["category_id"], ["financial_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "month",
            "scope_key",
            name="uq_financial_budget_owner_month_scope",
        ),
    )
    op.create_index(
        "ix_financial_budgets_owner_month",
        "financial_budgets",
        ["user_id", "month", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_budgets_owner_month", table_name="financial_budgets")
    op.drop_table("financial_budgets")
