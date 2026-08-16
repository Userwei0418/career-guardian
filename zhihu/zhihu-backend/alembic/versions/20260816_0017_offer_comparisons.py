"""Persist Offer comparison snapshots.

Revision ID: 20260816_0017
Revises: 20260816_0016
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0017"
down_revision = "20260816_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "offer_comparisons" in inspector.get_table_names():
        return
    op.create_table(
        "offer_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_a_id", sa.Integer(), sa.ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("offer_b_id", sa.Integer(), sa.ForeignKey("offers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="current"),
        sa.Column("preference_snapshot", sa.JSON(), nullable=False),
        sa.Column("assumption_snapshot", sa.JSON(), nullable=False),
        sa.Column("offer_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    for name, column in (
        ("ix_offer_comparisons_user_id", "user_id"),
        ("ix_offer_comparisons_offer_a_id", "offer_a_id"),
        ("ix_offer_comparisons_offer_b_id", "offer_b_id"),
        ("ix_offer_comparisons_status", "status"),
    ):
        op.create_index(name, "offer_comparisons", [column], unique=False)


def downgrade() -> None:
    if "offer_comparisons" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("offer_comparisons")
