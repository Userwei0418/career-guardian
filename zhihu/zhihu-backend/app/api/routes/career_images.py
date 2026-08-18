from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.ai_configuration import CareerImageGeneration
from app.models.user import User
from app.schemas.career_image import (
    CareerImageCurrentView,
    CareerImageGenerationView,
    CareerImageVersionList,
)
from app.services.ai_configuration_service import effective_image_configuration
from app.services.career_image_service import (
    CareerImageError,
    CareerImageProviderError,
    CareerImageSourceError,
    activate_version,
    generation_to_view,
    list_versions,
    mark_current_staleness,
    pending_generation,
    refresh_generation,
    start_generation,
)


router = APIRouter()


def _owned_generation(db: Session, user_id: int, generation_id: int) -> CareerImageGeneration:
    row = (
        db.query(CareerImageGeneration)
        .filter(
            CareerImageGeneration.id == generation_id,
            CareerImageGeneration.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="职业形象版本不存在")
    return row


@router.get("/current", response_model=CareerImageCurrentView)
def get_current_career_image(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pending = pending_generation(db, user.id)
    current, message, source_ready = mark_current_staleness(db, user.id)
    provider_ready = effective_image_configuration(db) is not None
    return CareerImageCurrentView(
        current=generation_to_view(current) if current else None,
        pending=generation_to_view(pending) if pending else None,
        can_generate=source_ready and provider_ready and pending is None,
        source_ready=source_ready,
        source_message=(
            message
            if provider_ready
            else f"{message}；图片生成服务尚未由管理员启用"
        ),
    )


@router.post(
    "/generate",
    response_model=CareerImageGenerationView,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_career_image(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return generation_to_view(start_generation(db, user.id))
    except CareerImageSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CareerImageProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/versions", response_model=CareerImageVersionList)
def get_career_image_versions(
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_versions(db, user.id, page=page, page_size=page_size)


@router.get("/generations/{generation_id}", response_model=CareerImageGenerationView)
def get_career_image_generation(
    generation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _owned_generation(db, user.id, generation_id)
    return generation_to_view(refresh_generation(db, row))


@router.post("/generations/{generation_id}/activate", response_model=CareerImageGenerationView)
def activate_career_image_generation(
    generation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return generation_to_view(activate_version(db, user.id, generation_id))
    except CareerImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/generations/{generation_id}/asset/{variant}")
def get_career_image_asset(
    generation_id: int,
    variant: Literal["landscape", "square"],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _owned_generation(db, user.id, generation_id)
    image = getattr(row, f"{variant}_image")
    content_type = getattr(row, f"{variant}_content_type")
    if not image or not content_type:
        raise HTTPException(status_code=404, detail="该尺寸图片尚未生成")
    return Response(
        content=image,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
