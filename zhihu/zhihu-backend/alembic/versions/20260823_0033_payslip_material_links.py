"""Allow one payslip to link multiple offers and contracts.

Revision ID: 20260823_0033
Revises: 20260823_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0033"
down_revision = "20260823_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payslip_material_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("payslip_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "(offer_id IS NOT NULL AND contract_id IS NULL) OR (offer_id IS NULL AND contract_id IS NOT NULL)",
            name="ck_payslip_material_exactly_one",
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payslip_id"], ["payslips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payslip_id", "contract_id", name="uq_payslip_material_contract"),
        sa.UniqueConstraint("payslip_id", "offer_id", name="uq_payslip_material_offer"),
    )
    op.create_index("ix_payslip_material_links_payslip_id", "payslip_material_links", ["payslip_id"])
    op.create_index("ix_payslip_material_offer", "payslip_material_links", ["offer_id"])
    op.create_index("ix_payslip_material_contract", "payslip_material_links", ["contract_id"])
    op.execute(
        "INSERT INTO payslip_material_links (payslip_id, offer_id) "
        "SELECT id, linked_offer_id FROM payslips WHERE linked_offer_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("payslip_material_links")
