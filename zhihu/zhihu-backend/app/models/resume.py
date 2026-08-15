from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base
from app.models.personal_attachment import PersonalAttachmentVersion  # noqa: F401


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("user_id", "version_number", name="uq_resume_user_version"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    display_name = Column(String(200), nullable=False)
    original_filename = Column(String(255), nullable=True)
    attachment_version_id = Column(
        Integer,
        ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    extracted_skills = Column(JSON, nullable=False, default=list)
    parse_mode = Column(String(20), nullable=False, default="text")
    structured_profile = Column(JSON, nullable=False, default=dict)
    profile_parse_mode = Column(String(20), nullable=False, default="rules")
    profile_parse_model = Column(String(200), nullable=True)
    profile_parsed_at = Column(DateTime, nullable=True)
    profile_parse_error = Column(String(500), nullable=True)
    parent_resume_version_id = Column(
        Integer,
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    creation_source = Column(String(30), nullable=False, default="upload")
    source_job_id = Column(String(100), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    @property
    def text_length(self) -> int:
        return len(self.content_text or "")

    @property
    def has_original_file(self) -> bool:
        return self.attachment_version_id is not None

    @property
    def profile_summary(self) -> str:
        value = self.structured_profile or {}
        return str(value.get("summary") or "") if isinstance(value, dict) else ""


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
    scoring_version = Column(String(40), nullable=False, default="resume-job-fit-v3")
    score_breakdown = Column(JSON, nullable=False, default=dict)
    matched_skills = Column(JSON, nullable=False, default=list)
    missing_skills = Column(JSON, nullable=False, default=list)
    strengths = Column(JSON, nullable=False, default=list)
    risks = Column(JSON, nullable=False, default=list)
    suggestions = Column(JSON, nullable=False, default=list)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
