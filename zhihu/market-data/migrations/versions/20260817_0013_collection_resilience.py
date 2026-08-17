"""Add collection health and strategy repair governance.

Revision ID: 20260817_0013
Revises: 20260817_0012
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0013"
down_revision = "20260817_0012"
branch_labels = None
depends_on = None


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def upgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "source_operational_states" not in tables:
        op.create_table(
            "source_operational_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("health_status", sa.String(20), nullable=False, server_default="healthy"),
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_failure_type", sa.String(60), nullable=True),
            sa.Column("last_failure_message", sa.Text(), nullable=True),
            sa.Column("last_failure_at", sa.DateTime(), nullable=True),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(), nullable=True),
            sa.Column("recovery_action", sa.String(60), nullable=True),
            sa.Column("recovery_recommendation", sa.Text(), nullable=True),
            sa.Column("alert_status", sa.String(20), nullable=False, server_default="closed"),
            sa.Column("alert_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_alert_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("source_id"),
        )
        for column in ("source_id", "health_status", "next_retry_at", "alert_status"):
            op.create_index(f"ix_source_operational_states_{column}", "source_operational_states", [column])
    if "strategy_repair_candidates" not in tables:
        op.create_table(
            "strategy_repair_candidates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("failure_task_id", sa.Integer(), nullable=True),
            sa.Column("base_strategy_version", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="candidate"),
            sa.Column("origin", sa.String(30), nullable=False, server_default="admin"),
            sa.Column("failure_signature", sa.String(160), nullable=True),
            sa.Column("proposed_strategy", sa.JSON(), nullable=False),
            sa.Column("replay_summary", sa.JSON(), nullable=False),
            sa.Column("canary_summary", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.String(100), nullable=False),
            sa.Column("reviewed_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("replayed_at", sa.DateTime(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["failure_task_id"], ["crawl_tasks.id"], ondelete="SET NULL"),
        )
        for column in ("source_id", "failure_task_id", "status"):
            op.create_index(f"ix_strategy_repair_candidates_{column}", "strategy_repair_candidates", [column])


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "strategy_repair_candidates" in tables:
        op.drop_table("strategy_repair_candidates")
    if "source_operational_states" in tables:
        op.drop_table("source_operational_states")
