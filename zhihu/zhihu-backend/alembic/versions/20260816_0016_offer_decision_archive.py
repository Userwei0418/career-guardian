"""Unify Offer decision archive context and source links.

Revision ID: 20260816_0016
Revises: 20260816_0015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0016"
down_revision = "20260816_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("offers")}
    with op.batch_alter_table("offers") as batch_op:
        if "job_target_id" not in columns:
            batch_op.add_column(sa.Column("job_target_id", sa.Integer(), sa.ForeignKey("job_targets.id", name="fk_offers_job_target_id_job_targets", ondelete="SET NULL"), nullable=True))
        if "source_attachment_id" not in columns:
            batch_op.add_column(sa.Column("source_attachment_id", sa.Integer(), sa.ForeignKey("personal_attachment_versions.id", name="fk_offers_source_attachment_id_personal_attachments", ondelete="SET NULL"), nullable=True))
        if "offer_kind" not in columns:
            batch_op.add_column(sa.Column("offer_kind", sa.String(length=20), nullable=False, server_default="written"))
        if "decision_status" not in columns:
            batch_op.add_column(sa.Column("decision_status", sa.String(length=20), nullable=False, server_default="evaluating"))
        if "response_deadline" not in columns:
            batch_op.add_column(sa.Column("response_deadline", sa.DateTime(), nullable=True))
        if "facts_confirmed_at" not in columns:
            batch_op.add_column(sa.Column("facts_confirmed_at", sa.DateTime(), nullable=True))
        if "employment_type" not in columns:
            batch_op.add_column(sa.Column("employment_type", sa.String(length=50), nullable=True))
        if "department" not in columns:
            batch_op.add_column(sa.Column("department", sa.String(length=200), nullable=True))
        if "job_level" not in columns:
            batch_op.add_column(sa.Column("job_level", sa.String(length=100), nullable=True))
        if "work_mode" not in columns:
            batch_op.add_column(sa.Column("work_mode", sa.String(length=50), nullable=True))

    inspector = sa.inspect(op.get_bind())
    index_names = {index["name"] for index in inspector.get_indexes("offers")}
    for name, columns_to_index in (
        ("ix_offers_job_target_id", ["job_target_id"]),
        ("ix_offers_source_attachment_id", ["source_attachment_id"]),
        ("ix_offers_decision_status", ["decision_status"]),
        ("ix_offers_response_deadline", ["response_deadline"]),
    ):
        if name not in index_names:
            op.create_index(name, "offers", columns_to_index, unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    index_names = {index["name"] for index in inspector.get_indexes("offers")}
    for name in (
        "ix_offers_response_deadline",
        "ix_offers_decision_status",
        "ix_offers_source_attachment_id",
        "ix_offers_job_target_id",
    ):
        if name in index_names:
            op.drop_index(name, table_name="offers")

    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("offers")}
    with op.batch_alter_table("offers") as batch_op:
        for name in (
            "work_mode",
            "job_level",
            "department",
            "employment_type",
            "facts_confirmed_at",
            "response_deadline",
            "decision_status",
            "offer_kind",
            "source_attachment_id",
            "job_target_id",
        ):
            if name in columns:
                batch_op.drop_column(name)
