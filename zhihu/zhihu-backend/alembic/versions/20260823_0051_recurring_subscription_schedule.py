"""Add user-confirmed subscription renewal schedule.

Revision ID: 20260823_0051
Revises: 20260823_0050
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0051"
down_revision = "20260823_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("financial_recurring_decisions", sa.Column("renewal_cycle", sa.String(20), nullable=True))
    op.add_column("financial_recurring_decisions", sa.Column("next_charge_date", sa.Date(), nullable=True))
    op.add_column("financial_recurring_decisions", sa.Column("auto_renewal", sa.Boolean(), nullable=True))
    op.add_column("financial_recurring_decisions", sa.Column("reminder_days_before", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_financial_recurring_renewal_cycle",
        "financial_recurring_decisions",
        "renewal_cycle IS NULL OR renewal_cycle IN ('monthly', 'quarterly', 'yearly', 'custom')",
    )
    op.create_check_constraint(
        "ck_financial_recurring_reminder_days",
        "financial_recurring_decisions",
        "reminder_days_before IS NULL OR (reminder_days_before >= 0 AND reminder_days_before <= 30)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_financial_recurring_reminder_days",
        "financial_recurring_decisions",
        type_="check",
    )
    op.drop_constraint(
        "ck_financial_recurring_renewal_cycle",
        "financial_recurring_decisions",
        type_="check",
    )
    op.drop_column("financial_recurring_decisions", "reminder_days_before")
    op.drop_column("financial_recurring_decisions", "auto_renewal")
    op.drop_column("financial_recurring_decisions", "next_charge_date")
    op.drop_column("financial_recurring_decisions", "renewal_cycle")
