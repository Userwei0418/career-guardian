"""Add economic fact relation revision history.

Revision ID: 20260823_0042
Revises: 20260823_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0042"
down_revision = "20260823_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "economic_fact_relation_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("relation_id", sa.Integer(), nullable=False),
        sa.Column("relation_revision", sa.Integer(), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relation_id"], ["economic_fact_relations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "relation_id",
            "relation_revision",
            name="uq_economic_fact_relation_revision_number",
        ),
    )
    op.create_index(
        "ix_economic_fact_relation_revisions_owner_created",
        "economic_fact_relation_revisions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_economic_fact_relation_revisions_owner_created",
        table_name="economic_fact_relation_revisions",
    )
    op.drop_table("economic_fact_relation_revisions")
