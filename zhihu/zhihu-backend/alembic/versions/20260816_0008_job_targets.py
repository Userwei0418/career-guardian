"""add saved and target jobs with resume tailoring drafts

Revision ID: 20260816_0008
Revises: 20260816_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0008"
down_revision = "20260816_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.add_column(sa.Column("parent_resume_version_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("creation_source", sa.String(length=30), nullable=False, server_default="upload"))
        batch_op.add_column(sa.Column("source_job_id", sa.String(length=100), nullable=True))
        batch_op.create_foreign_key("fk_resume_versions_parent", "resume_versions", ["parent_resume_version_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_resume_versions_parent_resume_version_id", ["parent_resume_version_id"])
        batch_op.create_index("ix_resume_versions_source_job_id", ["source_job_id"])

    op.create_table(
        "job_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="saved"),
        sa.Column("resume_version_id", sa.Integer(), nullable=True),
        sa.Column("job_snapshot", sa.JSON(), nullable=False),
        sa.Column("learning_plan", sa.JSON(), nullable=False),
        sa.Column("plan_mode", sa.String(length=20), nullable=True),
        sa.Column("plan_generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id", name="uq_job_target_user_job"),
    )
    op.create_index("ix_job_targets_user_id", "job_targets", ["user_id"])
    op.create_index("ix_job_targets_job_id", "job_targets", ["job_id"])
    op.create_index("ix_job_targets_status", "job_targets", ["status"])
    op.create_index("ix_job_targets_resume_version_id", "job_targets", ["resume_version_id"])

    op.create_table(
        "resume_tailoring_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_target_id", sa.Integer(), nullable=False),
        sa.Column("source_resume_version_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_resume_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("tailored_text", sa.Text(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("generation_mode", sa.String(length=20), nullable=False, server_default="rules"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["job_target_id"], ["job_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_resume_version_id"], ["resume_versions.id"]),
        sa.ForeignKeyConstraint(["confirmed_resume_version_id"], ["resume_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "job_target_id", "source_resume_version_id", "status"):
        op.create_index(f"ix_resume_tailoring_drafts_{column}", "resume_tailoring_drafts", [column])


def downgrade() -> None:
    op.drop_table("resume_tailoring_drafts")
    op.drop_table("job_targets")
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.drop_index("ix_resume_versions_source_job_id")
        batch_op.drop_index("ix_resume_versions_parent_resume_version_id")
        batch_op.drop_constraint("fk_resume_versions_parent", type_="foreignkey")
        batch_op.drop_column("source_job_id")
        batch_op.drop_column("creation_source")
        batch_op.drop_column("parent_resume_version_id")
