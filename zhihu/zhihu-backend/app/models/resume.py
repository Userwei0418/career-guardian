from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("user_id", "version_number", name="uq_resume_user_version"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    display_name = Column(String(200), nullable=False)
    original_filename = Column(String(255), nullable=True)
    content_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    extracted_skills = Column(JSON, nullable=False, default=list)
    parse_mode = Column(String(20), nullable=False, default="text")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    @property
    def text_length(self) -> int:
        return len(self.content_text or "")


class OpportunityAnalysis(Base):
    __tablename__ = "opportunity_analyses"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "resume_version_id", "job_id", name="uq_opportunity_analysis_version_job"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, unique=True)
    resume_version_id = Column(Integer, ForeignKey("resume_versions.id"), nullable=False, index=True)
    job_id = Column(String(100), nullable=False, index=True)
    analysis_mode = Column(String(20), nullable=False)
    match_score = Column(Integer, nullable=False)
    matched_skills = Column(JSON, nullable=False, default=list)
    missing_skills = Column(JSON, nullable=False, default=list)
    strengths = Column(JSON, nullable=False, default=list)
    risks = Column(JSON, nullable=False, default=list)
    suggestions = Column(JSON, nullable=False, default=list)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
