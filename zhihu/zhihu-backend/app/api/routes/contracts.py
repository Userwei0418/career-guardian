from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.deps import get_current_user
from app.api.ownership import get_owned_case, get_owned_contract, get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.user import User
from app.models.contract import Contract, ContractFollowUpTurn, ContractReviewSnapshot
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.models.career_event import ActionItem, CareerEvent, DecisionRecord, Evidence, GuardianFinding, Outcome
from app.schemas.contract import (
    ChecklistResponse,
    ConsistencyResponse,
    ContractCreate,
    ContractDetailResponse,
    ContractFollowUpHistoryResponse,
    ContractFollowUpRequest,
    ContractFollowUpResponse,
    ContractPasteCreate,
    ContractResponse,
    ContractReviewResponse,
    ContractUpdate,
)
from app.services.contract_review_service import (
    classify_labor_document,
    create_or_reuse_review_snapshot,
    generate_checklist,
    infer_document_kind,
    prepare_review_snapshot,
    review_contract,
    segment_contract_text,
)
from app.services.contract_ai_review_service import (
    ask_redacted_contract_clause,
    compare_offer_contract_with_ai,
    redact_contract_follow_up_text,
)
from app.services.consistency_service import check_consistency
from app.services.decision_handoff_service import record_decision_handoff_outcome
from app.services.document_service import validate_upload
from app.services.personal_attachment_service import resolve_attachment_path, save_personal_attachment
from app.services.user_record_deletion_service import delete_event_graph, delete_orphan_career_case

router = APIRouter()

DOCUMENT_KINDS = {
    "auto",
    "labor_contract",
    "internship_agreement",
    "non_compete_agreement",
    "confidentiality_agreement",
    "training_service_agreement",
    "supplemental_agreement",
    "separation_agreement",
    "other_employment_document",
}


def _validate_document_kind(value: str) -> str:
    if value not in DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="不支持的劳动用工文件类型")
    return value


def _latest_review(db: Session, contract_id: int) -> Optional[ContractReviewSnapshot]:
    return (
        db.query(ContractReviewSnapshot)
        .filter(ContractReviewSnapshot.contract_id == contract_id)
        .order_by(ContractReviewSnapshot.review_number.desc())
        .first()
    )


def _review_detail(review: ContractReviewSnapshot) -> dict:
    data = {
        column.name: getattr(review, column.name)
        for column in ContractReviewSnapshot.__table__.columns
    }
    # Snapshots created before the privacy metadata migration legitimately have
    # SQL NULL in these additive columns.  Preserve the old review itself while
    # returning the empty collection shape promised by the current API.
    data["clause_segments"] = data.get("clause_segments") or []
    data["redaction_report"] = data.get("redaction_report") or {}
    data["coverage_report"] = data.get("coverage_report") or {}
    data["ai_status"] = data.get("ai_status") or "not_requested"
    data["ai_input_clause_count"] = int(data.get("ai_input_clause_count") or 0)
    return data


def _contract_detail(db: Session, contract: Contract) -> dict:
    review = _latest_review(db, contract.id)
    review_count = (
        db.query(ContractReviewSnapshot)
        .filter(ContractReviewSnapshot.contract_id == contract.id)
        .count()
    )
    data = {column.name: getattr(contract, column.name) for column in Contract.__table__.columns}
    data["parse_quality"] = data.get("parse_quality") or {}
    data["latest_review"] = _review_detail(review) if review is not None else None
    data["review_count"] = review_count
    data["linked_offer"] = None
    data["linked_offer_contract_count"] = 0
    data["linked_offer_contract_index"] = None
    if contract.linked_offer_id is not None:
        offer = db.get(Offer, contract.linked_offer_id)
        if offer is not None:
            data["linked_offer"] = {
                "id": offer.id,
                "name": offer.name,
                "company_name": offer.company_name,
                "job_title": offer.job_title,
            }
            siblings = (
                db.query(Contract.id)
                .filter(
                    Contract.linked_offer_id == contract.linked_offer_id,
                    Contract.status != "archived",
                )
                .order_by(Contract.created_at.asc(), Contract.id.asc())
                .all()
            )
            sibling_ids = [row[0] for row in siblings]
            data["linked_offer_contract_count"] = len(sibling_ids)
            data["linked_offer_contract_index"] = sibling_ids.index(contract.id) + 1 if contract.id in sibling_ids else None
    return data


