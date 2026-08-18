"""Persist staged collection progress for administrator observability.

Revision ID: 20260818_0017
Revises: 20260818_0016
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260818_0017"
down_revision = "20260818_0016"
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
    if "crawl_tasks" not in set(sa.inspect(bind).get_table_names()):
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns("crawl_tasks")}
    if "progress_snapshot" in columns:
        return
    op.add_column("crawl_tasks", sa.Column("progress_snapshot", sa.JSON(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE crawl_tasks SET progress_snapshot = "
            "JSON_OBJECT('stage', CASE WHEN status = 'succeeded' THEN 'completed' ELSE status END, "
            "'overall_percent', CASE WHEN status = 'succeeded' THEN 100 ELSE 0 END, "
            "'stages', JSON_OBJECT()) WHERE progress_snapshot IS NULL"
        )
    )
    op.alter_column(
        "crawl_tasks",
        "progress_snapshot",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    bind = op.get_bind()
    if "crawl_tasks" not in set(sa.inspect(bind).get_table_names()):
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns("crawl_tasks")}
    if "progress_snapshot" in columns:
        op.drop_column("crawl_tasks", "progress_snapshot")
