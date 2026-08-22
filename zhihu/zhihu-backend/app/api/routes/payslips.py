"""工资条 API"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.ownership import get_owned_contract, get_owned_event, get_owned_offer
from app.db.session import get_db
from app.models.career_case import CareerCase
from app.models.career_event import ActionItem, CareerEvent, Evidence, GuardianFinding
from app.models.contract import Contract
from app.models.cashflow import FinancialTransaction
from app.models.offer import Offer
from app.models.payslip import Payslip, PayslipArrivalLink, PayslipMaterialLink
from app.models.user import User
from app.services.payslip_service import (
    analyze_payslip,
    build_arrival_suggestions,
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
    PayslipArrivalLinkSummary,
    PayslipArrivalSuggestionResponse,
    PayslipCreateRequest,
    PayslipCreateResponse,
    PayslipDetailResponse,
    PayslipGuardianSummary,
    PayslipMaterialSummary,
    PayslipMonthComparison,
    PayslipRecognitionResponse,
    PayslipResponse,
)
from app.services.cashflow_service import (
    commit_financial_ledger,
    get_owned_transaction,
    lock_financial_ledger_owner,
)
from app.services.payslip_intake_service import (
    PayslipRecognitionError,
    recognize_payslip_upload,
)

router = APIRouter()


def _unique_ids(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def _material_summaries(offers: list[Offer], contracts: list[Contract]) -> list[PayslipMaterialSummary]:
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
        )
        for offer in offers
    ]
    summaries.extend(
        PayslipMaterialSummary(
            material_type="contract",
            material_id=contract.id,
            title=contract.display_name or contract.employer or f"劳动合同 #{contract.id}",
            salary_reference=(contract.salary_terms or "合同薪资条款待确认")[:240],
        )
        for contract in contracts
    )
    return summaries


def _load_linked_materials(db: Session, payslip_id: int, user_id: int) -> tuple[list[Offer], list[Contract]]:
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
    return offers, contracts


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


def _arrival_link_summary(db: Session, payslip: Payslip) -> PayslipArrivalLinkSummary:
    rows = (
        db.query(PayslipArrivalLink, FinancialTransaction)
        .join(FinancialTransaction, FinancialTransaction.id == PayslipArrivalLink.transaction_id)
        .filter(PayslipArrivalLink.payslip_id == payslip.id, PayslipArrivalLink.status == "confirmed")
        .order_by(PayslipArrivalLink.confirmed_at.asc(), PayslipArrivalLink.id.asc())
        .all()
    )
    links = [
        PayslipArrivalLinkResponse(
            id=link.id,
            transaction_id=transaction.id,
            allocated_amount=link.allocated_amount,
            transaction_date=transaction.transaction_date,
            merchant=transaction.merchant,
            description=transaction.description,
            status=link.status,
            match_reason=link.match_reason or [],
            confirmed_at=link.confirmed_at,
            reversed_at=link.reversed_at,
        )
        for link, transaction in rows
    ]
    net_salary = Decimal(payslip.net_salary or 0)
    confirmed_amount = sum((Decimal(link.allocated_amount) for link, _ in rows), Decimal("0.00"))
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
    try:
        return recognize_payslip_upload(
            user_id=user_id,
            filename=Path(file.filename or "payslip").name,
            content=content,
            content_type=file.content_type or "application/octet-stream",
            confirm_external_processing=confirm_external_processing,
            expected_data_epoch=data_epoch,
        )
    except PayslipRecognitionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


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
    offers, contracts = _load_linked_materials(db, payslip.id, user.id)
    return PayslipDetailResponse(
        **PayslipResponse.model_validate(payslip).model_dump(),
        materials=_material_summaries(offers, contracts),
        material_comparisons=build_material_comparisons(payslip, offers, contracts),
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
    offers, contracts = _load_linked_materials(db, payslip.id, user.id)
    material_comparisons = build_material_comparisons(payslip, offers, contracts)
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
    current_link_ids = {
        row.transaction_id
        for row in db.query(PayslipArrivalLink.transaction_id).filter(
            PayslipArrivalLink.payslip_id == payslip.id,
            PayslipArrivalLink.status == "confirmed",
        ).all()
    }
    linked_elsewhere_ids = {
        row.transaction_id
        for row in db.query(PayslipArrivalLink.transaction_id).filter(
            PayslipArrivalLink.payslip_id != payslip.id,
            PayslipArrivalLink.status == "confirmed",
        ).all()
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
            ~FinancialTransaction.id.in_(current_link_ids) if current_link_ids else True,
        )
        .order_by(FinancialTransaction.transaction_date.asc(), FinancialTransaction.id.asc())
        .limit(100)
        .all()
    )
    suggestions = build_arrival_suggestions(
        net_salary=float(payslip.net_salary),
        reference_date=reference_date,
        employer_name=payslip.employer_name,
        transactions=transactions,
        linked_transaction_ids=linked_elsewhere_ids,
    )[:20]
    suggestions = enrich_arrival_suggestions_with_ai(
        suggestions,
        payslip_id=payslip.id,
        pay_month=payslip.pay_month,
        net_salary=float(payslip.net_salary),
        employer_name=payslip.employer_name,
        user_id=user.id,
        expected_data_epoch=user.business_data_epoch,
    )
    return PayslipArrivalSuggestionResponse(
        payslip_id=payslip.id,
        net_salary=payslip.net_salary,
        suggestions=suggestions,
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
    if len({item.transaction_id for item in data.links}) != len(data.links):
        raise HTTPException(status_code=400, detail="同一笔到账不能在一次确认中重复选择")
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user.id)
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

    for item in data.links:
        transaction = get_owned_transaction(db, user_id=user.id, transaction_id=item.transaction_id)
        if transaction.direction != "income" or transaction.status != "confirmed":
            raise HTTPException(status_code=409, detail="只能关联已确认的收入流水")
        allocated_elsewhere = sum(
            (
                Decimal(row.allocated_amount)
                for row in db.query(PayslipArrivalLink).filter(
                    PayslipArrivalLink.transaction_id == transaction.id,
                    PayslipArrivalLink.payslip_id != payslip.id,
                    PayslipArrivalLink.status == "confirmed",
                ).all()
            ),
            Decimal("0.00"),
        )
        if allocated_elsewhere + item.allocated_amount > Decimal(transaction.amount) + Decimal("0.01"):
            raise HTTPException(status_code=409, detail=f"流水 {transaction.id} 可分配金额不足")
        existing = (
            db.query(PayslipArrivalLink)
            .filter(
                PayslipArrivalLink.payslip_id == payslip.id,
                PayslipArrivalLink.transaction_id == transaction.id,
            )
            .first()
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if existing is not None and existing.status == "confirmed":
            raise HTTPException(status_code=409, detail=f"流水 {transaction.id} 已与这份工资条关联")
        if existing is None:
            existing = PayslipArrivalLink(
                payslip_id=payslip.id,
                transaction_id=transaction.id,
                allocated_amount=item.allocated_amount,
                status="confirmed",
                match_reason=item.reasons,
                confirmed_by_user_id=user.id,
                confirmed_at=now,
            )
            db.add(existing)
        else:
            existing.allocated_amount = item.allocated_amount
            existing.status = "confirmed"
            existing.match_reason = item.reasons
            existing.confirmed_by_user_id = user.id
            existing.confirmed_at = now
            existing.reversed_at = None
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
    lock_financial_ledger_owner(db, user_id=user.id)
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
    link.status = "reversed"
    link.reversed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()
    summary = _arrival_link_summary(db, payslip)
    _sync_salary_arrival_finding(db, payslip, summary)
    commit_financial_ledger(db)
    return summary


@router.post("/", response_model=PayslipCreateResponse)
def create_payslip(
    data: PayslipCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    revision_source: Payslip | None = None
    if data.supersedes_payslip_id is not None:
        user_id = user.id
        db.rollback()
        user = lock_financial_ledger_owner(db, user_id=user_id)
        revision_source = _get_owned_payslip(db, data.supersedes_payslip_id, user_id)
        if revision_source.record_status != "active":
            raise HTTPException(status_code=409, detail="只能基于当前有效工资条创建修订版")
    offer_ids = _unique_ids(
        ([data.linked_offer_id] if data.linked_offer_id is not None else [])
        + data.linked_offer_ids
    )
    contract_ids = _unique_ids(data.linked_contract_ids)
    offers = [get_owned_offer(db, offer_id, user) for offer_id in offer_ids]
    contracts = [get_owned_contract(db, contract_id, user) for contract_id in contract_ids]
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
        },
        exclude_unset=True,
    )
    payslip = Payslip(
        case_id=case_id,
        career_event_id=event.id,
        linked_offer_id=offer.id if offer else None,
        supersedes_payslip_id=revision_source.id if revision_source is not None else None,
        **model_data,
    )
    db.add(payslip)
    db.flush()
    if revision_source is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for link in db.query(PayslipArrivalLink).filter(
            PayslipArrivalLink.payslip_id == revision_source.id,
            PayslipArrivalLink.status == "confirmed",
        ).all():
            # A revised net salary is new evidence. Never carry an old cash-arrival
            # confirmation forward silently, even when the two amounts happen to match.
            link.status = "reversed"
            link.reversed_at = now
        revision_source.record_status = "superseded"
        _set_payslip_guardian_records_active(db, revision_source, active=False)
    for linked_offer in offers:
        db.add(PayslipMaterialLink(payslip_id=payslip.id, offer_id=linked_offer.id))
    for linked_contract in contracts:
        db.add(PayslipMaterialLink(payslip_id=payslip.id, contract_id=linked_contract.id))
    materials = _material_summaries(offers, contracts)
    material_comparisons = build_material_comparisons(data, offers, contracts)

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
    db.commit()
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


@router.delete("/{payslip_id}", response_model=PayslipResponse)
def delete_payslip(
    payslip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id
    db.rollback()
    lock_financial_ledger_owner(db, user_id=user_id)
    payslip = _get_owned_payslip(db, payslip_id, user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    was_active = payslip.record_status == "active"
    payslip.record_status = "deleted"
    payslip.deleted_at = now
    for link in db.query(PayslipArrivalLink).filter(
        PayslipArrivalLink.payslip_id == payslip.id,
        PayslipArrivalLink.status == "confirmed",
    ).all():
        link.status = "reversed"
        link.reversed_at = now
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
