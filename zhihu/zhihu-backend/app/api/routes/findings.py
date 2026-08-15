from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_case
from app.db.session import get_db
from app.models.user import User
from app.models.finding import Finding

router = APIRouter()


@router.get("/")
def list_findings(case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    get_owned_case(db, case_id, user)
    findings = db.query(Finding).filter(Finding.case_id == case_id).order_by(Finding.severity).all()
    return findings
