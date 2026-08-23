"""Link payslip arrivals to concrete economic facts.

Revision ID: 20260823_0046
Revises: 20260823_0045
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0046"
down_revision = "20260823_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payslip_arrival_links",
        sa.Column("economic_fact_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "payslip_arrival_links",
        sa.Column("ledger_revision", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payslip_arrival_links_economic_fact_id",
        "payslip_arrival_links",
        "economic_facts",
        ["economic_fact_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Preserve an existing relationship only when its source transaction maps
    # to exactly one active fact. This also covers a transaction that has become
    # corroborating evidence for another fact. An already-split transaction is
    # deliberately left unresolved: the migration must not guess which component
    # represents salary.
    op.execute(
        "UPDATE payslip_arrival_links pal "
        "JOIN ("
        "SELECT efa.transaction_id, MIN(efa.fact_id) AS fact_id "
        "FROM economic_fact_allocations efa "
        "JOIN economic_facts ef ON ef.id = efa.fact_id "
        "WHERE efa.status = 'confirmed' AND ef.status = 'confirmed' "
        "GROUP BY efa.transaction_id "
        "HAVING COUNT(DISTINCT efa.fact_id) = 1"
        ") resolved ON resolved.transaction_id = pal.transaction_id "
        "SET pal.economic_fact_id = resolved.fact_id "
        "WHERE pal.economic_fact_id IS NULL"
    )
    op.drop_constraint(
        "uq_payslip_arrival_transaction",
        "payslip_arrival_links",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_payslip_arrival_fact",
        "payslip_arrival_links",
        ["payslip_id", "economic_fact_id"],
    )
    op.create_index(
        "ix_payslip_arrival_fact",
        "payslip_arrival_links",
        ["economic_fact_id", "status"],
    )
    op.create_table(
        "payslip_arrival_link_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("link_revision", sa.Integer(), nullable=False),
        sa.Column("ledger_revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["link_id"], ["payslip_arrival_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "link_id",
            "link_revision",
            name="uq_payslip_arrival_link_revision_number",
        ),
    )
    op.create_index(
        "ix_payslip_arrival_link_revisions_owner_created",
        "payslip_arrival_link_revisions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("payslip_arrival_link_revisions")
    op.drop_constraint("uq_payslip_arrival_fact", "payslip_arrival_links", type_="unique")
    op.drop_constraint(
        "fk_payslip_arrival_links_economic_fact_id",
        "payslip_arrival_links",
        type_="foreignkey",
    )
    # MySQL requires the supporting index while the foreign key exists.
    op.drop_index("ix_payslip_arrival_fact", table_name="payslip_arrival_links")
    op.create_unique_constraint(
        "uq_payslip_arrival_transaction",
        "payslip_arrival_links",
        ["payslip_id", "transaction_id"],
    )
    op.drop_column("payslip_arrival_links", "ledger_revision")
    op.drop_column("payslip_arrival_links", "economic_fact_id")
