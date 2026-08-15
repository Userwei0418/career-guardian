"""add versioned personal attachments and structured resume profiles

Revision ID: 20260816_0006
Revises: 20260816_0005
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0006"
down_revision = "20260816_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_attachment_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("logical_key", sa.String(100), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(150), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id",
            "document_type",
            "logical_key",
            "version_number",
            name="uq_personal_attachment_version",
        ),
    )
    op.create_index("ix_personal_attachment_versions_user_id", "personal_attachment_versions", ["user_id"])
    op.create_index("ix_personal_attachment_versions_document_type", "personal_attachment_versions", ["document_type"])
    op.create_index("ix_personal_attachment_versions_content_hash", "personal_attachment_versions", ["content_hash"])
    op.create_index("ix_personal_attachment_versions_is_active", "personal_attachment_versions", ["is_active"])

    op.add_column("resume_versions", sa.Column("attachment_version_id", sa.Integer(), nullable=True))
    op.add_column("resume_versions", sa.Column("structured_profile", sa.JSON(), nullable=True))
    op.add_column(
        "resume_versions",
        sa.Column("profile_parse_mode", sa.String(20), nullable=False, server_default="rules"),
    )
    op.add_column("resume_versions", sa.Column("profile_parse_model", sa.String(200), nullable=True))
    op.add_column("resume_versions", sa.Column("profile_parsed_at", sa.DateTime(), nullable=True))
    op.add_column("resume_versions", sa.Column("profile_parse_error", sa.String(500), nullable=True))
    op.execute(sa.text("UPDATE resume_versions SET structured_profile = '{}' WHERE structured_profile IS NULL"))
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.alter_column("structured_profile", existing_type=sa.JSON(), nullable=False)
        batch_op.create_foreign_key(
            "fk_resume_attachment_version",
            "personal_attachment_versions",
            ["attachment_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_resume_versions_attachment_version_id", ["attachment_version_id"])


def downgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.drop_index("ix_resume_versions_attachment_version_id")
        batch_op.drop_constraint("fk_resume_attachment_version", type_="foreignkey")
        batch_op.drop_column("profile_parse_error")
        batch_op.drop_column("profile_parsed_at")
        batch_op.drop_column("profile_parse_model")
        batch_op.drop_column("profile_parse_mode")
        batch_op.drop_column("structured_profile")
        batch_op.drop_column("attachment_version_id")
    op.drop_table("personal_attachment_versions")
