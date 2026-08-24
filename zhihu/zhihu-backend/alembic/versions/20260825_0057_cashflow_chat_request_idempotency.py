"""Add request-level idempotency to cashflow chat turns.

Revision ID: 20260825_0057
Revises: 20260825_0056
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0057"
down_revision = "20260825_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cashflow_conversation_turns",
        sa.Column("request_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "cashflow_conversation_turns",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_cashflow_conversation_turn_owner_request",
        "cashflow_conversation_turns",
        ["user_id", "request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cashflow_conversation_turn_owner_request",
        "cashflow_conversation_turns",
        type_="unique",
    )
    op.drop_column("cashflow_conversation_turns", "request_fingerprint")
    op.drop_column("cashflow_conversation_turns", "request_id")
