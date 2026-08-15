"""Add perspective_code and risk_score to review tables

Revision ID: 20260716_0001
Revises: 20260714_161401
Create Date: 2026-07-16T10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260716_0001"
down_revision = "20260714_161401"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # contract_review_results: add perspective_code, risk_score, risk_grade
    op.add_column(
        "contract_review_results",
        sa.Column("perspective_code", sa.String(32), nullable=False, server_default="enterprise"),
    )
    op.add_column(
        "contract_review_results",
        sa.Column("risk_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "contract_review_results",
        sa.Column("risk_grade", sa.String(8), nullable=True),
    )
    # Drop old unique constraint on contract_file_id (find actual name dynamically)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'contract_review_results'::regclass "
            "AND contype = 'u' "
            "AND conname != 'uq_review_result_contract_perspective'"
        )
    )
    for row in result:
        old_name = row[0]
        # Check it's the single-column constraint on contract_file_id
        cols_result = conn.execute(
            sa.text(
                "SELECT a.attname FROM pg_attribute a "
                "JOIN pg_constraint c ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                "WHERE c.conname = :name AND c.conrelid = 'contract_review_results'::regclass"
            ),
            {"name": old_name},
        )
        col_names = [r[0] for r in cols_result]
        if col_names == ["contract_file_id"]:
            op.drop_constraint(old_name, "contract_review_results", type_="unique")
            break

    op.create_unique_constraint(
        "uq_review_result_contract_perspective",
        "contract_review_results",
        ["contract_file_id", "perspective_code"],
    )

    # review_versions: add perspective_code, risk_score, risk_grade
    op.add_column(
        "review_versions",
        sa.Column("perspective_code", sa.String(32), nullable=False, server_default="enterprise"),
    )
    op.add_column(
        "review_versions",
        sa.Column("risk_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "review_versions",
        sa.Column("risk_grade", sa.String(8), nullable=True),
    )


def downgrade() -> None:
    # review_versions
    op.drop_column("review_versions", "risk_grade")
    op.drop_column("review_versions", "risk_score")
    op.drop_column("review_versions", "perspective_code")

    # contract_review_results
    op.drop_constraint(
        "uq_review_result_contract_perspective",
        "contract_review_results",
        type_="unique",
    )
    op.create_unique_constraint(
        "contract_review_results_contract_file_id_key",
        "contract_review_results",
        ["contract_file_id"],
    )
    op.drop_column("contract_review_results", "risk_grade")
    op.drop_column("contract_review_results", "risk_score")
    op.drop_column("contract_review_results", "perspective_code")
