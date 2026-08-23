"""Add explicit user-owned payslip material preference metadata.

Revision ID: 20260823_0048
Revises: 20260823_0047
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0048"
down_revision = "20260823_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payslip_material_links",
        sa.Column(
            "application_status",
            sa.String(20),
            nullable=False,
            server_default="unresolved",
        ),
    )
    op.add_column(
        "payslip_material_links",
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "payslip_material_links",
        sa.Column("user_note", sa.String(500), nullable=True),
    )
    op.create_check_constraint(
        "ck_payslip_material_application_status",
        "payslip_material_links",
        "application_status IN ('preferred', 'reference', 'unresolved')",
    )
    op.create_check_constraint(
        "ck_payslip_material_priority_rank",
        "payslip_material_links",
        "priority_rank > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_payslip_material_priority_rank",
        "payslip_material_links",
        type_="check",
    )
    op.drop_constraint(
        "ck_payslip_material_application_status",
        "payslip_material_links",
        type_="check",
    )
    op.drop_column("payslip_material_links", "user_note")
    op.drop_column("payslip_material_links", "priority_rank")
    op.drop_column("payslip_material_links", "application_status")
