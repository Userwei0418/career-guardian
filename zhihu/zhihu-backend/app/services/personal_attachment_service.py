from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.personal_attachment import PersonalAttachmentVersion


DOCUMENT_TYPES = {"resume", "offer", "contract", "payslip", "other"}


def _upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).expanduser().resolve()


def _safe_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return extension if re.fullmatch(r"\.[a-z0-9]{1,10}", extension) else ".bin"


def save_personal_attachment(
    db: Session,
    *,
    user_id: int,
    document_type: str,
    logical_key: str,
    display_name: str,
    original_filename: str,
    content_type: str,
    content: bytes,
    version_number: int | None = None,
) -> PersonalAttachmentVersion:
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("不支持的附件类型")
    normalized_key = logical_key.strip()[:100] or "default"
    if version_number is None:
        version_number = int(
            db.query(func.max(PersonalAttachmentVersion.version_number))
            .filter(
                PersonalAttachmentVersion.user_id == user_id,
                PersonalAttachmentVersion.document_type == document_type,
                PersonalAttachmentVersion.logical_key == normalized_key,
            )
            .scalar()
            or 0
        ) + 1

    digest = hashlib.sha256(content).hexdigest()
    key_digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:16]
    relative_path = Path("personal") / str(user_id) / document_type / key_digest / f"v{version_number}-{digest[:16]}{_safe_extension(original_filename)}"
    absolute_path = (_upload_root() / relative_path).resolve()
    if _upload_root() not in absolute_path.parents:
        raise ValueError("附件存储路径无效")
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = absolute_path.with_suffix(f"{absolute_path.suffix}.part")
    temporary_path.write_bytes(content)
    os.replace(temporary_path, absolute_path)

    db.query(PersonalAttachmentVersion).filter(
        PersonalAttachmentVersion.user_id == user_id,
        PersonalAttachmentVersion.document_type == document_type,
        PersonalAttachmentVersion.logical_key == normalized_key,
    ).update({PersonalAttachmentVersion.is_active: False}, synchronize_session=False)
    attachment = PersonalAttachmentVersion(
        user_id=user_id,
        document_type=document_type,
        logical_key=normalized_key,
        version_number=version_number,
        display_name=display_name.strip()[:200] or original_filename[:200],
        original_filename=original_filename.replace("\\", "/").rsplit("/", 1)[-1][:255],
        content_type=(content_type or "application/octet-stream")[:150],
        storage_path=str(relative_path),
        file_size=len(content),
        content_hash=digest,
        is_active=True,
    )
    db.add(attachment)
    db.flush()
    return attachment


def resolve_attachment_path(attachment: PersonalAttachmentVersion) -> Path:
    root = _upload_root()
    path = (root / attachment.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError(attachment.storage_path)
    return path


def delete_user_attachment_files(db: Session, user_id: int) -> None:
    attachments = db.query(PersonalAttachmentVersion).filter_by(user_id=user_id).all()
    for attachment in attachments:
        try:
            resolve_attachment_path(attachment).unlink(missing_ok=True)
        except FileNotFoundError:
            continue
