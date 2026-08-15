"""Persist configurable quality gate policies in the product market fact schema.

Revision ID: 20260815_0004
Revises: 20260815_0003
"""

from alembic import context, op
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260815_0004"
down_revision = "20260815_0003"
branch_labels = None
depends_on = None


DEFAULT_CONFIGURATION = {
    "policy_version": "career-guardian-job-core-v1",
    "minimum_core_score": 55,
    "minimum_description_chars": 50,
    "live_freshness_days": 14,
    "maximum_future_hours": 48,
    "maximum_salary": 1_000_000,
    "required_facts": [
        "company_name", "title", "source_url", "content_hash", "observed_at"
    ],
    "score_weights": {
        "identity": 30,
        "source_url": 15,
        "content_hash": 5,
        "description": 15,
        "city": 10,
        "published_at": 5,
        "observed_at": 5,
        "skills": 5,
        "salary": 10,
    },
}


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def upgrade(**_: object) -> None:
    if selected_domain() != "core":
        return
    tables = inspect(op.get_bind()).get_table_names()
    if "market_quality_gate_policies" not in tables:
        op.create_table(
            "market_quality_gate_policies",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("policy_version", sa.String(80), nullable=False, unique=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("configuration", sa.JSON(), nullable=False),
            sa.Column("change_note", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(100), nullable=False),
            sa.Column("published_by", sa.String(100), nullable=True),
            sa.Column("preview_summary", sa.JSON(), nullable=True),
            sa.Column("previewed_at", sa.DateTime(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_market_quality_gate_policies_status", "market_quality_gate_policies", ["status"])
    table = sa.table(
        "market_quality_gate_policies",
        sa.column("policy_version", sa.String),
        sa.column("status", sa.String),
        sa.column("configuration", sa.JSON),
        sa.column("change_note", sa.Text),
        sa.column("created_by", sa.String),
        sa.column("published_by", sa.String),
        sa.column("published_at", sa.DateTime),
    )
    exists = op.get_bind().scalar(
        sa.select(sa.func.count()).select_from(table).where(table.c.status == "active")
    )
    if not exists:
        op.bulk_insert(
            table,
            [{
                "policy_version": DEFAULT_CONFIGURATION["policy_version"],
                "status": "active",
                "configuration": DEFAULT_CONFIGURATION,
                "change_note": "系统初始岗位准入标准",
                "created_by": "system",
                "published_by": "system",
                "published_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }],
        )


def downgrade(**_: object) -> None:
    pass
