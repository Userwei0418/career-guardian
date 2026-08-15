"""Add a stable market-list ordering index.

Revision ID: 20260815_0005
Revises: 20260815_0004
"""

from alembic import context, op
from sqlalchemy import inspect


revision = "20260815_0005"
down_revision = "20260815_0004"
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
    inspector = inspect(op.get_bind())
    if "market_jobs" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("market_jobs")}
    if "ix_market_jobs_order" not in indexes:
        op.create_index(
            "ix_market_jobs_order",
            "market_jobs",
            ["quality_score", "last_seen_at", "id"],
        )


def downgrade(**_: object) -> None:
    if selected_domain() != "core":
        return
    inspector = inspect(op.get_bind())
    if "market_jobs" not in inspector.get_table_names():
        return
    indexes = {item["name"] for item in inspector.get_indexes("market_jobs")}
    if "ix_market_jobs_order" in indexes:
        op.drop_index("ix_market_jobs_order", table_name="market_jobs")
