"""add administrator managed ai configuration

Revision ID: 20260816_0005
Revises: 20260815_0004
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0005"
down_revision = "20260815_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_suffix", sa.String(8), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_test_status", sa.String(20), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "ai_invocation_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("setting_id", sa.Integer(), sa.ForeignKey("ai_provider_settings.id"), nullable=True),
        sa.Column("feature", sa.String(100), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_invocation_logs_created_at", "ai_invocation_logs", ["created_at"])
    op.create_index("ix_ai_invocation_logs_feature", "ai_invocation_logs", ["feature"])
    op.create_table(
        "ai_configuration_audits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("setting_id", sa.Integer(), sa.ForeignKey("ai_provider_settings.id"), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("key_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_configuration_audits_created_at", "ai_configuration_audits", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_configuration_audits")
    op.drop_table("ai_invocation_logs")
    op.drop_table("ai_provider_settings")
