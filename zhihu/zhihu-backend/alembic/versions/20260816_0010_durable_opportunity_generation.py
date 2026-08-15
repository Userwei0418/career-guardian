"""persist opportunity generation progress and results

Revision ID: 20260816_0010
Revises: 20260816_0009
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0010"
down_revision = "20260816_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_targets") as batch_op:
        batch_op.add_column(sa.Column("plan_status", sa.String(length=20), nullable=False, server_default="idle"))
        batch_op.add_column(sa.Column("plan_error", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("plan_started_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_job_targets_plan_status", ["plan_status"])

    with op.batch_alter_table("resume_tailoring_drafts") as batch_op:
        batch_op.add_column(sa.Column("error_message", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("generation_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("generation_completed_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE job_targets SET plan_status='ready' WHERE plan_generated_at IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("resume_tailoring_drafts") as batch_op:
        batch_op.drop_column("generation_completed_at")
        batch_op.drop_column("generation_started_at")
        batch_op.drop_column("error_message")
    with op.batch_alter_table("job_targets") as batch_op:
        batch_op.drop_index("ix_job_targets_plan_status")
        batch_op.drop_column("plan_started_at")
        batch_op.drop_column("plan_error")
        batch_op.drop_column("plan_status")
