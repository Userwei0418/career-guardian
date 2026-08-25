"""Add Growth Guardian communication drafts and cross-domain handoffs.

Revision ID: 20260825_0061
Revises: 20260825_0060
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0061"
down_revision = "20260825_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_communication_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("supersedes_draft_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("draft_key", sa.String(length=180), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("audience", sa.String(length=200), nullable=False),
        sa.Column("scene", sa.String(length=100), nullable=False),
        sa.Column("goal", sa.String(length=500), nullable=False),
        sa.Column("known_facts", sa.JSON(), nullable=False),
        sa.Column("tone", sa.String(length=100), nullable=False),
        sa.Column("fact_questions", sa.JSON(), nullable=False),
        sa.Column("strategies", sa.JSON(), nullable=False),
        sa.Column("risk_notes", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("data_scope", sa.JSON(), nullable=False),
        sa.Column("generated_content", sa.Text(), nullable=False),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'reviewed', 'exported', 'archived', 'superseded')", name="ck_growth_communication_drafts_status"),
        sa.CheckConstraint("analysis_mode IN ('rules', 'ai')", name="ck_growth_communication_drafts_mode"),
        sa.ForeignKeyConstraint(["supersedes_draft_id"], ["growth_communication_drafts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_communication_owner_request"),
        sa.UniqueConstraint("user_id", "draft_key", "version", name="uq_growth_communication_owner_key_version"),
    )
    op.create_index("ix_growth_communication_owner_status", "growth_communication_drafts", ["user_id", "status", "created_at"])

    op.create_table(
        "growth_handoffs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("target_domain", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content_summary", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("impact_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_domain IN ('opportunity', 'decision', 'rights', 'income', 'resume')", name="ck_growth_handoffs_target_domain"),
        sa.CheckConstraint("source_type IN ('work_event', 'portfolio', 'evidence', 'skill', 'target', 'gap', 'milestone')", name="ck_growth_handoffs_source_type"),
        sa.CheckConstraint("status IN ('proposed', 'confirmed', 'revoked')", name="ck_growth_handoffs_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_handoff_owner_request"),
    )
    op.create_index("ix_growth_handoff_owner_status", "growth_handoffs", ["user_id", "status", "created_at"])
    op.create_index("ix_growth_handoff_target_inbox", "growth_handoffs", ["user_id", "target_domain", "status", "confirmed_at"])

    op.create_table(
        "growth_inquiries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("data_scopes", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("follow_up_questions", sa.JSON(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mode IN ('program', 'ai')", name="ck_growth_inquiries_mode"),
        sa.CheckConstraint("status IN ('completed', 'failed')", name="ck_growth_inquiries_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_inquiry_owner_request"),
    )
    op.create_index("ix_growth_inquiry_owner_created", "growth_inquiries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("growth_inquiries")
    op.drop_table("growth_handoffs")
    op.drop_table("growth_communication_drafts")
