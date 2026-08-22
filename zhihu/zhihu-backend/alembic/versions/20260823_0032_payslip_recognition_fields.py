"""Add complete payslip recognition fields while preserving unknowns.

Revision ID: 20260823_0032
Revises: 20260823_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0032"
down_revision = "20260823_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payslips", sa.Column("pay_date", sa.Date(), nullable=True))
    op.add_column("payslips", sa.Column("employer_name", sa.String(length=255), nullable=True))
    op.add_column("payslips", sa.Column("bonus", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslips", sa.Column("overtime_pay", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslips", sa.Column("attendance_deductions", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslips", sa.Column("meal_deductions", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslips", sa.Column("custom_items", sa.JSON(), nullable=True))
    op.add_column(
        "payslips",
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="manual"),
    )
    op.add_column("payslips", sa.Column("recognition_confidence", sa.Numeric(5, 4), nullable=True))
    op.create_check_constraint(
        "ck_payslips_source_type",
        "payslips",
        "source_type IN ('manual', 'file', 'ocr')",
    )
    op.create_index("ix_payslips_case_pay_month", "payslips", ["case_id", "pay_month"])


def downgrade() -> None:
    op.drop_index("ix_payslips_case_pay_month", table_name="payslips")
    op.drop_constraint("ck_payslips_source_type", "payslips", type_="check")
    op.drop_column("payslips", "recognition_confidence")
    op.drop_column("payslips", "source_type")
    op.drop_column("payslips", "custom_items")
    op.drop_column("payslips", "meal_deductions")
    op.drop_column("payslips", "attendance_deductions")
    op.drop_column("payslips", "overtime_pay")
    op.drop_column("payslips", "bonus")
    op.drop_column("payslips", "employer_name")
    op.drop_column("payslips", "pay_date")
