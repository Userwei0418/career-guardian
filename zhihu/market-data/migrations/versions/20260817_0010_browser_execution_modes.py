"""Persist the effective browser execution mode for every collection task.

Revision ID: 20260817_0010
Revises: 20260817_0009
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0010"
down_revision = "20260817_0009"
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
    columns = {item["name"] for item in inspector.get_columns("crawl_tasks")}
    if "browser_mode" in columns and "browser_mode_source" in columns:
        return
    with op.batch_alter_table("crawl_tasks") as batch:
        if "browser_mode" not in columns:
            batch.add_column(
                sa.Column(
                    "browser_mode",
                    sa.String(20),
                    nullable=False,
                    server_default="headless",
                )
            )
        if "browser_mode_source" not in columns:
            batch.add_column(
                sa.Column(
                    "browser_mode_source",
                    sa.String(30),
                    nullable=False,
                    server_default="channel_default",
                )
            )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("crawl_tasks")}
    with op.batch_alter_table("crawl_tasks") as batch:
        if "browser_mode_source" in columns:
            batch.drop_column("browser_mode_source")
        if "browser_mode" in columns:
            batch.drop_column("browser_mode")
