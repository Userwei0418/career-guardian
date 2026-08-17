"""Version reusable channel loading strategies and task strategy lineage.

Revision ID: 20260817_0011
Revises: 20260817_0010
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0011"
down_revision = "20260817_0010"
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
    if "collection_strategy_versions" not in tables:
        op.create_table(
            "collection_strategy_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="candidate"),
            sa.Column("origin", sa.String(30), nullable=False, server_default="runtime_discovery"),
            sa.Column("strategy", sa.JSON(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("validation_summary", sa.JSON(), nullable=False),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(100), nullable=False, server_default="system"),
            sa.Column("activated_at", sa.DateTime(), nullable=True),
            sa.Column("last_validated_at", sa.DateTime(), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("source_id", "version", name="uq_collection_strategy_version"),
        )
        op.create_index(
            "ix_collection_strategy_versions_source_id",
            "collection_strategy_versions",
            ["source_id"],
        )
        op.create_index(
            "ix_collection_strategy_versions_status",
            "collection_strategy_versions",
            ["status"],
        )
    columns = {item["name"] for item in inspector.get_columns("crawl_tasks")}
    with op.batch_alter_table("crawl_tasks") as batch:
        if "strategy_version" not in columns:
            batch.add_column(sa.Column("strategy_version", sa.Integer(), nullable=True))
        if "strategy_source" not in columns:
            batch.add_column(
                sa.Column(
                    "strategy_source",
                    sa.String(30),
                    nullable=False,
                    server_default="runtime_discovery",
                )
            )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    inspector = sa.inspect(op.get_bind())
    columns = {item["name"] for item in inspector.get_columns("crawl_tasks")}
    with op.batch_alter_table("crawl_tasks") as batch:
        if "strategy_source" in columns:
            batch.drop_column("strategy_source")
        if "strategy_version" in columns:
            batch.drop_column("strategy_version")
    if "collection_strategy_versions" in set(inspector.get_table_names()):
        op.drop_table("collection_strategy_versions")
