from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.session import Base


class PersonalAttachmentVersion(Base):
    """用户私有附件的通用版本记录。

    业务表只保存对附件版本的引用；真实存储路径不对前端暴露。
    """

    __tablename__ = "personal_attachment_versions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "document_type",
            "logical_key",
            "version_number",
            name="uq_personal_attachment_version",
        ),
        UniqueConstraint("id", "user_id", name="uq_personal_attachment_id_owner"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_type = Column(String(30), nullable=False, index=True)
    logical_key = Column(String(100), nullable=False)
    version_number = Column(Integer, nullable=False)
    display_name = Column(String(200), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(150), nullable=False, default="application/octet-stream")
    storage_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class PersonalAttachmentCleanupJob(Base):
    """Durable tombstone for a private file whose metadata has been deleted."""

    __tablename__ = "personal_attachment_cleanup_jobs"
    __table_args__ = (
        UniqueConstraint("storage_path", name="uq_attachment_cleanup_storage_path"),
        Index("ix_attachment_cleanup_user", "user_id", "status", "id"),
        Index("ix_attachment_cleanup_status", "status", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Deliberately no FK: account deletion must not erase the cleanup target.
    user_id = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    content_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)
