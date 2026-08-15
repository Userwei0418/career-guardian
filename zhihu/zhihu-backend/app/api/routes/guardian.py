from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.guardian import GuardianStateResponse
from app.services.guardian_state_service import build_guardian_state


router = APIRouter()


@router.get("/state", response_model=GuardianStateResponse)
def get_guardian_state(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return build_guardian_state(db, user.id)
