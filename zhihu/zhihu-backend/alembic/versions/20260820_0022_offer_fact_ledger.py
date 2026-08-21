"""Add auditable Offer revisions and fact assertions.

Revision ID: 20260820_0022
Revises: 20260819_0021
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0022"
down_revision = "20260819_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("facts_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_reason", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("supersedes_revision_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_revision_id"], ["offer_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", "revision_no", name="uq_offer_revisions_offer_no"),
    )
    op.create_index("ix_offer_revisions_offer_id", "offer_revisions", ["offer_id"], unique=False)
    op.create_index("ix_offer_revisions_created_by_user_id", "offer_revisions", ["created_by_user_id"], unique=False)

    op.create_table(
        "offer_fact_assertions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("period", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("observed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("supersedes_assertion_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["offer_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_assertion_id"], ["offer_fact_assertions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_offer_fact_assertions_offer_id", ["offer_id"]),
        ("ix_offer_fact_assertions_revision_id", ["revision_id"]),
        ("ix_offer_fact_assertions_field_key", ["field_key"]),
        ("ix_offer_fact_assertions_verification_status", ["verification_status"]),
        ("ix_offer_fact_assertions_evidence_id", ["evidence_id"]),
        ("ix_offer_fact_assertions_is_current", ["is_current"]),
    ):
        op.create_index(name, "offer_fact_assertions", columns, unique=False)

    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.add_column(sa.Column("offer_revision_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("preflight_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("acknowledged_unknowns", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_foreign_key(
            "fk_decision_records_offer_revision_id_offer_revisions",
            "offer_revisions",
            ["offer_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_decision_records_offer_revision_id", ["offer_revision_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("decision_records") as batch_op:
        batch_op.drop_constraint("fk_decision_records_offer_revision_id_offer_revisions", type_="foreignkey")
        batch_op.drop_index("ix_decision_records_offer_revision_id")
        batch_op.drop_column("acknowledged_unknowns")
        batch_op.drop_column("preflight_snapshot")
        batch_op.drop_column("offer_revision_id")
    op.drop_table("offer_fact_assertions")
    op.drop_table("offer_revisions")
