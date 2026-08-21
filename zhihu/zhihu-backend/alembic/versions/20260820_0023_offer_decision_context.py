"""Add per-Offer decision context and user boundaries.

Revision ID: 20260820_0023
Revises: 20260820_0022
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0023"
down_revision = "20260820_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_decision_contexts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("baseline_type", sa.String(length=30), nullable=True),
        sa.Column("baseline_label", sa.String(length=200), nullable=True),
        sa.Column("baseline_monthly_take_home", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("baseline_annual_bonus", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("baseline_city", sa.String(length=50), nullable=True),
        sa.Column("search_runway_months", sa.Integer(), nullable=True),
        sa.Column("baseline_notes", sa.Text(), nullable=True),
        sa.Column("must_haves", sa.JSON(), nullable=True),
        sa.Column("red_lines", sa.JSON(), nullable=True),
        sa.Column("acceptable_tradeoffs", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", name="uq_offer_decision_contexts_offer_id"),
    )
    op.create_index("ix_offer_decision_contexts_user_id", "offer_decision_contexts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("offer_decision_contexts")
