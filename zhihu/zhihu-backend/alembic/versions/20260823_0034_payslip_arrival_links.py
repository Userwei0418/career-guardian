"""Link payslip rights evidence to confirmed cash arrivals.

Revision ID: 20260823_0034
Revises: 20260823_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0034"
down_revision = "20260823_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payslip_arrival_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("payslip_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("match_reason", sa.JSON(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payslip_id"], ["payslips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["financial_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payslip_id", "transaction_id", name="uq_payslip_arrival_transaction"),
    )
    op.create_index("ix_payslip_arrival_links_payslip_id", "payslip_arrival_links", ["payslip_id"])
    op.create_index(
        "ix_payslip_arrival_transaction",
        "payslip_arrival_links",
        ["transaction_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("payslip_arrival_links")
