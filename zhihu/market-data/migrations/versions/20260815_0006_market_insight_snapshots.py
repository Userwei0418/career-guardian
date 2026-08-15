"""Add materialized market insight snapshots.

Revision ID: 20260815_0006
Revises: 20260815_0005
"""

from alembic import context, op

from market_data.db import CoreBase
from market_data.models import core  # noqa: F401


revision = "20260815_0006"
down_revision = "20260815_0005"
branch_labels = None
depends_on = None


def selected_domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in {"staging", "raw", "core"}:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def upgrade(**_: object) -> None:
    if selected_domain() == "core":
        CoreBase.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade(**_: object) -> None:
    pass
