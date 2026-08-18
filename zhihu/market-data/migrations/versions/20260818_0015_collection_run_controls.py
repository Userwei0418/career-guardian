"""Persist per-run collection controls and widen Raw schema identifiers.

Revision ID: 20260818_0015
Revises: 20260818_0014
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260818_0015"
down_revision = "20260818_0014"
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
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "raw_records" in tables:
        op.alter_column(
            "raw_records",
            "schema_version",
            existing_type=sa.String(length=20),
            type_=sa.String(length=80),
            existing_nullable=False,
        )
    if "crawl_tasks" in tables:
        columns = {item["name"] for item in sa.inspect(bind).get_columns("crawl_tasks")}
        if "run_options" not in columns:
            op.add_column(
                "crawl_tasks",
                sa.Column("run_options", sa.JSON(), nullable=True),
            )
            op.execute(sa.text("UPDATE crawl_tasks SET run_options = JSON_OBJECT() WHERE run_options IS NULL"))
            op.alter_column(
                "crawl_tasks",
                "run_options",
                existing_type=sa.JSON(),
                nullable=False,
            )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "crawl_tasks" in tables:
        columns = {item["name"] for item in sa.inspect(bind).get_columns("crawl_tasks")}
        if "run_options" in columns:
            op.drop_column("crawl_tasks", "run_options")
    if "raw_records" in tables:
        op.alter_column(
            "raw_records",
            "schema_version",
            existing_type=sa.String(length=80),
            type_=sa.String(length=20),
            existing_nullable=False,
        )
