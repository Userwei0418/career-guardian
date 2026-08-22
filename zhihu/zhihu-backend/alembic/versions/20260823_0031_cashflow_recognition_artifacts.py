"""Persist resumable cashflow recognition artifacts without whole uploads.

Revision ID: 20260823_0031
Revises: 20260822_0030
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260823_0031"
down_revision = "20260822_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_personal_attachment_id_owner",
        "personal_attachment_versions",
        ["id", "user_id"],
    )
    op.create_table(
        "financial_recognition_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(length=30), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
        sa.Column("content_text", mysql.MEDIUMTEXT(), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("attachment_version_id", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column("artifact_metadata", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "artifact_type IN ('tabular_manifest', 'normalized_rows', 'ocr_text', 'image_slice', 'pdf_page')",
            name="ck_fin_recognition_artifact_type",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'failed')",
            name="ck_fin_recognition_artifact_status",
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name="ck_fin_recognition_artifact_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["financial_import_batches.id", "financial_import_batches.user_id"],
            name="fk_fin_recognition_artifact_batch_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["attachment_version_id", "user_id"],
            ["personal_attachment_versions.id", "personal_attachment_versions.user_id"],
            name="fk_fin_recognition_artifact_attachment_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "artifact_type",
            "sequence_number",
            name="uq_fin_recognition_artifact_sequence",
        ),
    )
    op.create_index(
        "ix_fin_recognition_artifacts_owner_batch",
        "financial_recognition_artifacts",
        ["user_id", "batch_id", "artifact_type", "sequence_number"],
    )
    op.create_index(
        "ix_fin_recognition_artifacts_attachment",
        "financial_recognition_artifacts",
        ["attachment_version_id"],
    )


def downgrade() -> None:
    op.drop_table("financial_recognition_artifacts")
    op.drop_constraint(
        "uq_personal_attachment_id_owner",
        "personal_attachment_versions",
        type_="unique",
    )
