"""Durable, restart-recoverable worker for labor-contract review.

The request path only saves the private attachment and a Contract row.  This
worker performs local extraction/segmentation first, persists that evidence,
and only then invokes the privacy-bounded model.  A process restart can resume
rows left in ``processing`` or ``reviewing`` without asking the browser to keep
an HTTP request open for the model latency.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Event, Thread

from sqlalchemy.exc import DataError

from app.db.session import SessionLocal
from app.models.career_case import CareerCase
from app.models.contract import Contract, ContractReviewSnapshot
from app.models.personal_attachment import PersonalAttachmentVersion
from app.services.contract_review_service import (
    classify_labor_document,
    complete_review_snapshot,
    infer_document_kind,
    prepare_review_snapshot,
)
from app.services.document_service import EXTRACTOR_VERSION, extract_text
from app.services.personal_attachment_service import resolve_attachment_path


logger = logging.getLogger(__name__)


class ContractReviewWorker:
    def __init__(self, interval_seconds: float = 0.75) -> None:
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="contract-review-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            processed = False
            try:
                processed = self.run_once()
            except Exception:  # pragma: no cover - protects the daemon loop
                logger.exception("contract review worker loop failed")
            if not processed:
                self._stop.wait(self._interval_seconds)

    def run_once(self) -> bool:
        with SessionLocal() as db:
            contract = (
                db.query(Contract)
                .filter(Contract.parse_status.in_(("extracting", "processing", "reviewing")))
                .order_by(Contract.updated_at.asc(), Contract.id.asc())
                .first()
            )
            if contract is None:
                return False
            contract_id = contract.id
            case = db.get(CareerCase, contract.case_id)
            user_id = case.user_id if case is not None else None
            try:
                self._process(db, contract, user_id=user_id)
            except Exception as exc:
                logger.exception("contract review failed for contract %s", contract_id)
                db.rollback()
                current = db.get(Contract, contract_id)
                if current is not None:
                    latest = (
                        db.query(ContractReviewSnapshot)
                        .filter(ContractReviewSnapshot.contract_id == contract_id)
                        .order_by(ContractReviewSnapshot.review_number.desc())
                        .first()
                    )
                    if current.raw_text:
                        if latest is not None:
                            latest.ai_status = "failed"
                            latest.review_mode = "rules_only"
                        current.parse_status = "ready"
                        current.parse_error_code = "review_failed"
                        current.parse_notice = "文字已保存，但本次条款审查没有完成，可以重试。"
                    else:
                        current.parse_status = "failed"
                        if isinstance(exc, DataError):
                            current.parse_error_code = "storage_write_failed"
                            current.parse_notice = "文字已读出，但暂时没有完整保存，请稍后重试。"
                        elif isinstance(exc, FileNotFoundError):
                            current.parse_error_code = "attachment_missing"
                            current.parse_notice = "没有找到这份合同原件，请重新上传。"
                        else:
                            current.parse_error_code = "parse_failed"
                            current.parse_notice = "这份文件暂时没有可靠读出文字，可以改用粘贴文字继续。"
                    db.commit()
            return True

    @staticmethod
    def _process(db, contract: Contract, *, user_id: int | None) -> None:
        if contract.parse_status in {"extracting", "processing"}:
            review_requested = contract.parse_status == "processing"
            parse_quality = contract.parse_quality if isinstance(contract.parse_quality, dict) else {}
            force_review_requested = bool(parse_quality.get("force_review_requested"))
            needs_current_extraction = (
                contract.source_attachment_id is not None
                and parse_quality.get("extractor_version") != EXTRACTOR_VERSION
            )
            if not contract.raw_text or needs_current_extraction:
                attachment = db.get(PersonalAttachmentVersion, contract.source_attachment_id)
                if attachment is None:
                    raise FileNotFoundError("contract attachment missing")
                path = Path(resolve_attachment_path(attachment))
                result = extract_text(path.read_bytes(), attachment.original_filename)
                # A failed re-extraction must never erase previously persisted
                # readable text.  Successful current extraction atomically
                # replaces the old block-ordered representation.
                if result.parse_mode != "failed" and result.raw_text:
                    filename_hint = " ".join(
                        item
                        for item in (contract.display_name, attachment.original_filename)
                        if item
                    )
                    text_detected_kind = infer_document_kind(result.raw_text)
                    detected_kind = text_detected_kind or infer_document_kind(
                        result.raw_text,
                        filename_hint,
                    )
                    kind_was_automatic = contract.document_kind == "auto"
                    if kind_was_automatic and detected_kind:
                        contract.document_kind = detected_kind
                    contract.raw_text = result.raw_text
                    contract.page_count = result.page_count or None
                    contract.text_page_count = result.text_page_count or 0
                    contract.ocr_page_count = result.ocr_page_count or 0
                    contract.parse_mode = result.parse_mode
                    contract.parse_notice = result.parse_notice or None
                    contract.parse_error_code = result.parse_error_code
                    contract.parse_quality = {
                        **(result.parse_quality or {}),
                        "document_profile": classify_labor_document(result.raw_text),
                        "document_kind_detection": {
                            "status": (
                                "detected"
                                if kind_was_automatic and detected_kind
                                else "needs_confirmation"
                                if kind_was_automatic
                                else "manual"
                            ),
                            "value": detected_kind if kind_was_automatic else contract.document_kind,
                            "source": (
                                "local_text"
                                if kind_was_automatic and text_detected_kind
                                else "local_filename"
                                if kind_was_automatic and detected_kind
                                else "unresolved"
                                if kind_was_automatic
                                else "user_selection"
                            ),
                            "was_automatic": kind_was_automatic,
                        },
                        "force_review_requested": force_review_requested,
                    }
                elif contract.raw_text:
                    # Keep the last readable representation and its quality
                    # metadata. A transient extractor failure should not
                    # downgrade or erase a contract that was already usable.
                    contract.parse_notice = "新版解析暂时没有读出更多内容，本次继续使用已保存的合同文字。"
                    contract.parse_error_code = result.parse_error_code or "reextract_failed"
                    contract.parse_quality = {
                        **parse_quality,
                        "force_review_requested": force_review_requested,
                        "reextract_error_code": result.parse_error_code or "reextract_failed",
                    }
                else:
                    kind_was_automatic = contract.document_kind == "auto"
                    contract.page_count = result.page_count or None
                    contract.text_page_count = result.text_page_count or 0
                    contract.ocr_page_count = result.ocr_page_count or 0
                    contract.parse_mode = result.parse_mode
                    contract.parse_notice = result.parse_notice or None
                    contract.parse_error_code = result.parse_error_code
                    contract.parse_quality = {
                        **(result.parse_quality or {}),
                        "document_profile": classify_labor_document(result.raw_text or ""),
                        "document_kind_detection": {
                            "status": "needs_confirmation" if kind_was_automatic else "manual",
                            "value": None if kind_was_automatic else contract.document_kind,
                            "source": "local_text" if kind_was_automatic else "user_selection",
                            "was_automatic": kind_was_automatic,
                        },
                        "force_review_requested": force_review_requested,
                    }
                # 先独立持久本地解析结果。后续分段或模型失败不得回滚已读出的原文。
                db.commit()
                contract = db.get(Contract, contract.id)
                if result.parse_mode == "failed" and not contract.raw_text:
                    contract.parse_status = "failed"
                    db.commit()
                    return
            if not review_requested:
                contract.parse_status = "ready"
                contract.parse_notice = "合同文字已经读出，尚未开始审查。"
                db.commit()
                return
            contract.parse_status = "reviewing"
            contract.parse_notice = "合同文字已经读出，正在拆分条款并核对重点。"
            snapshot, reused = prepare_review_snapshot(db, contract, force=force_review_requested)
            if force_review_requested and isinstance(contract.parse_quality, dict):
                contract.parse_quality = {key: value for key, value in contract.parse_quality.items() if key != "force_review_requested"}
            db.commit()
            if reused and snapshot.ai_status not in {"queued", "running"}:
                contract = db.get(Contract, contract.id)
                contract.parse_status = "ready"
                contract.parse_notice = None
                db.commit()
                return

        contract = db.get(Contract, contract.id)
        snapshot = (
            db.query(ContractReviewSnapshot)
            .filter(ContractReviewSnapshot.contract_id == contract.id)
            .order_by(ContractReviewSnapshot.review_number.desc())
            .first()
        )
        if snapshot is None:
            snapshot, _ = prepare_review_snapshot(db, contract)
            db.commit()
        if snapshot.ai_status not in {"queued", "running"}:
            contract.parse_status = "ready"
            contract.parse_notice = None
            db.commit()
            return

        complete_review_snapshot(db, contract, snapshot, user_id=user_id)
        # Runtime import avoids coupling the worker module to FastAPI route
        # initialization while preserving the existing event/finding sync.
        from app.api.routes.contracts import _apply_extracted_fields, _sync_contract_review

        _apply_extracted_fields(contract, snapshot.extracted_fields or {})
        _sync_contract_review(db, contract, list(snapshot.findings or []))
        contract.parse_status = "ready"
        contract.parse_error_code = None if snapshot.ai_status in {"success", "partial_success"} else "model_review_incomplete"
        contract.parse_notice = (
            None
            if snapshot.ai_status == "success"
            else "已保留完成的解读；部分模型批次未完成，可以重试。" if snapshot.ai_status == "partial_success"
            else "模型解读没有完成，本地条款分段和规则核对结果已经保留。"
        )
        db.commit()
