from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


class CareerEvent(Base):
    __tablename__ = "career_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    legacy_case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=True, unique=True)
    event_type = Column(String(30), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    stage = Column(String(30), nullable=True)
    deadline = Column(DateTime, nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, index=True)
    evidence_type = Column(String(40), nullable=False)
    source_type = Column(String(30), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content_excerpt = Column(Text, nullable=True)
    source_ref = Column(String(500), nullable=True)
    extra_data = Column(JSON, nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class GuardianFinding(Base):
    __tablename__ = "guardian_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    domain = Column(String(20), nullable=False, index=True)
    category = Column(String(50), nullable=True)
    severity = Column(String(20), nullable=False, default="info", index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    title = Column(String(300), nullable=False)
    explanation = Column(Text, nullable=True)
    source_type = Column(String(30), nullable=False)
    confidence = Column(Numeric(4, 3), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, index=True)
    finding_id = Column(Integer, ForeignKey("guardian_findings.id"), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=100, index=True)
    due_at = Column(DateTime, nullable=True)
    requires_confirmation = Column(Boolean, nullable=False, default=True)
    confirmed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, index=True)
    decision_type = Column(String(50), nullable=False)
    choice = Column(String(300), nullable=False)
    rationale = Column(Text, nullable=True)
    offer_revision_id = Column(Integer, ForeignKey("offer_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    analysis_snapshot_id = Column(Integer, ForeignKey("offer_analysis_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    preflight_snapshot = Column(JSON, nullable=True)
    acknowledged_unknowns = Column(Boolean, nullable=False, default=False)
    decided_at = Column(DateTime, server_default=func.now(), nullable=False)


class Outcome(Base):
    __tablename__ = "outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("career_events.id"), nullable=False, index=True)
    action_id = Column(Integer, ForeignKey("action_items.id"), nullable=True)
    outcome_type = Column(String(50), nullable=False)
    result = Column(Text, nullable=False)
    recorded_at = Column(DateTime, server_default=func.now(), nullable=False)
