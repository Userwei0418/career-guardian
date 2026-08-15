"""Create isolated staging, raw, or core market schema."""

from alembic import context, op

from market_data.db import CoreBase, RawBase, StagingBase
from market_data.models import core, raw, staging  # noqa: F401

revision = "20260815_0001"
down_revision = None
branch_labels = None
depends_on = None

BASES = {"staging": StagingBase, "raw": RawBase, "core": CoreBase}


def _domain() -> str:
    domain = context.get_x_argument(as_dictionary=True).get("domain")
    if domain not in BASES:
        raise RuntimeError("Migration requires -x domain=staging|raw|core")
    return domain


def upgrade(**_: object) -> None:
    BASES[_domain()].metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade(**_: object) -> None:
    BASES[_domain()].metadata.drop_all(bind=op.get_bind(), checkfirst=True)
