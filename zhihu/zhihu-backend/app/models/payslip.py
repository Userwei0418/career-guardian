from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (
        CheckConstraint(
            "agreed_pay_date_source_type IS NULL OR agreed_pay_date_source_type IN ('manual', 'material_suggestion')",
            name="ck_payslip_agreed_date_source_type",
        ),
        CheckConstraint(
            "agreed_pay_date_adjustment IS NULL OR agreed_pay_date_adjustment IN ('contract_date', 'advance', 'defer')",
            name="ck_payslip_agreed_date_adjustment",
        ),
        Index("ix_payslip_agreed_date_source_contract", "agreed_pay_date_source_contract_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("career_cases.id"), nullable=False)
    career_event_id = Column(Integer, ForeignKey("career_events.id"), nullable=True, index=True)
    linked_offer_id = Column(Integer, ForeignKey("offers.id"), nullable=True)
    supersedes_payslip_id = Column(
        Integer,
        ForeignKey("payslips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    record_status = Column(String(20), nullable=False, default="active", server_default="active", index=True)
    pay_month = Column(String(10), nullable=True)
    pay_date = Column(Date, nullable=True)
    agreed_pay_date = Column(Date, nullable=True)
    agreed_pay_date_source_type = Column(String(30), nullable=True)
    agreed_pay_date_source_contract_id = Column(
        Integer,
        ForeignKey("contracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    agreed_pay_date_schedule = Column(String(50), nullable=True)
    agreed_pay_date_adjustment = Column(String(30), nullable=True)
    agreed_pay_date_calendar_version = Column(String(80), nullable=True)
    employer_name = Column(String(255), nullable=True)
    gross_salary = Column(Numeric(12, 2), nullable=True)
    base_salary = Column(Numeric(12, 2), nullable=True)
    performance = Column(Numeric(12, 2), nullable=True)
    bonus = Column(Numeric(12, 2), nullable=True)
    overtime_pay = Column(Numeric(12, 2), nullable=True)
    allowance = Column(Numeric(12, 2), nullable=True)
    social_insurance = Column(Numeric(12, 2), nullable=True)
    housing_fund = Column(Numeric(12, 2), nullable=True)
    individual_tax = Column(Numeric(12, 2), nullable=True)
    attendance_deductions = Column(Numeric(12, 2), nullable=True)
    meal_deductions = Column(Numeric(12, 2), nullable=True)
    other_deductions = Column(Numeric(12, 2), nullable=True)
    net_salary = Column(Numeric(12, 2), nullable=True)
    custom_items = Column(JSON, nullable=True)
    source_type = Column(String(30), nullable=False, default="manual", server_default="manual")
    recognition_confidence = Column(Numeric(5, 4), nullable=True)
    source_document_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class PayslipMaterialLink(Base):
    __tablename__ = "payslip_material_links"
    __table_args__ = (
        CheckConstraint(
            "(offer_id IS NOT NULL AND contract_id IS NULL) OR (offer_id IS NULL AND contract_id IS NOT NULL)",
            name="ck_payslip_material_exactly_one",
        ),
        UniqueConstraint("payslip_id", "offer_id", name="uq_payslip_material_offer"),
        UniqueConstraint("payslip_id", "contract_id", name="uq_payslip_material_contract"),
        CheckConstraint(
            "application_status IN ('preferred', 'reference', 'unresolved')",
            name="ck_payslip_material_application_status",
        ),
        CheckConstraint("priority_rank > 0", name="ck_payslip_material_priority_rank"),
        Index("ix_payslip_material_offer", "offer_id"),
        Index("ix_payslip_material_contract", "contract_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    payslip_id = Column(Integer, ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_id = Column(Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True)
    application_status = Column(
        String(20),
        nullable=False,
        default="unresolved",
        server_default="unresolved",
    )
    priority_rank = Column(Integer, nullable=False, default=100, server_default="100")
    user_note = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PayslipArrivalLink(Base):
    __tablename__ = "payslip_arrival_links"
    __table_args__ = (
        UniqueConstraint("payslip_id", "economic_fact_id", name="uq_payslip_arrival_fact"),
        Index("ix_payslip_arrival_transaction", "transaction_id", "status"),
        Index("ix_payslip_arrival_fact", "economic_fact_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    payslip_id = Column(Integer, ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(
        Integer,
        ForeignKey("financial_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    economic_fact_id = Column(
        Integer,
        ForeignKey("economic_facts.id", ondelete="CASCADE"),
        nullable=True,
    )
    allocated_amount = Column(Numeric(14, 2), nullable=False)
    status = Column(String(20), nullable=False, default="confirmed", server_default="confirmed")
    match_reason = Column(JSON, nullable=True)
    ledger_revision = Column(Integer, nullable=True)
    confirmed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    confirmed_at = Column(DateTime, nullable=False, server_default=func.now())
    reversed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class PayslipArrivalLinkRevision(Base):
    __tablename__ = "payslip_arrival_link_revisions"
    __table_args__ = (
        UniqueConstraint(
            "link_id",
            "link_revision",
            name="uq_payslip_arrival_link_revision_number",
        ),
        Index("ix_payslip_arrival_link_revisions_owner_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    link_id = Column(
        Integer,
        ForeignKey("payslip_arrival_links.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_revision = Column(Integer, nullable=False)
    ledger_revision = Column(Integer, nullable=False)
    operation = Column(String(20), nullable=False)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=False)
    reason = Column(String(255), nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PayslipRecognitionCandidateDraft(Base):
    """A resumable payslip candidate that is not yet formal salary evidence."""

    __tablename__ = "payslip_recognition_candidate_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["financial_import_batches.id", "financial_import_batches.user_id"],
            name="fk_payslip_recognition_draft_batch_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("batch_id", "row_number", name="uq_payslip_recognition_draft_row"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'excluded')",
            name="ck_payslip_recognition_draft_status",
        ),
        CheckConstraint(
            "confidence_tier IN ('high', 'medium', 'low')",
            name="ck_payslip_recognition_draft_tier",
        ),
        Index(
            "ix_payslip_recognition_drafts_owner_status",
            "user_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_payslip_recognition_drafts_batch_status",
            "batch_id",
            "status",
            "row_number",
        ),
        Index("ix_payslip_recognition_drafts_payslip", "payslip_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    batch_id = Column(Integer, nullable=False)
    row_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    confidence = Column(Numeric(5, 4), nullable=False)
    confidence_tier = Column(String(20), nullable=False)
    candidate_payload = Column(JSON, nullable=False)
    payslip_id = Column(Integer, ForeignKey("payslips.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    confirmed_at = Column(DateTime, nullable=True)
    excluded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __mapper_args__ = {"version_id_col": version}
