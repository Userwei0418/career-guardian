"""Persist Growth Guardian market-temperature comparison windows.

Revision ID: 20260825_0062
Revises: 20260825_0061
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0062"
down_revision = "20260825_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, column_type in (
        ("recent_count", sa.Integer()),
        ("previous_count", sa.Integer()),
        ("recent_share", sa.Float()),
        ("previous_share", sa.Float()),
        ("share_delta", sa.Float()),
        ("recent_sample_size", sa.Integer()),
        ("previous_sample_size", sa.Integer()),
        ("recent_window_start", sa.DateTime()),
        ("recent_window_end", sa.DateTime()),
        ("previous_window_start", sa.DateTime()),
        ("previous_window_end", sa.DateTime()),
    ):
        op.add_column("growth_market_signals", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name in (
        "previous_window_end",
        "previous_window_start",
        "recent_window_end",
        "recent_window_start",
        "previous_sample_size",
        "recent_sample_size",
        "share_delta",
        "previous_share",
        "recent_share",
        "previous_count",
        "recent_count",
    ):
        op.drop_column("growth_market_signals", name)
