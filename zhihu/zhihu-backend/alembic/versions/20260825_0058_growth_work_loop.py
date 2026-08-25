"""Add the first Growth Guardian work loop.

Revision ID: 20260825_0058
Revises: 20260825_0057
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0058"
down_revision = "20260825_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_work_intakes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_payload", sa.JSON(), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled')",
            name="ck_growth_work_intakes_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_intake_owner_request"),
    )
    op.create_index(
        "ix_growth_work_intakes_owner_status",
        "growth_work_intakes",
        ["user_id", "status", "created_at"],
    )

    op.create_table(
        "growth_work_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("intake_id", sa.Integer(), nullable=False),
        sa.Column("career_event_id", sa.Integer(), nullable=True),
        sa.Column("candidate_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fact_excerpt", sa.Text(), nullable=True),
        sa.Column("impact_level", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("energy_level", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("priority_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("selection_reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("reportable", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('captured', 'planned', 'in_progress', 'blocked', 'completed', 'deferred', 'cancelled')",
            name="ck_growth_work_items_status",
        ),
        sa.CheckConstraint(
            "impact_level IN ('high', 'medium', 'low', 'unknown')",
            name="ck_growth_work_items_impact",
        ),
        sa.CheckConstraint(
            "energy_level IN ('high', 'medium', 'low', 'unknown')",
            name="ck_growth_work_items_energy",
        ),
        sa.ForeignKeyConstraint(["career_event_id"], ["career_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["intake_id"], ["growth_work_intakes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intake_id", "candidate_key", name="uq_growth_work_item_intake_candidate"),
    )
    op.create_index(
        "ix_growth_work_items_owner_status",
        "growth_work_items",
        ["user_id", "status", "priority_order"],
    )
    op.create_index(
        "ix_growth_work_items_owner_due",
        "growth_work_items",
        ["user_id", "due_at"],
    )

    op.create_table(
        "growth_emotion_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("intake_id", sa.Integer(), nullable=False),
        sa.Column("encrypted_content", sa.Text(), nullable=False),
        sa.Column("deidentified_fact", sa.Text(), nullable=True),
        sa.Column("privacy_level", sa.String(length=30), server_default="private", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "privacy_level IN ('private', 'private_deidentified')",
            name="ck_growth_emotion_notes_privacy",
        ),
        sa.ForeignKeyConstraint(["intake_id"], ["growth_work_intakes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("intake_id", name="uq_growth_emotion_note_intake"),
    )
    op.create_index(
        "ix_growth_emotion_notes_owner_created",
        "growth_emotion_notes",
        ["user_id", "created_at"],
    )

    op.create_table(
        "growth_work_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("situation", sa.Text(), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=200), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="structured", nullable=False),
        sa.Column("visibility", sa.String(length=30), server_default="private", nullable=False),
        sa.Column("reportable", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("evidence_gaps", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('captured', 'structured', 'confirmed', 'needs_more_evidence', 'discarded', 'archived')",
            name="ck_growth_work_events_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'reportable', 'career_asset')",
            name="ck_growth_work_events_visibility",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["growth_work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_item_id", name="uq_growth_work_event_work_item"),
    )
    op.create_index(
        "ix_growth_work_events_owner_status",
        "growth_work_events",
        ["user_id", "status", "occurred_on"],
    )

    op.create_table(
        "growth_weekly_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("included_event_ids", sa.JSON(), nullable=False),
        sa.Column("generated_content", sa.Text(), nullable=False),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'reviewed', 'exported', 'archived')",
            name="ck_growth_weekly_reports_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "week_start", "version", name="uq_growth_weekly_report_version"),
    )
    op.create_index(
        "ix_growth_weekly_reports_owner_week",
        "growth_weekly_reports",
        ["user_id", "week_start", "version"],
    )

    op.create_table(
        "growth_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("before_payload", sa.JSON(), nullable=True),
        sa.Column("after_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_growth_audit_owner_created",
        "growth_audit_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_growth_audit_entity",
        "growth_audit_events",
        ["entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("growth_audit_events")
    op.drop_table("growth_weekly_reports")
    op.drop_table("growth_work_events")
    op.drop_table("growth_emotion_notes")
    op.drop_table("growth_work_items")
    op.drop_table("growth_work_intakes")
