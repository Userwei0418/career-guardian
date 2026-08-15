"""unify opportunity scoring evidence

Revision ID: 20260816_0011
Revises: 20260816_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0011"
down_revision = "20260816_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    json_default = sa.text("(JSON_OBJECT())") if dialect_name == "mysql" else sa.text("'{}'")
    op.add_column(
        "opportunity_analyses",
        sa.Column("scoring_version", sa.String(length=40), nullable=False, server_default="legacy-skill-ratio-v1"),
    )
    op.add_column(
        "opportunity_analyses",
        sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default=json_default),
    )
    op.add_column("job_targets", sa.Column("advice_kind", sa.String(length=30), nullable=True))
    op.add_column("job_targets", sa.Column("advice_summary", sa.Text(), nullable=True))
    op.add_column("job_targets", sa.Column("advice_source_analysis_id", sa.Integer(), nullable=True))
    op.add_column("job_targets", sa.Column("advice_updated_at", sa.DateTime(), nullable=True))
    if dialect_name == "sqlite":
        with op.batch_alter_table("job_targets") as batch_op:
            batch_op.create_foreign_key(
                "fk_job_targets_advice_analysis",
                "opportunity_analyses",
                ["advice_source_analysis_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "fk_job_targets_advice_analysis",
            "job_targets",
            "opportunity_analyses",
            ["advice_source_analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("job_targets") as batch_op:
            batch_op.drop_constraint("fk_job_targets_advice_analysis", type_="foreignkey")
    else:
        op.drop_constraint("fk_job_targets_advice_analysis", "job_targets", type_="foreignkey")
    op.drop_column("job_targets", "advice_updated_at")
    op.drop_column("job_targets", "advice_source_analysis_id")
    op.drop_column("job_targets", "advice_summary")
    op.drop_column("job_targets", "advice_kind")
    op.drop_column("opportunity_analyses", "score_breakdown")
    op.drop_column("opportunity_analyses", "scoring_version")
