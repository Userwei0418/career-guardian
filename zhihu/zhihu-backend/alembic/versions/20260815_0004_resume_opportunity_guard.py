"""add resume versions and opportunity analyses

Revision ID: 20260815_0004
Revises: 20260815_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0004"
down_revision = "20260815_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extracted_skills", sa.JSON(), nullable=False),
        sa.Column("parse_mode", sa.String(20), nullable=False, server_default="text"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "version_number", name="uq_resume_user_version"),
    )
    op.create_index("ix_resume_versions_user_id", "resume_versions", ["user_id"])
    op.create_index("ix_resume_versions_content_hash", "resume_versions", ["content_hash"])
    op.create_index("ix_resume_versions_is_active", "resume_versions", ["is_active"])

    op.create_table(
        "opportunity_analyses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("career_events.id"), nullable=False, unique=True),
        sa.Column("resume_version_id", sa.Integer(), sa.ForeignKey("resume_versions.id"), nullable=False),
        sa.Column("job_id", sa.String(100), nullable=False),
        sa.Column("analysis_mode", sa.String(20), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("suggestions", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "resume_version_id", "job_id", name="uq_opportunity_analysis_version_job"),
    )
    op.create_index("ix_opportunity_analyses_user_id", "opportunity_analyses", ["user_id"])
    op.create_index("ix_opportunity_analyses_resume_version_id", "opportunity_analyses", ["resume_version_id"])
    op.create_index("ix_opportunity_analyses_job_id", "opportunity_analyses", ["job_id"])


def downgrade() -> None:
    op.drop_table("opportunity_analyses")
    op.drop_table("resume_versions")
