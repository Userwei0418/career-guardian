"""Certify every Core job with a versioned quality gate policy.

Revision ID: 20260815_0003
Revises: 20260815_0002
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260815_0003"
down_revision = "20260815_0002"
branch_labels = None
depends_on = None


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def add_missing_column(table: str, column: sa.Column) -> bool:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if column.name in columns:
        return False
    op.add_column(table, column)
    return True


def upgrade(**_: object) -> None:
    if selected_domain() != "core":
        return
    if "jobs" in inspect(op.get_bind()).get_table_names():
        policy_added = add_missing_column(
            "jobs",
            sa.Column(
                "gate_policy_version",
                sa.String(80),
                nullable=False,
                server_default="uncertified",
            ),
        )
        add_missing_column(
            "jobs",
            sa.Column(
                "gate_evaluated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        if policy_added:
            op.create_index(
                "ix_jobs_gate_policy_version", "jobs", ["gate_policy_version"]
            )
    if "rejected_legacy_jobs" in inspect(op.get_bind()).get_table_names():
        add_missing_column(
            "rejected_legacy_jobs",
            sa.Column(
                "decision",
                sa.String(20),
                nullable=False,
                server_default="quarantined",
            ),
        )
        add_missing_column(
            "rejected_legacy_jobs",
            sa.Column(
                "policy_version",
                sa.String(80),
                nullable=False,
                server_default="uncertified",
            ),
        )


def downgrade(**_: object) -> None:
    pass
