"""Persist user-confirmed agreed pay-date provenance.

Revision ID: 20260823_0049
Revises: 20260823_0048
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0049"
down_revision = "20260823_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payslips", sa.Column("agreed_pay_date_source_type", sa.String(30), nullable=True))
    op.add_column("payslips", sa.Column("agreed_pay_date_source_contract_id", sa.Integer(), nullable=True))
    op.add_column("payslips", sa.Column("agreed_pay_date_schedule", sa.String(50), nullable=True))
    op.add_column("payslips", sa.Column("agreed_pay_date_adjustment", sa.String(30), nullable=True))
    op.add_column("payslips", sa.Column("agreed_pay_date_calendar_version", sa.String(80), nullable=True))
    op.create_foreign_key(
        "fk_payslips_agreed_date_source_contract",
        "payslips",
        "contracts",
        ["agreed_pay_date_source_contract_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_payslip_agreed_date_source_type",
        "payslips",
        "agreed_pay_date_source_type IS NULL OR agreed_pay_date_source_type IN ('manual', 'material_suggestion')",
    )
    op.create_check_constraint(
        "ck_payslip_agreed_date_adjustment",
        "payslips",
        "agreed_pay_date_adjustment IS NULL OR agreed_pay_date_adjustment IN ('contract_date', 'advance', 'defer')",
    )
    op.create_index(
        "ix_payslip_agreed_date_source_contract",
        "payslips",
        ["agreed_pay_date_source_contract_id"],
        unique=False,
    )
    op.execute(
        "UPDATE payslips SET agreed_pay_date_source_type = 'manual' "
        "WHERE agreed_pay_date IS NOT NULL AND agreed_pay_date_source_type IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_payslip_agreed_date_adjustment", "payslips", type_="check")
    op.drop_constraint("ck_payslip_agreed_date_source_type", "payslips", type_="check")
    op.drop_constraint("fk_payslips_agreed_date_source_contract", "payslips", type_="foreignkey")
    # MySQL uses this explicit index to enforce the foreign key.  The
    # constraint must be removed first or DROP INDEX fails with error 1553.
    op.drop_index("ix_payslip_agreed_date_source_contract", table_name="payslips")
    op.drop_column("payslips", "agreed_pay_date_calendar_version")
    op.drop_column("payslips", "agreed_pay_date_adjustment")
    op.drop_column("payslips", "agreed_pay_date_schedule")
    op.drop_column("payslips", "agreed_pay_date_source_contract_id")
    op.drop_column("payslips", "agreed_pay_date_source_type")
