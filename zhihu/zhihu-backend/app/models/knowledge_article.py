from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    applicable_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applicable_regions: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["全国通用"])
    source_title: Mapped[str] = mapped_column(String(255), nullable=False, default="职护知识库整理")
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    content_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
