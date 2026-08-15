"""Persist multimodal AI configuration, usage type and target-plan audio.

Revision ID: 20260816_0013
Revises: 20260816_0012
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "20260816_0013"
down_revision = "20260816_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_provider_settings") as batch_op:
        batch_op.add_column(sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("tts_model", sa.String(length=200), nullable=False, server_default="senseaudio-tts-1.5-260319"))
        batch_op.add_column(sa.Column("tts_voice_id", sa.String(length=200), nullable=False, server_default="female_0033_b"))
        batch_op.add_column(sa.Column("realtime_enabled", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("realtime_model", sa.String(length=200), nullable=False, server_default="senseaudio-realtime-1.0"))
        batch_op.add_column(sa.Column("realtime_voice_id", sa.String(length=200), nullable=False, server_default="f_y_0035_c"))

    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.add_column(sa.Column("modality", sa.String(length=20), nullable=False, server_default="text"))
        batch_op.add_column(sa.Column("usage_amount", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("usage_unit", sa.String(length=20), nullable=True))
    op.execute("UPDATE ai_invocation_logs SET usage_amount = total_tokens, usage_unit = 'tokens' WHERE total_tokens IS NOT NULL")

    with op.batch_alter_table("ai_configuration_audits") as batch_op:
        batch_op.add_column(sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("tts_model", sa.String(length=200), nullable=False, server_default="senseaudio-tts-1.5-260319"))
        batch_op.add_column(sa.Column("realtime_enabled", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("realtime_model", sa.String(length=200), nullable=False, server_default="senseaudio-realtime-1.0"))

    with op.batch_alter_table("job_targets") as batch_op:
        batch_op.add_column(sa.Column("plan_audio", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=True))
        batch_op.add_column(sa.Column("plan_audio_content_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("plan_audio_summary_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("plan_audio_generated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("job_targets") as batch_op:
        batch_op.drop_column("plan_audio_generated_at")
        batch_op.drop_column("plan_audio_summary_hash")
        batch_op.drop_column("plan_audio_content_type")
        batch_op.drop_column("plan_audio")
    with op.batch_alter_table("ai_configuration_audits") as batch_op:
        batch_op.drop_column("realtime_model")
        batch_op.drop_column("realtime_enabled")
        batch_op.drop_column("tts_model")
        batch_op.drop_column("tts_enabled")
    with op.batch_alter_table("ai_invocation_logs") as batch_op:
        batch_op.drop_column("usage_unit")
        batch_op.drop_column("usage_amount")
        batch_op.drop_column("modality")
    with op.batch_alter_table("ai_provider_settings") as batch_op:
        batch_op.drop_column("realtime_voice_id")
        batch_op.drop_column("realtime_model")
        batch_op.drop_column("realtime_enabled")
        batch_op.drop_column("tts_voice_id")
        batch_op.drop_column("tts_model")
        batch_op.drop_column("tts_enabled")
