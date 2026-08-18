"""Add school subjects, source ownership and school administrator audit trail.

Revision ID: 20260819_0018
Revises: 20260818_0017
"""

from alembic import context, op
import sqlalchemy as sa


revision = "20260819_0018"
down_revision = "20260818_0017"
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
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "recruitment_schools" not in tables:
        op.create_table(
            "recruitment_schools",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("employment_center_name", sa.String(length=255), nullable=False),
            sa.Column("short_name", sa.String(length=100), nullable=True),
            sa.Column("province", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=True),
            sa.Column("website_url", sa.String(length=1000), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("origin", sa.String(length=30), nullable=False, server_default="native"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_recruitment_schools_code"),
        )
        op.create_index("ix_recruitment_schools_name", "recruitment_schools", ["name"])
        op.create_index(
            "ix_recruitment_schools_employment_center_name",
            "recruitment_schools",
            ["employment_center_name"],
        )
        op.create_index("ix_recruitment_schools_status", "recruitment_schools", ["status"])

    inspector = sa.inspect(bind)
    if "data_sources" in set(inspector.get_table_names()):
        columns = {item["name"] for item in inspector.get_columns("data_sources")}
        if "school_id" not in columns:
            with op.batch_alter_table("data_sources") as batch:
                batch.add_column(sa.Column("school_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_data_sources_school",
                    "recruitment_schools",
                    ["school_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                batch.create_index("ix_data_sources_school_id", ["school_id"])
        op.execute(
            sa.text(
                "INSERT INTO recruitment_schools "
                "(code, name, employment_center_name, website_url, origin, status, created_at, updated_at) "
                "SELECT LOWER(legacy_company_code), "
                "MIN(TRIM(REPLACE(name, ' · 招聘公告', ''))), "
                "MIN(TRIM(REPLACE(name, ' · 招聘公告', ''))), "
                "MIN(base_url), 'catalog', 'active', NOW(), NOW() "
                "FROM data_sources "
                "WHERE source_kind = 'school_announcement' "
                "AND legacy_company_code IS NOT NULL AND legacy_company_code <> '' "
                "GROUP BY LOWER(legacy_company_code) "
                "ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at)"
            )
        )
        op.execute(
            sa.text(
                "UPDATE data_sources ds "
                "JOIN recruitment_schools rs ON rs.code = LOWER(ds.legacy_company_code) "
                "SET ds.school_id = rs.id "
                "WHERE ds.source_kind = 'school_announcement'"
            )
        )

    if "school_admin_audit_logs" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "school_admin_audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("school_id", sa.Integer(), nullable=True),
            sa.Column("entity_id", sa.String(length=80), nullable=False),
            sa.Column("action", sa.String(length=30), nullable=False),
            sa.Column("actor", sa.String(length=100), nullable=False),
            sa.Column("before_payload", sa.JSON(), nullable=True),
            sa.Column("after_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["school_id"], ["recruitment_schools.id"],
                name="fk_school_admin_audit_school", ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_school_admin_audit_logs_school_id", "school_admin_audit_logs", ["school_id"])
        op.create_index("ix_school_admin_audit_logs_entity_id", "school_admin_audit_logs", ["entity_id"])
        op.create_index("ix_school_admin_audit_logs_action", "school_admin_audit_logs", ["action"])
        op.create_index("ix_school_admin_audit_logs_created_at", "school_admin_audit_logs", ["created_at"])


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "school_admin_audit_logs" in tables:
        op.drop_table("school_admin_audit_logs")
    if "data_sources" in tables:
        columns = {item["name"] for item in sa.inspect(bind).get_columns("data_sources")}
        if "school_id" in columns:
            with op.batch_alter_table("data_sources") as batch:
                batch.drop_index("ix_data_sources_school_id")
                batch.drop_constraint("fk_data_sources_school", type_="foreignkey")
                batch.drop_column("school_id")
    if "recruitment_schools" in tables:
        op.drop_table("recruitment_schools")
