"""Store the promised pay date separately from actual arrival dates.

Revision ID: 20260823_0035
Revises: 20260823_0034
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0035"
down_revision = "20260823_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payslips", sa.Column("agreed_pay_date", sa.Date(), nullable=True))
    op.create_index("ix_payslips_agreed_pay_date", "payslips", ["agreed_pay_date"])


def downgrade() -> None:
    op.drop_index("ix_payslips_agreed_pay_date", table_name="payslips")
    op.drop_column("payslips", "agreed_pay_date")
