from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.schemas.personal_attachment import PersonalAttachmentResponse
from app.services.personal_attachment_service import DOCUMENT_TYPES, resolve_attachment_path


router = APIRouter()


def _owned_attachment(db: Session, user_id: int, attachment_id: int) -> PersonalAttachmentVersion:
    attachment = (
        db.query(PersonalAttachmentVersion)
        .filter(
            PersonalAttachmentVersion.id == attachment_id,
            PersonalAttachmentVersion.user_id == user_id,
        )
        .first()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件版本不存在")
    return attachment


@router.get("/", response_model=list[PersonalAttachmentResponse])
def list_attachments(
    document_type: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if document_type is not None and document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail="不支持的附件类型")
    query = db.query(PersonalAttachmentVersion).filter(PersonalAttachmentVersion.user_id == user.id)
    if document_type:
        query = query.filter(PersonalAttachmentVersion.document_type == document_type)
    return query.order_by(PersonalAttachmentVersion.created_at.desc(), PersonalAttachmentVersion.id.desc()).all()


@router.get("/{attachment_id}", response_model=PersonalAttachmentResponse)
def get_attachment(
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _owned_attachment(db, user.id, attachment_id)


@router.get("/{attachment_id}/file")
def get_attachment_file(
    attachment_id: int,
    inline: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    attachment = _owned_attachment(db, user.id, attachment_id)
    try:
        path = resolve_attachment_path(attachment)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="附件原件已丢失，请重新上传") from exc
    return FileResponse(
        path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
        content_disposition_type="inline" if inline else "attachment",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
