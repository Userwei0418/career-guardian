from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.sql import func

from app.db.session import Base


class Contract(Base):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    linked_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    source_attachment_id = Column(
        Integer,
        ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name = Column(String(200), nullable=True)
    document_kind = Column(String(30), nullable=False, default="labor_contract")
    status = Column(String(30), nullable=False, default="active", index=True)
    parse_status = Column(String(30), nullable=False, default="ready")
    parse_mode = Column(String(30), nullable=True)
    parse_notice = Column(String(500), nullable=True)
    parse_error_code = Column(String(80), nullable=True)
    page_count = Column(Integer, nullable=True)
    text_page_count = Column(Integer, nullable=True)
    ocr_page_count = Column(Integer, nullable=True)
    parse_quality = Column(JSON, nullable=True)
    employer = Column(String(200), nullable=True)
    contract_term = Column(String(100), nullable=True)
    probation = Column(String(100), nullable=True)
    salary_terms = Column(Text, nullable=True)
    work_location = Column(String(300), nullable=True)
    working_hours = Column(String(200), nullable=True)
    non_compete = Column(Text, nullable=True)
    penalty_terms = Column(Text, nullable=True)
    termination_terms = Column(Text, nullable=True)
    source_document_id = Column(Integer, nullable=True)
    # MySQL TEXT is limited to 65,535 bytes.  Employee handbooks and other
    # long employment documents routinely exceed that size even when the PDF
    # itself is perfectly readable, so MySQL must use LONGTEXT.
    raw_text = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ContractReviewSnapshot(Base):
    """一次可追溯的劳动合同审查结果。

    原件、规则或文本变化时创建新快照；相同输入重复审查复用现有快照。
    """

    __tablename__ = "contract_review_snapshots"
    __table_args__ = (
        UniqueConstraint("contract_id", "review_number", name="uq_contract_review_number"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    attachment_version_id = Column(
        Integer,
        ForeignKey("personal_attachment_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_number = Column(Integer, nullable=False)
    document_hash = Column(String(64), nullable=False, index=True)
    extracted_fields = Column(JSON, nullable=False)
    findings = Column(JSON, nullable=False)
    summary = Column(Text, nullable=False)
    review_mode = Column(String(30), nullable=False, default="rules")
    rule_version = Column(String(50), nullable=False)
    clause_segments = Column(JSON, nullable=True)
    provider_name = Column(String(100), nullable=True)
    model_name = Column(String(200), nullable=True)
    prompt_version = Column(String(80), nullable=True)
    redaction_version = Column(String(80), nullable=True)
    ai_status = Column(String(30), nullable=False, default="not_requested", server_default="not_requested")
    ai_input_clause_count = Column(Integer, nullable=False, default=0, server_default="0")
    ai_batch_count = Column(Integer, nullable=False, default=0, server_default="0")
    ai_completed_batch_count = Column(Integer, nullable=False, default=0, server_default="0")
    redaction_report = Column(JSON, nullable=True)
    coverage_report = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ContractFollowUpTurn(Base):
    """A private, review-versioned follow-up turn for one contract finding."""

    __tablename__ = "contract_follow_up_turns"
    __table_args__ = (
        UniqueConstraint(
            "review_snapshot_id",
            "clause_id",
            "finding_code",
            "turn_number",
            name="uq_contract_follow_up_turn",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True)
    review_snapshot_id = Column(
        Integer,
        ForeignKey("contract_review_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clause_id = Column(String(100), nullable=False)
    finding_code = Column(String(100), nullable=False)
    turn_number = Column(Integer, nullable=False)
    # Questions are locally redacted before persistence. The PDF, full contract,
    # file name and complete model payload are never copied into this table.
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    evidence_quote = Column(Text, nullable=True)
    limits = Column(Text, nullable=False)
    provider_name = Column(String(100), nullable=True)
    model_name = Column(String(200), nullable=True)
    prompt_version = Column(String(80), nullable=True)
    redaction_version = Column(String(80), nullable=True)
    review_method = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
