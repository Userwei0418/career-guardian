from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.resume import ResumeVersion
from app.models.user import User
from app.schemas.resume import ResumePasteRequest, ResumeVersionDetailResponse, ResumeVersionResponse
from app.services.document_service import extract_text, validate_upload
from app.services.opportunity_analysis_service import extract_resume_skills
from app.services.personal_attachment_service import save_personal_attachment
from app.services.resume_parsing_service import parse_resume_profile


router = APIRouter()


def _store_resume(
    db: Session,
    user: User,
    display_name: str,
    content_text: str,
    original_filename: str | None,
    parse_mode: str,
    attachment_version_id: int | None = None,
    version_number: int | None = None,
) -> ResumeVersion:
    cleaned = content_text.strip()
    content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    db.query(ResumeVersion).filter(ResumeVersion.user_id == user.id).update(
        {ResumeVersion.is_active: False}, synchronize_session=False
    )
    version = version_number or int(
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
        attachment_version_id=attachment_version_id,
        content_text=cleaned,
        content_hash=content_hash,
        extracted_skills=extract_resume_skills(cleaned),
        parse_mode=parse_mode,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    try:
        profile, profile_mode, model, parse_error, parsed_at = parse_resume_profile(cleaned, db, user.id)
        resume.structured_profile = profile
        resume.profile_parse_mode = profile_mode
        resume.profile_parse_model = model
        resume.profile_parse_error = parse_error
        resume.profile_parsed_at = parsed_at
        if isinstance(profile.get("skills"), list):
            resume.extracted_skills = list(dict.fromkeys([*resume.extracted_skills, *profile["skills"]]))[:40]
        db.commit()
        db.refresh(resume)
    except Exception as exc:
        db.rollback()
        resume = db.get(ResumeVersion, resume.id)
        if resume is not None:
            resume.profile_parse_mode = "rules"
            resume.profile_parse_error = f"结构化解析失败：{type(exc).__name__}"[:500]
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
    version_number = int(
        db.query(func.max(ResumeVersion.version_number))
        .filter(ResumeVersion.user_id == user.id)
        .scalar()
        or 0
    ) + 1
    attachment = save_personal_attachment(
        db,
        user_id=user.id,
        document_type="resume",
        logical_key="resume",
        display_name=filename.rsplit(".", 1)[0],
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
        version_number=version_number,
    )
    return _store_resume(
        db,
        user,
        filename.rsplit(".", 1)[0],
        result.raw_text,
        filename,
        result.parse_mode,
        attachment_version_id=attachment.id,
        version_number=version_number,
    )


@router.post("/paste", response_model=ResumeVersionResponse, status_code=status.HTTP_201_CREATED)
def paste_resume(
    data: ResumePasteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _store_resume(db, user, data.display_name, data.text, None, "text")


@router.get("/{resume_id}", response_model=ResumeVersionDetailResponse)
def get_resume_detail(
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
    return resume


@router.post("/{resume_id}/parse", response_model=ResumeVersionDetailResponse)
def reparse_resume(
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
    profile, profile_mode, model, parse_error, parsed_at = parse_resume_profile(resume.content_text, db, user.id)
    resume.structured_profile = profile
    resume.profile_parse_mode = profile_mode
    resume.profile_parse_model = model
    resume.profile_parse_error = parse_error
    resume.profile_parsed_at = parsed_at
    if isinstance(profile.get("skills"), list):
        resume.extracted_skills = list(dict.fromkeys([*resume.extracted_skills, *profile["skills"]]))[:40]
    db.commit()
    db.refresh(resume)
    return resume


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
