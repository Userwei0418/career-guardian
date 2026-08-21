"""Add privacy and model metadata to labor contract review snapshots.

Revision ID: 20260821_0026
Revises: 20260820_0025
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0026"
down_revision = "20260820_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contract_review_snapshots") as batch_op:
        batch_op.add_column(sa.Column("clause_segments", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("provider_name", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("model_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("redaction_version", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("ai_status", sa.String(length=30), server_default="not_requested", nullable=False)
        )
        batch_op.add_column(
            sa.Column("ai_input_clause_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("redaction_report", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contract_review_snapshots") as batch_op:
        batch_op.drop_column("redaction_report")
        batch_op.drop_column("ai_input_clause_count")
        batch_op.drop_column("ai_status")
        batch_op.drop_column("redaction_version")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("model_name")
        batch_op.drop_column("provider_name")
        batch_op.drop_column("clause_segments")
