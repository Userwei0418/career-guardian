"""Add human-defined project goals and project-level material effects.

Revision ID: 20260826_0068
Revises: 20260826_0067
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0068"
down_revision = "20260826_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "growth_project_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("account_name", sa.String(length=200), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("success_criteria", sa.JSON(), nullable=False),
        sa.Column("strategy_summary", sa.Text(), nullable=True),
        sa.Column("key_constraints", sa.JSON(), nullable=False),
        sa.Column("next_follow_up_at", sa.DateTime(), nullable=True),
        sa.Column("stale_after_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "stale_after_days BETWEEN 1 AND 365",
            name="ck_growth_project_profiles_stale_after_days",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "account_name",
            "project_name",
            name="uq_growth_project_profile_owner_account_project",
        ),
    )
    op.create_index(
        "ix_growth_project_profile_owner_updated",
        "growth_project_profiles",
        ["user_id", "updated_at"],
    )
    # Preserve the existing account grouping as one provisional project per
    # customer.  The migration must not invent a goal or mark it confirmed;
    # users can later name/split projects and confirm their project profile.
    op.execute(
        """
        INSERT IGNORE INTO growth_project_profiles
            (user_id, account_name, project_name, objective, success_criteria,
             strategy_summary, key_constraints, next_follow_up_at,
             stale_after_days, version, confirmed_at)
        SELECT DISTINCT user_id, account_name, account_name, NULL, JSON_ARRAY(),
               NULL, JSON_ARRAY(), NULL, 14, 1, NULL
        FROM growth_work_items
        WHERE account_name IS NOT NULL AND TRIM(account_name) <> ''
        """
    )
    # Some users may have uploaded materials before confirming any work line.
    # Preserve those customer groupings too, without inventing a goal.
    op.execute(
        """
        INSERT IGNORE INTO growth_project_profiles
            (user_id, account_name, project_name, objective, success_criteria,
             strategy_summary, key_constraints, next_follow_up_at,
             stale_after_days, version, confirmed_at)
        SELECT DISTINCT material.user_id, material.account_name, material.account_name,
               NULL, JSON_ARRAY(), NULL, JSON_ARRAY(), NULL, 14, 1, NULL
        FROM growth_work_materials AS material
        WHERE material.account_name IS NOT NULL
          AND TRIM(material.account_name) <> ''
        """
    )

    op.add_column("growth_work_items", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_growth_work_items_project_id",
        "growth_work_items",
        "growth_project_profiles",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_growth_work_items_owner_project",
        "growth_work_items",
        ["user_id", "project_id", "status"],
    )
    op.execute(
        """
        UPDATE growth_work_items AS item
        JOIN growth_project_profiles AS project
          ON project.user_id = item.user_id
         AND project.account_name = item.account_name
         AND project.project_name = item.account_name
        SET item.project_id = project.id
        WHERE item.account_name IS NOT NULL AND TRIM(item.account_name) <> ''
        """
    )

    op.add_column("growth_work_materials", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_growth_work_materials_project_id",
        "growth_work_materials",
        "growth_project_profiles",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_growth_work_materials_owner_project",
        "growth_work_materials",
        ["user_id", "project_id", "occurred_at"],
    )
    op.execute(
        """
        UPDATE growth_work_materials AS material
        JOIN growth_project_profiles AS project
          ON project.user_id = material.user_id
         AND project.account_name = material.account_name
         AND project.project_name = material.account_name
        SET material.project_id = project.id
        WHERE material.account_name IS NOT NULL AND TRIM(material.account_name) <> ''
        """
    )

    op.create_table(
        "growth_project_progress_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
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
        sa.Column("analysis_mode", sa.String(length=20), server_default="ai", nullable=False),
        sa.Column("rule_version", sa.String(length=80), nullable=False),
        sa.Column("base_project_version", sa.Integer(), nullable=False),
        sa.Column("base_confirmed_event_id", sa.Integer(), nullable=True),
        sa.Column("reportable", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "impact_kind IN ('advanced', 'setback', 'redirected', 'context', 'no_change', 'unknown')",
            name="ck_growth_project_progress_impact",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed', 'dismissed')",
            name="ck_growth_project_progress_status",
        ),
        sa.CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_project_progress_mode",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["growth_project_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["growth_work_materials.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "project_id",
            "rule_version",
            name="uq_growth_project_progress_material_project_rule",
        ),
    )
    op.create_index(
        "ix_growth_project_progress_owner_project_status",
        "growth_project_progress_events",
        ["user_id", "project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_growth_project_progress_owner_material",
        "growth_project_progress_events",
        ["user_id", "material_id"],
    )


def downgrade() -> None:
    op.drop_table("growth_project_progress_events")
    op.drop_index("ix_growth_work_materials_owner_project", table_name="growth_work_materials")
    op.drop_constraint(
        "fk_growth_work_materials_project_id",
        "growth_work_materials",
        type_="foreignkey",
    )
    op.drop_column("growth_work_materials", "project_id")
    op.drop_index("ix_growth_work_items_owner_project", table_name="growth_work_items")
    op.drop_constraint(
        "fk_growth_work_items_project_id",
        "growth_work_items",
        type_="foreignkey",
    )
    op.drop_column("growth_work_items", "project_id")
    op.drop_table("growth_project_profiles")
