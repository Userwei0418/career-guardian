from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_current_user
from app.api.ownership import get_owned_case, get_owned_contract, get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.contract import Contract
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.schemas.contract import ContractCreate, ContractResponse, ContractReviewResponse, ConsistencyResponse, ChecklistResponse
from app.services.contract_review_service import review_contract, compute_risk_score, generate_checklist
from app.services.consistency_service import check_consistency

router = APIRouter()


def _contract_evidence(db: Session, contract: Contract) -> Optional[Evidence]:
    if contract.career_event_id is None:
        return None
    source_ref = f"contract:{contract.id}"
    evidence = (
        db.query(Evidence)
        .filter(Evidence.event_id == contract.career_event_id, Evidence.source_ref == source_ref)
        .first()
    )
    if evidence is None:
        evidence = Evidence(
            event_id=contract.career_event_id,
            evidence_type="contract",
            source_type="user_material",
            title="合同关键条款与审查原文",
            content_excerpt=(contract.raw_text or "")[:500] or None,
            source_ref=source_ref,
            extra_data={
                "private_user_material": True,
                "linked_offer_id": contract.linked_offer_id,
            },
            confidence=1,
        )
        db.add(evidence)
        db.flush()
    return evidence


def _sync_contract_review(db: Session, contract: Contract, findings: list[dict]) -> tuple[int, int]:
    evidence = _contract_evidence(db, contract)
    if evidence is None:
        return 0, 0
    finding_count = 0
    action_count = 0
    severity_map = {"high": "high", "medium": "warning", "low": "info"}
    for item in findings:
        category = f"contract_rule:{item.get('code', 'unknown')}"
        finding = (
            db.query(GuardianFinding)
            .filter(
                GuardianFinding.event_id == contract.career_event_id,
                GuardianFinding.category == category,
            )
            .first()
        )
        if finding is None:
            finding = GuardianFinding(
                event_id=contract.career_event_id,
                evidence_id=evidence.id,
                domain="rights",
                category=category,
                severity=severity_map.get(item.get("severity"), "warning"),
                status="open",
                title=item["title"],
                explanation=item.get("description"),
                source_type="rule",
                confidence=item.get("confidence"),
            )
            db.add(finding)
            db.flush()
            finding_count += 1
        action = db.query(ActionItem).filter(ActionItem.finding_id == finding.id).first()
        if action is None:
            action = ActionItem(
                event_id=contract.career_event_id,
                finding_id=finding.id,
                title=item.get("recommendation") or f"确认：{item['title']}",
                status="pending",
                priority=10 if item.get("severity") == "high" else 30,
                requires_confirmation=True,
            )
            db.add(action)
            action_count += 1
    return finding_count, action_count


def _sync_consistency_diffs(db: Session, contract: Contract, diffs: list[dict]) -> tuple[int, int]:
    evidence = _contract_evidence(db, contract)
    if evidence is None:
        return 0, 0
    finding_count = 0
    action_count = 0
    for item in diffs:
        if item.get("status") == "consistent":
            continue
        category = f"offer_contract:{item['field']}"
        finding = (
            db.query(GuardianFinding)
            .filter(
                GuardianFinding.event_id == contract.career_event_id,
                GuardianFinding.category == category,
            )
            .first()
        )
        if finding is None:
            finding = GuardianFinding(
                event_id=contract.career_event_id,
                evidence_id=evidence.id,
                domain="rights",
                category=category,
                severity="high" if item.get("status") == "mismatch" else "warning",
                status="open",
                title=f"{item['field']}与 Offer 存在差异",
                explanation=item.get("suggestion"),
                source_type="calculation",
                confidence=1,
            )
            db.add(finding)
            db.flush()
            finding_count += 1
        action = db.query(ActionItem).filter(ActionItem.finding_id == finding.id).first()
        if action is None:
            action = ActionItem(
                event_id=contract.career_event_id,
                finding_id=finding.id,
                title=item.get("suggestion") or f"向 HR 确认{item['field']}差异",
                status="pending",
                priority=10 if item.get("status") == "mismatch" else 20,
                requires_confirmation=True,
            )
            db.add(action)
            action_count += 1
    return finding_count, action_count


def _sync_signing_checklist(db: Session, contract: Contract, checklist: list[dict]) -> int:
    if contract.career_event_id is None:
        return 0
    created = 0
    for item in checklist:
        existing = (
            db.query(ActionItem)
            .filter(
                ActionItem.event_id == contract.career_event_id,
                ActionItem.title == item["title"],
            )
            .first()
        )
        if existing is not None:
            continue
        db.add(
            ActionItem(
                event_id=contract.career_event_id,
                title=item["title"],
                description=item.get("description"),
                status="pending",
                priority={"must": 10, "should": 30, "nice": 50}.get(item.get("priority"), 50),
                requires_confirmation=True,
            )
        )
        created += 1
    return created


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
    synced_findings, synced_actions = _sync_contract_review(db, contract, findings)
    db.commit()

    return ContractReviewResponse(
        contract_id=contract_id,
        findings=findings,
        score=score,
        total_risks=len(findings),
        high_risks=len([f for f in findings if f["severity"] == "high"]),
        synced_finding_count=synced_findings,
        synced_action_count=synced_actions,
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
    synced_findings, synced_actions = _sync_consistency_diffs(db, contract, diffs)
    db.commit()
    return ConsistencyResponse(
        contract_id=contract_id,
        offer_id=offer.id,
        diffs=diffs,
        consistent_count=len([d for d in diffs if d["status"] == "consistent"]),
        issue_count=len([d for d in diffs if d["status"] != "consistent"]),
        synced_finding_count=synced_findings,
        synced_action_count=synced_actions,
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
    synced_actions = _sync_signing_checklist(db, contract, checklist)
    db.commit()
    return ChecklistResponse(
        contract_id=contract_id,
        checklist=checklist,
        synced_action_count=synced_actions,
    )
