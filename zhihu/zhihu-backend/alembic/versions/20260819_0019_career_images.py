"""Add personalized career image generation and image provider configuration."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260819_0019"
down_revision = "20260817_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_provider_settings", sa.Column("image_enabled", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("ai_provider_settings", sa.Column("image_base_url", sa.String(length=500), nullable=False, server_default="https://api.senseaudio.cn/v1"))
    op.add_column("ai_provider_settings", sa.Column("image_model", sa.String(length=200), nullable=False, server_default="senseaudio-image-2.0-260319"))
    op.add_column("ai_provider_settings", sa.Column("image_landscape_size", sa.String(length=30), nullable=False, server_default="1536x864"))
    op.add_column("ai_provider_settings", sa.Column("image_square_size", sa.String(length=30), nullable=False, server_default="1024x1024"))
    op.add_column("ai_provider_settings", sa.Column("image_poll_interval_seconds", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("ai_provider_settings", sa.Column("image_timeout_seconds", sa.Integer(), nullable=False, server_default="240"))
    op.add_column("ai_provider_settings", sa.Column("image_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column("ai_provider_settings", sa.Column("image_api_key_suffix", sa.String(length=8), nullable=True))

    op.add_column("ai_configuration_audits", sa.Column("image_enabled", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("ai_configuration_audits", sa.Column("image_base_url", sa.String(length=500), nullable=False, server_default="https://api.senseaudio.cn/v1"))
    op.add_column("ai_configuration_audits", sa.Column("image_model", sa.String(length=200), nullable=False, server_default="senseaudio-image-2.0-260319"))

    op.create_table(
        "career_image_generations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("setting_id", sa.Integer(), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("profile_summary", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("style_version", sa.String(length=60), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("landscape_size", sa.String(length=30), nullable=False),
        sa.Column("square_size", sa.String(length=30), nullable=False),
        sa.Column("landscape_task_id", sa.String(length=200), nullable=True),
        sa.Column("square_task_id", sa.String(length=200), nullable=True),
        sa.Column("landscape_status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("square_status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("landscape_image", mysql.MEDIUMBLOB(), nullable=True),
        sa.Column("square_image", mysql.MEDIUMBLOB(), nullable=True),
        sa.Column("landscape_content_type", sa.String(length=100), nullable=True),
        sa.Column("square_content_type", sa.String(length=100), nullable=True),
        sa.Column("landscape_prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("square_prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("landscape_error", sa.String(length=500), nullable=True),
        sa.Column("square_error", sa.String(length=500), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["setting_id"], ["ai_provider_settings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "version_number", name="uq_career_image_user_version"),
    )
    op.create_index("ix_career_image_generations_user_id", "career_image_generations", ["user_id"])
    op.create_index("ix_career_image_generations_status", "career_image_generations", ["status"])
    op.create_index("ix_career_image_generations_is_current", "career_image_generations", ["is_current"])
    op.create_index("ix_career_image_generations_is_stale", "career_image_generations", ["is_stale"])
    op.create_index("ix_career_image_generations_source_fingerprint", "career_image_generations", ["source_fingerprint"])
    op.create_index("ix_career_image_generations_landscape_task_id", "career_image_generations", ["landscape_task_id"])
    op.create_index("ix_career_image_generations_square_task_id", "career_image_generations", ["square_task_id"])


def downgrade():
    op.drop_table("career_image_generations")
    op.drop_column("ai_configuration_audits", "image_model")
    op.drop_column("ai_configuration_audits", "image_base_url")
    op.drop_column("ai_configuration_audits", "image_enabled")
    op.drop_column("ai_provider_settings", "image_api_key_suffix")
    op.drop_column("ai_provider_settings", "image_api_key_encrypted")
    op.drop_column("ai_provider_settings", "image_timeout_seconds")
    op.drop_column("ai_provider_settings", "image_poll_interval_seconds")
    op.drop_column("ai_provider_settings", "image_square_size")
    op.drop_column("ai_provider_settings", "image_landscape_size")
    op.drop_column("ai_provider_settings", "image_model")
    op.drop_column("ai_provider_settings", "image_base_url")
    op.drop_column("ai_provider_settings", "image_enabled")
