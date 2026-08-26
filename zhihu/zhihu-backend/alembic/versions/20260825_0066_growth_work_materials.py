"""Add evidence-led work materials, routing, and quadrant placement.

Revision ID: 20260825_0066
Revises: 20260825_0065
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260825_0066"
down_revision = "20260825_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "growth_work_items",
        sa.Column("priority_axis", sa.String(length=20), server_default="unknown", nullable=False),
    )
    op.add_column(
        "growth_work_items",
        sa.Column("progress_health", sa.String(length=20), server_default="unknown", nullable=False),
    )
    op.add_column(
        "growth_work_items",
        sa.Column("quadrant", sa.String(length=20), server_default="unknown", nullable=False),
    )
    op.add_column(
        "growth_work_items",
        sa.Column("placement_rule_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "growth_work_items",
        sa.Column("placement_updated_at", sa.DateTime(), nullable=True),
    )
    op.create_check_constraint(
        "ck_growth_work_items_priority_axis",
        "growth_work_items",
        "priority_axis IN ('high', 'low', 'unknown')",
    )
    op.create_check_constraint(
        "ck_growth_work_items_progress_health",
        "growth_work_items",
        "progress_health IN ('healthy', 'at_risk', 'unknown')",
    )
    op.create_check_constraint(
        "ck_growth_work_items_quadrant",
        "growth_work_items",
        "quadrant IN ('focus', 'breakthrough', 'maintain', 'clarify', 'unknown')",
    )

    op.create_table(
        "growth_work_materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("material_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("occurred_at_precision", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("source_document_id", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("analysis_rule_version", sa.String(length=80), nullable=False),
        sa.Column("ai_requested", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("external_processing_used", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("fallback_reason", sa.String(length=100), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "material_type IN ('meeting_minutes', 'transcript', 'note', 'proposal', 'plan', 'other')",
            name="ck_growth_work_materials_type",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_materials_analysis_mode",
        ),
        sa.CheckConstraint(
            "occurred_at_precision IN ('unknown', 'date', 'datetime')",
            name="ck_growth_work_materials_occurred_precision",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_growth_work_material_owner_hash"),
    )
    op.create_index(
        "ix_growth_work_materials_owner_occurred",
        "growth_work_materials",
        ["user_id", "occurred_at", "created_at"],
    )
    op.create_index(
        "ix_growth_work_materials_owner_source",
        "growth_work_materials",
        ["user_id", "source_document_id"],
    )

    op.create_table(
        "growth_work_material_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('create_analyze', 'confirm')",
            name="ck_growth_work_material_requests_operation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_growth_work_material_request_owner"),
    )
    op.create_index(
        "ix_growth_work_material_requests_owner_material",
        "growth_work_material_requests",
        ["user_id", "material_id"],
    )

    op.create_table(
        "growth_work_material_statements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("statement_key", sa.String(length=80), nullable=False),
        sa.Column("statement_type", sa.String(length=30), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "statement_type IN ('confirmed_fact', 'decision', 'proposal', 'open_question', 'vendor_claim', 'scope_change', 'action', 'conflict')",
            name="ck_growth_work_material_statements_type",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_work_material_statements_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_material_statements_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "statement_key", name="uq_growth_work_material_statement_key"),
    )
    op.create_index(
        "ix_growth_work_material_statements_owner_material_status",
        "growth_work_material_statements",
        ["user_id", "material_id", "status"],
    )

    op.create_table(
        "growth_work_material_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("link_type", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        sa.Column("proposed_node_status", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_type IN ('work_item', 'node')", name="ck_growth_work_material_links_target_type"),
        sa.CheckConstraint(
            "(target_type = 'work_item' AND node_id IS NULL AND target_id = work_item_id) OR "
            "(target_type = 'node' AND node_id IS NOT NULL AND target_id = node_id)",
            name="ck_growth_work_material_links_target_consistency",
        ),
        sa.CheckConstraint(
            "link_type IN ('confirmed_fact', 'decision', 'proposal', 'open_question', 'vendor_claim', 'scope_change', 'action', 'conflict', 'context')",
            name="ck_growth_work_material_links_link_type",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_work_material_links_status",
        ),
        sa.CheckConstraint(
            "proposed_node_status IS NULL OR proposed_node_status IN ('planned', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="ck_growth_work_material_links_node_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_material_links_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["growth_work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["growth_work_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "target_type",
            "target_id",
            "link_type",
            name="uq_growth_work_material_link_target",
        ),
    )
    op.create_index(
        "ix_growth_work_material_links_owner_item_status",
        "growth_work_material_links",
        ["user_id", "work_item_id", "status"],
    )
    op.create_index(
        "ix_growth_work_material_links_owner_material",
        "growth_work_material_links",
        ["user_id", "material_id"],
    )

    op.create_table(
        "growth_work_material_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("related_material_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('derived_from', 'same_event_version', 'supersedes', 'references')",
            name="ck_growth_work_material_relations_type",
        ),
        sa.CheckConstraint(
            "material_id <> related_material_id",
            name="ck_growth_work_material_relations_distinct",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "related_material_id",
            "relation_type",
            name="uq_growth_work_material_relation",
        ),
    )
    op.create_index(
        "ix_growth_work_material_relations_owner_material",
        "growth_work_material_relations",
        ["user_id", "material_id"],
    )

    op.create_table(
        "growth_work_placement_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("priority_axis", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("progress_health", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("quadrant", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("base_work_item_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "priority_axis IN ('high', 'low', 'unknown')",
            name="ck_growth_work_placement_priority",
        ),
        sa.CheckConstraint(
            "progress_health IN ('healthy', 'at_risk', 'unknown')",
            name="ck_growth_work_placement_health",
        ),
        sa.CheckConstraint(
            "quadrant IN ('focus', 'breakthrough', 'maintain', 'clarify', 'unknown')",
            name="ck_growth_work_placement_quadrant",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_work_placement_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_placement_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["growth_work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "work_item_id",
            "rule_version",
            name="uq_growth_work_placement_material_item_rule",
        ),
    )
    op.create_index(
        "ix_growth_work_placement_owner_item_status",
        "growth_work_placement_events",
        ["user_id", "work_item_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("growth_work_placement_events")
    op.drop_table("growth_work_material_relations")
    op.drop_table("growth_work_material_links")
    op.drop_table("growth_work_material_statements")
    op.drop_table("growth_work_material_requests")
    op.drop_table("growth_work_materials")
    op.drop_constraint("ck_growth_work_items_quadrant", "growth_work_items", type_="check")
    op.drop_constraint("ck_growth_work_items_progress_health", "growth_work_items", type_="check")
    op.drop_constraint("ck_growth_work_items_priority_axis", "growth_work_items", type_="check")
    op.drop_column("growth_work_items", "placement_updated_at")
    op.drop_column("growth_work_items", "placement_rule_version")
    op.drop_column("growth_work_items", "quadrant")
    op.drop_column("growth_work_items", "progress_health")
    op.drop_column("growth_work_items", "priority_axis")
