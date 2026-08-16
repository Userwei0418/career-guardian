"""Add mock interview summaries and parameter-aware plan audio cache.

Revision ID: 20260816_0014
Revises: 20260816_0013
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0014"
down_revision = "20260816_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    job_columns = {column["name"] for column in inspector.get_columns("job_targets")}
    if "plan_audio_summary_hash" in job_columns:
        with op.batch_alter_table("job_targets") as batch_op:
            batch_op.alter_column("plan_audio_summary_hash", new_column_name="plan_audio_cache_hash", existing_type=sa.String(length=64), nullable=True)

    provider_columns = {column["name"] for column in inspector.get_columns("ai_provider_settings")}
    with op.batch_alter_table("ai_provider_settings") as batch_op:
        if "interview_agent_name" not in provider_columns:
            batch_op.add_column(sa.Column("interview_agent_name", sa.String(length=100), nullable=False, server_default="职护模拟面试官"))
        if "interview_agent_prompt" not in provider_columns:
            batch_op.add_column(sa.Column("interview_agent_prompt", sa.Text(), nullable=True))
        if "interview_greeting" not in provider_columns:
            batch_op.add_column(sa.Column("interview_greeting", sa.Text(), nullable=True))
    connection.execute(sa.text("UPDATE ai_provider_settings SET interview_agent_prompt = :value WHERE interview_agent_prompt IS NULL"), {"value": "你是一位专业、耐心、尊重候选人的面试官。"})
    connection.execute(sa.text("UPDATE ai_provider_settings SET interview_greeting = :value WHERE interview_greeting IS NULL"), {"value": "你好，我是职护模拟面试官。准备好后，我们开始今天的模拟面试。"})
    with op.batch_alter_table("ai_provider_settings") as batch_op:
        batch_op.alter_column("interview_agent_prompt", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("interview_greeting", existing_type=sa.Text(), nullable=False)

    op.create_table(
        "mock_interview_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_target_id", sa.Integer(), nullable=False),
        sa.Column("resume_version_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="preparing"),
        sa.Column("interview_type", sa.String(length=30), nullable=False, server_default="comprehensive"),
        sa.Column("difficulty", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("planned_duration_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("voice_id", sa.String(length=200), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False, server_default="职护模拟面试官"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("transcript", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_target_id"], ["job_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_version_id"], ["resume_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mock_interview_sessions_user_id", "mock_interview_sessions", ["user_id"])
    op.create_index("ix_mock_interview_sessions_job_target_id", "mock_interview_sessions", ["job_target_id"])
    op.create_index("ix_mock_interview_sessions_resume_version_id", "mock_interview_sessions", ["resume_version_id"])
    op.create_index("ix_mock_interview_sessions_status", "mock_interview_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_mock_interview_sessions_status", table_name="mock_interview_sessions")
    op.drop_index("ix_mock_interview_sessions_resume_version_id", table_name="mock_interview_sessions")
    op.drop_index("ix_mock_interview_sessions_job_target_id", table_name="mock_interview_sessions")
    op.drop_index("ix_mock_interview_sessions_user_id", table_name="mock_interview_sessions")
    op.drop_table("mock_interview_sessions")
    with op.batch_alter_table("ai_provider_settings") as batch_op:
        batch_op.drop_column("interview_greeting")
        batch_op.drop_column("interview_agent_prompt")
        batch_op.drop_column("interview_agent_name")
    with op.batch_alter_table("job_targets") as batch_op:
        batch_op.alter_column("plan_audio_cache_hash", new_column_name="plan_audio_summary_hash", existing_type=sa.String(length=64), nullable=True)
