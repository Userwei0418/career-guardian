"""Expand staging lineage and the cleaned market Core model.

Revision ID: 20260815_0002
Revises: 20260815_0001
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect

from market_data.db import CoreBase, StagingBase
from market_data.models import core, staging  # noqa: F401


revision = "20260815_0002"
down_revision = "20260815_0001"
branch_labels = None
depends_on = None


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def add_missing_column(table: str, column: sa.Column) -> bool:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if column.name in columns:
        return False
    op.add_column(table, column)
    return True


def upgrade_core() -> None:
    # create_all only creates the new association/audit tables. Existing tables
    # are expanded explicitly below so a previously migrated database is safe.
    CoreBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    inspector = inspect(op.get_bind())
    if "companies" in inspector.get_table_names():
        additions = [
            sa.Column("legacy_company_id", sa.Integer(), nullable=True),
            sa.Column("alias_name", sa.String(255), nullable=True),
            sa.Column("short_name", sa.String(100), nullable=True),
            sa.Column("career_page_url", sa.String(1000), nullable=True),
            sa.Column("industry", sa.String(100), nullable=True),
            sa.Column("company_type", sa.String(100), nullable=True),
            sa.Column("size_range", sa.String(100), nullable=True),
            sa.Column("headquarters", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
        ]
        for column in additions:
            add_missing_column("companies", column)

    inspector = inspect(op.get_bind())
    if "jobs" in inspector.get_table_names():
        identity_added = add_missing_column(
            "jobs", sa.Column("identity_key", sa.String(64), nullable=True)
        )
        additions = [
            sa.Column("legacy_job_id", sa.Integer(), nullable=True),
            sa.Column("salary_min", sa.Integer(), nullable=True),
            sa.Column("salary_max", sa.Integer(), nullable=True),
            sa.Column("salary_period", sa.String(20), nullable=False, server_default="unknown"),
            sa.Column("salary_months", sa.Integer(), nullable=True),
            sa.Column("salary_currency", sa.String(20), nullable=False, server_default="CNY"),
            sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quality_grade", sa.String(20), nullable=False, server_default="C"),
            sa.Column("quality_reasons", sa.JSON(), nullable=True),
        ]
        for column in additions:
            add_missing_column("jobs", column)
        if identity_added:
            if op.get_bind().dialect.name == "mysql":
                op.execute("UPDATE jobs SET identity_key = CONCAT('pre-v2:', id)")
            else:
                op.execute("UPDATE jobs SET identity_key = 'pre-v2:' || id")
            with op.batch_alter_table("jobs") as batch:
                batch.alter_column("identity_key", existing_type=sa.String(64), nullable=False)
                batch.create_unique_constraint("uq_jobs_identity_key", ["identity_key"])

    inspector = inspect(op.get_bind())
    if "job_sources" in inspector.get_table_names():
        add_missing_column(
            "job_sources",
            sa.Column(
                "provenance_type", sa.String(30), nullable=False, server_default="live_raw"
            ),
        )
        legacy_source_added = add_missing_column(
            "job_sources", sa.Column("legacy_source_record_id", sa.Integer(), nullable=True)
        )
        if legacy_source_added:
            op.create_unique_constraint(
                "uq_job_sources_legacy_source_record_id",
                "job_sources",
                ["legacy_source_record_id"],
            )


def upgrade(**_: object) -> None:
    domain = selected_domain()
    if domain == "staging":
        StagingBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    elif domain == "core":
        upgrade_core()
    # Raw schema did not change in this revision.


def downgrade(**_: object) -> None:
    # This is a data-preserving migration. Rollback intentionally does not drop
    # imported staging lineage or cleaned Core facts.
    pass
