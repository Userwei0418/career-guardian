"""Add version control and optimistic locking to contract_files

Revision ID: 20260714_161401
Revises: 20260402_0012_add_contract_upload_versions
Create Date: 2026-07-14T16:14:01.683163
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260714_161401"
down_revision = "20260402_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contract_files", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("contract_files", sa.Column("locked_by_id", sa.Integer(), nullable=True))
    op.add_column("contract_files", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contract_files", sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="false"))
    op.create_foreign_key(
        "fk_contract_files_locked_by_id_users",
        "contract_files",
        "users",
        ["locked_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contract_files_version", "contract_files", ["version"])


def downgrade() -> None:
    op.drop_index("ix_contract_files_version", table_name="contract_files")
    op.drop_constraint("fk_contract_files_locked_by_id_users", "contract_files", type_="foreignkey")
    op.drop_column("contract_files", "is_locked")
    op.drop_column("contract_files", "locked_at")
    op.drop_column("contract_files", "locked_by_id")
    op.drop_column("contract_files", "version")