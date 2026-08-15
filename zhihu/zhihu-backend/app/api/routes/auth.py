from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.contract import Contract
from app.models.payslip import Payslip
from app.models.finding import Finding
from app.models.journey_node import JourneyNode
from app.models.salary_calculation import SalaryCalculation
from app.models.user_profile import UserProfile
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.models.resume import OpportunityAnalysis, ResumeVersion
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.api.deps import get_current_user, require_admin

router = APIRouter()


def _delete_business_data(user_id: int, db: Session) -> None:
    event_ids = [event.id for event in db.query(CareerEvent.id).filter(CareerEvent.user_id == user_id).all()]
    if event_ids:
        db.query(OpportunityAnalysis).filter(OpportunityAnalysis.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Outcome).filter(Outcome.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(DecisionRecord).filter(DecisionRecord.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(ActionItem).filter(ActionItem.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(GuardianFinding).filter(GuardianFinding.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Evidence).filter(Evidence.event_id.in_(event_ids)).delete(synchronize_session=False)
        db.query(Offer).filter(Offer.career_event_id.in_(event_ids)).update(
            {Offer.career_event_id: None}, synchronize_session=False
        )
        db.query(Contract).filter(Contract.career_event_id.in_(event_ids)).update(
            {Contract.career_event_id: None}, synchronize_session=False
        )
        db.query(Payslip).filter(Payslip.career_event_id.in_(event_ids)).update(
            {Payslip.career_event_id: None}, synchronize_session=False
        )
        db.query(CareerEvent).filter(CareerEvent.id.in_(event_ids)).delete(synchronize_session=False)

    case_ids = [case.id for case in db.query(CareerCase.id).filter(CareerCase.user_id == user_id).all()]
    if case_ids:
        db.query(Offer).filter(Offer.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Contract).filter(Contract.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Payslip).filter(Payslip.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(Finding).filter(Finding.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(JourneyNode).filter(JourneyNode.case_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(CareerCase).filter(CareerCase.id.in_(case_ids)).delete(synchronize_session=False)
    db.query(SalaryCalculation).filter(SalaryCalculation.user_id == user_id).delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id == user_id).delete(synchronize_session=False)
    db.query(OpportunityAnalysis).filter(OpportunityAnalysis.user_id == user_id).delete(synchronize_session=False)
    db.query(ResumeVersion).filter(ResumeVersion.user_id == user_id).delete(synchronize_session=False)
    db.query(JourneyNode).filter(JourneyNode.user_id == user_id, JourneyNode.case_id.is_(None)).delete(synchronize_session=False)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username, is_demo=user.is_demo, is_admin=user.is_admin)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=req.username, password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username, is_demo=user.is_demo, is_admin=user.is_admin)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.delete("/data")
def delete_user_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除用户所有业务数据（保留账号）"""
    _delete_business_data(user.id, db)
    db.commit()
    return {"ok": True, "message": "已清空所有业务数据"}


@router.delete("/account")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除整个账号及所有关联数据"""
    _delete_business_data(user.id, db)
    db.delete(user)
    db.commit()
    return {"ok": True, "message": "账号已删除"}


@router.get("/users", response_model=list[UserResponse])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员：获取所有用户列表"""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """管理员：删除指定用户及所有数据"""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    _delete_business_data(target.id, db)
    db.delete(target)
    db.commit()
    return {"ok": True, "message": f"用户 {target.username} 已删除"}
