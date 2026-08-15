from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.resume import ResumeVersion
from app.models.user import User
from app.schemas.resume import ResumePasteRequest, ResumeVersionResponse
from app.services.document_service import extract_text, validate_upload
from app.services.opportunity_analysis_service import extract_resume_skills


router = APIRouter()


def _store_resume(
    db: Session,
    user: User,
    display_name: str,
    content_text: str,
    original_filename: str | None,
    parse_mode: str,
) -> ResumeVersion:
    cleaned = content_text.strip()
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    existing = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.user_id == user.id, ResumeVersion.content_hash == content_hash)
        .first()
    )
    db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).update(
        {ResumeVersion.is_active: False}, synchronize_session=False
    )
    if existing is not None:
        existing.extracted_skills = extract_resume_skills(cleaned)
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing
    version = int(
        db.query(func.max(ResumeVersion.version_number))
        .filter(ResumeVersion.user_id == user.id)
        .scalar()
        or 0
    ) + 1
    resume = ResumeVersion(
        user_id=user.id,
        version_number=version,
        display_name=display_name.strip()[:200],
        original_filename=original_filename[:255] if original_filename else None,
        content_text=cleaned,
        content_hash=content_hash,
        extracted_skills=extract_resume_skills(cleaned),
        parse_mode=parse_mode,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("/", response_model=list[ResumeVersionResponse])
def list_resumes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(ResumeVersion)
        .filter(ResumeVersion.user_id == user.id)
        .order_by(ResumeVersion.version_number.desc())
        .all()
    )


@router.post("/upload", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = file.filename or "未命名简历"
    content = await file.read()
    error = validate_upload(filename, file.content_type or "", len(content))
    if error:
        raise HTTPException(status_code=400, detail=error)
    result = extract_text(content, filename)
    if result.parse_mode == "failed":
        raise HTTPException(status_code=400, detail=result.parse_notice or "简历文字解析失败")
    return _store_resume(db, user, filename.rsplit(".", 1)[0], result.raw_text, filename, result.parse_mode)


@router.post("/paste", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
def paste_resume(
    data: ResumePasteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _store_resume(db, user, data.display_name, data.text, None, "text")


@router.patch("/{resume_id}/activate", response_model=ResumeVersionResponse)
def activate_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.id == resume_id, ResumeVersion.user_id == user.id)
        .first()
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="简历版本不存在")
    db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).update(
        {ResumeVersion.is_active: False}, synchronize_session=False
    )
    resume.is_active = True
    db.commit()
    db.refresh(resume)
    return resume
