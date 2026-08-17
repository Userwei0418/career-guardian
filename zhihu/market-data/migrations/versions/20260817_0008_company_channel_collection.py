"""Model company recruitment channels and collection templates.

Revision ID: 20260817_0008
Revises: 20260817_0007
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260817_0008"
down_revision = "20260817_0007"
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
    # The foundation migration intentionally uses the current SQLAlchemy
    # metadata for brand-new databases. In that case these tables and columns
    # already exist before Alembic reaches this revision; existing deployments
    # still need the explicit additive migration below.
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    data_source_columns = (
        {item["name"] for item in inspector.get_columns("data_sources")}
        if "data_sources" in tables
        else set()
    )
    crawl_task_columns = (
        {item["name"] for item in inspector.get_columns("crawl_tasks")}
        if "crawl_tasks" in tables
        else set()
    )
    if {
        "collection_templates",
        "recruitment_companies",
        "crawl_batches",
    }.issubset(tables) and {
        "company_id",
        "template_id",
        "channel_type",
        "source_kind",
        "legacy_company_code",
        "configuration_status",
    }.issubset(data_source_columns) and "batch_id" in crawl_task_columns:
        op.execute(sa.text("UPDATE data_sources SET source_kind='development_fixture' WHERE code LIKE '%-fixture'"))
        op.execute(sa.text("UPDATE data_sources SET configuration_status='ready' WHERE code LIKE 'picc-%'"))
        return
    op.create_table(
        "collection_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("platform_type", sa.String(40), nullable=False),
        sa.Column("adapter_type", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("default_config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_collection_templates_platform_type", "collection_templates", ["platform_type"])
    op.create_table(
        "recruitment_companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("website_url", sa.String(1000), nullable=True),
        sa.Column("logo_url", sa.String(1000), nullable=True),
        sa.Column("origin", sa.String(30), nullable=False, server_default="native"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_recruitment_companies_name", "recruitment_companies", ["name"])
    op.create_table(
        "crawl_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_uid", sa.String(36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("requested_channels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_channels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_channels", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["recruitment_companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_uid"),
    )
    op.create_index("ix_crawl_batches_company_id", "crawl_batches", ["company_id"])
    op.create_index("ix_crawl_batches_status", "crawl_batches", ["status"])
    with op.batch_alter_table("data_sources") as batch:
        batch.add_column(sa.Column("company_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("channel_type", sa.String(30), nullable=False, server_default="mixed"))
        batch.add_column(sa.Column("source_kind", sa.String(30), nullable=False, server_default="company_channel"))
        batch.add_column(sa.Column("legacy_company_code", sa.String(80), nullable=True))
        batch.add_column(sa.Column("configuration_status", sa.String(30), nullable=False, server_default="needs_review"))
        batch.create_foreign_key("fk_data_sources_company", "recruitment_companies", ["company_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_data_sources_template", "collection_templates", ["template_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_data_sources_company_id", ["company_id"])
        batch.create_index("ix_data_sources_template_id", ["template_id"])
        batch.create_index("ix_data_sources_channel_type", ["channel_type"])
        batch.create_index("ix_data_sources_source_kind", ["source_kind"])
        batch.create_index("ix_data_sources_legacy_company_code", ["legacy_company_code"])
        batch.create_index("ix_data_sources_configuration_status", ["configuration_status"])
    with op.batch_alter_table("crawl_tasks") as batch:
        batch.add_column(sa.Column("batch_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_crawl_tasks_batch", "crawl_batches", ["batch_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_crawl_tasks_batch_id", ["batch_id"])

    op.execute(sa.text("UPDATE data_sources SET source_kind='development_fixture' WHERE code LIKE '%-fixture'"))
    op.execute(sa.text("UPDATE data_sources SET configuration_status='ready' WHERE code LIKE 'picc-%'"))


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    with op.batch_alter_table("crawl_tasks") as batch:
        batch.drop_index("ix_crawl_tasks_batch_id")
        batch.drop_constraint("fk_crawl_tasks_batch", type_="foreignkey")
        batch.drop_column("batch_id")
    with op.batch_alter_table("data_sources") as batch:
        for name in [
            "ix_data_sources_configuration_status", "ix_data_sources_legacy_company_code",
            "ix_data_sources_source_kind", "ix_data_sources_channel_type",
            "ix_data_sources_template_id", "ix_data_sources_company_id",
        ]:
            batch.drop_index(name)
        batch.drop_constraint("fk_data_sources_template", type_="foreignkey")
        batch.drop_constraint("fk_data_sources_company", type_="foreignkey")
        for name in ["configuration_status", "legacy_company_code", "source_kind", "channel_type", "template_id", "company_id"]:
            batch.drop_column(name)
    op.drop_table("crawl_batches")
    op.drop_table("recruitment_companies")
    op.drop_table("collection_templates")
