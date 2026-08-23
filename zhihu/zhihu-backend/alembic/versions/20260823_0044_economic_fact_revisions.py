"""Add economic fact revision history.

Revision ID: 20260823_0044
Revises: 20260823_0043
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0044"
down_revision = "20260823_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "economic_fact_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=False),
        sa.Column("fact_revision", sa.Integer(), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fact_id"], ["economic_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fact_id",
            "fact_revision",
            name="uq_economic_fact_revision_number",
        ),
    )
    op.create_index(
        "ix_economic_fact_revisions_owner_created",
        "economic_fact_revisions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # Dropping the table removes its indexes.  MySQL may also use this index
    # for the user_id foreign key and refuses a standalone DROP INDEX first.
    op.drop_table("economic_fact_revisions")
