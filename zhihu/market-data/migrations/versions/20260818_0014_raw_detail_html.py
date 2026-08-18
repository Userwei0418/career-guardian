"""Allow complete rendered detail HTML in Raw evidence.

Revision ID: 20260818_0014
Revises: 20260817_0013
"""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260818_0014"
down_revision = "20260817_0013"
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
    if "raw_records" not in set(sa.inspect(bind).get_table_names()):
        return
    if bind.dialect.name == "mysql":
        op.alter_column(
            "raw_records",
            "raw_text",
            existing_type=sa.Text(),
            type_=mysql.LONGTEXT(),
            existing_nullable=True,
        )


def downgrade(**_: object) -> None:
    if selected_domain() != "raw":
        return
    bind = op.get_bind()
    if "raw_records" not in set(sa.inspect(bind).get_table_names()):
        return
    if bind.dialect.name == "mysql":
        op.alter_column(
            "raw_records",
            "raw_text",
            existing_type=mysql.LONGTEXT(),
            type_=sa.Text(),
            existing_nullable=True,
        )
