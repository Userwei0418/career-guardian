"""Add saved Offer analysis snapshots and decision linkage.

Revision ID: 20260820_0024
Revises: 20260820_0023
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0024"
down_revision = "20260820_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_analysis_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("offer_revision_id", sa.Integer(), nullable=True),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_revision_id"], ["offer_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offer_analysis_snapshots_offer_id", "offer_analysis_snapshots", ["offer_id"], unique=False)
    op.create_index("ix_offer_analysis_snapshots_user_id", "offer_analysis_snapshots", ["user_id"], unique=False)
    op.create_index("ix_offer_analysis_snapshots_offer_revision_id", "offer_analysis_snapshots", ["offer_revision_id"], unique=False)

    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.add_column(sa.Column("analysis_snapshot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_decision_analysis_snapshot",
            "offer_analysis_snapshots",
            ["analysis_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_decision_records_analysis_snapshot_id", ["analysis_snapshot_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.drop_constraint(
            "fk_decision_analysis_snapshot",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_decision_records_analysis_snapshot_id")
        batch_op.drop_column("analysis_snapshot_id")
    op.drop_table("offer_analysis_snapshots")
