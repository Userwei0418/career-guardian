"""Add reusable interview practice modes and comparable rubric metadata.

Revision ID: 20260816_0015
Revises: 20260816_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0015"
down_revision = "20260816_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("mock_interview_sessions")}
    with op.batch_alter_table("mock_interview_sessions") as batch_op:
        if "practice_type" not in columns:
            batch_op.add_column(sa.Column("practice_type", sa.String(length=30), nullable=False, server_default="full_interview"))
        if "rubric_version" not in columns:
            batch_op.add_column(sa.Column("rubric_version", sa.String(length=30), nullable=False, server_default="interview_v1"))
        if "target_duration_seconds" not in columns:
            batch_op.add_column(sa.Column("target_duration_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("mock_interview_sessions")}
    with op.batch_alter_table("mock_interview_sessions") as batch_op:
        if "target_duration_seconds" in columns:
            batch_op.drop_column("target_duration_seconds")
        if "rubric_version" in columns:
            batch_op.drop_column("rubric_version")
        if "practice_type" in columns:
            batch_op.drop_column("practice_type")
