"""Add monotonic ledger revisions and transaction change history.

Revision ID: 20260823_0040
Revises: 20260823_0039
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0040"
down_revision = "20260823_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("financial_ledger_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "financial_ledger_revision_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "revision_number",
            name="uq_financial_ledger_revision_owner_number",
        ),
    )
    op.create_index(
        "ix_financial_ledger_revisions_owner_created",
        "financial_ledger_revision_events",
        ["user_id", "created_at"],
    )
    op.create_table(
        "financial_transaction_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("transaction_revision", sa.Integer(), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=30), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["financial_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "transaction_id",
            "transaction_revision",
            name="uq_financial_transaction_revision_number",
        ),
    )
    op.create_index(
        "ix_financial_transaction_revisions_owner_created",
        "financial_transaction_revisions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_transaction_revisions_owner_created",
        table_name="financial_transaction_revisions",
    )
    op.drop_table("financial_transaction_revisions")
    op.drop_index(
        "ix_financial_ledger_revisions_owner_created",
        table_name="financial_ledger_revision_events",
    )
    op.drop_table("financial_ledger_revision_events")
    op.drop_column("users", "financial_ledger_revision")
