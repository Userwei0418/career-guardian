from sqlalchemy import LargeBinary, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class JobTarget(Base):
    __tablename__ = "job_targets"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_job_target_user_job"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="saved", index=True)
    resume_version_id = Column(Integer, ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    job_snapshot = Column(JSON, nullable=False, default=dict)
    learning_plan = Column(JSON, nullable=False, default=dict)
    plan_mode = Column(String(20), nullable=True)
    plan_status = Column(String(20), nullable=False, default="idle", index=True)
    plan_error = Column(String(500), nullable=True)
    plan_started_at = Column(DateTime, nullable=True)
    plan_generated_at = Column(DateTime, nullable=True)
    plan_audio = Column(LargeBinary(length=16777215), nullable=True)
    plan_audio_content_type = Column(String(100), nullable=True)
    plan_audio_cache_hash = Column(String(64), nullable=True)
    plan_audio_generated_at = Column(DateTime, nullable=True)
    advice_kind = Column(String(30), nullable=True)
    advice_summary = Column(Text, nullable=True)
    advice_source_analysis_id = Column(Integer, ForeignKey("opportunity_analyses.id", ondelete="SET NULL"), nullable=True)
    advice_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ResumeTailoringDraft(Base):
    __tablename__ = "resume_tailoring_drafts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    job_target_id = Column(Integer, ForeignKey("job_targets.id", ondelete="CASCADE"), nullable=False, index=True)
    source_resume_version_id = Column(Integer, ForeignKey("resume_versions.id"), nullable=False, index=True)
    confirmed_resume_version_id = Column(Integer, ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    tailored_text = Column(Text, nullable=False)
    changes = Column(JSON, nullable=False, default=list)
    warnings = Column(JSON, nullable=False, default=list)
    generation_mode = Column(String(20), nullable=False, default="rules")
    error_message = Column(String(500), nullable=True)
    generation_started_at = Column(DateTime, nullable=True)
    generation_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime, nullable=True)


class MockInterviewSession(Base):
    __tablename__ = "mock_interview_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_target_id = Column(Integer, ForeignKey("job_targets.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id = Column(Integer, ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="preparing", index=True)
    practice_type = Column(String(30), nullable=False, default="full_interview")
    rubric_version = Column(String(30), nullable=False, default="interview_v1")
    interview_type = Column(String(30), nullable=False, default="comprehensive")
    difficulty = Column(String(20), nullable=False, default="standard")
    planned_duration_minutes = Column(Integer, nullable=False, default=15)
    target_duration_seconds = Column(Integer, nullable=True)
    model = Column(String(200), nullable=False)
    voice_id = Column(String(200), nullable=False)
    agent_name = Column(String(100), nullable=False, default="职护模拟面试官")
    summary = Column(Text, nullable=True)
    report = Column(JSON, nullable=False, default=dict)
    transcript = Column(JSON, nullable=False, default=list)
    error_message = Column(String(500), nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    turn_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
