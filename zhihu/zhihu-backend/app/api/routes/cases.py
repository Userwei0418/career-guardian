from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.career_case import CareerCase
from app.schemas.offer import CaseCreateRequest, CaseResponse

router = APIRouter()


@router.get("/", response_model=list[CaseResponse])
def list_cases(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cases = db.query(CareerCase).filter(CareerCase.user_id == user.id).order_by(CareerCase.started_at.desc()).all()
    return cases


@router.post("/", response_model=CaseResponse)
def create_case(req: CaseCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = CareerCase(user_id=user.id, type=req.type, title=req.title)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(CareerCase).filter(CareerCase.id == case_id, CareerCase.user_id == user.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="任务不存在")
    return case


@router.delete("/{case_id}")
def delete_case(case_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case = db.query(CareerCase).filter(CareerCase.id == case_id, CareerCase.user_id == user.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.delete(case)
    db.commit()
    return {"ok": True}
