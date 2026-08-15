"""associate AI invocation logs with the calling user

Revision ID: 20260816_0007
Revises: 20260816_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0007"
down_revision = "20260816_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ai_invocation_logs_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_ai_invocation_logs_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.drop_index("ix_ai_invocation_logs_user_id")
        batch_op.drop_constraint("fk_ai_invocation_logs_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
