from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.career_case import CareerCase
from app.models.contract import Contract
from app.models.offer import Offer
from app.models.user import User


def get_owned_case(db: Session, case_id: int, user: User) -> CareerCase:
    case = (
        db.query(CareerCase)
        .filter(CareerCase.id == case_id, CareerCase.user_id == user.id)
        .first()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return case


def get_owned_offer(db: Session, offer_id: int, user: User) -> Offer:
    offer = (
        db.query(Offer)
        .join(CareerCase, CareerCase.id == Offer.case_id)
        .filter(Offer.id == offer_id, CareerCase.user_id == user.id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer 不存在")
    return offer


def get_owned_contract(db: Session, contract_id: int, user: User) -> Contract:
    contract = (
        db.query(Contract)
        .join(CareerCase, CareerCase.id == Contract.case_id)
        .filter(Contract.id == contract_id, CareerCase.user_id == user.id)
        .first()
    )
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    return contract

