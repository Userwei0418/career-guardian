from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