def _apply_extracted_fields(contract: Contract, extracted_fields: dict) -> None:
    for field_name in (
        "employer",
        "contract_term",
        "probation",
        "salary_terms",
        "work_location",
        "working_hours",
        "non_compete",
        "termination_terms",
    ):
        item = extracted_fields.get(field_name) or {}
        value = item.get("value")
        if item.get("status") == "extracted" and value and not getattr(contract, field_name):
            setattr(contract, field_name, value)


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
    severity_map = {"important": "high", "review": "warning", "note": "info"}
    for item in findings:
        category = f"contract:{contract.id}:rule:{item.get('code', 'unknown')}"
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
                severity=severity_map.get(item.get("attention"), "warning"),
                status="open",
                title=item["title"],
                explanation=item.get("explanation"),
                source_type="rule",
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
                title=item.get("next_step") or f"确认：{item['title']}",
                status="pending",
                priority=10 if item.get("attention") == "important" else 30,
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
    status_titles = {
        "mismatch": "与 Offer 存在差异",
        "missing": "在合同中未找到明确约定",
        "vague": "合同表述还不够明确",
        "uncertain": "暂时无法确认是否一致",
    }
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
        finding_title = f"{item['field']}{status_titles.get(item.get('status'), '需要进一步核对')}"
        source_type = "ai_assistance" if item.get("source") == "ai_model" else "calculation"
        if finding is None:
            finding = GuardianFinding(
                event_id=contract.career_event_id,
                evidence_id=evidence.id,
                domain="rights",
                category=category,
                severity="high" if item.get("status") == "mismatch" else "warning",
                status="open",
                title=finding_title,
                explanation=item.get("suggestion"),
                source_type=source_type,
                confidence=item.get("confidence") or 1,
            )
            db.add(finding)
            db.flush()
            finding_count += 1
        else:
            finding.severity = "high" if item.get("status") == "mismatch" else "warning"
            finding.status = "open"
            finding.title = finding_title
            finding.explanation = item.get("suggestion")
            finding.source_type = source_type
            finding.confidence = item.get("confidence") or 1
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
        else:
            action.title = item.get("suggestion") or f"确认{item['field']}的书面约定"
            action.priority = 10 if item.get("status") == "mismatch" else 20
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


