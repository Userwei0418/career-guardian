"""Add stable project profiles and material-led progress events.

Revision ID: 20260826_0067
Revises: 20260825_0066
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0067"
down_revision = "20260825_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("growth_work_items", sa.Column("account_name", sa.String(length=200), nullable=True))
    op.add_column("growth_work_items", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("growth_work_items", sa.Column("success_criteria", sa.JSON(), nullable=True))
    op.add_column("growth_work_items", sa.Column("strategy_summary", sa.Text(), nullable=True))
    op.add_column("growth_work_items", sa.Column("key_constraints", sa.JSON(), nullable=True))
    op.add_column("growth_work_items", sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))
    op.add_column(
        "growth_work_items",
        sa.Column("stale_after_days", sa.Integer(), server_default="14", nullable=False),
    )
    op.execute("UPDATE growth_work_items SET success_criteria = JSON_ARRAY() WHERE success_criteria IS NULL")
    op.execute("UPDATE growth_work_items SET key_constraints = JSON_ARRAY() WHERE key_constraints IS NULL")
    op.alter_column("growth_work_items", "success_criteria", existing_type=sa.JSON(), nullable=False)
    op.alter_column("growth_work_items", "key_constraints", existing_type=sa.JSON(), nullable=False)
    op.create_check_constraint(
        "ck_growth_work_items_stale_after_days",
        "growth_work_items",
        "stale_after_days BETWEEN 1 AND 365",
    )
    op.create_index(
        "ix_growth_work_items_owner_account",
        "growth_work_items",
        ["user_id", "account_name", "status"],
    )

    op.add_column("growth_work_materials", sa.Column("account_name", sa.String(length=200), nullable=True))
    op.add_column("growth_work_materials", sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_growth_work_materials_owner_account",
        "growth_work_materials",
        ["user_id", "account_name", "occurred_at"],
    )

    op.create_table(
        "growth_work_progress_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_item_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("impact_kind", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("causal_reason", sa.Text(), nullable=False),
        sa.Column("previous_state", sa.Text(), nullable=True),
        sa.Column("current_state", sa.Text(), nullable=True),
        sa.Column("next_gap", sa.Text(), nullable=True),
        sa.Column("evidence_spans", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("analysis_mode", sa.String(length=20), server_default="rules", nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("base_work_item_version", sa.Integer(), nullable=False),
        sa.Column("reportable", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "impact_kind IN ('advanced', 'setback', 'redirected', 'context', 'no_change', 'unknown')",
            name="ck_growth_work_progress_impact",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_work_progress_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_work_progress_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["growth_work_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "work_item_id",
            "rule_version",
            name="uq_growth_work_progress_material_item_rule",
        ),
    )
    op.create_index(
        "ix_growth_work_progress_owner_item_status",
        "growth_work_progress_events",
        ["user_id", "work_item_id", "status", "created_at"],
    )
    op.create_index(
        "ix_growth_work_progress_owner_material",
        "growth_work_progress_events",
        ["user_id", "material_id"],
    )


def downgrade() -> None:
    # MySQL may choose the explicit composite indexes above to back the table's
    # foreign-key constraints. Dropping those indexes before the table then
    # fails with error 1553. Dropping the table removes its indexes and foreign
    # keys atomically and is portable across the supported MySQL variants.
    op.drop_table("growth_work_progress_events")

    op.drop_index("ix_growth_work_materials_owner_account", table_name="growth_work_materials")
    op.drop_column("growth_work_materials", "next_follow_up_at")
    op.drop_column("growth_work_materials", "account_name")

    op.drop_index("ix_growth_work_items_owner_account", table_name="growth_work_items")
    op.drop_constraint("ck_growth_work_items_stale_after_days", "growth_work_items", type_="check")
    op.drop_column("growth_work_items", "stale_after_days")
    op.drop_column("growth_work_items", "next_follow_up_at")
    op.drop_column("growth_work_items", "key_constraints")
    op.drop_column("growth_work_items", "strategy_summary")
    op.drop_column("growth_work_items", "success_criteria")
    op.drop_column("growth_work_items", "objective")
    op.drop_column("growth_work_items", "account_name")
