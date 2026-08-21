"""Persist private, review-versioned contract follow-up conversations.

Revision ID: 20260821_0028
Revises: 20260821_0027
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0028"
down_revision = "20260821_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_follow_up_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("review_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("clause_id", sa.String(length=100), nullable=False),
        sa.Column("finding_code", sa.String(length=100), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("limits", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("redaction_version", sa.String(length=80), nullable=True),
        sa.Column("review_method", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["review_snapshot_id"],
            ["contract_review_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_snapshot_id",
            "clause_id",
            "finding_code",
            "turn_number",
            name="uq_contract_follow_up_turn",
        ),
    )
    op.create_index("ix_contract_follow_up_turns_user_id", "contract_follow_up_turns", ["user_id"])
    op.create_index("ix_contract_follow_up_turns_contract_id", "contract_follow_up_turns", ["contract_id"])
    op.create_index(
        "ix_contract_follow_up_turns_review_snapshot_id",
        "contract_follow_up_turns",
        ["review_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contract_follow_up_turns_review_snapshot_id", table_name="contract_follow_up_turns")
    op.drop_index("ix_contract_follow_up_turns_contract_id", table_name="contract_follow_up_turns")
    op.drop_index("ix_contract_follow_up_turns_user_id", table_name="contract_follow_up_turns")
    op.drop_table("contract_follow_up_turns")