def _create_contract_record(data: ContractCreate, user: User, db: Session) -> Contract:
    _validate_document_kind(data.document_kind)
    contract_data = data.model_dump(exclude={"source_action_id"}, exclude_unset=True)
    case = None
    offer = None

    if data.source_attachment_id is not None:
        attachment = (
            db.query(PersonalAttachmentVersion)
            .filter(
                PersonalAttachmentVersion.id == data.source_attachment_id,
                PersonalAttachmentVersion.user_id == user.id,
                PersonalAttachmentVersion.document_type == "contract",
            )
            .first()
        )
        if attachment is None:
            raise HTTPException(status_code=404, detail="合同原件不存在")

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
            title=f"{data.display_name or data.employer or '新'} 合同检查",
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
            title=f"{data.display_name or data.employer or '新'} 合同权益检查",
            status="active",
        )
        db.add(event)
        db.flush()
        contract_data["career_event_id"] = event.id

    contract = Contract(**contract_data)
    db.add(contract)
    db.flush()
    if data.source_action_id is not None:
        action = (
            db.query(ActionItem)
            .filter(ActionItem.id == data.source_action_id, ActionItem.event_id == event.id)
            .first()
        )
        if action is None:
            raise HTTPException(status_code=404, detail="权益守护待办不存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        action.status = "completed"
        action.confirmed_at = action.confirmed_at or now
        action.completed_at = now
        record_decision_handoff_outcome(
            db,
            user_id=user.id,
            handoff_event=event,
            outcome_type="contract_recorded",
            result=f"合同 {contract.id} 已保存并进入权益核对",
            action_id=action.id,
        )
    return contract


@router.get("/", response_model=List[ContractDetailResponse])
def list_contracts(
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_ids = [c.id for c in db.query(CareerCase).filter(CareerCase.user_id == user.id).all()]
    if not case_ids:
        return []
    query = db.query(Contract).filter(Contract.case_id.in_(case_ids))
    if not include_archived:
        query = query.filter(Contract.status != "archived")
    contracts = query.order_by(Contract.updated_at.desc(), Contract.id.desc()).all()
    return [_contract_detail(db, contract) for contract in contracts]


@router.post("/", response_model=ContractResponse)
def create_contract(data: ContractCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = _create_contract_record(data, user, db)
    db.commit()
    db.refresh(contract)
    return contract


@router.post("/upload", response_model=ContractDetailResponse)
async def upload_contract(
    file: UploadFile = File(...),
    display_name: Optional[str] = Form(None),
    document_kind: str = Form("auto"),
    linked_offer_id: Optional[int] = Form(None),
    career_event_id: Optional[int] = Form(None),
    source_action_id: Optional[int] = Form(None),
    auto_review: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_document_kind(document_kind)
    filename = file.filename or "contract.bin"
    content = await file.read()
    error = validate_upload(filename, file.content_type or "", len(content))
    if error:
        raise HTTPException(status_code=400, detail=error)

    contract = _create_contract_record(
        ContractCreate(
            display_name=display_name or filename.rsplit(".", 1)[0],
            document_kind=document_kind,
            linked_offer_id=linked_offer_id,
            career_event_id=career_event_id,
            source_action_id=source_action_id,
            parse_status="processing",
        ),
        user,
        db,
    )
    attachment = save_personal_attachment(
        db,
        user_id=user.id,
        document_type="contract",
        logical_key=f"contract-{contract.id}",
        display_name=contract.display_name or filename,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    contract.source_attachment_id = attachment.id
    contract.parse_status = "processing" if auto_review else "extracting"
    contract.parse_notice = "原件已经保存，正在本地读取合同文字。" if auto_review else "原件已经保存，尚未开始审查。"
    db.commit()
    db.refresh(contract)
    return _contract_detail(db, contract)


@router.post("/paste", response_model=ContractDetailResponse)
def paste_contract(
    data: ContractPasteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = data.text.strip()
    if len(text) < 50:
        raise HTTPException(status_code=400, detail="合同文字太少，请粘贴更完整的劳动用工文件")
    _validate_document_kind(data.document_kind)
    text_detected_kind = infer_document_kind(text) if data.document_kind == "auto" else None
    detected_kind = (
        text_detected_kind or infer_document_kind(text, data.display_name)
        if data.document_kind == "auto"
        else None
    )
    resolved_kind = detected_kind or data.document_kind
    contract = _create_contract_record(
        ContractCreate(
            display_name=data.display_name or "粘贴的劳动合同",
            document_kind=resolved_kind,
            linked_offer_id=data.linked_offer_id,
            career_event_id=data.career_event_id,
            source_action_id=data.source_action_id,
            parse_status="processing" if data.auto_review else "ready",
            parse_mode="paste",
            raw_text=text,
        ),
        user,
        db,
    )
    contract.parse_notice = "文字已经保存，正在拆分合同条款。" if data.auto_review else "文字已经保存，尚未开始审查。"
    contract.text_page_count = 1
    contract.ocr_page_count = 0
    contract.page_count = 1
    contract.parse_quality = {
        "actual_page_count": 1,
        "text_page_count": 1,
        "ocr_page_count": 0,
        "empty_page_count": 0,
        "low_quality_page_count": 0,
        "repeated_block_count": 0,
        "character_count": len(text),
        "document_profile": classify_labor_document(text),
        "document_kind_detection": {
            "status": "detected" if detected_kind else "needs_confirmation" if data.document_kind == "auto" else "manual",
            "value": detected_kind or (data.document_kind if data.document_kind != "auto" else None),
            "source": (
                "local_text"
                if text_detected_kind
                else "local_filename"
                if detected_kind
                else "unresolved"
                if data.document_kind == "auto"
                else "user_selection"
            ),
            "was_automatic": data.document_kind == "auto",
        },
        "pages": [{"page": 1, "start": 0, "end": len(text), "character_count": len(text), "source_mode": "paste"}],
    }
    db.commit()
    db.refresh(contract)
    return _contract_detail(db, contract)


@router.get("/{contract_id}", response_model=ContractDetailResponse)
def get_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _contract_detail(db, get_owned_contract(db, contract_id, user))


@router.patch("/{contract_id}", response_model=ContractDetailResponse)
def update_contract(
    contract_id: int,
    data: ContractUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = get_owned_contract(db, contract_id, user)
    updates = data.model_dump(exclude_unset=True)
    if "document_kind" in updates:
        updates["document_kind"] = _validate_document_kind(updates["document_kind"])
    if "status" in updates and updates["status"] not in {"active", "archived"}:
        raise HTTPException(status_code=400, detail="不支持的合同状态")
    if "linked_offer_id" in updates and updates["linked_offer_id"] is not None:
        get_owned_offer(db, updates["linked_offer_id"], user)
    for field, value in updates.items():
        setattr(contract, field, value)
    if "document_kind" in updates and updates["document_kind"] != "auto":
        contract.parse_quality = {
            **(contract.parse_quality if isinstance(contract.parse_quality, dict) else {}),
            "document_kind_detection": {
                "status": "manual",
                "value": updates["document_kind"],
                "source": "user_selection",
                "was_automatic": False,
            },
        }
    if updates.get("status") == "archived":
        contract.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif updates.get("status") == "active":
        contract.archived_at = None
    db.commit()
    db.refresh(contract)
    return _contract_detail(db, contract)


@router.post("/{contract_id}/review", response_model=ContractReviewResponse)
def review_contract_endpoint(
    contract_id: int,
    refresh: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = get_owned_contract(db, contract_id, user)

    raw_text = contract.raw_text or ""
    if not raw_text:
        raise HTTPException(status_code=400, detail="合同文本为空，请先上传或粘贴合同内容")

    snapshot, reused = create_or_reuse_review_snapshot(db, contract, user_id=user.id, force=refresh)
    _apply_extracted_fields(contract, snapshot.extracted_fields)
    synced_findings, synced_actions = _sync_contract_review(db, contract, snapshot.findings)
    db.commit()
    db.refresh(snapshot)

    return ContractReviewResponse(
        contract_id=contract_id,
        snapshot_id=snapshot.id,
        review_number=snapshot.review_number,
        findings=snapshot.findings,
        extracted_fields=snapshot.extracted_fields,
        summary=snapshot.summary,
        important_count=len([item for item in snapshot.findings if item["attention"] == "important"]),
        review_count=len([item for item in snapshot.findings if item["attention"] == "review"]),
        reused=reused,
        reviewed_at=snapshot.created_at,
        synced_finding_count=synced_findings,
        synced_action_count=synced_actions,
    )


@router.post("/{contract_id}/review-task", response_model=ContractDetailResponse)
def queue_contract_review(
    contract_id: int,
    refresh: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue a recoverable review and return before the remote model call."""

    contract = get_owned_contract(db, contract_id, user)
    if contract.parse_status in {"processing", "reviewing"}:
        return _contract_detail(db, contract)
    if not (contract.raw_text or "").strip():
        raise HTTPException(status_code=400, detail="合同文本为空，请先上传或粘贴合同内容")
    if refresh and contract.source_attachment_id is not None:
        # Re-run local extraction first so reviews created before the
        # coordinate-aware PDF parser do not keep stale, displaced values.
        contract.parse_status = "processing"
        contract.parse_notice = "正在用新版本地解析重新读取原件，再逐段审查。"
        contract.parse_quality = {
            **(contract.parse_quality if isinstance(contract.parse_quality, dict) else {}),
            "force_review_requested": True,
        }
        db.commit()
        db.refresh(contract)
        return _contract_detail(db, contract)
    snapshot, reused = prepare_review_snapshot(db, contract, force=refresh)
    if reused and snapshot.ai_status not in {"queued", "running"} and not refresh:
        return _contract_detail(db, contract)
    contract.parse_status = "reviewing"
    contract.parse_notice = "合同条款已经拆分，正在等待模型逐段核对。"
    db.commit()
    db.refresh(contract)
    return _contract_detail(db, contract)


def _follow_up_context(
    db: Session,
    contract: Contract,
    clause_id: str,
    finding_code: str,
) -> tuple[ContractReviewSnapshot, dict, dict]:
    snapshot = _latest_review(db, contract.id)
    if snapshot is None:
        raise HTTPException(status_code=409, detail="请先完成一次合同审查，再继续追问")
    segment = next((item for item in list(snapshot.clause_segments or []) if item.get("id") == clause_id), None)
    finding = next((item for item in list(snapshot.findings or []) if item.get("code") == finding_code), None)
    if segment is None or finding is None or finding.get("clause_id") != clause_id:
        raise HTTPException(status_code=404, detail="没有找到这条核对结论对应的合同原文")
    return snapshot, segment, finding


@router.get("/{contract_id}/review-follow-up", response_model=ContractFollowUpHistoryResponse)
def get_contract_review_follow_up_history(
    contract_id: int,
    clause_id: str = Query(min_length=1, max_length=100),
    finding_code: str = Query(min_length=1, max_length=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = get_owned_contract(db, contract_id, user)
    snapshot, _, _ = _follow_up_context(db, contract, clause_id, finding_code)
    items = (
        db.query(ContractFollowUpTurn)
        .filter(
            ContractFollowUpTurn.user_id == user.id,
            ContractFollowUpTurn.contract_id == contract.id,
            ContractFollowUpTurn.review_snapshot_id == snapshot.id,
            ContractFollowUpTurn.clause_id == clause_id,
            ContractFollowUpTurn.finding_code == finding_code,
        )
        .order_by(ContractFollowUpTurn.turn_number.asc())
        .all()
    )
    return ContractFollowUpHistoryResponse(
        contract_id=contract.id,
        review_snapshot_id=snapshot.id,
        clause_id=clause_id,
        finding_code=finding_code,
        items=items,
    )


@router.post("/{contract_id}/review-follow-up", response_model=ContractFollowUpResponse)
def follow_up_contract_review(
    contract_id: int,
    data: ContractFollowUpRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = get_owned_contract(db, contract_id, user)
    snapshot, segment, finding = _follow_up_context(db, contract, data.clause_id, data.finding_code)
    previous_turns = (
        db.query(ContractFollowUpTurn)
        .filter(
            ContractFollowUpTurn.user_id == user.id,
            ContractFollowUpTurn.contract_id == contract.id,
            ContractFollowUpTurn.review_snapshot_id == snapshot.id,
            ContractFollowUpTurn.clause_id == data.clause_id,
            ContractFollowUpTurn.finding_code == data.finding_code,
        )
        .order_by(ContractFollowUpTurn.turn_number.desc())
        .limit(3)
        .all()
    )
    previous_turns.reverse()
    persisted_history = [
        message
        for turn in previous_turns
        for message in (
            {"role": "user", "content": turn.question},
            {"role": "assistant", "content": turn.answer},
        )
    ]
    try:
        redacted_question = redact_contract_follow_up_text(contract.raw_text or "", data.question)
        result = ask_redacted_contract_clause(
            db,
            raw_text=contract.raw_text or "",
            clause_segment=segment,
            finding=finding,
            question=data.question,
            # The database is the conversation source of truth. Client-supplied
            # history remains accepted for API compatibility but is not trusted.
            history=persisted_history,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="追问内容含有尚未安全脱敏的信息，请去掉联系方式或身份证件信息后再试") from exc
    except RuntimeError as exc:
        code = str(exc)
        if "Timeout" in code:
            message = "模型这次没有在时限内完成回答，请稍后再试"
        elif code == "FollowUpAnswerMissing":
            message = "模型连续两次没有返回完整回答，请稍后重试；你的问题没有问题"
        elif code == "ModelResponseInvalidJSON":
            message = "模型连续两次返回了异常格式，请稍后重试；你的问题没有问题"
        else:
            message = "这次追问没有完成，请稍后重试；你的问题没有问题"
        raise HTTPException(status_code=503, detail=message) from exc
    next_turn = int(
        db.query(func.max(ContractFollowUpTurn.turn_number))
        .filter(
            ContractFollowUpTurn.review_snapshot_id == snapshot.id,
            ContractFollowUpTurn.clause_id == data.clause_id,
            ContractFollowUpTurn.finding_code == data.finding_code,
        )
        .scalar()
        or 0
    ) + 1
    db.add(ContractFollowUpTurn(
        user_id=user.id,
        contract_id=contract.id,
        review_snapshot_id=snapshot.id,
        clause_id=data.clause_id,
        finding_code=data.finding_code,
        turn_number=next_turn,
        question=redacted_question,
        answer=result.answer,
        evidence_quote=result.evidence_quote,
        limits=result.limits,
        provider_name=result.provider_name,
        model_name=result.model_name,
        prompt_version=result.prompt_version,
        redaction_version=result.redaction_version,
        review_method=result.review_method,
    ))
    db.commit()
    return ContractFollowUpResponse(**result.__dict__)


@router.delete("/{contract_id}")
def delete_contract(contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    contract = get_owned_contract(db, contract_id, user)
    case_id = contract.case_id
    event_id = contract.career_event_id
    attachments = (
        db.query(PersonalAttachmentVersion)
        .filter(
            PersonalAttachmentVersion.user_id == user.id,
            PersonalAttachmentVersion.document_type == "contract",
            PersonalAttachmentVersion.logical_key == f"contract-{contract.id}",
        )
        .all()
    )
    attachment_paths = []
    for attachment in attachments:
        try:
            attachment_paths.append(resolve_attachment_path(attachment))
        except FileNotFoundError:
            continue
    db.delete(contract)
    for attachment in attachments:
        db.delete(attachment)
    db.flush()

    if event_id is not None:
        evidence = db.query(Evidence).filter(
            Evidence.event_id == event_id,
            Evidence.source_ref == f"contract:{contract_id}",
        ).first()
        if evidence is not None:
            finding_ids = [
                row.id for row in db.query(GuardianFinding.id).filter(
                    GuardianFinding.event_id == event_id,
                    GuardianFinding.evidence_id == evidence.id,
                ).all()
            ]
            if finding_ids:
                db.query(ActionItem).filter(ActionItem.finding_id.in_(finding_ids)).delete(synchronize_session=False)
                db.query(GuardianFinding).filter(GuardianFinding.id.in_(finding_ids)).delete(synchronize_session=False)
            db.delete(evidence)
            db.flush()
        event_has_records = any(
            query.first() is not None
            for query in (
                db.query(Contract.id).filter(Contract.career_event_id == event_id),
                db.query(Evidence.id).filter(Evidence.event_id == event_id),
                db.query(GuardianFinding.id).filter(GuardianFinding.event_id == event_id),
                db.query(ActionItem.id).filter(ActionItem.event_id == event_id),
                db.query(DecisionRecord.id).filter(DecisionRecord.event_id == event_id),
                db.query(Outcome.id).filter(Outcome.event_id == event_id),
            )
        )
        if not event_has_records:
            delete_event_graph(db, [event_id])
    delete_orphan_career_case(db, case_id, user.id)
    db.commit()
    for path in attachment_paths:
        path.unlink(missing_ok=True)
    return {"ok": True, "message": "合同记录和对应私有原件已删除"}


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

    fallback_diffs = check_consistency(offer_data, contract_data)
    latest_review = _latest_review(db, contract.id)
    clause_segments = list(latest_review.clause_segments or []) if latest_review is not None else segment_contract_text(contract.raw_text or "")
    ai_result = compare_offer_contract_with_ai(
        db,
        raw_text=contract.raw_text or "",
        clause_segments=clause_segments,
        offer_data=offer_data,
        fallback_diffs=fallback_diffs,
        user_id=user.id,
    )
    diffs = ai_result.diffs
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
        review_mode=ai_result.review_mode,
        model_status=ai_result.model_status,
        provider_name=ai_result.provider_name,
        model_name=ai_result.model_name,
        prompt_version=ai_result.prompt_version,
        redaction_version=ai_result.redaction_version,
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
