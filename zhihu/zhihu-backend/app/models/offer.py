from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    job_target_id = Column(Integer, ForeignKey("job_targets.id", ondelete="SET NULL"), nullable=True, index=True)
    source_attachment_id = Column(Integer, ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(200), nullable=True)  # 用户自定义名称，如"字节终面"、"Offer A"
    offer_kind = Column(String(20), nullable=False, default="written")
    decision_status = Column(String(20), nullable=False, default="evaluating", index=True)
    response_deadline = Column(DateTime, nullable=True, index=True)
    facts_confirmed_at = Column(DateTime, nullable=True)
    company_name = Column(String(200), nullable=True)
    job_title = Column(String(200), nullable=True)
    city = Column(String(50), nullable=True)
    employment_type = Column(String(50), nullable=True)
    department = Column(String(200), nullable=True)
    job_level = Column(String(100), nullable=True)
    work_mode = Column(String(50), nullable=True)
    monthly_salary = Column(Numeric(12, 2), nullable=True)
    salary_months = Column(Integer, nullable=True)
    fixed_salary = Column(Numeric(12, 2), nullable=True)
    variable_salary = Column(Numeric(12, 2), nullable=True)
    bonus = Column(String(100), nullable=True)
    allowance = Column(Numeric(12, 2), nullable=True)
    probation_months = Column(Integer, nullable=True)
    probation_salary_rate = Column(Numeric(4, 2), nullable=True)
    work_location = Column(String(300), nullable=True)
    working_hours = Column(String(200), nullable=True)
    start_date = Column(String(50), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    extraction_confidence = Column(Numeric(4, 3), default=1.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class OfferRevision(Base):
    __tablename__ = "offer_revisions"
    __table_args__ = (UniqueConstraint("offer_id", "revision_no", name="uq_offer_revisions_offer_no"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False)
    facts_snapshot = Column(JSON, nullable=False)
    created_reason = Column(String(50), nullable=False)
    source_type = Column(String(30), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supersedes_revision_id = Column(Integer, ForeignKey("offer_revisions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class FactAssertion(Base):
    __tablename__ = "offer_fact_assertions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(Integer, ForeignKey("offer_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key = Column(String(80), nullable=False, index=True)
    value_json = Column(JSON, nullable=False)
    unit = Column(String(30), nullable=True)
    currency = Column(String(10), nullable=True)
    period = Column(String(20), nullable=True)
    source_type = Column(String(30), nullable=False)
    verification_status = Column(String(30), nullable=False, index=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True, index=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    is_current = Column(Boolean, nullable=False, default=True, index=True)
    observed_at = Column(DateTime, nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    supersedes_assertion_id = Column(Integer, ForeignKey("offer_fact_assertions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class OfferDecisionContext(Base):
    """用户针对一份 Offer 保存的现实替代方案、底线和取舍。"""

    __tablename__ = "offer_decision_contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    baseline_type = Column(String(30), nullable=True)
    baseline_label = Column(String(200), nullable=True)
    baseline_monthly_take_home = Column(Numeric(12, 2), nullable=True)
    baseline_annual_bonus = Column(Numeric(12, 2), nullable=True)
    baseline_city = Column(String(50), nullable=True)
    search_runway_months = Column(Integer, nullable=True)
    baseline_notes = Column(Text, nullable=True)
    must_haves = Column(JSON, nullable=True)
    red_lines = Column(JSON, nullable=True)
    acceptable_tradeoffs = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class OfferAnalysisSnapshot(Base):
    """用户显式保存的单 Offer 分析，不随之后的事实和假设静默变化。"""

    __tablename__ = "offer_analysis_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_revision_id = Column(Integer, ForeignKey("offer_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    assumptions = Column(JSON, nullable=False)
    result_snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
