from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ContractReviewResult(Base):
    __tablename__ = "contract_review_results"
    __table_args__ = (
        UniqueConstraint("contract_file_id", "perspective_code", name="uq_review_result_contract_perspective"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    contract_file_id: Mapped[int] = mapped_column(
        ForeignKey("contract_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    perspective_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="enterprise", server_default="enterprise",
    )
    extracted_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    risks: Mapped[list] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_grade: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    latest_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("review_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    latest_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    contract_file: Mapped["ContractFile"] = relationship()
