"""Allow long image tasks to survive page navigation and slow provider queues."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0021"
down_revision = "20260819_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "ai_provider_settings",
        "image_timeout_seconds",
        existing_type=sa.Integer(),
        server_default="900",
        nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE ai_provider_settings "
            "SET image_timeout_seconds = 900 "
            "WHERE image_timeout_seconds < 900"
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "UPDATE ai_provider_settings "
            "SET image_timeout_seconds = 240 "
            "WHERE image_timeout_seconds = 900"
        )
    )
    op.alter_column(
        "ai_provider_settings",
        "image_timeout_seconds",
        existing_type=sa.Integer(),
        server_default="240",
        nullable=False,
    )
