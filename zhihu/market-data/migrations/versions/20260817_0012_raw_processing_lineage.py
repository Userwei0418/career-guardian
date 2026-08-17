"""Persist source-grounded Raw processing lineage.

Revision ID: 20260817_0012
Revises: 20260817_0011
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0012"
down_revision = "20260817_0011"
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
    columns = {item["name"] for item in inspector.get_columns("raw_records")}
    with op.batch_alter_table("raw_records") as batch:
        if "normalized_payload" not in columns:
            batch.add_column(sa.Column("normalized_payload", sa.JSON(), nullable=True))
        if "processing_status" not in columns:
            batch.add_column(
                sa.Column("processing_status", sa.String(30), nullable=False, server_default="pending")
            )
        if "processing_attempts" not in columns:
            batch.add_column(
                sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0")
            )
        if "processing_version" not in columns:
            batch.add_column(sa.Column("processing_version", sa.String(40), nullable=True))
    inspector = sa.inspect(op.get_bind())
    raw_indexes = {item["name"] for item in inspector.get_indexes("raw_records")}
    if "ix_raw_records_processing_status" not in raw_indexes:
        op.create_index(
            "ix_raw_records_processing_status", "raw_records", ["processing_status"]
        )
    if "raw_processing_attempts" not in set(inspector.get_table_names()):
        op.create_table(
            "raw_processing_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("raw_record_id", sa.Integer(), nullable=False),
            sa.Column("crawl_task_id", sa.Integer(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(40), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("processor_type", sa.String(20), nullable=False),
            sa.Column("provider", sa.String(100), nullable=True),
            sa.Column("model", sa.String(160), nullable=True),
            sa.Column("prompt_version", sa.String(80), nullable=True),
            sa.Column("input_hash", sa.String(64), nullable=True),
            sa.Column("output_hash", sa.String(64), nullable=True),
            sa.Column("reason_codes", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["crawl_task_id"], ["crawl_tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        )
        for column in ("raw_record_id", "crawl_task_id", "source_id", "stage", "status"):
            op.create_index(
                f"ix_raw_processing_attempts_{column}", "raw_processing_attempts", [column]
            )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    inspector = sa.inspect(op.get_bind())
    if "raw_processing_attempts" in set(inspector.get_table_names()):
        op.drop_table("raw_processing_attempts")
    columns = {item["name"] for item in inspector.get_columns("raw_records")}
    with op.batch_alter_table("raw_records") as batch:
        for column in (
            "processing_version",
            "processing_attempts",
            "processing_status",
            "normalized_payload",
        ):
            if column in columns:
                batch.drop_column(column)
