"""Add confirmed nodes for long-running Growth Guardian work items.

Revision ID: 20260825_0065
Revises: 20260825_0064
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260825_0065"
down_revision = "20260825_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "growth_work_updates",
        "content",
        existing_type=sa.Text(),
        type_=mysql.MEDIUMTEXT(),
        existing_nullable=False,
    )
    op.add_column("growth_work_items", sa.Column("resource_links", sa.JSON(), nullable=True))
    op.add_column("growth_work_items", sa.Column("open_questions", sa.JSON(), nullable=True))
    op.add_column("growth_work_items", sa.Column("tracking_rule", sa.Text(), nullable=True))
    op.add_column("growth_work_updates", sa.Column("node_suggestions", sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE growth_work_items SET resource_links = JSON_ARRAY() WHERE resource_links IS NULL"))
    op.execute(sa.text("UPDATE growth_work_items SET open_questions = JSON_ARRAY() WHERE open_questions IS NULL"))
    op.execute(sa.text("UPDATE growth_work_updates SET node_suggestions = JSON_ARRAY() WHERE node_suggestions IS NULL"))
    op.alter_column("growth_work_items", "resource_links", existing_type=sa.JSON(), nullable=False)
    op.alter_column("growth_work_items", "open_questions", existing_type=sa.JSON(), nullable=False)
    op.alter_column("growth_work_updates", "node_suggestions", existing_type=sa.JSON(), nullable=False)
    op.create_table(
        "growth_work_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("node_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="planned", nullable=False),
        sa.Column("priority_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("depends_on_node_keys", sa.JSON(), nullable=False),
        sa.Column("time_hint", sa.String(length=200), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("source_update_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="ck_growth_work_nodes_status",
        ),
        sa.CheckConstraint(
            "source IN ('intake', 'manual', 'work_update')",
            name="ck_growth_work_nodes_source",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["growth_work_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_update_id"],
            ["growth_work_updates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "work_item_id",
            "node_key",
            name="uq_growth_work_node_item_key",
        ),
        sa.UniqueConstraint(
            "user_id",
            "request_id",
            name="uq_growth_work_node_owner_request",
        ),
    )
    op.create_index(
        "ix_growth_work_nodes_owner_item_status",
        "growth_work_nodes",
        ["user_id", "work_item_id", "status", "priority_order"],
    )
    op.create_table(
        "growth_work_node_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("work_update_id", sa.Integer(), nullable=False),
        sa.Column("relation_kind", sa.String(length=20), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("analysis_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "relation_kind IN ('context', 'progress', 'blocker', 'completion')",
            name="ck_growth_work_node_evidence_relation",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_work_node_evidence_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_node_evidence_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["growth_work_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_update_id"],
            ["growth_work_updates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id",
            "work_update_id",
            "relation_kind",
            name="uq_growth_work_node_evidence_relation",
        ),
    )
    op.create_index(
        "ix_growth_work_node_evidence_owner_node_status",
        "growth_work_node_evidence",
        ["user_id", "node_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("growth_work_node_evidence")
    op.drop_table("growth_work_nodes")
    op.drop_column("growth_work_updates", "node_suggestions")
    op.drop_column("growth_work_items", "tracking_rule")
    op.drop_column("growth_work_items", "open_questions")
    op.drop_column("growth_work_items", "resource_links")
    op.alter_column(
        "growth_work_updates",
        "content",
        existing_type=mysql.MEDIUMTEXT(),
        type_=sa.Text(),
        existing_nullable=False,
    )
