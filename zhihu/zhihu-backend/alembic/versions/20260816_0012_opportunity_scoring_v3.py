"""Use the corrected v3 opportunity scoring version for new analyses.

Revision ID: 20260816_0012
Revises: 20260816_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0012"
down_revision = "20260816_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunity_analyses") as batch_op:
        batch_op.alter_column(
            "scoring_version",
            existing_type=sa.String(length=40),
            existing_nullable=False,
            server_default="resume-job-fit-v3",
        )


def downgrade() -> None:
    with op.batch_alter_table("opportunity_analyses") as batch_op:
        batch_op.alter_column(
            "scoring_version",
            existing_type=sa.String(length=40),
            existing_nullable=False,
            server_default="resume-job-fit-v2",
        )
