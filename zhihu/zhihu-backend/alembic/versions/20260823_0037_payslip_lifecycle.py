"""Add payslip revision and recoverable deletion lifecycle.

Revision ID: 20260823_0037
Revises: 20260823_0036
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0037"
down_revision = "20260823_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payslips", sa.Column("supersedes_payslip_id", sa.Integer(), nullable=True))
    op.add_column(
        "payslips",
        sa.Column("record_status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("payslips", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_payslips_supersedes_payslip_id",
        "payslips",
        "payslips",
        ["supersedes_payslip_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_payslips_supersedes_payslip_id", "payslips", ["supersedes_payslip_id"])
    op.create_index("ix_payslips_record_status", "payslips", ["record_status"])


def downgrade() -> None:
    op.drop_index("ix_payslips_record_status", table_name="payslips")
    op.drop_index("ix_payslips_supersedes_payslip_id", table_name="payslips")
    op.drop_constraint("fk_payslips_supersedes_payslip_id", "payslips", type_="foreignkey")
    op.drop_column("payslips", "deleted_at")
    op.drop_column("payslips", "record_status")
    op.drop_column("payslips", "supersedes_payslip_id")
