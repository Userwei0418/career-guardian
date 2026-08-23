"""工资条 API"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_contract, get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.contract import Contract
from app.models.cashflow import EconomicFact, EconomicFactRelation, FinancialTransaction
from app.models.cashflow_import import FinancialImportBatch, FinancialRecognitionArtifact
from app.models.offer import Offer
from app.models.payslip import (
    Payslip,
    PayslipArrivalLink,
    PayslipArrivalLinkRevision,
    PayslipMaterialLink,
    PayslipRecognitionCandidateDraft,
)
from app.models.user import User
from app.services.payslip_service import (
    analyze_payslip,
    build_arrival_suggestions,
    build_contract_pay_date_suggestion,
    build_payslip_guardian_summary,
    build_material_comparisons,
    build_month_comparison,
    enrich_arrival_suggestions_with_ai,
)
from app.services.decision_handoff_service import record_decision_handoff_outcome
from app.schemas.payslip import (
    PayslipAnalyzeRequest,
    PayslipAnalyzeResponse,
    PayslipArrivalLinkCreateRequest,
    PayslipArrivalLinkResponse,
    PayslipArrivalLinkRevisionResponse,
    PayslipArrivalLinkSummary,
    PayslipArrivalSuggestionResponse,
    PayslipCreateRequest,
    PayslipCreateResponse,
    PayslipDetailResponse,
    PayslipGuardianSummary,
    PayslipMaterialSummary,
    PayslipMonthComparison,
    PayslipPayDateSuggestionRequest,
    PayslipPayDateSuggestionResponse,
    PayslipRecognitionResponse,
    PayslipRecognitionBatchSummary,
    PayslipRecognitionBulkConfirmRequest,
    PayslipRecognitionBulkConfirmResponse,
    PayslipRecognitionCandidate,
    PayslipRecognitionCandidateUpdateRequest,
    PayslipResponse,
)
from app.services.cashflow_service import (
    commit_financial_ledger,
    get_owned_transaction,
    lock_financial_ledger_owner,
    record_financial_ledger_event,
)
from app.services.economic_fact_service import (
    get_fact_source_transaction,
    get_transaction_facts,
    get_transactions_facts,
)
from app.services.payslip_intake_service import (
    PARSER_VERSION,
    PayslipRecognitionError,
    recognize_payslip_upload,
)

router = APIRouter()


def _unique_ids(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def _resolved_material_preferences(
    preferences,
    *,
    offer_ids: list[int],
    contract_ids: list[int],
) -> dict[tuple[str, int], dict]:
    linked_keys = {("offer", material_id) for material_id in offer_ids}
    linked_keys.update(("contract", material_id) for material_id in contract_ids)
    resolved: dict[tuple[str, int], dict] = {}
    for preference in preferences:
        key = (preference.material_type, preference.material_id)
        if key not in linked_keys:
            raise HTTPException(status_code=400, detail="材料优先级只能设置给本次实际关联的 Offer 或合同")
        if key in resolved:
            raise HTTPException(status_code=400, detail="同一份关联材料不能重复设置优先级")
        resolved[key] = {
            "application_status": preference.application_status,
            "priority_rank": preference.priority_rank,
            "user_note": (preference.user_note or "").strip() or None,
        }
    for material_type in ("offer", "contract"):
        preferred = [
            key for key, value in resolved.items()
            if key[0] == material_type and value["application_status"] == "preferred"
        ]
        if len(preferred) > 1:
            label = "Offer" if material_type == "offer" else "合同/协议"
            raise HTTPException(status_code=400, detail=f"同一份工资条最多选择一份{label}作为当前优先参照")
    for index, key in enumerate(sorted(linked_keys), start=1):
        resolved.setdefault(key, {
            "application_status": "unresolved",
            "priority_rank": index * 10,
            "user_note": None,
        })
    return resolved


def _material_preference_map(
    links: list[PayslipMaterialLink],
) -> dict[tuple[str, int], PayslipMaterialLink]:
    preferences: dict[tuple[str, int], PayslipMaterialLink] = {}
    for link in links:
        if link.offer_id is not None:
            preferences[("offer", link.offer_id)] = link
        elif link.contract_id is not None:
            preferences[("contract", link.contract_id)] = link
    return preferences


def _material_summaries(
    offers: list[Offer],
    contracts: list[Contract],
    links: list[PayslipMaterialLink] | None = None,
) -> list[PayslipMaterialSummary]:
    preferences = _material_preference_map(links or [])
    summaries = [
        PayslipMaterialSummary(
            material_type="offer",
            material_id=offer.id,
            title=offer.name or offer.company_name or f"Offer #{offer.id}",
            salary_reference=(
                f"税前月薪 ¥{float(offer.monthly_salary):,.2f}"
                if offer.monthly_salary is not None
                else "税前月薪待确认"
            ),
            document_kind=getattr(offer, "offer_kind", None) or "offer",
            application_status=getattr(preferences.get(("offer", offer.id)), "application_status", "unresolved"),
            priority_rank=getattr(preferences.get(("offer", offer.id)), "priority_rank", 100),
            user_note=getattr(preferences.get(("offer", offer.id)), "user_note", None),
        )
        for offer in offers
    ]
    summaries.extend(
        PayslipMaterialSummary(
            material_type="contract",
            material_id=contract.id,
            title=contract.display_name or contract.employer or f"劳动合同 #{contract.id}",
            salary_reference=(contract.salary_terms or "合同薪资条款待确认")[:240],
            document_kind=contract.document_kind,
            application_status=getattr(preferences.get(("contract", contract.id)), "application_status", "unresolved"),
            priority_rank=getattr(preferences.get(("contract", contract.id)), "priority_rank", 100),
            user_note=getattr(preferences.get(("contract", contract.id)), "user_note", None),
        )
        for contract in contracts
    )
    return sorted(
        summaries,
        key=lambda item: (
            0 if item.material_type == "offer" else 1,
            item.priority_rank,
            item.material_id,
        ),
    )


def _load_linked_materials(
    db: Session,
    payslip_id: int,
    user_id: int,
) -> tuple[list[Offer], list[Contract], list[PayslipMaterialLink]]:
    offers = (
        db.query(Offer)
        .join(PayslipMaterialLink, PayslipMaterialLink.offer_id == Offer.id)
        .join(CareerCase, CareerCase.id == Offer.case_id)
        .filter(PayslipMaterialLink.payslip_id == payslip_id, CareerCase.user_id == user_id)
        .order_by(PayslipMaterialLink.id.asc())
        .all()
    )
    contracts = (
        db.query(Contract)
        .join(PayslipMaterialLink, PayslipMaterialLink.contract_id == Contract.id)
        .join(CareerCase, CareerCase.id == Contract.case_id)
        .filter(PayslipMaterialLink.payslip_id == payslip_id, CareerCase.user_id == user_id)
        .order_by(PayslipMaterialLink.id.asc())
        .all()
    )
    links = db.query(PayslipMaterialLink).filter(
        PayslipMaterialLink.payslip_id == payslip_id,
    ).order_by(PayslipMaterialLink.priority_rank.asc(), PayslipMaterialLink.id.asc()).all()
    return offers, contracts, links


def _enrich_material_comparisons(
    comparisons: list[dict],
    offers: list[Offer],
    contracts: list[Contract],
    links: list[PayslipMaterialLink],
) -> list[dict]:
    preferences = _material_preference_map(links)
    document_kinds = {
        **{("offer", offer.id): getattr(offer, "offer_kind", None) or "offer" for offer in offers},
        **{("contract", contract.id): contract.document_kind for contract in contracts},
    }
    enriched: list[dict] = []
    for comparison in comparisons:
        key = (comparison["material_type"], comparison["material_id"])
        preference = preferences.get(key)
        enriched.append({
            **comparison,
            "document_kind": document_kinds.get(key),
            "application_status": getattr(preference, "application_status", "unresolved"),
            "priority_rank": getattr(preference, "priority_rank", 100),
            "user_note": getattr(preference, "user_note", None),
        })
    return sorted(
        enriched,
        key=lambda item: (
            0 if item["material_type"] == "offer" else 1,
            item["priority_rank"],
            item["material_id"],
        ),
    )


def _get_owned_payslip(
    db: Session,
    payslip_id: int,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> Payslip:
    query = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(Payslip.id == payslip_id, CareerCase.user_id == user_id)
    )
    if not include_deleted:
        query = query.filter(Payslip.record_status != "deleted")
    payslip = query.first()
    if payslip is None:
        raise HTTPException(status_code=404, detail="工资条不存在")
    return payslip


def _payslip_user_id(db: Session, payslip: Payslip) -> int:
    user_id = db.query(CareerCase.user_id).filter(CareerCase.id == payslip.case_id).scalar()
    if user_id is None:
        raise HTTPException(status_code=409, detail="工资条缺少有效的用户归属")
    return int(user_id)


def _set_payslip_guardian_records_active(db: Session, payslip: Payslip, *, active: bool) -> None:
    evidence_rows = db.query(Evidence).filter(Evidence.source_ref == f"payslip:{payslip.id}").all()
    evidence_ids = [item.id for item in evidence_rows]
    if not evidence_ids:
        return
    findings = db.query(GuardianFinding).filter(GuardianFinding.evidence_id.in_(evidence_ids)).all()
    finding_ids = [item.id for item in findings]
    for finding in findings:
        if not active:
            finding.status = "superseded"
        elif finding.severity == "info" and any(word in finding.title for word in ("一致", "未关联")):
            finding.status = "confirmed"
        else:
            finding.status = "open"
    if finding_ids:
        actions = db.query(ActionItem).filter(ActionItem.finding_id.in_(finding_ids)).all()
        for action in actions:
            action.status = "pending" if active else "cancelled"
            if active:
                action.completed_at = None


def _arrival_link_fact(
    db: Session,
    *,
    link: PayslipArrivalLink,
    user_id: int,
) -> EconomicFact:
    if link.economic_fact_id is not None:
        fact = db.query(EconomicFact).filter(
            EconomicFact.id == link.economic_fact_id,
            EconomicFact.user_id == user_id,
        ).one_or_none()
        if fact is None:
            raise HTTPException(status_code=409, detail="工资到账关系引用的经济事实不存在")
        return fact
    facts = get_transaction_facts(
        db,
        transaction_id=link.transaction_id,
        user_id=user_id,
    )
    if len(facts) != 1:
        raise HTTPException(status_code=409, detail="历史工资到账关系无法唯一定位经济事实，请先完成数据升级")
    return facts[0]


def _arrival_fact_transaction(
    db: Session,
    *,
    fact: EconomicFact,
    link_transaction_id: int,
    user_id: int,
) -> FinancialTransaction:
    transaction = get_fact_source_transaction(db, fact=fact, user_id=user_id)
    if transaction is None or transaction.id != link_transaction_id:
        raise HTTPException(status_code=409, detail="工资到账事实与来源流水不一致")
    return transaction


def _arrival_link_snapshot(link: PayslipArrivalLink) -> dict:
    return {
        "id": link.id,
        "payslip_id": link.payslip_id,
        "transaction_id": link.transaction_id,
        "economic_fact_id": link.economic_fact_id,
        "allocated_amount": format(Decimal(link.allocated_amount), "f"),
        "status": link.status,
        "match_reason": link.match_reason or [],
        "ledger_revision": link.ledger_revision,
        "confirmed_by_user_id": link.confirmed_by_user_id,
        "confirmed_at": link.confirmed_at.isoformat() if link.confirmed_at else None,
        "reversed_at": link.reversed_at.isoformat() if link.reversed_at else None,
    }


def _record_arrival_link_revision(
    db: Session,
    *,
    owner: User,
    link: PayslipArrivalLink,
    operation: str,
    ledger_revision: int,
    before_snapshot: dict | None,
    reason: str,
) -> None:
    link_revision = (
        db.query(func.max(PayslipArrivalLinkRevision.link_revision))
        .filter(PayslipArrivalLinkRevision.link_id == link.id)
        .scalar()
        or 0
    ) + 1
    db.add(PayslipArrivalLinkRevision(
        user_id=owner.id,
        link_id=link.id,
        link_revision=link_revision,
        ledger_revision=ledger_revision,
        operation=operation,
        before_snapshot=before_snapshot,
        after_snapshot=_arrival_link_snapshot(link),
        reason=reason,
        actor_user_id=owner.id,
    ))


def _reverse_all_arrival_links(
    db: Session,
    *,
    owner: User,
    payslip: Payslip,
    reason: str,
) -> list[PayslipArrivalLink]:
    links = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id == payslip.id,
        PayslipArrivalLink.status == "confirmed",
    ).all()
    if not links:
        return []
    before_snapshots = {link.id: _arrival_link_snapshot(link) for link in links}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for link in links:
        link.status = "reversed"
        link.reversed_at = now
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="payslip_arrival_reverse",
        entity_type="payslip",
        entity_id=payslip.id,
        summary=f"因工资条状态变化撤销 {len(links)} 个到账事实关系",
    )
    for link in links:
        link.ledger_revision = ledger_revision
        _record_arrival_link_revision(
            db,
            owner=owner,
            link=link,
            operation="reverse",
            ledger_revision=ledger_revision,
            before_snapshot=before_snapshots[link.id],
            reason=reason,
        )
    return links


def _arrival_link_response(
    db: Session,
    *,
    link: PayslipArrivalLink,
    user_id: int,
) -> PayslipArrivalLinkResponse:
    fact = _arrival_link_fact(db, link=link, user_id=user_id)
    transaction = _arrival_fact_transaction(
        db,
        fact=fact,
        link_transaction_id=link.transaction_id,
        user_id=user_id,
    )
    return PayslipArrivalLinkResponse(
        id=link.id,
        transaction_id=transaction.id,
        economic_fact_id=fact.id,
        allocated_amount=link.allocated_amount,
        transaction_date=fact.occurred_date,
        fact_title=fact.title,
        fact_amount=fact.amount,
        is_split_component=fact.primary_transaction_id is None,
        ledger_revision=link.ledger_revision,
        merchant=transaction.merchant,
        description=fact.description or transaction.description,
        status=link.status,
        match_reason=link.match_reason or [],
        confirmed_at=link.confirmed_at,
        reversed_at=link.reversed_at,
    )


def _arrival_link_summary(db: Session, payslip: Payslip) -> PayslipArrivalLinkSummary:
    rows = (
        db.query(PayslipArrivalLink)
        .filter(PayslipArrivalLink.payslip_id == payslip.id, PayslipArrivalLink.status == "confirmed")
        .order_by(PayslipArrivalLink.confirmed_at.asc(), PayslipArrivalLink.id.asc())
        .all()
    )
    user_id = _payslip_user_id(db, payslip)
    links = [
        _arrival_link_response(db, link=link, user_id=user_id)
        for link in rows
    ]
    net_salary = Decimal(payslip.net_salary or 0)
    confirmed_amount = sum((Decimal(link.allocated_amount) for link in rows), Decimal("0.00"))
    remaining_amount = max(Decimal("0.00"), net_salary - confirmed_amount)
    if confirmed_amount <= 0:
        match_status = "unmatched"
    elif remaining_amount <= Decimal("1.00"):
        match_status = "matched"
    else:
        match_status = "partial"
    return PayslipArrivalLinkSummary(
        payslip_id=payslip.id,
        net_salary=net_salary,
        confirmed_amount=confirmed_amount,
        remaining_amount=remaining_amount,
        match_status=match_status,
        links=links,
    )


def _arrival_search_window(payslip: Payslip) -> tuple[date, date, date]:
    if payslip.agreed_pay_date is not None:
        return (
            payslip.agreed_pay_date - timedelta(days=14),
            payslip.agreed_pay_date + timedelta(days=15),
            payslip.agreed_pay_date,
        )
    if payslip.pay_date is not None:
        return payslip.pay_date - timedelta(days=14), payslip.pay_date + timedelta(days=15), payslip.pay_date
    if payslip.pay_month:
        try:
            month_start = date.fromisoformat(f"{payslip.pay_month[:7]}-01")
            next_month = (
                date(month_start.year + 1, 1, 1)
                if month_start.month == 12
                else date(month_start.year, month_start.month + 1, 1)
            )
            reference_date = next_month + timedelta(days=9)
            return month_start, next_month + timedelta(days=20), reference_date
        except ValueError:
            pass
    created_date = payslip.created_at.date() if payslip.created_at is not None else date.today()
    return created_date - timedelta(days=30), created_date + timedelta(days=31), created_date


def _previous_payslip(db: Session, payslip: Payslip, user_id: int) -> Payslip | None:
    if not payslip.pay_month or not (payslip.employer_name or "").strip():
        return None
    employer = payslip.employer_name.strip().lower()
    return (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(
            Payslip.id != payslip.id,
            CareerCase.user_id == user_id,
            Payslip.record_status != "deleted",
            Payslip.pay_month.isnot(None),
            Payslip.pay_month < payslip.pay_month,
            func.lower(func.trim(Payslip.employer_name)) == employer,
        )
        .order_by(Payslip.pay_month.desc(), Payslip.created_at.desc(), Payslip.id.desc())
        .first()
    )


def _sync_salary_arrival_finding(
    db: Session,
    payslip: Payslip,
    summary: PayslipArrivalLinkSummary,
) -> None:
    if payslip.career_event_id is None:
        return
    finding = (
        db.query(GuardianFinding)
        .filter(
            GuardianFinding.event_id == payslip.career_event_id,
            GuardianFinding.category == "salary_arrival_status",
        )
        .order_by(GuardianFinding.id.desc())
        .first()
    )
    action_title: str | None = None
    if summary.match_status == "matched":
        latest_arrival = max(link.transaction_date for link in summary.links)
        if payslip.agreed_pay_date is not None:
            delay_days = (latest_arrival - payslip.agreed_pay_date).days
            if delay_days > 0:
                title = f"工资实际到账比约定日期晚 {delay_days} 天"
                explanation = "到账日期已由用户关联的真实收入流水确认；是否属于迟发还需结合合同条款和发放口径判断。"
                severity, finding_status = "high", "open"
                action_title = f"确认工资晚到 {delay_days} 天的原因和发薪口径"
            else:
                title = "工资实际到账日期未晚于已知约定日期"
                explanation = "已用真实收入流水核清到账金额和日期。"
                severity, finding_status = "info", "confirmed"
        else:
            title = "工资实际到账已核清，约定发薪日尚未提供"
            explanation = "已确认实际到账；因缺少约定发薪日，系统不作迟发判断。"
            severity, finding_status = "info", "confirmed"
    elif summary.match_status == "partial":
        title = f"工资已匹配部分到账，仍有 {float(summary.remaining_amount):.2f} 元待核清"
        explanation = "可继续关联分次到账，也可撤销错误关联；未核清前不认定漏发。"
        severity, finding_status = "high", "open"
        action_title = "继续核对剩余工资到账或确认差额原因"
    else:
        title = "工资条尚未关联真实到账证据"
        if payslip.agreed_pay_date is not None and date.today() > payslip.agreed_pay_date:
            explanation = "约定发薪日已过，但系统只能说“尚未核清”；请关联真实流水后再判断是否晚到。"
            action_title = "确认工资是否已到账并关联真实收入流水"
        else:
            explanation = "工资条实发只是权益证据，在用户关联真实收入流水前不作已到账结论。"
        severity, finding_status = "info", "open"

    if finding is None:
        finding = GuardianFinding(
            event_id=payslip.career_event_id,
            domain="income",
            category="salary_arrival_status",
            severity=severity,
            status=finding_status,
            title=title,
            explanation=explanation,
            source_type="calculation",
            confidence=1,
        )
        db.add(finding)
        db.flush()
    else:
        finding.severity = severity
        finding.status = finding_status
        finding.title = title
        finding.explanation = explanation
    pending_action = (
        db.query(ActionItem)
        .filter(ActionItem.finding_id == finding.id, ActionItem.status == "pending")
        .first()
    )
    if action_title:
        event = db.query(CareerEvent).filter(CareerEvent.id == payslip.career_event_id).first()
        if event is not None:
            event.status = "attention"
        if pending_action is None:
            db.add(
                ActionItem(
                    event_id=payslip.career_event_id,
                    finding_id=finding.id,
                    title=action_title,
                    status="pending",
                    priority=10,
                    requires_confirmation=True,
                )
            )
        else:
            pending_action.title = action_title
    elif pending_action is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        pending_action.status = "completed"
        pending_action.completed_at = now


@router.get("/", response_model=list[PayslipResponse])
def list_payslips(
    include_deleted: bool = Query(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case_ids = [item.id for item in db.query(CareerCase.id).filter(CareerCase.user_id == user.id).all()]
    if not case_ids:
        return []
    query = db.query(Payslip).filter(Payslip.case_id.in_(case_ids))
    if not include_deleted:
        query = query.filter(Payslip.record_status != "deleted")
    return (
        query
        .order_by(Payslip.created_at.desc(), Payslip.id.desc())
        .all()
    )


def _read_payslip_upload(file: UploadFile, max_size: int = 30 * 1024 * 1024) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = file.file.read(min(1024 * 1024, max_size + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > max_size:
            raise HTTPException(
                status_code=413,
                detail={"code": "payslip_upload_too_large", "message": "工资条文件不能超过 30MB"},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _payslip_recognition_origin(filename: str, content_type: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".csv", ".tsv", ".xlsx"}:
        return "file"
    if extension in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
        return "ocr"
    return "ocr" if content_type.startswith("image/") or content_type == "application/pdf" else "file"


def _owned_recognition_batch(
    db: Session,
    batch_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> FinancialImportBatch:
    query = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.id == batch_id,
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.source_type == "payslip",
    )
    if for_update:
        query = query.with_for_update()
    batch = query.first()
    if batch is None:
        raise HTTPException(status_code=404, detail="工资条识别批次不存在")
    return batch


def _owned_recognition_candidate(
    db: Session,
    candidate_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> PayslipRecognitionCandidateDraft:
    query = db.query(PayslipRecognitionCandidateDraft).join(
        FinancialImportBatch,
        FinancialImportBatch.id == PayslipRecognitionCandidateDraft.batch_id,
    ).filter(
        PayslipRecognitionCandidateDraft.id == candidate_id,
        PayslipRecognitionCandidateDraft.user_id == user_id,
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.source_type == "payslip",
    )
    if for_update:
        query = query.with_for_update()
    candidate = query.first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="工资条候选不存在")
    return candidate


def _sync_recognition_batch_counts(db: Session, batch: FinancialImportBatch) -> None:
    counts = dict(
        db.query(
            PayslipRecognitionCandidateDraft.status,
            func.count(PayslipRecognitionCandidateDraft.id),
        ).filter(
            PayslipRecognitionCandidateDraft.batch_id == batch.id,
            PayslipRecognitionCandidateDraft.user_id == batch.user_id,
        ).group_by(PayslipRecognitionCandidateDraft.status).all()
    )
    pending = int(counts.get("pending", 0))
    confirmed = int(counts.get("confirmed", 0))
    excluded = int(counts.get("excluded", 0))
    batch.total_count = pending + confirmed + excluded
    batch.review_count = pending
    batch.confirmed_count = confirmed
    batch.excluded_count = excluded
    batch.status = "completed" if batch.total_count > 0 and pending == 0 else "review"
    if batch.status == "completed" and batch.confirmed_at is None:
        batch.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif batch.status == "review":
        batch.confirmed_at = None


def _recognition_candidate_response(draft: PayslipRecognitionCandidateDraft) -> PayslipRecognitionCandidate:
    return PayslipRecognitionCandidate.model_validate({
        **dict(draft.candidate_payload or {}),
        "candidate_id": draft.id,
        "review_status": draft.status,
        "version": draft.version,
        "payslip_id": draft.payslip_id,
        "row_number": draft.row_number,
        "confidence": draft.confidence,
        "confidence_tier": draft.confidence_tier,
    })


def _recognition_batch_raw_text(db: Session, batch: FinancialImportBatch) -> str | None:
    artifact = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.artifact_type == "ocr_text",
        FinancialRecognitionArtifact.status == "ready",
    ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).first()
    return artifact.content_text if artifact else None


def _recognition_batch_response(
    db: Session,
    batch: FinancialImportBatch,
    *,
    resumed_existing_batch: bool = False,
) -> PayslipRecognitionResponse:
    drafts = db.query(PayslipRecognitionCandidateDraft).filter(
        PayslipRecognitionCandidateDraft.batch_id == batch.id,
        PayslipRecognitionCandidateDraft.user_id == batch.user_id,
    ).order_by(PayslipRecognitionCandidateDraft.row_number.asc()).all()
    source_type = str((batch.parse_hints or {}).get("payslip_source_type") or batch.origin_type)
    return PayslipRecognitionResponse(
        batch_id=batch.id,
        batch_status="completed" if batch.status == "completed" else "review",
        resumed_existing_batch=resumed_existing_batch,
        source_type=source_type,
        original_filename=batch.original_filename or "工资条",
        original_file_retained=False,
        raw_text=_recognition_batch_raw_text(db, batch),
        candidates=[_recognition_candidate_response(draft) for draft in drafts],
    )


def _recognition_batch_summary(batch: FinancialImportBatch) -> PayslipRecognitionBatchSummary:
    return PayslipRecognitionBatchSummary(
        batch_id=batch.id,
        batch_status="completed" if batch.status == "completed" else "review",
        source_type=str((batch.parse_hints or {}).get("payslip_source_type") or batch.origin_type),
        original_filename=batch.original_filename or "工资条",
        total_count=batch.total_count,
        pending_count=batch.review_count,
        confirmed_count=batch.confirmed_count,
        excluded_count=batch.excluded_count,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


@router.post("/recognize", response_model=PayslipRecognitionResponse)
def recognize_payslip(
    file: Annotated[UploadFile, File(...)],
    confirm_external_processing: Annotated[bool, Form()] = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    data_epoch = user.business_data_epoch
    db.rollback()
    content = _read_payslip_upload(file)
    safe_filename = Path(file.filename or "payslip").name
    content_type = file.content_type or "application/octet-stream"
    origin_type = _payslip_recognition_origin(safe_filename, content_type)
    content_hash = hashlib.sha256(content).hexdigest()
    existing_batch = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == origin_type,
        FinancialImportBatch.source_type == "payslip",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == PARSER_VERSION,
    ).first()
    if existing_batch is not None:
        return _recognition_batch_response(
            db,
            existing_batch,
            resumed_existing_batch=True,
        )
    try:
        result = recognize_payslip_upload(
            user_id=user_id,
            filename=safe_filename,
            content=content,
            content_type=content_type,
            confirm_external_processing=confirm_external_processing,
            expected_data_epoch=data_epoch,
        )
    except PayslipRecognitionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    candidate_payloads = [
        candidate.model_dump(
            mode="json",
            exclude={"candidate_id", "review_status", "version", "payslip_id"},
        )
        for candidate in result.candidates
    ]
    batch = FinancialImportBatch(
        user_id=user_id,
        origin_type=result.source_type,
        source_type="payslip",
        original_filename=safe_filename,
        content_type=content_type,
        file_size=len(content),
        content_hash=content_hash,
        parser_version=PARSER_VERSION,
        status="review",
        column_mapping={},
        parse_hints={
            "payslip_source_type": result.source_type,
            "original_file_retained": False,
        },
        total_count=len(candidate_payloads),
        ready_count=sum(item.get("confidence_tier") == "high" for item in candidate_payloads),
        review_count=len(candidate_payloads),
        parsed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(batch)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent_batch = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == origin_type,
            FinancialImportBatch.source_type == "payslip",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == PARSER_VERSION,
        ).first()
        if concurrent_batch is None:
            raise
        return _recognition_batch_response(
            db,
            concurrent_batch,
            resumed_existing_batch=True,
        )
    for row_number, (candidate, payload) in enumerate(zip(result.candidates, candidate_payloads), start=1):
        db.add(PayslipRecognitionCandidateDraft(
            user_id=user_id,
            batch_id=batch.id,
            row_number=candidate.row_number or row_number,
            status="pending",
            confidence=candidate.confidence,
            confidence_tier=candidate.confidence_tier,
            candidate_payload=payload,
        ))
    normalized_json = json.dumps(candidate_payloads, ensure_ascii=False, sort_keys=True).encode("utf-8")
    db.add(FinancialRecognitionArtifact(
        user_id=user_id,
        batch_id=batch.id,
        artifact_type="normalized_rows",
        sequence_number=1,
        status="ready",
        content_json=candidate_payloads,
        content_hash=hashlib.sha256(normalized_json).hexdigest(),
        content_type="application/json",
        byte_size=len(normalized_json),
        source_locator={"filename": safe_filename},
        artifact_metadata={"candidate_count": len(candidate_payloads), "original_file_retained": False},
    ))
    if result.raw_text:
        raw_bytes = result.raw_text.encode("utf-8")
        db.add(FinancialRecognitionArtifact(
            user_id=user_id,
            batch_id=batch.id,
            artifact_type="ocr_text",
            sequence_number=1,
            status="ready",
            content_text=result.raw_text,
            content_hash=hashlib.sha256(raw_bytes).hexdigest(),
            content_type="text/plain; charset=utf-8",
            byte_size=len(raw_bytes),
            source_locator={"filename": safe_filename},
            artifact_metadata={"complete_local_ocr_text": True, "original_file_retained": False},
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent_batch = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == origin_type,
            FinancialImportBatch.source_type == "payslip",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == PARSER_VERSION,
        ).first()
        if concurrent_batch is None:
            raise
        return _recognition_batch_response(
            db,
            concurrent_batch,
            resumed_existing_batch=True,
        )
    db.refresh(batch)
    return _recognition_batch_response(db, batch)


@router.get("/recognition-batches/open", response_model=list[PayslipRecognitionBatchSummary])
def list_open_recognition_batches(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batches = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user.id,
        FinancialImportBatch.source_type == "payslip",
        FinancialImportBatch.status == "review",
    ).order_by(FinancialImportBatch.updated_at.desc(), FinancialImportBatch.id.desc()).all()
    return [_recognition_batch_summary(batch) for batch in batches]


@router.get("/recognition-batches/{batch_id}", response_model=PayslipRecognitionResponse)
def get_recognition_batch(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _recognition_batch_response(db, _owned_recognition_batch(db, batch_id, user.id), resumed_existing_batch=True)


@router.put("/recognition-candidates/{candidate_id}", response_model=PayslipRecognitionResponse)
def update_recognition_candidate(
    candidate_id: int,
    data: PayslipRecognitionCandidateUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = _owned_recognition_candidate(db, candidate_id, user.id, for_update=True)
    if draft.status != "pending":
        raise HTTPException(status_code=409, detail="只有待核对工资条候选可以暂存修改")
    if draft.version != data.version:
        raise HTTPException(status_code=409, detail="候选已在其他页面更新，请刷新后继续")
    candidate = data.candidate.model_copy(update={
        "candidate_id": draft.id,
        "review_status": "pending",
        "version": draft.version,
        "payslip_id": None,
        "row_number": draft.row_number,
    })
    draft.confidence = candidate.confidence
    draft.confidence_tier = candidate.confidence_tier
    draft.candidate_payload = candidate.model_dump(
        mode="json",
        exclude={"candidate_id", "review_status", "version", "payslip_id"},
    )
    batch = _owned_recognition_batch(db, draft.batch_id, user.id, for_update=True)
    batch.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(draft)
    db.refresh(batch)
    return _recognition_batch_response(db, batch, resumed_existing_batch=True)


def _set_recognition_candidate_excluded(
    db: Session,
    *,
    draft: PayslipRecognitionCandidateDraft,
    excluded: bool,
) -> FinancialImportBatch:
    if excluded and draft.status != "pending":
        detail = "已经保存为正式工资条的候选不能排除" if draft.status == "confirmed" else "这份工资条候选已经排除"
        raise HTTPException(status_code=409, detail=detail)
    if not excluded and draft.status != "excluded":
        raise HTTPException(status_code=409, detail="这份工资条候选当前没有被排除")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    draft.status = "excluded" if excluded else "pending"
    draft.excluded_at = now if excluded else None
    batch = _owned_recognition_batch(db, draft.batch_id, draft.user_id, for_update=True)
    db.flush()
    _sync_recognition_batch_counts(db, batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/recognition-candidates/{candidate_id}/exclude", response_model=PayslipRecognitionResponse)
def exclude_recognition_candidate(
    candidate_id: int,
    version: int = Query(ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = _owned_recognition_candidate(db, candidate_id, user.id, for_update=True)
    if draft.version != version:
        raise HTTPException(status_code=409, detail="候选已在其他页面更新，请刷新后继续")
    return _recognition_batch_response(
        db,
        _set_recognition_candidate_excluded(db, draft=draft, excluded=True),
        resumed_existing_batch=True,
    )


@router.post("/recognition-candidates/{candidate_id}/reopen", response_model=PayslipRecognitionResponse)
def reopen_recognition_candidate(
    candidate_id: int,
    version: int = Query(ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft = _owned_recognition_candidate(db, candidate_id, user.id, for_update=True)
    if draft.version != version:
        raise HTTPException(status_code=409, detail="候选已在其他页面更新，请刷新后继续")
    return _recognition_batch_response(
        db,
        _set_recognition_candidate_excluded(db, draft=draft, excluded=False),
        resumed_existing_batch=True,
    )


@router.post(
    "/recognition-batches/{batch_id}/confirm-selected",
    response_model=PayslipRecognitionBulkConfirmResponse,
)
def confirm_selected_recognition_candidates(
    batch_id: int,
    data: PayslipRecognitionBulkConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    batch = _owned_recognition_batch(db, batch_id, user_id, for_update=True)
    requested_versions = {item.candidate_id: item.version for item in data.items}
    if len(requested_versions) != len(data.items):
        raise HTTPException(status_code=400, detail="批量确认不能重复选择同一份工资条候选")
    drafts = db.query(PayslipRecognitionCandidateDraft).filter(
        PayslipRecognitionCandidateDraft.user_id == user_id,
        PayslipRecognitionCandidateDraft.batch_id == batch.id,
        PayslipRecognitionCandidateDraft.id.in_(requested_versions),
    ).order_by(PayslipRecognitionCandidateDraft.row_number.asc()).with_for_update().all()
    if len(drafts) != len(requested_versions):
        raise HTTPException(status_code=404, detail="部分工资条候选不存在或不属于当前批次")

    prepared: list[tuple[PayslipRecognitionCandidateDraft, PayslipRecognitionCandidate]] = []
    selected_keys: set[tuple[str, str]] = set()
    for draft in drafts:
        if draft.version != requested_versions[draft.id]:
            raise HTTPException(status_code=409, detail=f"候选 #{draft.id} 已更新，请刷新批次后重试")
        if draft.status != "pending":
            raise HTTPException(status_code=409, detail=f"候选 #{draft.id} 已经处理")
        candidate = _recognition_candidate_response(draft)
        if candidate.confidence_tier != "high":
            raise HTTPException(status_code=409, detail=f"候选 #{draft.id} 不是绿色高置信项，必须逐份人工核对")
        if not candidate.pay_month or candidate.gross_salary is None or candidate.net_salary is None:
            raise HTTPException(status_code=409, detail=f"候选 #{draft.id} 缺少月份、应发或实发，不能批量确认")
        employer_key = (candidate.employer_name or "").strip().casefold()
        candidate_key = (candidate.pay_month, employer_key)
        if candidate_key in selected_keys:
            raise HTTPException(status_code=409, detail=f"批次中存在重复的 {candidate.pay_month} 工资条，请逐份确认")
        selected_keys.add(candidate_key)
        prepared.append((draft, candidate))

    months = {candidate.pay_month for _, candidate in prepared if candidate.pay_month}
    existing = db.query(Payslip).join(CareerCase, CareerCase.id == Payslip.case_id).filter(
        CareerCase.user_id == user_id,
        Payslip.record_status != "deleted",
        Payslip.pay_month.in_(months),
    ).all()
    for _, candidate in prepared:
        employer_key = (candidate.employer_name or "").strip().casefold()
        conflict = next((item for item in existing if item.pay_month == candidate.pay_month and (
            not employer_key or (item.employer_name or "").strip().casefold() == employer_key
        )), None)
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail=f"{candidate.pay_month} 已有工资条 #{conflict.id}，请逐份判断补发、修订或重复导入",
            )

    payslip_ids: list[int] = []
    try:
        for draft, candidate in prepared:
            response = _create_payslip_record(
                PayslipCreateRequest(
                    linked_offer_ids=data.linked_offer_ids,
                    linked_contract_ids=data.linked_contract_ids,
                    material_preferences=data.material_preferences,
                    pay_month=candidate.pay_month,
                    pay_date=candidate.pay_date,
                    employer_name=candidate.employer_name,
                    gross_salary=float(candidate.gross_salary),
                    base_salary=float(candidate.base_salary) if candidate.base_salary is not None else None,
                    performance=float(candidate.performance) if candidate.performance is not None else None,
                    bonus=float(candidate.bonus) if candidate.bonus is not None else None,
                    overtime_pay=float(candidate.overtime_pay) if candidate.overtime_pay is not None else None,
                    allowance=float(candidate.allowance) if candidate.allowance is not None else None,
                    social_insurance=float(candidate.social_insurance) if candidate.social_insurance is not None else None,
                    housing_fund=float(candidate.housing_fund) if candidate.housing_fund is not None else None,
                    individual_tax=float(candidate.individual_tax) if candidate.individual_tax is not None else None,
                    attendance_deductions=float(candidate.attendance_deductions) if candidate.attendance_deductions is not None else None,
                    meal_deductions=float(candidate.meal_deductions) if candidate.meal_deductions is not None else None,
                    other_deductions=float(candidate.other_deductions) if candidate.other_deductions is not None else None,
                    net_salary=float(candidate.net_salary),
                    custom_items=candidate.custom_items,
                    source_type=str((batch.parse_hints or {}).get("payslip_source_type") or batch.origin_type),
                    recognition_confidence=candidate.confidence,
                    recognition_candidate_id=draft.id,
                    recognition_candidate_version=draft.version,
                    expected_salary=data.expected_salary,
                    city=data.city,
                ),
                user=user,
                db=db,
                commit=False,
            )
            payslip_ids.append(response.payslip.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed_batch = _owned_recognition_batch(db, batch_id, user_id)
    return PayslipRecognitionBulkConfirmResponse(
        batch=_recognition_batch_response(db, refreshed_batch, resumed_existing_batch=True),
        payslip_ids=payslip_ids,
    )


@router.post(
    "/agreed-pay-date-suggestions",
    response_model=PayslipPayDateSuggestionResponse,
)
def suggest_agreed_pay_dates(
    data: PayslipPayDateSuggestionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract_ids = _unique_ids(data.linked_contract_ids)
    if len(contract_ids) != len(data.linked_contract_ids):
        raise HTTPException(status_code=400, detail="发薪日建议不能重复关联同一份合同")
    preferences = _resolved_material_preferences(
        data.material_preferences,
        offer_ids=[],
        contract_ids=contract_ids,
    )
    contracts = [get_owned_contract(db, contract_id, user) for contract_id in contract_ids]
    suggestions = [
        build_contract_pay_date_suggestion(
            pay_month=data.pay_month,
            contract=contract,
            application_status=preferences[("contract", contract.id)]["application_status"],
        )
        for contract in contracts
    ]
    suggestions.sort(key=lambda item: (
        0 if item["application_status"] == "preferred" else 1,
        preferences[("contract", item["contract_id"])]["priority_rank"],
        item["contract_id"],
    ))
    return PayslipPayDateSuggestionResponse(
        pay_month=data.pay_month,
        suggestions=suggestions,
    )


@router.get("/{payslip_id}", response_model=PayslipDetailResponse)
def get_payslip(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = (
        db.query(Payslip)
        .join(CareerCase, CareerCase.id == Payslip.case_id)
        .filter(Payslip.id == payslip_id, CareerCase.user_id == user.id)
        .first()
    )
    if payslip is None:
        raise HTTPException(status_code=404, detail="工资条不存在")
    offers, contracts, links = _load_linked_materials(db, payslip.id, user.id)
    return PayslipDetailResponse(
        **PayslipResponse.model_validate(payslip).model_dump(),
        materials=_material_summaries(offers, contracts, links),
        material_comparisons=_enrich_material_comparisons(
            build_material_comparisons(payslip, offers, contracts),
            offers,
            contracts,
            links,
        ),
    )


@router.get("/{payslip_id}/month-comparison", response_model=PayslipMonthComparison)
def get_month_comparison(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    return build_month_comparison(payslip, _previous_payslip(db, payslip, user.id))


@router.get("/{payslip_id}/guardian-summary", response_model=PayslipGuardianSummary)
def get_guardian_summary(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    offers, contracts, links = _load_linked_materials(db, payslip.id, user.id)
    material_comparisons = _enrich_material_comparisons(
        build_material_comparisons(payslip, offers, contracts),
        offers,
        contracts,
        links,
    )
    month_comparison = build_month_comparison(
        payslip,
        _previous_payslip(db, payslip, user.id),
    )
    return build_payslip_guardian_summary(
        payslip=payslip,
        material_comparisons=material_comparisons,
        arrival_summary=_arrival_link_summary(db, payslip),
        month_comparison=month_comparison,
        offers=offers,
    )


@router.get("/{payslip_id}/arrival-suggestions", response_model=PayslipArrivalSuggestionResponse)
def get_arrival_suggestions(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    if payslip.record_status != "active":
        raise HTTPException(status_code=409, detail="历史版本不能重新建立到账关联")
    if payslip.net_salary is None:
        raise HTTPException(status_code=409, detail="工资条缺少实发金额，无法匹配到账")
    start, end, reference_date = _arrival_search_window(payslip)
    current_links = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id == payslip.id,
        PayslipArrivalLink.status == "confirmed",
    ).all()
    current_fact_ids = {
        row.economic_fact_id
        for row in current_links
        if row.economic_fact_id is not None
    }
    current_legacy_transaction_ids = {
        row.transaction_id
        for row in current_links
        if row.economic_fact_id is None
    }
    other_links = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id != payslip.id,
        PayslipArrivalLink.status == "confirmed",
    ).all()
    linked_elsewhere_fact_ids = {
        row.economic_fact_id
        for row in other_links
        if row.economic_fact_id is not None
    }
    blocked_legacy_transaction_ids = current_legacy_transaction_ids | {
        row.transaction_id
        for row in other_links
        if row.economic_fact_id is None
    }
    transactions = (
        db.query(FinancialTransaction)
        .filter(
            FinancialTransaction.user_id == user.id,
            FinancialTransaction.direction == "income",
            FinancialTransaction.status == "confirmed",
            FinancialTransaction.deleted_at.is_(None),
            FinancialTransaction.transaction_date >= start,
            FinancialTransaction.transaction_date < end,
            ~FinancialTransaction.id.in_(blocked_legacy_transaction_ids)
            if blocked_legacy_transaction_ids
            else True,
        )
        .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        .limit(100)
        .all()
    )
    facts_by_transaction = get_transactions_facts(
        db,
        transaction_ids=[transaction.id for transaction in transactions],
        user_id=user.id,
    )
    candidate_fact_ids = {
        fact.id
        for facts in facts_by_transaction.values()
        for fact in facts
        if fact.id not in current_fact_ids and fact.fact_type == "income"
    }
    relation_allocated = {fact_id: Decimal("0.00") for fact_id in candidate_fact_ids}
    if candidate_fact_ids:
        for relation in db.query(EconomicFactRelation).filter(
            EconomicFactRelation.user_id == user.id,
            EconomicFactRelation.status == "confirmed",
            or_(
                EconomicFactRelation.source_fact_id.in_(candidate_fact_ids),
                EconomicFactRelation.target_fact_id.in_(candidate_fact_ids),
            ),
        ).all():
            amount = Decimal(relation.allocated_amount)
            if relation.source_fact_id in relation_allocated:
                relation_allocated[relation.source_fact_id] += amount
            if relation.target_fact_id in relation_allocated:
                relation_allocated[relation.target_fact_id] += amount
    arrival_allocated = {fact_id: Decimal("0.00") for fact_id in candidate_fact_ids}
    if candidate_fact_ids:
        for link in db.query(PayslipArrivalLink).filter(
            PayslipArrivalLink.economic_fact_id.in_(candidate_fact_ids),
            PayslipArrivalLink.status == "confirmed",
        ).all():
            arrival_allocated[link.economic_fact_id] += Decimal(link.allocated_amount)
    observations: list[SimpleNamespace] = []
    for transaction in transactions:
        for fact in facts_by_transaction.get(transaction.id, []):
            if fact.id not in candidate_fact_ids:
                continue
            available = max(
                Decimal("0.00"),
                Decimal(fact.amount)
                - relation_allocated[fact.id]
                - arrival_allocated[fact.id],
            )
            if available <= 0:
                continue
            observations.append(SimpleNamespace(
                id=transaction.id,
                economic_fact_id=fact.id,
                amount=Decimal(fact.amount),
                available_amount=available,
                source_transaction_amount=Decimal(transaction.amount),
                transaction_date=fact.occurred_date,
                fact_title=fact.title,
                is_split_component=fact.primary_transaction_id is None,
                merchant=fact.title if fact.primary_transaction_id is None else transaction.merchant,
                description=fact.description or transaction.description,
            ))
    confirmed_amount = sum(
        (Decimal(link.allocated_amount) for link in current_links),
        Decimal("0.00"),
    )
    remaining_net_salary = max(
        Decimal("0.00"),
        Decimal(payslip.net_salary) - confirmed_amount,
    )
    if remaining_net_salary <= Decimal("1.00"):
        return PayslipArrivalSuggestionResponse(
            payslip_id=payslip.id,
            net_salary=payslip.net_salary,
            suggestions=[],
        )
    suggestions = build_arrival_suggestions(
        net_salary=float(remaining_net_salary),
        reference_date=reference_date,
        employer_name=payslip.employer_name,
        transactions=observations,
        linked_fact_ids=linked_elsewhere_fact_ids,
    )[:20]
    suggestions = enrich_arrival_suggestions_with_ai(
        suggestions,
        payslip_id=payslip.id,
        pay_month=payslip.pay_month,
        net_salary=float(remaining_net_salary),
        employer_name=payslip.employer_name,
        user_id=user.id,
        expected_data_epoch=user.business_data_epoch,
    )
    return PayslipArrivalSuggestionResponse(
        payslip_id=payslip.id,
        net_salary=payslip.net_salary,
        suggestions=suggestions,
    )


def _resolve_arrival_endpoint(
    db: Session,
    *,
    user_id: int,
    transaction_id: int,
    economic_fact_id: int | None,
) -> tuple[FinancialTransaction, EconomicFact]:
    transaction = get_owned_transaction(db, user_id=user_id, transaction_id=transaction_id)
    facts = get_transaction_facts(
        db,
        transaction_id=transaction.id,
        user_id=user_id,
    )
    if economic_fact_id is None:
        if len(facts) != 1:
            raise HTTPException(
                status_code=409,
                detail=f"收入流水 {transaction.id} 已拆成 {len(facts)} 个经济事实，请明确选择工资到账部分",
            )
        fact = facts[0]
    else:
        fact = next((item for item in facts if item.id == economic_fact_id), None)
        if fact is None:
            raise HTTPException(status_code=409, detail=f"经济事实 {economic_fact_id} 不属于收入流水 {transaction.id}")
    if (
        transaction.direction != "income"
        or transaction.status != "confirmed"
        or transaction.deleted_at is not None
        or fact.fact_type != "income"
    ):
        raise HTTPException(status_code=409, detail="只能关联有效且尚未归类为退款、报销或转账的收入事实")
    return transaction, fact


def _allocated_fact_relation_amount(db: Session, fact_id: int) -> Decimal:
    return sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(EconomicFactRelation).filter(
                EconomicFactRelation.status == "confirmed",
                or_(
                    EconomicFactRelation.source_fact_id == fact_id,
                    EconomicFactRelation.target_fact_id == fact_id,
                ),
            ).all()
        ),
        Decimal("0.00"),
    )


@router.get("/{payslip_id}/arrival-links", response_model=PayslipArrivalLinkSummary)
def list_arrival_links(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    return _arrival_link_summary(db, payslip)


@router.post("/{payslip_id}/arrival-links", response_model=PayslipArrivalLinkSummary)
def confirm_arrival_links(
    payslip_id: int,
    data: PayslipArrivalLinkCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    endpoint_keys = [(item.transaction_id, item.economic_fact_id) for item in data.links]
    if len(set(endpoint_keys)) != len(endpoint_keys):
        raise HTTPException(status_code=400, detail="同一个到账事实不能在一次确认中重复选择")
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    if payslip.record_status != "active":
        raise HTTPException(status_code=409, detail="历史版本不能新增到账关联")
    net_salary = Decimal(payslip.net_salary or 0)
    active_amount = sum(
        (
            Decimal(row.allocated_amount)
            for row in db.query(PayslipArrivalLink).filter(
                PayslipArrivalLink.payslip_id == payslip.id,
                PayslipArrivalLink.status == "confirmed",
            ).all()
        ),
        Decimal("0.00"),
    )
    requested_amount = sum((item.allocated_amount for item in data.links), Decimal("0.00"))
    if active_amount + requested_amount > net_salary + Decimal("1.00"):
        raise HTTPException(status_code=409, detail="本次分配后的到账总额超过工资条实发金额")

    changed_links: list[tuple[PayslipArrivalLink, dict | None, str]] = []
    resolved_fact_ids: set[int] = set()
    for item in data.links:
        transaction, fact = _resolve_arrival_endpoint(
            db,
            user_id=user.id,
            transaction_id=item.transaction_id,
            economic_fact_id=item.economic_fact_id,
        )
        if fact.id in resolved_fact_ids:
            raise HTTPException(status_code=400, detail=f"经济事实 {fact.id} 不能在一次确认中重复选择")
        resolved_fact_ids.add(fact.id)
        unresolved_legacy_link = db.query(PayslipArrivalLink).filter(
            PayslipArrivalLink.transaction_id == transaction.id,
            PayslipArrivalLink.economic_fact_id.is_(None),
            PayslipArrivalLink.status == "confirmed",
        ).first()
        if unresolved_legacy_link is not None:
            raise HTTPException(
                status_code=409,
                detail=f"流水 {transaction.id} 仍有未定位到具体经济事实的历史工资到账关系，请先撤销后重新确认",
            )
        allocated_elsewhere = sum(
            (
                Decimal(row.allocated_amount)
                for row in db.query(PayslipArrivalLink).filter(
                    or_(
                        PayslipArrivalLink.economic_fact_id == fact.id,
                        (
                            PayslipArrivalLink.economic_fact_id.is_(None)
                            & (PayslipArrivalLink.transaction_id == transaction.id)
                        ),
                    ),
                    PayslipArrivalLink.payslip_id != payslip.id,
                    PayslipArrivalLink.status == "confirmed",
                ).all()
            ),
            Decimal("0.00"),
        )
        allocated_relations = _allocated_fact_relation_amount(db, fact.id)
        if (
            allocated_elsewhere
            + allocated_relations
            + item.allocated_amount
            > Decimal(fact.amount) + Decimal("0.01")
        ):
            raise HTTPException(status_code=409, detail=f"经济事实 {fact.id} 可分配金额不足")
        existing = (
            db.query(PayslipArrivalLink)
            .filter(
                PayslipArrivalLink.payslip_id == payslip.id,
                PayslipArrivalLink.economic_fact_id == fact.id,
            )
            .first()
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if existing is not None and existing.status == "confirmed":
            raise HTTPException(status_code=409, detail=f"经济事实 {fact.id} 已与这份工资条关联")
        before_snapshot = _arrival_link_snapshot(existing) if existing is not None else None
        if existing is None:
            existing = PayslipArrivalLink(
                payslip_id=payslip.id,
                transaction_id=transaction.id,
                economic_fact_id=fact.id,
                allocated_amount=item.allocated_amount,
                status="confirmed",
                match_reason=item.reasons,
                confirmed_by_user_id=user.id,
                confirmed_at=now,
            )
            db.add(existing)
        else:
            existing.transaction_id = transaction.id
            existing.economic_fact_id = fact.id
            existing.allocated_amount = item.allocated_amount
            existing.status = "confirmed"
            existing.match_reason = item.reasons
            existing.confirmed_by_user_id = user.id
            existing.confirmed_at = now
            existing.reversed_at = None
        changed_links.append((
            existing,
            before_snapshot,
            ("; ".join(item.reasons) or "用户确认工资到账事实")[:255],
        ))
    db.flush()
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="payslip_arrival_confirm",
        entity_type="payslip",
        entity_id=payslip.id,
        summary=f"为工资条 {payslip.id} 确认 {len(changed_links)} 个到账事实",
    )
    for link, before_snapshot, reason in changed_links:
        link.ledger_revision = ledger_revision
        _record_arrival_link_revision(
            db,
            owner=owner,
            link=link,
            operation="confirm",
            ledger_revision=ledger_revision,
            before_snapshot=before_snapshot,
            reason=reason,
        )
    db.flush()
    summary = _arrival_link_summary(db, payslip)
    _sync_salary_arrival_finding(db, payslip, summary)
    commit_financial_ledger(db)
    return summary


@router.delete("/{payslip_id}/arrival-links/{link_id}", response_model=PayslipArrivalLinkSummary)
def reverse_arrival_link(
    payslip_id: int,
    link_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user.id)
    payslip = _get_owned_payslip(db, payslip_id, user.id)
    link = (
        db.query(PayslipArrivalLink)
        .filter(
            PayslipArrivalLink.id == link_id,
            PayslipArrivalLink.payslip_id == payslip.id,
            PayslipArrivalLink.status == "confirmed",
        )
        .first()
    )
    if link is None:
        raise HTTPException(status_code=404, detail="到账关联不存在")
    before_snapshot = _arrival_link_snapshot(link)
    link.status = "reversed"
    link.reversed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    ledger_revision = record_financial_ledger_event(
        db,
        owner=owner,
        event_type="payslip_arrival_reverse",
        entity_type="payslip_arrival_link",
        entity_id=link.id,
        summary=f"撤销工资条 {payslip.id} 的到账事实关系 {link.id}",
    )
    link.ledger_revision = ledger_revision
    _record_arrival_link_revision(
        db,
        owner=owner,
        link=link,
        operation="reverse",
        ledger_revision=ledger_revision,
        before_snapshot=before_snapshot,
        reason="用户撤销工资到账事实关系",
    )
    db.flush()
    summary = _arrival_link_summary(db, payslip)
    _sync_salary_arrival_finding(db, payslip, summary)
    commit_financial_ledger(db)
    return summary


@router.get(
    "/{payslip_id}/arrival-links/{link_id}/revisions",
    response_model=list[PayslipArrivalLinkRevisionResponse],
)
def list_arrival_link_revisions(
    payslip_id: int,
    link_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _get_owned_payslip(db, payslip_id, user.id, include_deleted=True)
    link = db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.id == link_id,
        PayslipArrivalLink.payslip_id == payslip.id,
    ).one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="到账关联不存在")
    return (
        db.query(PayslipArrivalLinkRevision)
        .filter(
            PayslipArrivalLinkRevision.link_id == link.id,
            PayslipArrivalLinkRevision.user_id == user.id,
        )
        .order_by(PayslipArrivalLinkRevision.link_revision.desc())
        .all()
    )


def _resolved_agreed_pay_date_provenance(
    data: PayslipCreateRequest,
    contracts: list[Contract],
) -> dict:
    empty = {
        "agreed_pay_date_source_type": None,
        "agreed_pay_date_source_contract_id": None,
        "agreed_pay_date_schedule": None,
        "agreed_pay_date_adjustment": None,
        "agreed_pay_date_calendar_version": None,
    }
    if data.agreed_pay_date is None:
        if data.agreed_pay_date_source_contract_id is not None or data.agreed_pay_date_adjustment is not None:
            raise HTTPException(status_code=400, detail="未填写约定发薪日时不能伪造材料来源")
        return empty
    if data.agreed_pay_date_source_contract_id is None:
        if data.agreed_pay_date_adjustment is not None:
            raise HTTPException(status_code=400, detail="手工填写约定日期时不能声称使用了合同调整规则")
        return {
            **empty,
            "agreed_pay_date_source_type": "manual",
        }
    if data.agreed_pay_date_adjustment is None:
        raise HTTPException(status_code=400, detail="采用合同发薪日建议时必须提交用户选中的日期口径")
    contract = next(
        (item for item in contracts if item.id == data.agreed_pay_date_source_contract_id),
        None,
    )
    if contract is None:
        raise HTTPException(status_code=400, detail="约定发薪日只能引用本次实际关联的合同")
    suggestion = build_contract_pay_date_suggestion(
        pay_month=data.pay_month or "",
        contract=contract,
    )
    selected_option = next(
        (
            option for option in suggestion["options"]
            if option["adjustment"] == data.agreed_pay_date_adjustment
        ),
        None,
    )
    if selected_option is None or selected_option["date"] != data.agreed_pay_date:
        raise HTTPException(
            status_code=400,
            detail="约定发薪日与当前工资月份、合同条款或节假日选择不一致，请重新读取建议",
        )
    return {
        "agreed_pay_date_source_type": "material_suggestion",
        "agreed_pay_date_source_contract_id": contract.id,
        "agreed_pay_date_schedule": suggestion["schedule_text"],
        "agreed_pay_date_adjustment": data.agreed_pay_date_adjustment,
        "agreed_pay_date_calendar_version": suggestion["calendar_version"],
    }


def _create_payslip_record(
    data: PayslipCreateRequest,
    *,
    user: User,
    db: Session,
    commit: bool,
):
    if data.recognition_candidate_id is not None and data.supersedes_payslip_id is not None:
        raise HTTPException(status_code=400, detail="识别候选不能同时作为历史工资条修订版")
    revision_source: Payslip | None = None
    if data.supersedes_payslip_id is not None:
        user_id = user.id
        db.rollback()
        user = lock_financial_ledger_owner(db, user_id=user_id)
        revision_source = _get_owned_payslip(db, data.supersedes_payslip_id, user_id)
        if revision_source.record_status != "active":
            raise HTTPException(status_code=409, detail="只能基于当前有效工资条创建修订版")
    recognition_draft: PayslipRecognitionCandidateDraft | None = None
    recognition_batch: FinancialImportBatch | None = None
    if data.recognition_candidate_id is not None:
        if data.recognition_candidate_version is None:
            raise HTTPException(status_code=400, detail="保存识别候选时必须提交当前版本")
        recognition_draft = _owned_recognition_candidate(
            db,
            data.recognition_candidate_id,
            user.id,
            for_update=True,
        )
        if recognition_draft.status != "pending":
            raise HTTPException(status_code=409, detail="这份识别候选已经处理，请刷新批次")
        if recognition_draft.version != data.recognition_candidate_version:
            raise HTTPException(status_code=409, detail="候选已在其他页面更新，请刷新后继续")
        recognition_batch = _owned_recognition_batch(
            db,
            recognition_draft.batch_id,
            user.id,
            for_update=True,
        )
    offer_ids = _unique_ids(
        ([data.linked_offer_id] if data.linked_offer_id is not None else [])
        + data.linked_offer_ids
    )
    contract_ids = _unique_ids(data.linked_contract_ids)
    material_preferences = _resolved_material_preferences(
        data.material_preferences,
        offer_ids=offer_ids,
        contract_ids=contract_ids,
    )
    offers = [get_owned_offer(db, offer_id, user) for offer_id in offer_ids]
    contracts = [get_owned_contract(db, contract_id, user) for contract_id in contract_ids]
    agreed_pay_date_provenance = _resolved_agreed_pay_date_provenance(data, contracts)
    offer: Optional[Offer] = offers[0] if offers else None
    if revision_source is not None:
        case_id = revision_source.case_id
    elif offers:
        case_id = offers[0].case_id
    elif contracts:
        case_id = contracts[0].case_id
    else:
        case = CareerCase(
            user_id=user.id,
            type="payslip_review",
            title=f"{data.pay_month or '本月'}工资核对",
        )
        db.add(case)
        db.flush()
        case_id = case.id

    if revision_source is not None and revision_source.career_event_id is not None:
        if data.career_event_id is not None and data.career_event_id != revision_source.career_event_id:
            raise HTTPException(status_code=400, detail="工资条修订版必须保留原收支守护事件")
        event = get_owned_event(db, revision_source.career_event_id, user)
    elif data.career_event_id is not None:
        event = get_owned_event(db, data.career_event_id, user)
        if event.event_type != "income":
            raise HTTPException(status_code=400, detail="工资条必须关联收支守护事件")
    else:
        event = CareerEvent(
            user_id=user.id,
            event_type="income",
            title=f"{data.pay_month or '本月'}工资核对",
            status="active",
            stage="payslip_review",
        )
        db.add(event)
        db.flush()
    model_data = data.model_dump(
        exclude={
            "expected_salary",
            "city",
            "career_event_id",
            "source_action_id",
            "supersedes_payslip_id",
            "linked_offer_id",
            "linked_offer_ids",
            "linked_contract_ids",
            "material_preferences",
            "agreed_pay_date_source_contract_id",
            "agreed_pay_date_adjustment",
            "recognition_candidate_id",
            "recognition_candidate_version",
        },
        exclude_unset=True,
    )
    model_data.update(agreed_pay_date_provenance)
    if recognition_draft is not None and recognition_batch is not None:
        model_data["source_type"] = str(
            (recognition_batch.parse_hints or {}).get("payslip_source_type")
            or recognition_batch.origin_type
        )
        model_data["recognition_confidence"] = recognition_draft.confidence
        model_data["raw_text"] = _recognition_batch_raw_text(db, recognition_batch)
    payslip = Payslip(
        case_id=case_id,
        career_event_id=event.id,
        linked_offer_id=offer.id if offer else None,
        supersedes_payslip_id=revision_source.id if revision_source is not None else None,
        **model_data,
    )
    db.add(payslip)
    db.flush()
    if recognition_draft is not None:
        final_candidate_values = data.model_dump(
            mode="json",
            include={
                "pay_month",
                "pay_date",
                "employer_name",
                "gross_salary",
                "base_salary",
                "performance",
                "bonus",
                "overtime_pay",
                "allowance",
                "social_insurance",
                "housing_fund",
                "individual_tax",
                "attendance_deductions",
                "meal_deductions",
                "other_deductions",
                "net_salary",
                "custom_items",
            },
        )
        recognition_draft.candidate_payload = {
            **dict(recognition_draft.candidate_payload or {}),
            **final_candidate_values,
        }
        recognition_draft.status = "confirmed"
        recognition_draft.payslip_id = payslip.id
        recognition_draft.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        recognition_draft.excluded_at = None
    if revision_source is not None:
        # A revised net salary is new evidence. Never carry an old cash-arrival
        # confirmation forward silently, even when the two amounts happen to match.
        _reverse_all_arrival_links(
            db,
            owner=user,
            payslip=revision_source,
            reason=f"工资条已被修订版 {payslip.id} 替代，到账事实必须重新确认",
        )
        revision_source.record_status = "superseded"
        _set_payslip_guardian_records_active(db, revision_source, active=False)
    material_links: list[PayslipMaterialLink] = []
    for linked_offer in offers:
        preference = material_preferences[("offer", linked_offer.id)]
        link = PayslipMaterialLink(
            payslip_id=payslip.id,
            offer_id=linked_offer.id,
            **preference,
        )
        db.add(link)
        material_links.append(link)
    for linked_contract in contracts:
        preference = material_preferences[("contract", linked_contract.id)]
        link = PayslipMaterialLink(
            payslip_id=payslip.id,
            contract_id=linked_contract.id,
            **preference,
        )
        db.add(link)
        material_links.append(link)
    db.flush()
    materials = _material_summaries(offers, contracts, material_links)
    material_comparisons = _enrich_material_comparisons(
        build_material_comparisons(data, offers, contracts),
        offers,
        contracts,
        material_links,
    )

    expected_salary = (
        float(offer.monthly_salary)
        if offer is not None and offer.monthly_salary is not None
        else data.expected_salary
    )
    city = offer.city if offer is not None and offer.city else data.city
    analysis_data = {
        "gross_salary": data.gross_salary,
        "base_salary": data.base_salary,
        "performance": data.performance,
        "bonus": data.bonus,
        "overtime_pay": data.overtime_pay,
        "allowance": data.allowance,
        "social_insurance": data.social_insurance,
        "housing_fund": data.housing_fund,
        "individual_tax": data.individual_tax,
        "attendance_deductions": data.attendance_deductions,
        "meal_deductions": data.meal_deductions,
        "other_deductions": data.other_deductions,
        "net_salary": data.net_salary,
    }
    analysis = PayslipAnalyzeResponse.model_validate(
        analyze_payslip(analysis_data, expected_salary, city)
    )
    gross_difference = data.gross_salary - expected_salary if expected_salary is not None else None
    evidence = Evidence(
        event_id=event.id,
        evidence_type="payslip",
        source_type="user_material",
        title=f"{data.pay_month or '本月'}工资条金额",
        content_excerpt=f"应发 {data.gross_salary:.0f} 元，实发 {data.net_salary:.0f} 元",
        source_ref=f"payslip:{payslip.id}",
        extra_data={
            "private_user_material": True,
            "linked_offer_id": offer.id if offer else None,
            "linked_offer_ids": offer_ids,
            "linked_contract_ids": contract_ids,
            "offer_monthly_salary": expected_salary,
            "gross_salary": data.gross_salary,
            "difference": gross_difference,
            "material_comparisons": material_comparisons,
        },
        confidence=1,
    )
    db.add(evidence)
    db.flush()
    different_count = sum(
        check["status"] == "different"
        for item in material_comparisons
        for check in item.get("field_checks", [])
    )
    unknown_count = sum(
        check["status"] == "unknown"
        for item in material_comparisons
        for check in item.get("field_checks", [])
    )
    if different_count:
        finding_title = f"工资条与关联材料有 {different_count} 个字段口径不同"
        severity = "high"
        finding_status = "open"
        action_title = "逐项确认 Offer、合同与工资条的字段差异"
    elif unknown_count:
        finding_title = f"关联材料有 {unknown_count} 个字段口径尚未核清"
        severity = "info"
        finding_status = "open"
        action_title = "确认关联材料中尚未核清的薪资字段"
    elif material_comparisons:
        finding_title = "工资条与关联材料的可计算月薪基本一致"
        severity = "info"
        finding_status = "confirmed"
        action_title = None
    elif gross_difference is not None and abs(gross_difference) > 100:
        direction = "少" if gross_difference < 0 else "多"
        finding_title = f"本月应发比手工填写的约定月薪{direction} {abs(gross_difference):.0f} 元"
        severity = "high"
        finding_status = "open"
        action_title = f"向薪酬确认本月{direction}发 {abs(gross_difference):.0f} 元的原因"
    elif gross_difference is not None:
        finding_title = "本月应发与手工填写的约定月薪基本一致"
        severity = "info"
        finding_status = "confirmed"
        action_title = None
    else:
        finding_title = "工资条已保存，本次未关联 Offer 或合同"
        severity = "info"
        finding_status = "confirmed"
        action_title = None
    finding = GuardianFinding(
        event_id=event.id,
        evidence_id=evidence.id,
        domain="income",
        category="offer_payslip_difference",
        severity=severity,
        status=finding_status,
        title=finding_title,
        explanation=(
            "系统按每份材料独立计算差异，不会自行决定哪份材料正确。"
            "差额仍需结合入职日、试用期、请假和绩效明细确认。"
        ),
        source_type="calculation",
        confidence=1,
    )
    db.add(finding)
    db.flush()
    action = None
    if action_title:
        action = ActionItem(
            event_id=event.id,
            finding_id=finding.id,
            title=action_title,
            status="pending",
            priority=5,
            requires_confirmation=True,
        )
        db.add(action)
        db.flush()
        event.status = "attention"
    _sync_salary_arrival_finding(db, payslip, _arrival_link_summary(db, payslip))
    if data.source_action_id is not None:
        source_action = (
            db.query(ActionItem)
            .filter(ActionItem.id == data.source_action_id, ActionItem.event_id == event.id)
            .first()
        )
        if source_action is None:
            raise HTTPException(status_code=404, detail="收支守护待办不存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        source_action.status = "completed"
        source_action.confirmed_at = source_action.confirmed_at or now
        source_action.completed_at = now
        record_decision_handoff_outcome(
            db,
            user_id=user.id,
            handoff_event=event,
            outcome_type="first_payslip_recorded",
            result=f"{data.pay_month or '本月'}工资条 {payslip.id} 已保存并进入收入核对",
            action_id=source_action.id,
        )
    if recognition_batch is not None:
        db.flush()
        _sync_recognition_batch_counts(db, recognition_batch)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(payslip)
    return PayslipCreateResponse(
        payslip=payslip,
        analysis=analysis,
        difference_from_offer_gross=gross_difference,
        materials=materials,
        material_comparisons=material_comparisons,
        finding_id=finding.id,
        action_id=action.id if action else None,
    )


@router.post("/", response_model=PayslipCreateResponse)
def create_payslip(
    data: PayslipCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _create_payslip_record(data, user=user, db=db, commit=True)


@router.delete("/{payslip_id}", response_model=PayslipResponse)
def delete_payslip(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    payslip = _get_owned_payslip(db, payslip_id, user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    was_active = payslip.record_status == "active"
    payslip.record_status = "deleted"
    payslip.deleted_at = now
    _reverse_all_arrival_links(
        db,
        owner=owner,
        payslip=payslip,
        reason="工资条被删除，到账事实关系随之撤销且不会自动恢复",
    )
    _set_payslip_guardian_records_active(db, payslip, active=False)

    predecessor = None
    if was_active and payslip.supersedes_payslip_id is not None:
        predecessor = _get_owned_payslip(
            db,
            payslip.supersedes_payslip_id,
            user_id,
            include_deleted=True,
        )
        other_successor = db.query(Payslip.id).filter(
            Payslip.supersedes_payslip_id == predecessor.id,
            Payslip.id != payslip.id,
            Payslip.record_status != "deleted",
        ).first()
        if predecessor.record_status == "superseded" and other_successor is None:
            predecessor.record_status = "active"
            predecessor.deleted_at = None
            _set_payslip_guardian_records_active(db, predecessor, active=True)
            _sync_salary_arrival_finding(db, predecessor, _arrival_link_summary(db, predecessor))
    active_event_payslip = None
    if payslip.career_event_id is not None:
        active_event_payslip = db.query(Payslip).filter(
            Payslip.career_event_id == payslip.career_event_id,
            Payslip.id != payslip.id,
            Payslip.record_status == "active",
        ).first()
    if predecessor is None and payslip.career_event_id is not None and active_event_payslip is None:
        arrival_finding = db.query(GuardianFinding).filter(
            GuardianFinding.event_id == payslip.career_event_id,
            GuardianFinding.category == "salary_arrival_status",
        ).order_by(GuardianFinding.id.desc()).first()
        if arrival_finding is not None:
            arrival_finding.status = "superseded"
            arrival_finding.title = "工资条已删除，原到账判断已撤销"
    commit_financial_ledger(db)
    db.refresh(payslip)
    return payslip


@router.post("/{payslip_id}/restore", response_model=PayslipResponse)
def restore_payslip(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user_id)
    payslip = _get_owned_payslip(db, payslip_id, user_id, include_deleted=True)
    if payslip.record_status != "deleted":
        raise HTTPException(status_code=409, detail="这份工资条当前没有被删除")
    successor = db.query(Payslip.id).filter(
        Payslip.supersedes_payslip_id == payslip.id,
        Payslip.record_status != "deleted",
    ).first()
    payslip.record_status = "superseded" if successor is not None else "active"
    payslip.deleted_at = None
    if payslip.record_status == "active" and payslip.supersedes_payslip_id is not None:
        predecessor = _get_owned_payslip(
            db,
            payslip.supersedes_payslip_id,
            user_id,
            include_deleted=True,
        )
        if predecessor.record_status == "active":
            predecessor.record_status = "superseded"
            _set_payslip_guardian_records_active(db, predecessor, active=False)
    _set_payslip_guardian_records_active(db, payslip, active=payslip.record_status == "active")
    if payslip.record_status == "active":
        _sync_salary_arrival_finding(db, payslip, _arrival_link_summary(db, payslip))
    commit_financial_ledger(db)
    db.refresh(payslip)
    return payslip


@router.post("/analyze", response_model=PayslipAnalyzeResponse)
def analyze(
    data: PayslipAnalyzeRequest,
    user: User = Depends(get_current_user),
):
    result = analyze_payslip(data.payslip, data.expected_salary, data.city)
    return result
