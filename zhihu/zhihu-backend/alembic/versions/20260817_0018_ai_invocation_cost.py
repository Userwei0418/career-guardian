"""Persist provider-reported AI invocation cost when available.

Revision ID: 20260817_0018
Revises: 20260816_0017
"""

from alembic import op
import sqlalchemy as sa


revision = "20260817_0018"
down_revision = "20260816_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.add_column(sa.Column("estimated_cost_microunits", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cost_currency", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.drop_column("cost_currency")
        batch_op.drop_column("estimated_cost_microunits")
