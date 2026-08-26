"""Add append-only Growth Guardian work updates.

Revision ID: 20260825_0064
Revises: 20260825_0063
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0064"
down_revision = "20260825_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_work_updates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("assistant_summary", sa.Text(), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("star_hints", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('context', 'progress', 'blocker', 'next_action', 'result')",
            name="ck_growth_work_updates_kind",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["growth_work_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "request_id",
            name="uq_growth_work_update_owner_request",
        ),
    )
    op.create_index(
        "ix_growth_work_updates_owner_item_created",
        "growth_work_updates",
        ["user_id", "work_item_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("growth_work_updates")
