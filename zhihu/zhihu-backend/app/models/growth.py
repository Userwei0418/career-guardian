from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Float,
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


class GrowthPortfolioItem(Base):
    __tablename__ = "growth_portfolio_items"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_portfolio_owner_request"),
        CheckConstraint(
            "item_type IN ('github', 'project', 'link', 'design', 'article', 'speech', 'certificate', 'feedback', 'attachment', 'other')",
            name="ck_growth_portfolio_items_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'unavailable', 'archived')",
            name="ck_growth_portfolio_items_status",
        ),
        CheckConstraint(
            "privacy_level IN ('private', 'shared', 'public')",
            name="ck_growth_portfolio_items_privacy",
        ),
        Index("ix_growth_portfolio_owner_status", "user_id", "status", "occurred_on"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    source_work_event_id = Column(Integer, ForeignKey("growth_work_events.id", ondelete="SET NULL"), nullable=True)
    source_attachment_id = Column(Integer, ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"), nullable=True)
    item_type = Column(String(30), nullable=False)
    title = Column(String(300), nullable=False)
    summary = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=True)
    source_label = Column(String(300), nullable=True)
    occurred_on = Column(Date, nullable=True)
    privacy_level = Column(String(20), nullable=False, default="private", server_default="private")
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    unavailable_reason = Column(String(500), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthEvidenceItem(Base):
    __tablename__ = "growth_evidence_items"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_evidence_owner_request"),
        CheckConstraint(
            "evidence_type IN ('project_result', 'collaboration', 'leadership', 'customer_feedback', 'public_work', 'certificate', 'method', 'other')",
            name="ck_growth_evidence_items_type",
        ),
        CheckConstraint(
            "status IN ('candidate', 'confirmed', 'unavailable', 'archived')",
            name="ck_growth_evidence_items_status",
        ),
        CheckConstraint(
            "privacy_level IN ('private', 'shared', 'public')",
            name="ck_growth_evidence_items_privacy",
        ),
        Index("ix_growth_evidence_owner_status", "user_id", "status", "occurred_on"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    portfolio_item_id = Column(Integer, ForeignKey("growth_portfolio_items.id", ondelete="SET NULL"), nullable=True)
    work_event_id = Column(Integer, ForeignKey("growth_work_events.id", ondelete="SET NULL"), nullable=True)
    evidence_type = Column(String(30), nullable=False)
    title = Column(String(300), nullable=False)
    summary = Column(Text, nullable=False)
    source_label = Column(String(300), nullable=True)
    occurred_on = Column(Date, nullable=True)
    role = Column(String(200), nullable=True)
    result_type = Column(String(100), nullable=True)
    privacy_level = Column(String(20), nullable=False, default="private", server_default="private")
    status = Column(String(20), nullable=False, default="candidate", server_default="candidate")
    unavailable_reason = Column(String(500), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthSkillAssessment(Base):
    __tablename__ = "growth_skill_assessments"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_key", "version", name="uq_growth_skill_owner_key_version"),
        CheckConstraint(
            "source_layer IN ('market_signal', 'ai_candidate', 'user_claimed', 'evidence_confirmed')",
            name="ck_growth_skill_assessments_layer",
        ),
        CheckConstraint(
            "status IN ('candidate', 'confirmed', 'rejected', 'superseded', 'archived')",
            name="ck_growth_skill_assessments_status",
        ),
        CheckConstraint(
            "evidence_sufficiency IN ('none', 'partial', 'supported')",
            name="ck_growth_skill_assessments_sufficiency",
        ),
        Index("ix_growth_skill_owner_status", "user_id", "status", "skill_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supersedes_assessment_id = Column(Integer, ForeignKey("growth_skill_assessments.id", ondelete="SET NULL"), nullable=True)
    skill_key = Column(String(160), nullable=False)
    skill_name = Column(String(160), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    source_layer = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="candidate", server_default="candidate")
    evidence_sufficiency = Column(String(20), nullable=False, default="none", server_default="none")
    user_note = Column(Text, nullable=True)
    latest_used_on = Column(Date, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthSkillEvidenceLink(Base):
    __tablename__ = "growth_skill_evidence_links"
    __table_args__ = (
        UniqueConstraint("assessment_id", "evidence_id", name="uq_growth_skill_evidence_link"),
        Index("ix_growth_skill_evidence_owner", "user_id", "assessment_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    assessment_id = Column(Integer, ForeignKey("growth_skill_assessments.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("growth_evidence_items.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthReflection(Base):
    __tablename__ = "growth_reflections"
    __table_args__ = (
        UniqueConstraint("user_id", "work_event_id", name="uq_growth_reflection_owner_event"),
        CheckConstraint(
            "status IN ('prompted', 'answered', 'confirmed', 'archived')",
            name="ck_growth_reflections_status",
        ),
        CheckConstraint(
            "privacy_level IN ('private', 'shared')",
            name="ck_growth_reflections_privacy",
        ),
        Index("ix_growth_reflections_owner_status", "user_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    work_event_id = Column(Integer, ForeignKey("growth_work_events.id", ondelete="SET NULL"), nullable=True)
    evidence_id = Column(Integer, ForeignKey("growth_evidence_items.id", ondelete="SET NULL"), nullable=True)
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=True)
    privacy_level = Column(String(20), nullable=False, default="private", server_default="private")
    status = Column(String(20), nullable=False, default="prompted", server_default="prompted")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthFutureTarget(Base):
    __tablename__ = "growth_future_targets"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_target_owner_request"),
        UniqueConstraint("user_id", "target_key", "version", name="uq_growth_target_owner_key_version"),
        CheckConstraint("target_type IN ('role', 'job_family', 'level', 'transition', 'other')", name="ck_growth_future_targets_type"),
        CheckConstraint("status IN ('draft', 'active', 'paused', 'completed', 'superseded')", name="ck_growth_future_targets_status"),
        Index("ix_growth_target_owner_status", "user_id", "status", "target_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supersedes_target_id = Column(Integer, ForeignKey("growth_future_targets.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    target_key = Column(String(180), nullable=False)
    target_type = Column(String(30), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    source_label = Column(String(300), nullable=True)
    target_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthMarketSignal(Base):
    __tablename__ = "growth_market_signals"
    __table_args__ = (
        UniqueConstraint("user_id", "batch_request_id", "signal_key", name="uq_growth_market_signal_batch_key"),
        CheckConstraint("direction IN ('rising', 'stable', 'declining', 'unknown')", name="ck_growth_market_signals_direction"),
        CheckConstraint("quality_grade IN ('A', 'B', 'C', 'insufficient')", name="ck_growth_market_signals_quality"),
        CheckConstraint("availability IN ('available', 'insufficient_sample', 'stale', 'unavailable')", name="ck_growth_market_signals_availability"),
        CheckConstraint("status IN ('active', 'weak', 'expired', 'rejected')", name="ck_growth_market_signals_status"),
        Index("ix_growth_market_signal_owner_target", "user_id", "target_id", "status", "calculated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(Integer, ForeignKey("growth_future_targets.id", ondelete="CASCADE"), nullable=False)
    batch_request_id = Column(String(80), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    signal_key = Column(String(180), nullable=False)
    skill_name = Column(String(160), nullable=False)
    occurrence_count = Column(Integer, nullable=False, default=0, server_default="0")
    share = Column(Float, nullable=True)
    recent_count = Column(Integer, nullable=True)
    previous_count = Column(Integer, nullable=True)
    recent_share = Column(Float, nullable=True)
    previous_share = Column(Float, nullable=True)
    share_delta = Column(Float, nullable=True)
    recent_sample_size = Column(Integer, nullable=True)
    previous_sample_size = Column(Integer, nullable=True)
    recent_window_start = Column(DateTime, nullable=True)
    recent_window_end = Column(DateTime, nullable=True)
    previous_window_start = Column(DateTime, nullable=True)
    previous_window_end = Column(DateTime, nullable=True)
    direction = Column(String(20), nullable=False, default="unknown", server_default="unknown")
    availability = Column(String(30), nullable=False)
    data_mode = Column(String(20), nullable=False)
    quality_grade = Column(String(20), nullable=False)
    sample_size = Column(Integer, nullable=False, default=0, server_default="0")
    methodology_version = Column(String(100), nullable=False)
    sources = Column(JSON, nullable=False, default=list)
    calculated_at = Column(DateTime, nullable=False)
    limitation = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="weak", server_default="weak")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthGapSnapshot(Base):
    __tablename__ = "growth_gap_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_gap_owner_request"),
        UniqueConstraint("user_id", "target_id", "version", name="uq_growth_gap_target_version"),
        CheckConstraint("quality IN ('strong', 'limited', 'insufficient', 'stale')", name="ck_growth_gap_snapshots_quality"),
        CheckConstraint("status IN ('candidate', 'confirmed', 'superseded')", name="ck_growth_gap_snapshots_status"),
        Index("ix_growth_gap_owner_target", "user_id", "target_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(Integer, ForeignKey("growth_future_targets.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    market_signal_ids = Column(JSON, nullable=False, default=list)
    career_chip_refs = Column(JSON, nullable=False, default=list)
    matched_items = Column(JSON, nullable=False, default=list)
    gap_items = Column(JSON, nullable=False, default=list)
    unknown_items = Column(JSON, nullable=False, default=list)
    quality = Column(String(20), nullable=False)
    confidence = Column(Float, nullable=False, default=0, server_default="0")
    limitation = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="candidate", server_default="candidate")
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthMilestone(Base):
    __tablename__ = "growth_milestones"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_milestone_owner_request"),
        UniqueConstraint("user_id", "milestone_key", "version", name="uq_growth_milestone_owner_key_version"),
        CheckConstraint("timeframe IN ('30d', '60d', '90d', 'quarter', 'custom')", name="ck_growth_milestones_timeframe"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'in_progress', 'completed', 'cancelled', 'superseded')", name="ck_growth_milestones_status"),
        Index("ix_growth_milestone_owner_target", "user_id", "target_id", "status", "due_on"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supersedes_milestone_id = Column(Integer, ForeignKey("growth_milestones.id", ondelete="SET NULL"), nullable=True)
    target_id = Column(Integer, ForeignKey("growth_future_targets.id", ondelete="CASCADE"), nullable=False)
    gap_snapshot_id = Column(Integer, ForeignKey("growth_gap_snapshots.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    milestone_key = Column(String(180), nullable=False)
    title = Column(String(300), nullable=False)
    success_criteria = Column(Text, nullable=False)
    timeframe = Column(String(20), nullable=False, default="custom", server_default="custom")
    due_on = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="proposed", server_default="proposed")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthCommunicationDraft(Base):
    __tablename__ = "growth_communication_drafts"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_communication_owner_request"),
        UniqueConstraint("user_id", "draft_key", "version", name="uq_growth_communication_owner_key_version"),
        CheckConstraint(
            "status IN ('draft', 'reviewed', 'exported', 'archived', 'superseded')",
            name="ck_growth_communication_drafts_status",
        ),
        CheckConstraint(
            "analysis_mode IN ('rules', 'ai')",
            name="ck_growth_communication_drafts_mode",
        ),
        Index("ix_growth_communication_owner_status", "user_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supersedes_draft_id = Column(Integer, ForeignKey("growth_communication_drafts.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    draft_key = Column(String(180), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    audience = Column(String(200), nullable=False)
    scene = Column(String(100), nullable=False)
    goal = Column(String(500), nullable=False)
    known_facts = Column(JSON, nullable=False, default=list)
    tone = Column(String(100), nullable=False)
    fact_questions = Column(JSON, nullable=False, default=list)
    strategies = Column(JSON, nullable=False, default=list)
    risk_notes = Column(JSON, nullable=False, default=list)
    source_refs = Column(JSON, nullable=False, default=list)
    data_scope = Column(JSON, nullable=False, default=list)
    generated_content = Column(Text, nullable=False)
    edited_content = Column(Text, nullable=True)
    analysis_mode = Column(String(20), nullable=False, default="rules", server_default="rules")
    provider_name = Column(String(100), nullable=True)
    model = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    reviewed_at = Column(DateTime, nullable=True)
    exported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class GrowthHandoff(Base):
    __tablename__ = "growth_handoffs"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_handoff_owner_request"),
        CheckConstraint(
            "target_domain IN ('opportunity', 'decision', 'rights', 'income', 'resume')",
            name="ck_growth_handoffs_target_domain",
        ),
        CheckConstraint(
            "source_type IN ('work_event', 'portfolio', 'evidence', 'skill', 'target', 'gap', 'milestone')",
            name="ck_growth_handoffs_source_type",
        ),
        CheckConstraint(
            "status IN ('proposed', 'confirmed', 'revoked')",
            name="ck_growth_handoffs_status",
        ),
        Index("ix_growth_handoff_owner_status", "user_id", "status", "created_at"),
        Index("ix_growth_handoff_target_inbox", "user_id", "target_domain", "status", "confirmed_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    input_fingerprint = Column(String(64), nullable=False)
    target_domain = Column(String(30), nullable=False)
    source_type = Column(String(30), nullable=False)
    source_id = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    content_summary = Column(Text, nullable=False)
    evidence_refs = Column(JSON, nullable=False, default=list)
    impact_summary = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="proposed", server_default="proposed")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class GrowthInquiry(Base):
    __tablename__ = "growth_inquiries"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_growth_inquiry_owner_request"),
        CheckConstraint("mode IN ('program', 'ai')", name="ck_growth_inquiries_mode"),
        CheckConstraint("status IN ('completed', 'failed')", name="ck_growth_inquiries_status"),
        Index("ix_growth_inquiry_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    request_id = Column(String(80), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    mode = Column(String(20), nullable=False)
    data_scopes = Column(JSON, nullable=False, default=list)
    evidence_refs = Column(JSON, nullable=False, default=list)
    follow_up_questions = Column(JSON, nullable=False, default=list)
    provider_name = Column(String(100), nullable=True)
    model = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="completed", server_default="completed")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
