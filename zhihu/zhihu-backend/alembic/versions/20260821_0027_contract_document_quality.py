"""Support long employment documents and persist parsing/review quality.

Revision ID: 20260821_0027
Revises: 20260821_0026
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260821_0027"
down_revision = "20260821_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch_op:
        batch_op.alter_column(
            "raw_text",
            existing_type=sa.Text(),
            type_=mysql.LONGTEXT(),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column("parse_error_code", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("text_page_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ocr_page_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parse_quality", sa.JSON(), nullable=True))

    with op.batch_alter_table("contract_review_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("ai_batch_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("ai_completed_batch_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("coverage_report", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contract_review_snapshots") as batch_op:
        batch_op.drop_column("coverage_report")
        batch_op.drop_column("ai_completed_batch_count")
        batch_op.drop_column("ai_batch_count")

    with op.batch_alter_table("contracts") as batch_op:
        batch_op.drop_column("parse_quality")
        batch_op.drop_column("ocr_page_count")
        batch_op.drop_column("text_page_count")
        batch_op.drop_column("parse_error_code")
        batch_op.alter_column(
            "raw_text",
            existing_type=mysql.LONGTEXT(),
            type_=sa.Text(),
            existing_nullable=True,
        )
