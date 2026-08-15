from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_user
from app.api.ownership import get_owned_case, get_owned_contract, get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.contract import Contract
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.career_event import CareerEvent
from app.schemas.contract import ContractCreate, ContractResponse, ContractReviewResponse, ConsistencyResponse, ChecklistResponse
from app.services.contract_review_service import review_contract, compute_risk_score, generate_checklist
from app.services.consistency_service import check_consistency

router = APIRouter()


@router.get("/", response_model=List[ContractResponse])
def list_contracts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case_ids = [c.id for c in db.query(CareerCase).filter(CareerCase.user_id == user.id).all()]
    if not case_ids:
        return []
    contracts = db.query(Contract).filter(Contract.case_id.in_(case_ids)).all()
    return contracts


@router.post("/", response_model=ContractResponse)
def create_contract(data: ContractCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract_data = data.model_dump(exclude_unset=True)
    case = None
    offer = None

    if data.case_id is not None:
        case = get_owned_case(db, data.case_id, user)

    if data.linked_offer_id is not None:
        offer = get_owned_offer(db, data.linked_offer_id, user)
        if case is not None and offer.case_id != case.id:
            raise HTTPException(status_code=400, detail="合同任务与关联 Offer 不一致")

    if case is None and offer is not None:
        contract_data["case_id"] = offer.case_id
    elif case is None:
        case = CareerCase(
            user_id=user.id,
            type="contract_review",
            title=f"{data.employer or '新'} 合同检查",
        )
        db.add(case)
        db.flush()
        contract_data["case_id"] = case.id

    if data.career_event_id is not None:
        event = get_owned_event(db, data.career_event_id, user)
        if event.event_type != "rights":
            raise HTTPException(status_code=400, detail="合同必须关联权益守护事件")
    else:
        event = CareerEvent(
            user_id=user.id,
            event_type="rights",
            title=f"{data.employer or '新'} 合同权益检查",
            status="active",
        )
        db.add(event)
        db.flush()
        contract_data["career_event_id"] = event.id

    contract = Contract(**contract_data)
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


@router.get("/{contract_id}", response_model=ContractResponse)
def get_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_contract(db, contract_id, user)


@router.post("/{contract_id}/review", response_model=ContractReviewResponse)
def review_contract_endpoint(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_owned_contract(db, contract_id, user)

    raw_text = contract.raw_text or ""
    if not raw_text:
        raise HTTPException(status_code=400, detail="合同文本为空，请先上传或粘贴合同内容")

    findings = review_contract(raw_text, db=db)
    score = compute_risk_score(findings)

    return ContractReviewResponse(
        contract_id=contract_id,
        findings=findings,
        score=score,
        total_risks=len(findings),
        high_risks=len([f for f in findings if f["severity"] == "high"]),
    )


@router.post("/{contract_id}/consistency", response_model=ConsistencyResponse)
def check_consistency_endpoint(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_owned_contract(db, contract_id, user)

    if not contract.linked_offer_id:
        raise HTTPException(status_code=400, detail="合同未关联 Offer，无法进行一致性检查")

    offer = get_owned_offer(db, contract.linked_offer_id, user)

    offer_data = {
        "monthly_salary": str(offer.monthly_salary) if offer.monthly_salary else None,
        "city": offer.city,
        "probation_months": str(offer.probation_months) if offer.probation_months else None,
        "bonus": offer.bonus,
    }
    contract_data = {
        "salary_terms": contract.salary_terms,
        "work_location": contract.work_location,
        "probation": contract.probation,
    }

    diffs = check_consistency(offer_data, contract_data)
    return ConsistencyResponse(
        contract_id=contract_id,
        offer_id=offer.id,
        diffs=diffs,
        consistent_count=len([d for d in diffs if d["status"] == "consistent"]),
        issue_count=len([d for d in diffs if d["status"] != "consistent"]),
    )


@router.post("/{contract_id}/checklist", response_model=ChecklistResponse)
def get_checklist(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_owned_contract(db, contract_id, user)

    raw_text = contract.raw_text or ""
    findings = review_contract(raw_text, db=db) if raw_text else []

    offer_data = None
    if contract.linked_offer_id:
        offer = get_owned_offer(db, contract.linked_offer_id, user)
        offer_data = {
            "monthly_salary": str(offer.monthly_salary) if offer.monthly_salary else None,
            "city": offer.city,
        }

    checklist = generate_checklist(findings, offer_data)
    return ChecklistResponse(contract_id=contract_id, checklist=checklist)
