from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.session import Base


class GrowthWorkIntake(Base):
    __tablename__ = "growth_work_intakes"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_intake_owner_request"),
        CheckConstraint(
            "status IN ('draft', 'confirmed', 'cancelled')",
            name="ck_growth_work_intakes_status",
        ),
        Index("ix_growth_work_intakes_owner_status", "user_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    candidate_payload = Column(JSON, nullable=False)
    parser_version = Column(String(80), nullable=False)
    analysis_mode = Column(String(20), nullable=False)
    provider_name = Column(String(100), nullable=True)
    model = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    confirmed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthWorkItem(Base):
    __tablename__ = "growth_work_items"
    __table_args__ = (
        UniqueConstraint("intake_id", "candidate_key", name="uq_growth_work_item_intake_candidate"),
        CheckConstraint(
            "status IN ('captured', 'planned', 'in_progress', 'blocked', 'completed', 'deferred', 'cancelled')",
            name="ck_growth_work_items_status",
        ),
        CheckConstraint(
            "impact_level IN ('high', 'medium', 'low', 'unknown')",
            name="ck_growth_work_items_impact",
        ),
        CheckConstraint(
            "energy_level IN ('high', 'medium', 'low', 'unknown')",
            name="ck_growth_work_items_energy",
        ),
        Index("ix_growth_work_items_owner_status", "user_id", "status", "priority_order"),
        Index("ix_growth_work_items_owner_due", "user_id", "due_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    intake_id = Column(
        Integer,
        ForeignKey("growth_work_intakes.id", ondelete="CASCADE"),
        nullable=False,
    )
    career_event_id = Column(
        Integer,
        ForeignKey("career_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    candidate_key = Column(String(80), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    fact_excerpt = Column(Text, nullable=True)
    impact_level = Column(String(20), nullable=False, default="unknown", server_default="unknown")
    energy_level = Column(String(20), nullable=False, default="unknown", server_default="unknown")
    priority_order = Column(Integer, nullable=False, default=100, server_default="100")
    selection_reason = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="planned", server_default="planned")
    due_at = Column(DateTime, nullable=True)
    result_summary = Column(Text, nullable=True)
    reportable = Column(Boolean, nullable=False, default=False, server_default="0")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthEmotionNote(Base):
    __tablename__ = "growth_emotion_notes"
    __table_args__ = (
        UniqueConstraint("intake_id", name="uq_growth_emotion_note_intake"),
        CheckConstraint(
            "privacy_level IN ('private', 'private_deidentified')",
            name="ck_growth_emotion_notes_privacy",
        ),
        Index("ix_growth_emotion_notes_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    intake_id = Column(
        Integer,
        ForeignKey("growth_work_intakes.id", ondelete="CASCADE"),
        nullable=False,
    )
    encrypted_content = Column(Text, nullable=False)
    deidentified_fact = Column(Text, nullable=True)
    privacy_level = Column(String(30), nullable=False, default="private", server_default="private")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    deleted_at = Column(DateTime, nullable=True)


class GrowthWorkEvent(Base):
    __tablename__ = "growth_work_events"
    __table_args__ = (
        UniqueConstraint("work_item_id", name="uq_growth_work_event_work_item"),
        CheckConstraint(
            "status IN ('captured', 'structured', 'confirmed', 'needs_more_evidence', 'discarded', 'archived')",
            name="ck_growth_work_events_status",
        ),
        CheckConstraint(
            "visibility IN ('private', 'reportable', 'career_asset')",
            name="ck_growth_work_events_visibility",
        ),
        Index("ix_growth_work_events_owner_status", "user_id", "status", "occurred_on"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_item_id = Column(
        Integer,
        ForeignKey("growth_work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    situation = Column(Text, nullable=True)
    task = Column(Text, nullable=False)
    action = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    role = Column(String(200), nullable=True)
    occurred_on = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="structured", server_default="structured")
    visibility = Column(String(30), nullable=False, default="private", server_default="private")
    reportable = Column(Boolean, nullable=False, default=False, server_default="0")
    evidence_gaps = Column(JSON, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthWeeklyReport(Base):
    __tablename__ = "growth_weekly_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", "version", name="uq_growth_weekly_report_version"),
        CheckConstraint(
            "status IN ('draft', 'reviewed', 'exported', 'archived')",
            name="ck_growth_weekly_reports_status",
        ),
        Index("ix_growth_weekly_reports_owner_week", "user_id", "week_start", "version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    included_event_ids = Column(JSON, nullable=False, default=list)
    generated_content = Column(Text, nullable=False)
    edited_content = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthAuditEvent(Base):
    __tablename__ = "growth_audit_events"
    __table_args__ = (
        Index("ix_growth_audit_owner_created", "user_id", "created_at"),
        Index("ix_growth_audit_entity", "entity_type", "entity_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False)
    request_id = Column(String(80), nullable=True)
    before_payload = Column(JSON, nullable=True)
    after_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
