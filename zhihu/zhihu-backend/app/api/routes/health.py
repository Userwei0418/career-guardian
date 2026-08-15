from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "dependencies": {"database": database_status},
    }


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库不可用",
        ) from exc

    return {
        "status": "ready",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "dependencies": {"database": "ok"},
    }
