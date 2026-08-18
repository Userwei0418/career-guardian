"""Add audit trail for Core company and job administration.

Revision ID: 20260818_0016
Revises: 20260818_0015
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260818_0016"
down_revision = "20260818_0015"
branch_labels = None
depends_on = None


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def upgrade(**_: object) -> None:
    if selected_domain() != "core":
        return
    if "market_admin_audit_logs" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "market_admin_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("before_payload", sa.JSON(), nullable=True),
        sa.Column("after_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_admin_audit_logs_entity_type", "market_admin_audit_logs", ["entity_type"])
    op.create_index("ix_market_admin_audit_logs_entity_id", "market_admin_audit_logs", ["entity_id"])
    op.create_index("ix_market_admin_audit_logs_action", "market_admin_audit_logs", ["action"])
    op.create_index("ix_market_admin_audit_logs_created_at", "market_admin_audit_logs", ["created_at"])
    op.create_index("ix_market_admin_audit_entity", "market_admin_audit_logs", ["entity_type", "entity_id", "created_at"])


def downgrade(**_: object) -> None:
    if selected_domain() == "core":
        op.drop_table("market_admin_audit_logs")
