"""Persist per-task Growth Guardian coaching notes.

Revision ID: 20260825_0063
Revises: 20260825_0062
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0063"
down_revision = "20260825_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("growth_work_items", sa.Column("progress_summary", sa.Text(), nullable=True))
    op.add_column("growth_work_items", sa.Column("blocker_note", sa.Text(), nullable=True))
    op.add_column("growth_work_items", sa.Column("next_action", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("growth_work_items", "next_action")
    op.drop_column("growth_work_items", "blocker_note")
    op.drop_column("growth_work_items", "progress_summary")
