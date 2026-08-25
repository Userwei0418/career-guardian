"""Add Growth Guardian past-assets domain.

Revision ID: 20260825_0059
Revises: 20260825_0058
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0059"
down_revision = "20260825_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_portfolio_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_work_event_id", sa.Integer(), nullable=True),
        sa.Column("source_attachment_id", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_label", sa.String(length=300), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("privacy_level", sa.String(length=20), server_default="private", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("unavailable_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("item_type IN ('github', 'project', 'link', 'design', 'article', 'speech', 'certificate', 'feedback', 'attachment', 'other')", name="ck_growth_portfolio_items_type"),
        sa.CheckConstraint("status IN ('draft', 'active', 'unavailable', 'archived')", name="ck_growth_portfolio_items_status"),
        sa.CheckConstraint("privacy_level IN ('private', 'shared', 'public')", name="ck_growth_portfolio_items_privacy"),
        sa.ForeignKeyConstraint(["source_attachment_id"], ["personal_attachment_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_work_event_id"], ["growth_work_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_portfolio_owner_request"),
    )
    op.create_index("ix_growth_portfolio_owner_status", "growth_portfolio_items", ["user_id", "status", "occurred_on"])

    op.create_table(
        "growth_evidence_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("portfolio_item_id", sa.Integer(), nullable=True),
        sa.Column("work_event_id", sa.Integer(), nullable=True),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(length=300), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=True),
        sa.Column("role", sa.String(length=200), nullable=True),
        sa.Column("result_type", sa.String(length=100), nullable=True),
        sa.Column("privacy_level", sa.String(length=20), server_default="private", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="candidate", nullable=False),
        sa.Column("unavailable_reason", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("evidence_type IN ('project_result', 'collaboration', 'leadership', 'customer_feedback', 'public_work', 'certificate', 'method', 'other')", name="ck_growth_evidence_items_type"),
        sa.CheckConstraint("status IN ('candidate', 'confirmed', 'unavailable', 'archived')", name="ck_growth_evidence_items_status"),
        sa.CheckConstraint("privacy_level IN ('private', 'shared', 'public')", name="ck_growth_evidence_items_privacy"),
        sa.ForeignKeyConstraint(["portfolio_item_id"], ["growth_portfolio_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_event_id"], ["growth_work_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_evidence_owner_request"),
    )
    op.create_index("ix_growth_evidence_owner_status", "growth_evidence_items", ["user_id", "status", "occurred_on"])

    op.create_table(
        "growth_skill_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("supersedes_assessment_id", sa.Integer(), nullable=True),
        sa.Column("skill_key", sa.String(length=160), nullable=False),
        sa.Column("skill_name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_layer", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="candidate", nullable=False),
        sa.Column("evidence_sufficiency", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("latest_used_on", sa.Date(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_layer IN ('market_signal', 'ai_candidate', 'user_claimed', 'evidence_confirmed')", name="ck_growth_skill_assessments_layer"),
        sa.CheckConstraint("status IN ('candidate', 'confirmed', 'rejected', 'superseded', 'archived')", name="ck_growth_skill_assessments_status"),
        sa.CheckConstraint("evidence_sufficiency IN ('none', 'partial', 'supported')", name="ck_growth_skill_assessments_sufficiency"),
        sa.ForeignKeyConstraint(["supersedes_assessment_id"], ["growth_skill_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "skill_key", "version", name="uq_growth_skill_owner_key_version"),
    )
    op.create_index("ix_growth_skill_owner_status", "growth_skill_assessments", ["user_id", "status", "skill_key"])

    op.create_table(
        "growth_skill_evidence_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["growth_skill_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["growth_evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "evidence_id", name="uq_growth_skill_evidence_link"),
    )
    op.create_index("ix_growth_skill_evidence_owner", "growth_skill_evidence_links", ["user_id", "assessment_id"])

    op.create_table(
        "growth_reflections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_event_id", sa.Integer(), nullable=True),
        sa.Column("evidence_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("privacy_level", sa.String(length=20), server_default="private", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="prompted", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('prompted', 'answered', 'confirmed', 'archived')", name="ck_growth_reflections_status"),
        sa.CheckConstraint("privacy_level IN ('private', 'shared')", name="ck_growth_reflections_privacy"),
        sa.ForeignKeyConstraint(["evidence_id"], ["growth_evidence_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_event_id"], ["growth_work_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "work_event_id", name="uq_growth_reflection_owner_event"),
    )
    op.create_index("ix_growth_reflections_owner_status", "growth_reflections", ["user_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_table("growth_reflections")
    op.drop_table("growth_skill_evidence_links")
    op.drop_table("growth_skill_assessments")
    op.drop_table("growth_evidence_items")
    op.drop_table("growth_portfolio_items")
