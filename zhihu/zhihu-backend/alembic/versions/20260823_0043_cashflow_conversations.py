"""Persist cashflow AI conversations and versioned turns.

Revision ID: 20260823_0043
Revises: 20260823_0042
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0043"
down_revision = "20260823_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cashflow_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cashflow_conversations_owner_month",
        "cashflow_conversations",
        ["user_id", "month", "updated_at"],
    )
    op.create_table(
        "cashflow_conversation_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("data_start", sa.Date(), nullable=False),
        sa.Column("data_end", sa.Date(), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("payslip_references", sa.JSON(), nullable=False),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["conversation_id"], ["cashflow_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cashflow_conversation_turns_conversation",
        "cashflow_conversation_turns",
        ["conversation_id", "id"],
    )
    op.create_index(
        "ix_cashflow_conversation_turns_owner_created",
        "cashflow_conversation_turns",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cashflow_conversation_turns_owner_created",
        table_name="cashflow_conversation_turns",
    )
    op.drop_index(
        "ix_cashflow_conversation_turns_conversation",
        table_name="cashflow_conversation_turns",
    )
    op.drop_table("cashflow_conversation_turns")
    op.drop_index(
        "ix_cashflow_conversations_owner_month",
        table_name="cashflow_conversations",
    )
    op.drop_table("cashflow_conversations")
