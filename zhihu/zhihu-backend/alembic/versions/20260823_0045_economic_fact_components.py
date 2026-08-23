"""Add category details for split economic fact components.

Revision ID: 20260823_0045
Revises: 20260823_0044
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0045"
down_revision = "20260823_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("economic_facts", sa.Column("category_id", sa.Integer(), nullable=True))
    op.add_column("economic_facts", sa.Column("nature", sa.String(length=30), nullable=True))
    op.add_column("economic_facts", sa.Column("description", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_economic_facts_category_id",
        "economic_facts",
        "financial_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_economic_facts_category_id", "economic_facts", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_economic_facts_category_id", table_name="economic_facts")
    op.drop_constraint("fk_economic_facts_category_id", "economic_facts", type_="foreignkey")
    op.drop_column("economic_facts", "description")
    op.drop_column("economic_facts", "nature")
    op.drop_column("economic_facts", "category_id")
