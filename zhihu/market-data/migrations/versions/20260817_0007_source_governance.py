"""Persist market source approval audit fields.

Revision ID: 20260817_0007
Revises: 20260815_0006
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0007"
down_revision = "20260815_0006"
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
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("data_sources")}
    if "terms_reviewed_by" not in columns:
        op.add_column("data_sources", sa.Column("terms_reviewed_by", sa.String(100), nullable=True))
    if "terms_reviewed_at" not in columns:
        op.add_column("data_sources", sa.Column("terms_reviewed_at", sa.DateTime(), nullable=True))
    if "terms_review_note" not in columns:
        op.add_column("data_sources", sa.Column("terms_review_note", sa.Text(), nullable=True))
    if "configuration_updated_by" not in columns:
        op.add_column(
            "data_sources", sa.Column("configuration_updated_by", sa.String(100), nullable=True)
        )
    if "configuration_updated_at" not in columns:
        op.add_column(
            "data_sources", sa.Column("configuration_updated_at", sa.DateTime(), nullable=True)
        )
    task_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("crawl_tasks")}
    if "promoted_records" not in task_columns:
        op.add_column(
            "crawl_tasks",
            sa.Column("promoted_records", sa.Integer(), nullable=False, server_default="0"),
        )
    if "quarantined_records" not in task_columns:
        op.add_column(
            "crawl_tasks",
            sa.Column("quarantined_records", sa.Integer(), nullable=False, server_default="0"),
        )
    # Superseded by the separately governed campus/internship/social sources.
    op.execute(
        sa.text(
            "DELETE FROM data_sources WHERE code = 'picc-public-api-candidate' "
            "AND NOT EXISTS (SELECT 1 FROM crawl_tasks WHERE crawl_tasks.source_id = data_sources.id) "
            "AND NOT EXISTS (SELECT 1 FROM raw_records WHERE raw_records.source_id = data_sources.id)"
        )
    )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    task_columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("crawl_tasks")}
    if "quarantined_records" in task_columns:
        op.drop_column("crawl_tasks", "quarantined_records")
    if "promoted_records" in task_columns:
        op.drop_column("crawl_tasks", "promoted_records")
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("data_sources")}
    if "configuration_updated_at" in columns:
        op.drop_column("data_sources", "configuration_updated_at")
    if "configuration_updated_by" in columns:
        op.drop_column("data_sources", "configuration_updated_by")
    if "terms_review_note" in columns:
        op.drop_column("data_sources", "terms_review_note")
    if "terms_reviewed_at" in columns:
        op.drop_column("data_sources", "terms_reviewed_at")
    if "terms_reviewed_by" in columns:
        op.drop_column("data_sources", "terms_reviewed_by")
