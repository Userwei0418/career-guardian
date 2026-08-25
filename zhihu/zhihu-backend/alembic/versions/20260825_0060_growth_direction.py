"""Add Growth Guardian future-direction domain.

Revision ID: 20260825_0060
Revises: 20260825_0059
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0060"
down_revision = "20260825_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_future_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("supersedes_target_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_key", sa.String(length=180), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_label", sa.String(length=300), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_type IN ('role', 'job_family', 'level', 'transition', 'other')", name="ck_growth_future_targets_type"),
        sa.CheckConstraint("status IN ('draft', 'active', 'paused', 'completed', 'superseded')", name="ck_growth_future_targets_status"),
        sa.ForeignKeyConstraint(["supersedes_target_id"], ["growth_future_targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_target_owner_request"),
        sa.UniqueConstraint("user_id", "target_key", "version", name="uq_growth_target_owner_key_version"),
    )
    op.create_index("ix_growth_target_owner_status", "growth_future_targets", ["user_id", "status", "target_date"])

    op.create_table(
        "growth_market_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("batch_request_id", sa.String(length=80), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("signal_key", sa.String(length=180), nullable=False),
        sa.Column("skill_name", sa.String(length=160), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("share", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("availability", sa.String(length=30), nullable=False),
        sa.Column("data_mode", sa.String(length=20), nullable=False),
        sa.Column("quality_grade", sa.String(length=20), nullable=False),
        sa.Column("sample_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("methodology_version", sa.String(length=100), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.Column("limitation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="weak", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("direction IN ('rising', 'stable', 'declining', 'unknown')", name="ck_growth_market_signals_direction"),
        sa.CheckConstraint("quality_grade IN ('A', 'B', 'C', 'insufficient')", name="ck_growth_market_signals_quality"),
        sa.CheckConstraint("availability IN ('available', 'insufficient_sample', 'stale', 'unavailable')", name="ck_growth_market_signals_availability"),
        sa.CheckConstraint("status IN ('active', 'weak', 'expired', 'rejected')", name="ck_growth_market_signals_status"),
        sa.ForeignKeyConstraint(["target_id"], ["growth_future_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "batch_request_id", "signal_key", name="uq_growth_market_signal_batch_key"),
    )
    op.create_index("ix_growth_market_signal_owner_target", "growth_market_signals", ["user_id", "target_id", "status", "calculated_at"])

    op.create_table(
        "growth_gap_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("market_signal_ids", sa.JSON(), nullable=False),
        sa.Column("career_chip_refs", sa.JSON(), nullable=False),
        sa.Column("matched_items", sa.JSON(), nullable=False),
        sa.Column("gap_items", sa.JSON(), nullable=False),
        sa.Column("unknown_items", sa.JSON(), nullable=False),
        sa.Column("quality", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("limitation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="candidate", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quality IN ('strong', 'limited', 'insufficient', 'stale')", name="ck_growth_gap_snapshots_quality"),
        sa.CheckConstraint("status IN ('candidate', 'confirmed', 'superseded')", name="ck_growth_gap_snapshots_status"),
        sa.ForeignKeyConstraint(["target_id"], ["growth_future_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_gap_owner_request"),
        sa.UniqueConstraint("user_id", "target_id", "version", name="uq_growth_gap_target_version"),
    )
    op.create_index("ix_growth_gap_owner_target", "growth_gap_snapshots", ["user_id", "target_id", "status", "created_at"])

    op.create_table(
        "growth_milestones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("supersedes_milestone_id", sa.Integer(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("gap_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("milestone_key", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.String(length=20), server_default="custom", nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("timeframe IN ('30d', '60d', '90d', 'quarter', 'custom')", name="ck_growth_milestones_timeframe"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'in_progress', 'completed', 'cancelled', 'superseded')", name="ck_growth_milestones_status"),
        sa.ForeignKeyConstraint(["gap_snapshot_id"], ["growth_gap_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_milestone_id"], ["growth_milestones.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["growth_future_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_milestone_owner_request"),
        sa.UniqueConstraint("user_id", "milestone_key", "version", name="uq_growth_milestone_owner_key_version"),
    )
    op.create_index("ix_growth_milestone_owner_target", "growth_milestones", ["user_id", "target_id", "status", "due_on"])


def downgrade() -> None:
    op.drop_table("growth_milestones")
    op.drop_table("growth_gap_snapshots")
    op.drop_table("growth_market_signals")
    op.drop_table("growth_future_targets")
