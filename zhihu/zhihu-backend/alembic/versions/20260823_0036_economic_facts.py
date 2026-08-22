"""Create economic facts, transaction allocations and fact relations.

Revision ID: 20260823_0036
Revises: 20260823_0035
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0036"
down_revision = "20260823_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "economic_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("primary_transaction_id", sa.Integer(), nullable=True),
        sa.Column("fact_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("occurred_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["primary_transaction_id"], ["financial_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("primary_transaction_id", name="uq_economic_fact_primary_transaction"),
    )
    op.create_index("ix_economic_facts_owner_date", "economic_facts", ["user_id", "occurred_date", "status", "fact_type"])
    op.create_table(
        "economic_fact_allocations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fact_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="primary"),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fact_id"], ["economic_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["financial_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_id", "transaction_id", name="uq_economic_fact_allocation"),
    )
    op.create_index("ix_economic_fact_allocations_fact_id", "economic_fact_allocations", ["fact_id"])
    op.create_index("ix_economic_fact_allocations_transaction", "economic_fact_allocations", ["transaction_id", "status"])
    op.create_table(
        "economic_fact_relations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_fact_id", sa.Integer(), nullable=False),
        sa.Column("target_fact_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("detection_method", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("source_fact_id <> target_fact_id", name="ck_economic_fact_relation_distinct"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_fact_id"], ["economic_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_fact_id"], ["economic_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_fact_id", "target_fact_id", "relation_type", name="uq_economic_fact_relation_pair"),
    )
    op.create_index("ix_economic_fact_relations_owner", "economic_fact_relations", ["user_id", "status", "relation_type"])

    op.execute(
        "INSERT INTO economic_facts "
        "(user_id, primary_transaction_id, fact_type, title, occurred_date, amount, currency, status) "
        "SELECT user_id, id, "
        "CASE WHEN direction = 'transfer' THEN 'transfer' "
        "WHEN direction = 'expense' AND nature = 'reimbursable' THEN 'reimbursable_expense' "
        "ELSE direction END, "
        "COALESCE(NULLIF(merchant, ''), NULLIF(description, ''), "
        "CASE WHEN direction = 'income' THEN '收入' WHEN direction = 'expense' THEN '支出' ELSE '转账' END), "
        "transaction_date, amount, currency, 'confirmed' "
        "FROM financial_transactions WHERE status = 'confirmed' AND deleted_at IS NULL"
    )
    op.execute(
        "INSERT INTO economic_fact_allocations "
        "(fact_id, transaction_id, role, allocated_amount, status, reasons, confirmed_by_user_id) "
        "SELECT ef.id, ft.id, 'primary', ft.amount, 'confirmed', NULL, ft.user_id "
        "FROM economic_facts ef JOIN financial_transactions ft ON ft.id = ef.primary_transaction_id"
    )


def downgrade() -> None:
    op.drop_table("economic_fact_relations")
    op.drop_table("economic_fact_allocations")
    op.drop_table("economic_facts")
