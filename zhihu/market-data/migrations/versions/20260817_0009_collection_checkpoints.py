"""Add platform pagination task metadata and durable collection checkpoints.

Revision ID: 20260817_0009
Revises: 20260817_0008
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0009"
down_revision = "20260817_0008"
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
    task_columns = {item["name"] for item in inspector.get_columns("crawl_tasks")}
    if "collection_mode" not in task_columns or "checkpoint_version" not in task_columns:
        with op.batch_alter_table("crawl_tasks") as batch:
            if "collection_mode" not in task_columns:
                batch.add_column(
                    sa.Column("collection_mode", sa.String(20), nullable=False, server_default="full")
                )
                batch.create_index("ix_crawl_tasks_collection_mode", ["collection_mode"])
            if "checkpoint_version" not in task_columns:
                batch.add_column(sa.Column("checkpoint_version", sa.Integer(), nullable=True))
    if "source_collection_checkpoints" not in tables:
        op.create_table(
            "source_collection_checkpoints",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("cursor_payload", sa.JSON(), nullable=False),
            sa.Column("successful_incremental_runs", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_successful_task_id", sa.Integer(), nullable=True),
            sa.Column("last_successful_at", sa.DateTime(), nullable=True),
            sa.Column("last_full_crawl_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["last_successful_task_id"], ["crawl_tasks.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_id"),
        )
        op.create_index(
            "ix_source_collection_checkpoints_source_id",
            "source_collection_checkpoints",
            ["source_id"],
            unique=True,
        )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    op.drop_index(
        "ix_source_collection_checkpoints_source_id",
        table_name="source_collection_checkpoints",
    )
    op.drop_table("source_collection_checkpoints")
    with op.batch_alter_table("crawl_tasks") as batch:
        batch.drop_column("checkpoint_version")
        batch.drop_index("ix_crawl_tasks_collection_mode")
        batch.drop_column("collection_mode")
