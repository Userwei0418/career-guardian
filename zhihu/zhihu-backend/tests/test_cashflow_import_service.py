from __future__ import annotations

import tempfile
import time
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.api.routes.auth import _delete_business_data
from app.api.routes.cashflow import _build_user_month_summary
from app.db.session import Base
from app.models.cashflow import (
    EconomicFact,
    EconomicFactAllocation,
    EconomicFactRevision,
    FinancialCategory,
    FinancialLedgerRevisionEvent,
    FinancialTransaction,
    FinancialTransactionRevision,
)
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import (
    PersonalAttachmentCleanupJob,
    PersonalAttachmentVersion,
)
from app.models.user import User
from app.schemas.cashflow_import import (
    FinancialImportCandidateUpdate,
    FinancialImportConfirmRequest,
    FinancialImportConfirmReport,
)
from app.services.cashflow_import_service import (
    apply_mapping,
    batch_payload,
    candidate_payload,
    confirm_candidates,
    create_file_import,
    create_generated_import,
    update_candidate,
)
from app.services.economic_fact_service import sync_transaction_fact
from app.services.cashflow_import_parser import (
    ParsedCandidate,
    build_candidate_fingerprint,
    read_import_table,
)
from app.services.personal_attachment_service import (
    _BoundedAttachmentTreeScanner,
    _is_cleanup_path_conflict,
    claim_attachment_cleanup_jobs,
    enqueue_orphaned_attachment_cleanup,
    process_attachment_cleanup_jobs,
    resolve_attachment_path,
    save_personal_attachment,
)


@compiles(MEDIUMBLOB, "sqlite")
def _compile_mediumblob_for_sqlite(_type, _compiler, **_kwargs):
    return "BLOB"


def _wechat_csv(*rows: str, metadata: str = "微信支付账单明细") -> bytes:
    lines = [
        metadata,
        "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号",
        *rows,
    ]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def _income_row(
    *,
    external_id: str,
    amount: str = "12000.00",
    transaction_date: str = "2026-08-01 09:30:00",
    merchant: str = "公司财务",
    description: str = "八月工资",
) -> str:
    return (
        f"{transaction_date},转账,{merchant},{description},收入,{amount},银行卡,支付成功,{external_id}"
    )


def _expense_row(
    *,
    external_id: str,
    amount: str = "35.00",
    transaction_date: str = "2026-08-02 12:00:00",
    merchant: str = "午餐餐厅",
    description: str = "工作午餐",
) -> str:
    return (
        f"{transaction_date},商户消费,{merchant},{description},支出,{amount},零钱,支付成功,{external_id}"
    )


class CashflowImportServiceTest(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory(prefix="cashflow-import-test-")
        self.original_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = self.upload_directory.name
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        session_factory = sessionmaker(bind=self.engine)
        self.db = session_factory()

        self.user = User(
            username="cashflow-import-user",
            password_hash="test-only",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.flush()
        self.user_id = self.user.id
        self.categories = {}
        for direction, name in (
            ("income", "工资"),
            ("income", "其他收入"),
            ("expense", "餐饮"),
            ("expense", "购物"),
            ("expense", "其他支出"),
        ):
            category = FinancialCategory(
                user_id=None,
                direction=direction,
                name=name,
                is_system=True,
                is_active=True,
            )
            self.db.add(category)
            self.db.flush()
            self.categories[(direction, name)] = category
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self.original_upload_dir
        self.upload_directory.cleanup()

    def _create_ready_income(self, *, external_id: str = "income-001"):
        content = _wechat_csv(_income_row(external_id=external_id))
        batch, reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=content,
            source_hint="auto",
        )
        candidate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id, user_id=self.user_id)
            .one()
        )
        self.assertFalse(reused)
        self.assertEqual("ready", candidate.status)
        return batch, candidate, content

    def _confirm_one(self, batch, candidate):
        request = FinancialImportConfirmRequest(
            expected_batch_version=batch.version,
            candidates=[
                {
                    "candidate_id": candidate.id,
                    "expected_version": candidate.version,
                }
            ],
        )
        report = confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            data=request,
        )
        return request, report

    def _create_formal_income(
        self,
        *,
        amount: Decimal = Decimal("12000.00"),
        transaction_date: date = date(2026, 8, 1),
        merchant: str = "公司财务",
        description: str = "八月工资",
        source_type: str = "manual",
    ) -> tuple[FinancialTransaction, EconomicFact]:
        transaction = FinancialTransaction(
            user_id=self.user_id,
            category_id=self.categories[("income", "工资")].id,
            direction="income",
            amount=amount,
            currency="CNY",
            transaction_date=transaction_date,
            merchant=merchant,
            description=description,
            source_type=source_type,
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(transaction)
        self.db.flush()
        fact = sync_transaction_fact(
            self.db,
            transaction=transaction,
            user_id=self.user_id,
            assume_missing=True,
        )
        self.db.commit()
        return transaction, fact

    def _generated_income_candidate(
        self,
        *,
        row_number: int,
        external_key: str,
        amount: Decimal,
        direction: str | None = "income",
        currency: str = "CNY",
        transaction_date: date | None = date(2026, 8, 20),
        merchant: str | None = None,
        description: str | None = None,
        evidence: dict | None = None,
        validation_errors: list[dict] | None = None,
        warnings: list[dict] | None = None,
    ) -> ParsedCandidate:
        merchant = merchant if merchant is not None else f"收入方-{row_number}"
        description = description if description is not None else f"收入说明-{row_number}"
        fingerprint = build_candidate_fingerprint(
            direction=direction,
            amount=amount,
            transaction_date=transaction_date,
            merchant=merchant,
            description=description,
        )
        return ParsedCandidate(
            row_number=row_number,
            direction=direction,
            amount=amount,
            currency=currency,
            transaction_date=transaction_date,
            occurred_at=None,
            category_name="工资",
            merchant=merchant,
            description=description,
            nature=None,
            external_key=external_key,
            fingerprint=fingerprint,
            original_payload={"amount": format(amount, "f")},
            evidence=evidence or {"origin": "test"},
            validation_errors=validation_errors or [],
            warnings=warnings or [],
        )

    def test_same_file_reupload_reuses_artifacts_without_storing_original_file(self):
        content = _wechat_csv(_income_row(external_id="same-file-001"))

        first_batch, first_reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信账单.csv",
            content=content,
            source_hint="auto",
        )
        second_batch, second_reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信账单-重复上传.csv",
            content=content,
            source_hint="auto",
        )

        self.assertFalse(first_reused)
        self.assertTrue(second_reused)
        self.assertEqual(first_batch.id, second_batch.id)
        self.assertIsNone(first_batch.attachment_version_id)
        self.assertIsNone(second_batch.attachment_version_id)
        self.assertEqual(
            1,
            self.db.query(FinancialImportBatch).filter_by(user_id=self.user_id).count(),
        )
        self.assertEqual(
            0,
            self.db.query(PersonalAttachmentVersion).filter_by(user_id=self.user_id).count(),
        )
        artifact_types = [
            row.artifact_type
            for row in self.db.query(FinancialRecognitionArtifact).filter_by(
                user_id=self.user_id,
                batch_id=first_batch.id,
            ).order_by(
                FinancialRecognitionArtifact.artifact_type,
                FinancialRecognitionArtifact.sequence_number,
            ).all()
        ]
        self.assertEqual(["normalized_rows", "tabular_manifest"], artifact_types)
        stored_files = [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()]
        self.assertEqual([], stored_files)

    def test_custom_mapping_creates_candidates_from_recognition_artifacts(self):
        content = (
            "流水日,数额,流向值,对手方,附言,编号\n"
            "2026/08/08,42.50,支出,午餐餐厅,下午咖啡,custom-001\n"
        ).encode("utf-8")
        batch, reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="custom.csv",
            content=content,
            source_hint="generic",
        )

        self.assertFalse(reused)
        self.assertEqual("mapping_required", batch.status)
        self.assertEqual(
            0,
            self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).count(),
        )

        with patch(
            "app.services.cashflow_import_service.read_import_table",
            side_effect=AssertionError("mapping must not reopen the original file"),
        ):
            mapped = apply_mapping(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                expected_batch_version=batch.version,
                mapping={
                    "transaction_date": "流水日",
                    "amount": "数额",
                    "direction": "流向值",
                    "merchant": "对手方",
                    "description": "附言",
                    "external_id": "编号",
                },
            )
        candidate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id, user_id=self.user_id)
            .one()
        )

        self.assertEqual("review_ready", mapped.status)
        self.assertEqual("needs_review", candidate.status)
        self.assertEqual("expense", candidate.direction)
        self.assertEqual(Decimal("42.50"), candidate.amount)
        self.assertEqual("午餐餐厅", candidate.merchant)
        self.assertEqual(
            self.categories[("expense", "餐饮")].id,
            candidate.category_id,
        )
        self.assertEqual(1, mapped.total_count)
        self.assertEqual(0, mapped.ready_count)
        self.assertEqual(1, mapped.review_count)

    def test_import_marks_exact_and_possible_duplicates_without_formal_writes(self):
        existing = FinancialTransaction(
            user_id=self.user_id,
            category_id=self.categories[("expense", "餐饮")].id,
            direction="expense",
            amount=Decimal("66.00"),
            currency="CNY",
            transaction_date=date(2026, 8, 6),
            merchant="疑似重复餐厅",
            description="团队午餐",
            source_type="manual",
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(existing)
        self.db.commit()
        formal_count_before = self.db.query(FinancialTransaction).count()
        content = _wechat_csv(
            _income_row(external_id="duplicate-key", amount="100.00"),
            _income_row(
                external_id="duplicate-key",
                amount="101.00",
                transaction_date="2026-08-03 09:30:00",
            ),
            _expense_row(
                external_id="possible-001",
                amount="66.00",
                transaction_date="2026-08-06 12:00:00",
                merchant="疑似重复餐厅",
                description="团队午餐",
            ),
        )

        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="有重复项的微信账单.csv",
            content=content,
            source_hint="auto",
        )
        candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id, user_id=self.user_id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )

        self.assertEqual(
            ["ready", "exact_duplicate", "possible_duplicate"],
            [candidate.status for candidate in candidates],
        )
        self.assertEqual(candidates[0].external_key, candidates[1].external_key)
        self.assertIsNone(candidates[1].duplicate_transaction_id)
        self.assertEqual(existing.id, candidates[2].duplicate_transaction_id)
        self.assertEqual(
            [existing.id],
            candidates[2].evidence["possible_duplicate_transaction_ids"],
        )
        self.assertEqual(1, batch.exact_duplicate_count)
        self.assertEqual(1, batch.possible_duplicate_count)
        self.assertEqual(2, batch.duplicate_count)
        self.assertEqual(formal_count_before, self.db.query(FinancialTransaction).count())

    def test_possible_duplicate_can_confirm_as_cross_source_fact_evidence(self):
        target, target_fact = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="merge-evidence-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        self.assertEqual("possible_duplicate", candidate.status)
        response = candidate_payload(self.db, batch=batch, candidate=candidate)
        self.assertEqual(target.id, response.duplicate_matches[0].transaction_id)
        self.assertEqual(target_fact.id, response.duplicate_matches[0].economic_fact_id)
        self.assertTrue(response.duplicate_matches[0].can_merge_as_evidence)

        ready, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                target_transaction_id=target.id,
                allocated_amount=Decimal("12000.00"),
                evidence_merge_reason="银行到账与微信账单是同一笔工资的两份证据",
            ),
        )
        self.assertEqual("ready", ready.status)
        intent = ready.evidence["economic_fact_merge"]
        self.assertEqual(target.id, intent["target_transaction_id"])
        self.assertEqual(target_fact.id, intent["target_fact_id"])

        request, report = self._confirm_one(refreshed_batch, ready)
        response_report = FinancialImportConfirmReport.model_validate(report)
        self.assertEqual([ready.id], report["corroborating_candidate_ids"])
        self.assertEqual([target_fact.id], report["corroborating_fact_ids"])
        self.assertEqual([], report["independent_candidate_ids"])
        self.assertEqual(1, report["corroborating_count"])
        self.assertEqual(0, report["independent_count"])
        self.assertEqual(1, report["confirmed_count"])
        self.assertEqual([target_fact.id], response_report.corroborating_fact_ids)

        self.db.refresh(ready)
        source_transaction = self.db.get(FinancialTransaction, ready.transaction_id)
        source_fact = self.db.query(EconomicFact).filter_by(
            primary_transaction_id=source_transaction.id,
        ).one()
        corroborating = self.db.query(EconomicFactAllocation).filter_by(
            fact_id=target_fact.id,
            transaction_id=source_transaction.id,
            role="corroborating",
            status="confirmed",
        ).one()
        self.assertEqual(Decimal("12000.00"), corroborating.allocated_amount)
        self.assertEqual("superseded", source_fact.status)
        self.assertEqual(Decimal("0.00"), source_fact.amount)
        self.assertEqual(
            {"merge_import_evidence"},
            {
                row.operation
                for row in self.db.query(EconomicFactRevision).filter(
                    EconomicFactRevision.fact_id.in_({target_fact.id, source_fact.id}),
                ).all()
            },
        )
        summary = _build_user_month_summary(
            self.db,
            user_id=self.user_id,
            month="2026-08",
        )
        self.assertEqual(Decimal("12000.00"), summary["income"])
        self.assertEqual(1, summary["confirmed_count"])

        allocation_count = self.db.query(EconomicFactAllocation).count()
        fact_revision_count = self.db.query(EconomicFactRevision).count()
        ledger_revision_count = self.db.query(FinancialLedgerRevisionEvent).count()
        repeated = confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            data=request,
        )
        self.assertEqual(report["corroborating_candidate_ids"], repeated["corroborating_candidate_ids"])
        self.assertEqual(allocation_count, self.db.query(EconomicFactAllocation).count())
        self.assertEqual(fact_revision_count, self.db.query(EconomicFactRevision).count())
        self.assertEqual(ledger_revision_count, self.db.query(FinancialLedgerRevisionEvent).count())

    def test_partial_candidate_evidence_merge_keeps_remainder_as_independent_fact(self):
        target, target_fact = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="partial-merge-evidence-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        ready, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                target_transaction_id=target.id,
                allocated_amount=Decimal("5000.00"),
                evidence_merge_reason="只有其中 5000 元能与已有到账证据对上",
            ),
        )

        _, report = self._confirm_one(refreshed_batch, ready)
        self.assertEqual([ready.id], report["corroborating_candidate_ids"])
        self.assertEqual([ready.id], report["independent_candidate_ids"])
        self.assertEqual(1, report["corroborating_count"])
        self.assertEqual(1, report["independent_count"])

        source_transaction = self.db.get(FinancialTransaction, ready.transaction_id)
        source_fact = self.db.query(EconomicFact).filter_by(
            primary_transaction_id=source_transaction.id,
        ).one()
        self.assertEqual("confirmed", source_fact.status)
        self.assertEqual(Decimal("7000.00"), source_fact.amount)
        allocation = self.db.query(EconomicFactAllocation).filter_by(
            fact_id=target_fact.id,
            transaction_id=source_transaction.id,
            role="corroborating",
            status="confirmed",
        ).one()
        self.assertEqual(Decimal("5000.00"), allocation.allocated_amount)
        summary = _build_user_month_summary(
            self.db,
            user_id=self.user_id,
            month="2026-08",
        )
        self.assertEqual(Decimal("19000.00"), summary["income"])
        self.assertEqual(2, summary["confirmed_count"])

    def test_evidence_merge_rejects_even_one_cent_over_available_amount(self):
        target, _ = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="over-available-merge-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        with self.assertRaises(HTTPException) as context:
            update_candidate(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                candidate_id=candidate.id,
                data=FinancialImportCandidateUpdate(
                    expected_version=candidate.version,
                    action="merge_evidence",
                    target_transaction_id=target.id,
                    allocated_amount=Decimal("12000.01"),
                    evidence_merge_reason="超过当前候选和目标金额一分钱",
                ),
            )
        self.assertEqual("cashflow_import_merge_amount_invalid", context.exception.detail["code"])
        self.db.rollback()
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

    def test_same_source_duplicate_is_visible_but_cannot_merge_as_evidence(self):
        target, _ = self._create_formal_income(source_type="import_wechat")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="same-source-merge-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        response = candidate_payload(self.db, batch=batch, candidate=candidate)
        self.assertFalse(response.duplicate_matches[0].can_merge_as_evidence)
        self.assertIn("同一来源", response.duplicate_matches[0].merge_block_reason)
        with self.assertRaises(HTTPException) as context:
            update_candidate(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                candidate_id=candidate.id,
                data=FinancialImportCandidateUpdate(
                    expected_version=candidate.version,
                    action="merge_evidence",
                    target_transaction_id=target.id,
                    allocated_amount=Decimal("12000.00"),
                    evidence_merge_reason="看起来是同一笔，但来源一致",
                ),
            )
        self.assertEqual("cashflow_import_merge_not_allowed", context.exception.detail["code"])
        self.db.rollback()
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

    def test_merge_evidence_applies_missing_category_from_the_same_patch(self):
        target, target_fact = self._create_formal_income()
        parsed = self._generated_income_candidate(
            row_number=1,
            external_key="merge-with-category-001",
            amount=Decimal("12000.00"),
            transaction_date=date(2026, 8, 1),
            merchant="公司财务",
            description="八月工资",
        )
        parsed = ParsedCandidate(
            row_number=parsed.row_number,
            direction=parsed.direction,
            amount=parsed.amount,
            currency=parsed.currency,
            transaction_date=parsed.transaction_date,
            occurred_at=parsed.occurred_at,
            category_name=None,
            merchant=parsed.merchant,
            description=parsed.description,
            nature=parsed.nature,
            external_key=parsed.external_key,
            fingerprint=parsed.fingerprint,
            original_payload=parsed.original_payload,
            evidence=parsed.evidence,
            validation_errors=parsed.validation_errors,
            warnings=parsed.warnings,
        )
        batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="wechat_ocr",
            content_hash="c" * 64,
            parser_version="merge-category-test-v1",
            parsed=[parsed],
            ocr_text="2026-08-01 八月工资 12000.00",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        self.assertEqual("possible_duplicate", candidate.status)
        self.assertIsNone(candidate.category_id)
        self.assertIn(
            "CATEGORY_REVIEW_REQUIRED",
            {issue["code"] for issue in candidate.warnings},
        )

        ready, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                category_id=self.categories[("income", "工资")].id,
                target_transaction_id=target.id,
                allocated_amount=Decimal("12000.00"),
                evidence_merge_reason="同一请求补齐分类并确认跨来源证据",
            ),
        )
        self.assertEqual("ready", ready.status)
        self.assertEqual(self.categories[("income", "工资")].id, ready.category_id)
        self.assertEqual("工资", ready.category_name)
        self.assertNotIn(
            "CATEGORY_REVIEW_REQUIRED",
            {issue["code"] for issue in ready.warnings},
        )
        self.assertIn("category_id", ready.evidence["user_modified_fields"])

        _, report = self._confirm_one(refreshed_batch, ready)
        self.assertEqual([ready.id], report["corroborating_candidate_ids"])
        self.assertEqual([target_fact.id], report["corroborating_fact_ids"])
        self.assertEqual(1, report["corroborating_count"])

    def test_merge_evidence_rejects_missing_or_direction_mismatched_category(self):
        target, _ = self._create_formal_income()
        parsed = self._generated_income_candidate(
            row_number=1,
            external_key="merge-invalid-category-001",
            amount=Decimal("12000.00"),
            transaction_date=date(2026, 8, 1),
            merchant="公司财务",
            description="八月工资",
        )
        parsed = ParsedCandidate(
            row_number=parsed.row_number,
            direction=parsed.direction,
            amount=parsed.amount,
            currency=parsed.currency,
            transaction_date=parsed.transaction_date,
            occurred_at=parsed.occurred_at,
            category_name=None,
            merchant=parsed.merchant,
            description=parsed.description,
            nature=parsed.nature,
            external_key=parsed.external_key,
            fingerprint=parsed.fingerprint,
            original_payload=parsed.original_payload,
            evidence=parsed.evidence,
            validation_errors=parsed.validation_errors,
            warnings=parsed.warnings,
        )
        batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="wechat_ocr",
            content_hash="d" * 64,
            parser_version="merge-category-test-v1",
            parsed=[parsed],
            ocr_text="2026-08-01 八月工资 12000.00",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()

        for category_id in (
            999_999,
            self.categories[("expense", "餐饮")].id,
        ):
            with self.subTest(category_id=category_id):
                with self.assertRaises(HTTPException) as context:
                    update_candidate(
                        self.db,
                        user_id=self.user_id,
                        batch_id=batch.id,
                        candidate_id=candidate.id,
                        data=FinancialImportCandidateUpdate(
                            expected_version=candidate.version,
                            action="merge_evidence",
                            category_id=category_id,
                            target_transaction_id=target.id,
                            allocated_amount=Decimal("12000.00"),
                            evidence_merge_reason="无效分类不应允许写入合并意图",
                        ),
                    )
                self.assertEqual(
                    "cashflow_import_candidate_not_ready",
                    context.exception.detail["code"],
                )
                self.db.rollback()
                self.db.refresh(candidate)
                self.assertEqual("possible_duplicate", candidate.status)
                self.assertIsNone(candidate.category_id)
                self.assertNotIn("economic_fact_merge", candidate.evidence)

    def test_merge_target_change_rolls_back_source_observation_atomically(self):
        target, target_fact = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="stale-merge-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        ready, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                target_transaction_id=target.id,
                allocated_amount=Decimal("12000.00"),
                evidence_merge_reason="两份跨来源的工资到账证据",
            ),
        )
        target.amount = Decimal("11999.00")
        target_fact.amount = Decimal("11999.00")
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            self._confirm_one(refreshed_batch, ready)
        self.assertEqual("cashflow_import_merge_target_changed", context.exception.detail["code"])
        self.assertEqual(1, self.db.query(FinancialTransaction).count())
        self.assertEqual(
            0,
            self.db.query(EconomicFactAllocation).filter_by(role="corroborating", status="confirmed").count(),
        )
        self.db.refresh(ready)
        self.assertEqual("ready", ready.status)
        self.assertIsNone(ready.transaction_id)

    def test_merge_execution_failure_rolls_back_created_observation_and_revisions(self):
        target, _ = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="atomic-merge-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        ready, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                target_transaction_id=target.id,
                allocated_amount=Decimal("12000.00"),
                evidence_merge_reason="用于验证原子回滚的跨来源证据",
            ),
        )
        with patch(
            "app.services.cashflow_import_service.merge_fact_evidence_locked",
            side_effect=HTTPException(status_code=409, detail="forced merge failure"),
        ):
            with self.assertRaises(HTTPException):
                self._confirm_one(refreshed_batch, ready)

        self.assertEqual(1, self.db.query(FinancialTransaction).count())
        self.assertEqual(0, self.db.query(FinancialTransactionRevision).count())
        self.assertEqual(0, self.db.query(EconomicFactRevision).count())
        self.assertEqual(0, self.db.query(FinancialLedgerRevisionEvent).count())
        self.assertEqual(
            0,
            self.db.query(EconomicFactAllocation).filter_by(role="corroborating", status="confirmed").count(),
        )
        self.db.refresh(ready)
        self.assertEqual("ready", ready.status)
        self.assertIsNone(ready.transaction_id)

    def test_accept_review_clears_saved_merge_intent(self):
        target, _ = self._create_formal_income()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信收入账单.csv",
            content=_wechat_csv(_income_row(external_id="clear-merge-001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            user_id=self.user_id,
        ).one()
        ready, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="merge_evidence",
                target_transaction_id=target.id,
                allocated_amount=Decimal("12000.00"),
                evidence_merge_reason="两份跨来源证据",
            ),
        )
        as_new_fact, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=ready.id,
            data=FinancialImportCandidateUpdate(
                expected_version=ready.version,
                action="accept_review",
            ),
        )
        self.assertEqual("ready", as_new_fact.status)
        self.assertNotIn("economic_fact_merge", as_new_fact.evidence)

    def test_merge_evidence_update_schema_requires_target_amount_and_reason(self):
        with self.assertRaises(ValueError):
            FinancialImportCandidateUpdate(
                expected_version=1,
                action="merge_evidence",
                target_transaction_id=1,
            )
        valid = FinancialImportCandidateUpdate(
            expected_version=1,
            action="merge_evidence",
            target_transaction_id=2,
            allocated_amount=Decimal("88.00"),
            evidence_merge_reason="用户核对后确认为跨来源证据",
        )
        self.assertEqual("merge_evidence", valid.action)
        self.assertEqual(Decimal("88.00"), valid.allocated_amount)

    def test_candidate_version_conflict_prevents_stale_edit(self):
        batch, candidate, _ = self._create_ready_income(external_id="version-001")
        original_version = candidate.version

        with self.assertRaises(HTTPException) as stale_context:
            update_candidate(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                candidate_id=candidate.id,
                data=FinancialImportCandidateUpdate(
                    expected_version=original_version + 1,
                    merchant="过期客户端修改",
                ),
            )
        self.assertEqual(409, stale_context.exception.status_code)
        self.assertEqual(
            "cashflow_import_stale_candidate",
            stale_context.exception.detail["code"],
        )
        self.db.rollback()
        self.db.refresh(candidate)
        self.assertEqual("公司财务", candidate.merchant)

        updated, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=original_version,
                merchant="已核对公司财务",
            ),
        )
        self.assertGreater(updated.version, original_version)
        self.assertEqual("已核对公司财务", updated.merchant)

        with self.assertRaises(HTTPException) as repeated_stale_context:
            update_candidate(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                candidate_id=candidate.id,
                data=FinancialImportCandidateUpdate(
                    expected_version=original_version,
                    description="旧页面覆盖",
                ),
            )
        self.assertEqual(409, repeated_stale_context.exception.status_code)
        self.assertEqual(
            "cashflow_import_stale_candidate",
            repeated_stale_context.exception.detail["code"],
        )

    def test_confirmation_is_the_only_formal_write_and_is_idempotent(self):
        batch, candidate, _ = self._create_ready_income(external_id="confirm-001")
        self.assertEqual(0, self.db.query(FinancialTransaction).count())

        request, report = self._confirm_one(batch, candidate)

        self.assertEqual(1, report["confirmed_count"])
        self.assertEqual(1, self.db.query(FinancialTransaction).count())
        transaction = self.db.query(FinancialTransaction).one()
        self.assertEqual("confirmed", transaction.status)
        self.assertEqual("import_wechat", transaction.source_type)
        self.assertEqual(candidate.external_key, transaction.external_key)
        self.assertIsNotNone(candidate.occurred_at)
        self.assertIsNone(transaction.occurred_at)
        self.assertEqual(candidate.id, report["confirmed_candidate_ids"][0])
        revision = self.db.query(FinancialTransactionRevision).one()
        self.assertEqual(transaction.id, revision.transaction_id)
        self.assertEqual("create", revision.operation)
        self.assertEqual(self.user_id, revision.actor_user_id)
        ledger_event = self.db.query(FinancialLedgerRevisionEvent).one()
        self.assertEqual(transaction.id, ledger_event.entity_id)
        self.assertEqual("transaction_create", ledger_event.event_type)

        repeated_report = confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            data=request,
        )
        self.assertEqual(1, repeated_report["confirmed_count"])
        self.assertEqual([transaction.id], repeated_report["transaction_ids"])
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

    def test_soft_deleted_formal_transaction_still_blocks_external_key_reimport(self):
        batch, candidate, _ = self._create_ready_income(external_id="deleted-key-001")
        _, report = self._confirm_one(batch, candidate)
        transaction = self.db.get(FinancialTransaction, report["transaction_ids"][0])
        transaction.deleted_at = datetime.utcnow()
        self.db.commit()

        changed_content = _wechat_csv(
            _income_row(
                external_id="deleted-key-001",
                description="八月工资重新导入",
            ),
            metadata="微信支付账单明细（重新下载）",
        )
        second_batch, reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="微信账单重新下载.csv",
            content=changed_content,
            source_hint="auto",
        )
        duplicate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=second_batch.id, user_id=self.user_id)
            .one()
        )

        self.assertFalse(reused)
        self.assertNotEqual(batch.id, second_batch.id)
        self.assertEqual("exact_duplicate", duplicate.status)
        self.assertEqual(transaction.id, duplicate.duplicate_transaction_id)
        self.assertTrue(
            any(
                issue.get("code") == "EXACT_DUPLICATE" and "原记录已删除" in issue.get("message", "")
                for issue in duplicate.warnings
            )
        )
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

        with self.assertRaises(HTTPException) as confirmation_context:
            confirm_candidates(
                self.db,
                user_id=self.user_id,
                batch_id=second_batch.id,
                data=FinancialImportConfirmRequest(
                    expected_batch_version=second_batch.version,
                    candidates=[
                        {
                            "candidate_id": duplicate.id,
                            "expected_version": duplicate.version,
                        }
                    ],
                ),
            )
        self.assertEqual(409, confirmation_context.exception.status_code)
        self.assertEqual(
            "cashflow_import_candidate_not_ready",
            confirmation_context.exception.detail["code"],
        )
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

    def test_exact_duplicate_can_be_explicitly_restored_without_silent_write(self):
        first_batch, first_candidate, content = self._create_ready_income(
            external_id="explicit-duplicate-001"
        )
        _, first_report = self._confirm_one(first_batch, first_candidate)
        original_transaction_id = first_report["transaction_ids"][0]
        duplicate_batch, reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="需要明确重复入账的工资.csv",
            content=content.replace(b"\xef\xbb\xbf", b"\xef\xbb\xbf", 1) + b"\n",
            source_hint="auto",
        )
        duplicate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=duplicate_batch.id, user_id=self.user_id)
            .one()
        )
        self.assertFalse(reused)
        self.assertEqual("exact_duplicate", duplicate.status)
        self.assertEqual(original_transaction_id, duplicate.duplicate_transaction_id)

        restored, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=duplicate_batch.id,
            candidate_id=duplicate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=duplicate.version,
                action="record_duplicate",
                duplicate_override_reason="这是第二次实际到账",
            ),
        )

        self.assertEqual("ready", restored.status)
        self.assertIsNone(restored.external_key)
        self.assertIsNone(restored.duplicate_transaction_id)
        self.assertEqual(
            "这是第二次实际到账",
            restored.evidence["duplicate_override_reason"],
        )
        self.assertEqual(
            [original_transaction_id],
            restored.evidence["duplicate_override_transaction_ids"],
        )
        self.assertIn("duplicate_override_original_external_key_hash", restored.evidence)
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

        _, second_report = self._confirm_one(refreshed_batch, restored)
        self.assertEqual(1, second_report["confirmed_count"])
        self.assertEqual(2, self.db.query(FinancialTransaction).count())

    def test_separate_unconfirmed_batches_cross_reference_exact_and_fuzzy_duplicates(self):
        first_content = _wechat_csv(
            _expense_row(
                external_id="cross-screen-001",
                amount="48.00",
                merchant="截图重叠咖啡店",
                description="下午咖啡",
            )
        )
        first_batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="第一张长截图.csv",
            content=first_content,
            source_hint="auto",
        )
        first_candidate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=first_batch.id, user_id=self.user_id)
            .one()
        )
        self.assertEqual("ready", first_candidate.status)

        exact_batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="第二张含重叠区.csv",
            content=first_content + b"\n",
            source_hint="auto",
        )
        exact_candidate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=exact_batch.id, user_id=self.user_id)
            .one()
        )
        self.assertEqual("exact_duplicate", exact_candidate.status)
        self.assertEqual(
            [first_candidate.id],
            exact_candidate.evidence["exact_duplicate_candidate_ids"],
        )

        fuzzy_content = _wechat_csv(
            _expense_row(
                external_id="cross-screen-002",
                amount="48.00",
                merchant="截图重叠咖啡店",
                description="下午咖啡 重叠片段",
            ),
            metadata="微信支付账单明细（第三张）",
        )
        fuzzy_batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="第三张相似截图.csv",
            content=fuzzy_content,
            source_hint="auto",
        )
        fuzzy_candidate = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=fuzzy_batch.id, user_id=self.user_id)
            .one()
        )
        self.assertEqual("possible_duplicate", fuzzy_candidate.status)
        self.assertIn(
            first_candidate.id,
            fuzzy_candidate.evidence["possible_duplicate_candidate_ids"],
        )
        self.assertEqual(0, self.db.query(FinancialTransaction).count())

    def test_clear_business_data_removes_cashflow_artifacts_and_ledger(self):
        custom_category = FinancialCategory(
            user_id=self.user_id,
            direction="expense",
            name="本人自定义支出",
            is_system=False,
            is_active=True,
        )
        self.db.add(custom_category)
        self.db.commit()
        batch, candidate, _ = self._create_ready_income(external_id="clear-data-001")
        self.assertGreater(
            self.db.query(FinancialRecognitionArtifact).filter_by(
                user_id=self.user_id,
                batch_id=batch.id,
            ).count(),
            0,
        )
        self._confirm_one(batch, candidate)

        cleanup_ids = _delete_business_data(self.user_id, self.db)
        self.db.commit()
        cleanup = process_attachment_cleanup_jobs(self.db, cleanup_ids)

        self.assertEqual(cleanup_ids, cleanup["completed_ids"])
        self.assertEqual(
            0,
            self.db.query(FinancialRecognitionArtifact).filter_by(user_id=self.user_id).count(),
        )
        self.assertEqual(
            0,
            self.db.query(FinancialTransactionCandidate).filter_by(user_id=self.user_id).count(),
        )
        self.assertEqual(
            0,
            self.db.query(FinancialImportBatch).filter_by(user_id=self.user_id).count(),
        )
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user_id).count(),
        )
        self.assertEqual(
            0,
            self.db.query(FinancialCategory).filter_by(user_id=self.user_id).count(),
        )
        self.assertGreater(
            self.db.query(FinancialCategory).filter(FinancialCategory.user_id.is_(None)).count(),
            0,
        )

    def test_failed_data_clear_commit_keeps_recognition_artifacts_and_rows(self):
        batch, _candidate, _ = self._create_ready_income(external_id="clear-rollback-001")

        cleanup_ids = _delete_business_data(self.user_id, self.db)
        with patch.object(self.db, "commit", side_effect=RuntimeError("synthetic clear commit failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic clear commit failure"):
                self.db.commit()
        self.db.rollback()

        self.assertEqual([], cleanup_ids)
        self.assertEqual(1, self.db.query(FinancialImportBatch).filter_by(user_id=self.user_id).count())
        self.assertGreater(
            self.db.query(FinancialRecognitionArtifact).filter_by(user_id=self.user_id).count(),
            0,
        )
        self.assertEqual(0, self.db.query(PersonalAttachmentVersion).filter_by(user_id=self.user_id).count())
        self.assertEqual(0, self.db.query(PersonalAttachmentCleanupJob).count())

    def test_pre_clear_intake_epoch_cannot_repopulate_business_data(self):
        stale_epoch = self.user.business_data_epoch
        cleanup_ids = _delete_business_data(self.user_id, self.db)
        self.db.commit()
        cleanup = process_attachment_cleanup_jobs(self.db, cleanup_ids)
        self.assertEqual(cleanup_ids, cleanup["completed_ids"])

        with self.assertRaises(HTTPException) as conflict:
            create_generated_import(
                self.db,
                user_id=self.user_id,
                origin_type="ocr",
                source_type="receipt",
                content_hash="d" * 64,
                parser_version="cashflow-ocr-stale-epoch-v1",
                parsed=[],
                original_filename="清空前已开始.png",
                original_content_type="image/png",
                original_file_size=len(b"must-not-be-persisted"),
                expected_data_epoch=stale_epoch,
            )

        self.assertEqual(409, conflict.exception.status_code)
        self.assertEqual("cashflow_import_data_cleared", conflict.exception.detail["code"])
        self.assertEqual(0, self.db.query(FinancialImportBatch).count())
        self.assertEqual(0, self.db.query(PersonalAttachmentVersion).count())
        self.assertEqual(
            [],
            [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()],
        )

    def test_failed_attachment_cleanup_is_durable_and_retryable(self):
        attachment = save_personal_attachment(
            self.db,
            user_id=self.user_id,
            document_type="cashflow_import",
            logical_key="cleanup-retry-001",
            display_name="待清理历史原件.csv",
            original_filename="待清理历史原件.csv",
            content_type="text/csv",
            content=b"legacy-private-content",
            version_number=1,
        )
        self.db.commit()
        stored_path = resolve_attachment_path(attachment)
        cleanup_ids = _delete_business_data(self.user_id, self.db)
        self.db.commit()

        with patch.object(Path, "unlink", side_effect=PermissionError("synthetic permission failure")):
            failed = process_attachment_cleanup_jobs(self.db, cleanup_ids)

        self.assertEqual(cleanup_ids, failed["failed_ids"])
        self.assertTrue(stored_path.is_file())
        durable_job = self.db.get(PersonalAttachmentCleanupJob, cleanup_ids[0])
        self.assertEqual("failed", durable_job.status)
        self.assertGreaterEqual(durable_job.attempts, 1)

        retried = process_attachment_cleanup_jobs(self.db, cleanup_ids)
        self.assertEqual(cleanup_ids, retried["completed_ids"])
        self.assertFalse(stored_path.exists())
        self.assertIsNone(self.db.get(PersonalAttachmentCleanupJob, cleanup_ids[0]))

    def test_ai_text_candidate_uses_same_review_and_confirmation_boundary(self):
        fingerprint = build_candidate_fingerprint(
            direction="expense",
            amount=Decimal("32.00"),
            transaction_date=date(2026, 8, 22),
            merchant="午餐餐厅",
            description="工作午饭",
        )
        parsed = ParsedCandidate(
            row_number=1,
            direction="expense",
            amount=Decimal("32.00"),
            currency="CNY",
            transaction_date=date(2026, 8, 22),
            occurred_at=None,
            category_name="餐饮",
            merchant="午餐餐厅",
            description="工作午饭",
            nature="flexible",
            external_key="ai_text:test-key",
            fingerprint=fingerprint,
            original_payload={"amount": "32.00"},
            evidence={"origin": "ai_text", "prompt_version": "test-v1"},
            validation_errors=[],
            warnings=[
                {
                    "field": "candidate",
                    "code": "AI_REVIEW_REQUIRED",
                    "message": "这是 AI 识别候选，请核对后再入账",
                }
            ],
        )
        batch, reused = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash="a" * 64,
            parser_version="cashflow-ai-test-v1",
            parsed=[parsed],
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()

        self.assertFalse(reused)
        self.assertEqual("needs_review", candidate.status)
        self.assertEqual(0, self.db.query(FinancialTransaction).count())

        accepted, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="accept_review",
            ),
        )
        self.assertEqual("ready", accepted.status)
        _request, report = self._confirm_one(refreshed_batch, accepted)
        self.assertEqual(1, report["confirmed_count"])
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

    def test_failed_source_transaction_cannot_be_unblocked_by_cosmetic_edit(self):
        failed_row = _income_row(external_id="failed-source-001").replace("支付成功", "交易关闭")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="关闭交易.csv",
            content=_wechat_csv(failed_row),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()
        self.assertEqual("invalid", candidate.status)

        updated, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                merchant="只改显示名称",
            ),
        )

        self.assertEqual("invalid", updated.status)
        self.assertTrue(
            any(issue.get("code") == "SOURCE_NOT_COMPLETED" for issue in updated.validation_errors)
        )
        self.assertEqual(0, self.db.query(FinancialTransaction).count())

    def test_negative_split_amount_cannot_be_unblocked_by_cosmetic_edit(self):
        content = (
            "交易日期,贷方金额,借方金额,对方户名,摘要,流水号\n"
            "2026-08-09,-100.00,,异常收入,负数贷方,negative-split-001\n"
        ).encode("utf-8")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="分列负数.csv",
            content=content,
            source_hint="bank",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()

        self.assertEqual("invalid", candidate.status)
        self.assertIsNone(candidate.amount)
        self.assertIn(
            "SIGN_DIRECTION_CONFLICT",
            {issue.get("code") for issue in candidate.validation_errors},
        )
        updated, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                merchant="只修改显示名称",
            ),
        )

        self.assertEqual("invalid", updated.status)
        self.assertIsNone(updated.amount)
        self.assertIn(
            "AMOUNT_INVALID",
            {issue.get("code") for issue in updated.validation_errors},
        )

    def test_direction_column_conflict_requires_explicit_direction_review(self):
        content = (
            "交易日期,方向,贷方金额,对方户名,流水号\n"
            "2026-08-01,支出,100.00,工资发放,conflicting-direction-001\n"
        ).encode("utf-8")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="方向冲突.csv",
            content=content,
            source_hint="bank",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).one()
        self.assertEqual("invalid", candidate.status)
        self.assertEqual("income", candidate.direction)
        self.assertIn(
            "DIRECTION_COLUMN_CONFLICT",
            {issue.get("code") for issue in candidate.validation_errors},
        )

        cosmetic, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                merchant="仅修改展示名称",
            ),
        )
        self.assertEqual("invalid", cosmetic.status)
        self.assertIn(
            "DIRECTION_COLUMN_CONFLICT",
            {issue.get("code") for issue in cosmetic.validation_errors},
        )

        reviewed, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=cosmetic.version,
                direction="income",
            ),
        )
        self.assertNotIn(
            "DIRECTION_COLUMN_CONFLICT",
            {issue.get("code") for issue in reviewed.validation_errors},
        )
        self.assertNotEqual("invalid", reviewed.status)

    def test_invalid_amount_is_not_rounded_into_a_candidate_fact(self):
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="金额精度错误.csv",
            content=_wechat_csv(_expense_row(external_id="scale-001", amount="0.001")),
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()

        self.assertEqual("invalid", candidate.status)
        self.assertIsNone(candidate.amount)
        self.assertEqual("", candidate.original_payload["amount"])
        self.assertTrue(any(issue.get("code") == "AMOUNT_SCALE" for issue in candidate.validation_errors))

    def test_invalid_row_does_not_poison_valid_row_with_same_external_key(self):
        content = _wechat_csv(
            _income_row(external_id="shared-after-invalid", amount="NaN"),
            _income_row(
                external_id="shared-after-invalid",
                amount="100.00",
                transaction_date="2026-08-03 09:30:00",
            ),
        )
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="无效行不占号.csv",
            content=content,
            source_hint="auto",
        )
        candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )

        self.assertEqual(["invalid", "ready"], [item.status for item in candidates])

    def test_new_parser_ignores_same_source_pending_candidates_but_keeps_confirmed_ledger_duplicate(self):
        content_hash = "9" * 64
        old_parsed = [
            self._generated_income_candidate(
                row_number=1,
                external_key="ai_text:same-source-invalid",
                amount=Decimal("101.00"),
                validation_errors=[{
                    "field": "occurrence",
                    "code": "TRANSACTION_NOT_OCCURRED",
                    "message": "发生状态不明确",
                }],
            ),
            self._generated_income_candidate(
                row_number=2,
                external_key="ai_text:same-source-pending",
                amount=Decimal("102.00"),
                warnings=[{
                    "field": "candidate",
                    "code": "AI_REVIEW_REQUIRED",
                    "message": "请核对",
                }],
            ),
            self._generated_income_candidate(
                row_number=3,
                external_key="ai_text:same-source-confirmed",
                amount=Decimal("103.00"),
            ),
        ]
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-v1",
            parsed=old_parsed,
        )
        old_candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=old_batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )
        self._confirm_one(old_batch, old_candidates[2])

        new_parsed = [
            self._generated_income_candidate(
                row_number=index,
                external_key=external_key,
                amount=amount,
            )
            for index, external_key, amount in (
                (1, "ai_text:same-source-invalid", Decimal("101.00")),
                (2, "ai_text:same-source-pending", Decimal("102.00")),
                (3, "ai_text:same-source-confirmed", Decimal("103.00")),
            )
        ]
        new_batch, reused = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-v2",
            parsed=new_parsed,
        )
        new_candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=new_batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )

        self.assertFalse(reused)
        self.assertEqual(
            ["ready", "ready", "exact_duplicate"],
            [item.status for item in new_candidates],
        )

    def test_historical_invalid_candidate_never_claims_duplicate_identity(self):
        invalid = self._generated_income_candidate(
            row_number=1,
            external_key="ai_text:historical-invalid",
            amount=Decimal("88.00"),
            validation_errors=[{
                "field": "occurrence",
                "code": "TRANSACTION_NOT_OCCURRED",
                "message": "发生状态不明确",
            }],
        )
        create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash="7" * 64,
            parser_version="historical-invalid-v1",
            parsed=[invalid],
        )

        valid = self._generated_income_candidate(
            row_number=1,
            external_key="ai_text:historical-invalid",
            amount=Decimal("88.00"),
        )
        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash="8" * 64,
            parser_version="historical-invalid-v2",
            parsed=[valid],
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("ready", candidate.status)

    def test_same_source_confirmed_replay_across_parsers_is_conservative_and_never_writes(self):
        content_hash = "6" * 64
        old_specs = (
            ("exact", Decimal("201.00"), date(2026, 8, 20), "已确认收入甲"),
            ("inferred", Decimal("202.00"), date(2026, 8, 21), "已确认收入乙"),
            ("missing", Decimal("203.00"), date(2026, 8, 22), "已确认收入丙"),
            ("weak", Decimal("204.00"), date(2026, 8, 23), "已确认收入丁"),
            ("amount-only", Decimal("205.00"), date(2026, 8, 24), "已确认收入戊"),
        )
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-replay-v1",
            parsed=[
                self._generated_income_candidate(
                    row_number=index,
                    external_key=f"old-parser:{key}",
                    amount=amount,
                    transaction_date=transaction_date,
                    merchant=merchant,
                    description="同一原图收入",
                )
                for index, (key, amount, transaction_date, merchant) in enumerate(
                    old_specs,
                    start=1,
                )
            ],
        )
        old_candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=old_batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )
        confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=old_batch.id,
            data=FinancialImportConfirmRequest(
                expected_batch_version=old_batch.version,
                candidates=[
                    {
                        "candidate_id": candidate.id,
                        "expected_version": candidate.version,
                    }
                    for candidate in old_candidates
                ],
            ),
        )
        transactions_by_amount = {
            Decimal(candidate.amount): candidate.transaction_id
            for candidate in old_candidates
        }
        formal_count_before = self.db.query(FinancialTransaction).count()

        new_batch, reused = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-replay-v2",
            parsed=[
                self._generated_income_candidate(
                    row_number=1,
                    external_key="new-parser:exact",
                    amount=Decimal("201.00"),
                    transaction_date=date(2026, 8, 20),
                    merchant="已确认收入甲",
                    description="同一原图收入",
                ),
                self._generated_income_candidate(
                    row_number=2,
                    external_key="new-parser:inferred",
                    amount=Decimal("202.00"),
                    transaction_date=date(2025, 8, 21),
                    merchant="已确认收入乙",
                    description="同一原图收入",
                    warnings=[{
                        "field": "transaction_date",
                        "code": "PROGRAM_YEAR_INFERRED",
                        "message": "年份由程序推断",
                    }],
                ),
                self._generated_income_candidate(
                    row_number=3,
                    external_key="new-parser:missing",
                    amount=Decimal("203.00"),
                    transaction_date=None,
                    merchant="已确认收入丙",
                    description="同一原图收入",
                    validation_errors=[{
                        "field": "transaction_date",
                        "code": "DATE_INVALID",
                        "message": "日期缺失",
                    }],
                ),
                self._generated_income_candidate(
                    row_number=4,
                    external_key="new-parser:weak",
                    amount=Decimal("204.00"),
                    transaction_date=date(2026, 8, 25),
                    merchant="已确认收入丁",
                    description="同一原图收入",
                ),
                self._generated_income_candidate(
                    row_number=5,
                    external_key="new-parser:amount-only",
                    amount=Decimal("205.00"),
                    transaction_date=date(2026, 8, 26),
                    merchant="完全不同的收入方",
                    description="完全不同的用途",
                ),
            ],
        )
        new_candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=new_batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )

        self.assertFalse(reused)
        self.assertEqual(
            ["exact_duplicate", "possible_duplicate", "possible_duplicate", "possible_duplicate", "ready"],
            [candidate.status for candidate in new_candidates],
        )
        exact = new_candidates[0]
        self.assertEqual(
            transactions_by_amount[Decimal(exact.amount)],
            exact.duplicate_transaction_id,
        )
        self.assertEqual(
            "strong",
            exact.evidence["same_source_replay_match"]["strength"],
        )
        for candidate in new_candidates[1:3]:
            self.assertEqual(
                transactions_by_amount[Decimal(candidate.amount)],
                candidate.duplicate_transaction_id,
            )
            self.assertEqual(
                "weak",
                candidate.evidence["same_source_replay_match"]["strength"],
            )
            self.assertEqual(
                "same_source_identity_date_uncertain",
                candidate.evidence["same_source_replay_match"]["reason_code"],
            )
        weak = new_candidates[3]
        self.assertEqual(
            transactions_by_amount[Decimal("204.00")],
            weak.duplicate_transaction_id,
        )
        self.assertEqual(
            "same_source_text_date_conflict",
            weak.evidence["same_source_replay_match"]["reason_code"],
        )
        self.assertTrue(any(
            warning.get("code") == "POSSIBLE_DUPLICATE"
            and "日期冲突" in warning.get("message", "")
            for warning in weak.warnings
        ))
        self.assertNotIn("same_source_replay_match", new_candidates[4].evidence)
        self.assertEqual(
            formal_count_before,
            self.db.query(FinancialTransaction).count(),
        )

    def test_same_source_common_description_with_different_merchants_is_never_strong(self):
        content_hash = "4" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-common-text-v1",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:common-text",
                amount=Decimal("207.00"),
                merchant="甲商户",
                description="微信支付",
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        self._confirm_one(old_batch, old_candidate)

        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-common-text-v2",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:common-text",
                amount=Decimal("207.00"),
                merchant="乙商户",
                description="微信支付",
            )],
        )
        replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("possible_duplicate", replay.status)
        self.assertEqual(old_candidate.transaction_id, replay.duplicate_transaction_id)
        self.assertEqual(
            "weak",
            replay.evidence["same_source_replay_match"]["strength"],
        )
        self.assertEqual(
            "same_source_core_identity_weak",
            replay.evidence["same_source_replay_match"]["reason_code"],
        )

    def test_same_source_payment_channel_merchant_is_never_a_strong_identity(self):
        content_hash = "b" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-channel-merchant-v1",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:channel-merchant",
                amount=Decimal("207.50"),
                merchant="微信支付",
                description="第一笔实际收款",
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        self._confirm_one(old_batch, old_candidate)

        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-channel-merchant-v2",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:channel-merchant",
                amount=Decimal("207.50"),
                merchant="微信支付",
                description="第二笔实际收款",
            )],
        )
        replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("possible_duplicate", replay.status)
        self.assertEqual(
            "weak",
            replay.evidence["same_source_replay_match"]["strength"],
        )
        self.assertEqual(
            "same_source_core_identity_weak",
            replay.evidence["same_source_replay_match"]["reason_code"],
        )

    def test_confirmation_rechecks_same_source_rows_confirmed_after_preview(self):
        content_hash = "a" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-late-confirm-v1",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:late-confirm",
                amount=Decimal("207.75"),
                transaction_date=date(2026, 8, 20),
                merchant="同源已确认收入",
                description="旧解析文本",
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-late-confirm-v2",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:late-confirm",
                amount=Decimal("207.75"),
                transaction_date=date(2026, 8, 21),
                merchant="同源已确认收入",
                description="新解析文本",
            )],
        )
        new_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()
        self.assertEqual("ready", new_candidate.status)

        self._confirm_one(old_batch, old_candidate)
        formal_count_before = self.db.query(FinancialTransaction).count()
        with self.assertRaises(HTTPException) as conflict:
            self._confirm_one(new_batch, new_candidate)

        self.assertEqual(
            "cashflow_import_possible_duplicate",
            conflict.exception.detail["code"],
        )
        self.db.refresh(new_candidate)
        self.assertEqual("possible_duplicate", new_candidate.status)
        self.assertEqual(
            "same_source_text_date_conflict",
            new_candidate.evidence["same_source_replay_match"]["reason_code"],
        )
        self.assertEqual(
            formal_count_before,
            self.db.query(FinancialTransaction).count(),
        )

    def test_same_source_one_strong_plus_other_weak_transaction_is_ambiguous(self):
        content_hash = "3" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-ambiguous-v1",
            parsed=[
                self._generated_income_candidate(
                    row_number=1,
                    external_key="old-parser:ambiguous-a",
                    amount=Decimal("208.00"),
                    merchant="明确商户甲",
                    description="甲订单",
                ),
                self._generated_income_candidate(
                    row_number=2,
                    external_key="old-parser:ambiguous-b",
                    amount=Decimal("208.00"),
                    merchant="明确商户乙",
                    description="乙订单",
                ),
            ],
        )
        old_candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=old_batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )
        confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=old_batch.id,
            data=FinancialImportConfirmRequest(
                expected_batch_version=old_batch.version,
                candidates=[
                    {
                        "candidate_id": candidate.id,
                        "expected_version": candidate.version,
                    }
                    for candidate in old_candidates
                ],
            ),
        )

        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-ambiguous-v2",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:ambiguous",
                amount=Decimal("208.00"),
                merchant="明确商户甲",
                description="甲订单",
            )],
        )
        replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("possible_duplicate", replay.status)
        self.assertEqual(
            "weak",
            replay.evidence["same_source_replay_match"]["strength"],
        )
        self.assertEqual(
            "same_source_confirmed_match_ambiguous",
            replay.evidence["same_source_replay_match"]["reason_code"],
        )
        self.assertEqual(
            {candidate.transaction_id for candidate in old_candidates},
            set(replay.evidence["same_source_replay_match"]["transaction_ids"]),
        )

    def test_same_source_replay_uses_current_transaction_identity_across_parser_versions(self):
        content_hash = "2" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-edited-ledger-v1",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:edited-ledger",
                amount=Decimal("209.00"),
                merchant="旧解析商户",
                description="旧解析说明",
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        self._confirm_one(old_batch, old_candidate)
        transaction = self.db.query(FinancialTransaction).filter_by(
            id=old_candidate.transaction_id,
        ).one()
        transaction.merchant = "用户修正商户"
        transaction.description = "用户修正说明"
        self.db.flush()

        stale_text_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-edited-ledger-v2",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:edited-ledger-stale",
                amount=Decimal("209.00"),
                merchant="旧解析商户",
                description="旧解析说明",
            )],
        )
        stale_text_replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=stale_text_batch.id,
        ).one()
        self.assertEqual("possible_duplicate", stale_text_replay.status)
        self.assertEqual(
            "weak",
            stale_text_replay.evidence["same_source_replay_match"]["strength"],
        )

        current_text_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash=content_hash,
            parser_version="same-source-edited-ledger-v3",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:edited-ledger-current",
                amount=Decimal("209.00"),
                merchant="用户修正商户",
                description="用户修正说明",
            )],
        )
        current_text_replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=current_text_batch.id,
        ).one()
        self.assertEqual("exact_duplicate", current_text_replay.status)
        self.assertEqual(
            "strong",
            current_text_replay.evidence["same_source_replay_match"]["strength"],
        )
        self.assertEqual(
            "same_source_merchant_date_exact",
            current_text_replay.evidence["same_source_replay_match"]["reason_code"],
        )

    def test_same_source_stable_row_identity_can_resolve_an_uncertain_date(self):
        content_hash = "1" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            content_hash=content_hash,
            parser_version="same-source-stable-row-v1",
            ocr_text="旧版稳定来源行",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:stable-row",
                amount=Decimal("210.00"),
                merchant="旧版商户",
                description="旧版说明",
                evidence={"source_row_id": "full-image-row-42"},
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        self._confirm_one(old_batch, old_candidate)

        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            content_hash=content_hash,
            parser_version="same-source-stable-row-v2",
            ocr_text="新版稳定来源行",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:stable-row",
                amount=Decimal("210.00"),
                transaction_date=date(2025, 8, 20),
                merchant="新版商户",
                description="新版说明",
                evidence={"source_row_id": "full-image-row-42"},
                warnings=[{
                    "field": "transaction_date",
                    "code": "PROGRAM_YEAR_INFERRED",
                    "message": "年份由程序推断",
                }],
            )],
        )
        replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("exact_duplicate", replay.status)
        self.assertEqual(old_candidate.transaction_id, replay.duplicate_transaction_id)
        self.assertEqual(
            "same_source_anchor_date_relaxed",
            replay.evidence["same_source_replay_match"]["reason_code"],
        )

    def test_same_source_uncertain_date_same_slice_is_visible_possible_duplicate(self):
        content_hash = "5" * 64
        old_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            content_hash=content_hash,
            parser_version="same-slice-replay-v1",
            ocr_text="旧版测试识别文字",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="old-parser:same-slice",
                amount=Decimal("206.00"),
                transaction_date=date(2026, 8, 20),
                merchant="旧版识别文字",
                description="旧版说明",
                evidence={"slice_sequence": 3, "evidence_quote": "旧版证据"},
            )],
        )
        old_candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=old_batch.id,
        ).one()
        self._confirm_one(old_batch, old_candidate)
        formal_count_before = self.db.query(FinancialTransaction).count()

        new_batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            content_hash=content_hash,
            parser_version="same-slice-replay-v2",
            ocr_text="新版测试识别文字",
            parsed=[self._generated_income_candidate(
                row_number=1,
                external_key="new-parser:same-slice",
                amount=Decimal("206.00"),
                direction=None,
                currency="UNK",
                transaction_date=None,
                merchant="完全不同的新版文字",
                description="完全不同的新版说明",
                evidence={"slice_sequence": 3, "evidence_quote": "新版证据"},
                validation_errors=[{
                    "field": "transaction_date",
                    "code": "DATE_INVALID",
                    "message": "日期缺失",
                }, {
                    "field": "direction",
                    "code": "DIRECTION_REQUIRED",
                    "message": "方向缺失",
                }, {
                    "field": "currency",
                    "code": "CURRENCY_REQUIRED",
                    "message": "币种缺失",
                }],
            )],
        )
        replay = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=new_batch.id,
        ).one()

        self.assertEqual("possible_duplicate", replay.status)
        self.assertEqual(old_candidate.transaction_id, replay.duplicate_transaction_id)
        self.assertEqual(
            "same_source_slice_amount_core_uncertain",
            replay.evidence["same_source_replay_match"]["reason_code"],
        )
        self.assertEqual(
            formal_count_before,
            self.db.query(FinancialTransaction).count(),
        )

    def test_edit_that_matches_sibling_requires_explicit_duplicate_review(self):
        content = _wechat_csv(
            _income_row(
                external_id="sibling-001",
                amount="100.00",
                merchant="甲公司",
                description="项目款",
            ),
            _income_row(
                external_id="sibling-002",
                amount="200.00",
                transaction_date="2026-08-02 09:30:00",
                merchant="乙公司",
                description="其他款",
            ),
        )
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="同批编辑查重.csv",
            content=content,
            source_hint="auto",
        )
        first, second = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )

        updated, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=second.id,
            data=FinancialImportCandidateUpdate(
                expected_version=second.version,
                amount=first.amount,
                transaction_date=first.transaction_date,
                category_id=first.category_id,
                merchant=first.merchant,
                description=first.description,
            ),
        )

        self.assertEqual("possible_duplicate", updated.status)
        self.assertIn(
            "POSSIBLE_DUPLICATE",
            {issue.get("code") for issue in updated.warnings},
        )

    def test_mixed_confirmed_and_confirmation_duplicate_replay_is_idempotent(self):
        content = _wechat_csv(
            _income_row(external_id="mixed-confirm-001", amount="100.00"),
            _income_row(
                external_id="mixed-confirm-002",
                amount="200.00",
                transaction_date="2026-08-02 09:30:00",
                merchant="另一公司",
                description="另一笔款",
            ),
        )
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="混合确认重放.csv",
            content=content,
            source_hint="auto",
        )
        first, second = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id)
            .order_by(FinancialTransactionCandidate.row_number)
            .all()
        )
        existing = FinancialTransaction(
            user_id=self.user_id,
            category_id=second.category_id,
            direction=second.direction,
            amount=second.amount,
            currency="CNY",
            transaction_date=second.transaction_date,
            occurred_at=second.occurred_at,
            merchant=second.merchant,
            description=second.description,
            source_type="import_wechat",
            external_key=second.external_key,
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(existing)
        self.db.commit()
        request = FinancialImportConfirmRequest(
            expected_batch_version=batch.version,
            candidates=[
                {"candidate_id": first.id, "expected_version": first.version},
                {"candidate_id": second.id, "expected_version": second.version},
            ],
        )

        first_report = confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            data=request,
        )
        repeated_report = confirm_candidates(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            data=request,
        )

        self.assertEqual(1, first_report["confirmed_count"])
        self.assertEqual(1, first_report["duplicate_count"])
        self.assertEqual(first_report["transaction_ids"], repeated_report["transaction_ids"])
        self.assertEqual(first_report["duplicate_candidate_ids"], repeated_report["duplicate_candidate_ids"])
        self.assertEqual(2, self.db.query(FinancialTransaction).count())

    def test_new_possible_duplicate_at_confirmation_requires_fresh_acceptance(self):
        batch, candidate, _ = self._create_ready_income(external_id="late-possible-001")
        manual = FinancialTransaction(
            user_id=self.user_id,
            category_id=candidate.category_id,
            direction=candidate.direction,
            amount=candidate.amount,
            currency="CNY",
            transaction_date=candidate.transaction_date,
            occurred_at=candidate.occurred_at,
            merchant=candidate.merchant,
            description=candidate.description,
            source_type="manual",
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(manual)
        self.db.commit()

        with self.assertRaises(HTTPException) as conflict:
            self._confirm_one(batch, candidate)
        self.assertEqual("cashflow_import_possible_duplicate", conflict.exception.detail["code"])
        self.assertEqual(1, self.db.query(FinancialTransaction).count())

        self.db.refresh(batch)
        self.db.refresh(candidate)
        self.assertEqual("possible_duplicate", candidate.status)
        accepted, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="accept_review",
            ),
        )
        self.assertEqual("ready", accepted.status)
        _, report = self._confirm_one(refreshed_batch, accepted)

        self.assertEqual(1, report["confirmed_count"])
        self.assertEqual(2, self.db.query(FinancialTransaction).count())

    def test_new_member_in_accepted_duplicate_set_requires_review_again(self):
        batch, candidate, _ = self._create_ready_income(external_id="duplicate-set-001")

        def add_manual(description_suffix: str) -> FinancialTransaction:
            transaction = FinancialTransaction(
                user_id=self.user_id,
                category_id=candidate.category_id,
                direction=candidate.direction,
                amount=candidate.amount,
                currency="CNY",
                transaction_date=candidate.transaction_date,
                occurred_at=candidate.occurred_at,
                merchant=candidate.merchant,
                description=candidate.description,
                source_type=f"manual_{description_suffix}",
                status="confirmed",
                confirmed_at=datetime.utcnow(),
            )
            self.db.add(transaction)
            self.db.commit()
            return transaction

        first_duplicate = add_manual("first")
        with self.assertRaises(HTTPException):
            self._confirm_one(batch, candidate)
        self.db.refresh(batch)
        self.db.refresh(candidate)
        accepted, accepted_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="accept_review",
            ),
        )
        self.assertEqual(
            [first_duplicate.id],
            accepted.evidence["duplicate_review_transaction_ids"],
        )

        second_duplicate = add_manual("second")
        with self.assertRaises(HTTPException) as conflict:
            self._confirm_one(accepted_batch, accepted)

        self.assertEqual("cashflow_import_possible_duplicate", conflict.exception.detail["code"])
        self.db.refresh(accepted)
        self.assertEqual("possible_duplicate", accepted.status)
        self.assertEqual(
            [first_duplicate.id, second_duplicate.id],
            accepted.evidence["possible_duplicate_transaction_ids"],
        )
        self.assertEqual(2, self.db.query(FinancialTransaction).count())

    def test_overflow_duplicate_review_is_bound_to_bucket_watermark(self):
        batch, candidate, _ = self._create_ready_income(external_id="overflow-watermark-001")
        self.db.add_all([
            FinancialTransaction(
                user_id=self.user_id,
                category_id=candidate.category_id,
                direction=candidate.direction,
                amount=candidate.amount,
                currency="CNY",
                transaction_date=candidate.transaction_date,
                merchant=f"历史商户 {index}",
                description=f"历史记录 {index}",
                source_type="manual",
                status="confirmed",
                confirmed_at=datetime.utcnow(),
            )
            for index in range(101)
        ])
        self.db.commit()

        with self.assertRaises(HTTPException) as first_conflict:
            self._confirm_one(batch, candidate)
        self.assertEqual(
            "cashflow_import_possible_duplicate",
            first_conflict.exception.detail["code"],
        )
        self.db.refresh(batch)
        self.db.refresh(candidate)
        first_watermark = candidate.evidence["possible_duplicate_bucket_watermark"]
        self.assertEqual(101, first_watermark["count"])
        self.assertIsNone(candidate.duplicate_transaction_id)
        self.assertIn("101 笔记录", candidate.warnings[0]["message"])

        accepted, accepted_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                action="accept_review",
            ),
        )
        self.assertEqual(
            first_watermark,
            accepted.evidence["duplicate_review_bucket_watermark"],
        )

        self.db.add(FinancialTransaction(
            user_id=self.user_id,
            category_id=candidate.category_id,
            direction=candidate.direction,
            amount=candidate.amount,
            currency="CNY",
            transaction_date=candidate.transaction_date,
            merchant=candidate.merchant,
            description=candidate.description,
            source_type="manual",
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        ))
        self.db.commit()

        with self.assertRaises(HTTPException) as second_conflict:
            self._confirm_one(accepted_batch, accepted)
        self.assertEqual(
            "cashflow_import_possible_duplicate",
            second_conflict.exception.detail["code"],
        )
        self.db.refresh(accepted)
        second_watermark = accepted.evidence["possible_duplicate_bucket_watermark"]
        self.assertEqual(102, second_watermark["count"])
        self.assertNotEqual(first_watermark, second_watermark)
        self.assertEqual(102, self.db.query(FinancialTransaction).count())

    def test_possible_duplicate_scan_does_not_stop_before_late_match(self):
        batch, candidate, _ = self._create_ready_income(external_id="late-scan-001")
        for index in range(50):
            self.db.add(FinancialTransaction(
                user_id=self.user_id,
                category_id=candidate.category_id,
                direction=candidate.direction,
                amount=candidate.amount,
                currency="CNY",
                transaction_date=candidate.transaction_date,
                merchant=f"不同商户 {index}",
                description=f"不同描述 {index}",
                source_type="manual",
                status="confirmed",
                confirmed_at=datetime.utcnow(),
            ))
        matching = FinancialTransaction(
            user_id=self.user_id,
            category_id=candidate.category_id,
            direction=candidate.direction,
            amount=candidate.amount,
            currency="CNY",
            transaction_date=candidate.transaction_date,
            merchant=candidate.merchant,
            description=candidate.description,
            source_type="manual",
            status="confirmed",
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(matching)
        self.db.commit()

        with self.assertRaises(HTTPException) as conflict:
            self._confirm_one(batch, candidate)

        self.assertEqual("cashflow_import_possible_duplicate", conflict.exception.detail["code"])
        self.db.refresh(candidate)
        self.assertEqual(matching.id, candidate.duplicate_transaction_id)
        self.assertEqual(51, self.db.query(FinancialTransaction).count())

    def test_500_candidate_confirmation_uses_bounded_selects_and_time(self):
        parsed: list[ParsedCandidate] = []
        for index in range(1, 501):
            amount = Decimal(index) + Decimal("0.01")
            merchant = f"批量收入方-{index}"
            description = f"批量收入-{index}"
            fingerprint = build_candidate_fingerprint(
                direction="income",
                amount=amount,
                transaction_date=date(2026, 8, 20),
                merchant=merchant,
                description=description,
            )
            parsed.append(ParsedCandidate(
                row_number=index,
                direction="income",
                amount=amount,
                currency="CNY",
                transaction_date=date(2026, 8, 20),
                occurred_at=None,
                category_name="工资",
                merchant=merchant,
                description=description,
                nature=None,
                external_key=f"ai_text:bulk-confirm-{index}",
                fingerprint=fingerprint,
                original_payload={"row": str(index)},
                evidence={"origin": "test"},
                validation_errors=[],
                warnings=[],
            ))
        batch, _ = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ai_text",
            source_type="ai_text",
            content_hash="e" * 64,
            parser_version="cashflow-bulk-confirm-v1",
            parsed=parsed,
        )
        candidates = (
            self.db.query(FinancialTransactionCandidate)
            .filter_by(batch_id=batch.id)
            .order_by(FinancialTransactionCandidate.id.asc())
            .all()
        )
        self.assertEqual(500, len(candidates))
        self.assertTrue(all(item.status == "ready" for item in candidates))
        request = FinancialImportConfirmRequest(
            expected_batch_version=batch.version,
            candidates=[
                {"candidate_id": item.id, "expected_version": item.version}
                for item in candidates
            ],
        )
        select_count = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(self.engine, "before_cursor_execute", count_selects)
        started = time.monotonic()
        try:
            report = confirm_candidates(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                data=request,
            )
        finally:
            elapsed = time.monotonic() - started
            event.remove(self.engine, "before_cursor_execute", count_selects)

        self.assertEqual(500, report["confirmed_count"])
        self.assertLessEqual(select_count, 12)
        self.assertLess(elapsed, 10.0)

    def test_editing_transaction_date_clears_stale_occurred_at(self):
        batch, candidate, _ = self._create_ready_income(external_id="date-edit-001")
        self.assertIsNotNone(candidate.occurred_at)

        updated, refreshed_batch = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                transaction_date=date(2026, 8, 2),
            ),
        )
        self.assertIsNone(updated.occurred_at)
        _, report = self._confirm_one(refreshed_batch, updated)
        transaction = self.db.get(FinancialTransaction, report["transaction_ids"][0])
        self.assertEqual(date(2026, 8, 2), transaction.transaction_date)
        self.assertIsNone(transaction.occurred_at)

    def test_date_only_import_keeps_formal_occurrence_unknown(self):
        content = _wechat_csv(
            _income_row(
                external_id="date-only-001",
                transaction_date="2026-08-01",
            )
        )
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="仅日期账单.csv",
            content=content,
            source_hint="auto",
        )
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()

        self.assertEqual(date(2026, 8, 1), candidate.transaction_date)
        self.assertIsNone(candidate.occurred_at)
        _, report = self._confirm_one(batch, candidate)
        transaction = self.db.get(FinancialTransaction, report["transaction_ids"][0])
        self.assertEqual(date(2026, 8, 1), transaction.transaction_date)
        self.assertIsNone(transaction.occurred_at)

    def test_same_date_edit_preserves_precise_occurred_at(self):
        batch, candidate, _ = self._create_ready_income(external_id="same-date-edit-001")
        original_occurred_at = candidate.occurred_at

        updated, _ = update_candidate(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            candidate_id=candidate.id,
            data=FinancialImportCandidateUpdate(
                expected_version=candidate.version,
                transaction_date=candidate.transaction_date,
                merchant="已核对公司财务",
            ),
        )

        self.assertEqual(original_occurred_at, updated.occurred_at)

    def test_generic_sample_rows_hide_sensitive_values_even_under_generic_headers(self):
        content = (
            "日期,方向,金额,备注\n"
            "2026-08-08,支出,12.00,联系138-0013-8000\n"
            "2026-08-09,支出,13.00,卡6222021234567890\n"
        ).encode("utf-8")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="泛化列隐私.csv",
            content=content,
            source_hint="generic",
        )

        samples = batch.parse_hints["sample_rows"]
        self.assertEqual("已隐藏", samples[0]["备注"])
        self.assertEqual("已隐藏", samples[1]["备注"])

    def test_sensitive_header_is_redacted_and_public_mapping_round_trips(self):
        raw_account = "6222021234567890"
        content = (
            f"发生日,收支标记,交易数额,账号{raw_account}\n"
            "2026-08-22,支出,12.00,午餐商户\n"
        ).encode("utf-8")
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="自定义账单.csv",
            content=content,
            source_hint="generic",
        )

        self.assertEqual("mapping_required", batch.status)
        public_header = next(
            header for header in batch.parse_hints["headers"] if "账号已隐藏" in header
        )
        self.assertNotIn(raw_account, repr(batch_payload(batch)))

        mapped = apply_mapping(
            self.db,
            user_id=self.user_id,
            batch_id=batch.id,
            expected_batch_version=batch.version,
            mapping={
                "transaction_date": "发生日",
                "direction": "收支标记",
                "amount": "交易数额",
                "merchant": public_header,
            },
        )

        self.assertEqual("review_ready", mapped.status)
        self.assertNotIn(raw_account, repr(batch_payload(mapped)))
        self.assertEqual(public_header, mapped.column_mapping["merchant"])
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=mapped.id,
        ).one()
        self.assertEqual("午餐商户", candidate.merchant)

    def test_attachment_flush_failure_removes_only_new_file(self):
        with patch.object(self.db, "flush", side_effect=RuntimeError("synthetic flush failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic flush failure"):
                save_personal_attachment(
                    self.db,
                    user_id=self.user_id,
                    document_type="cashflow_import",
                    logical_key="orphan-cleanup-test",
                    display_name="孤儿清理.csv",
                    original_filename="孤儿清理.csv",
                    content_type="text/csv",
                    content=b"private-test-content",
                    version_number=1,
                )
        self.db.rollback()

        remaining_files = [
            path
            for path in Path(self.upload_directory.name).rglob("*")
            if path.is_file()
        ]
        self.assertEqual([], remaining_files)

    def test_file_import_refresh_failure_keeps_committed_artifacts_only(self):
        with patch.object(self.db, "refresh", side_effect=RuntimeError("synthetic refresh failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic refresh failure"):
                create_file_import(
                    self.db,
                    user_id=self.user_id,
                    filename="已提交附件.csv",
                    content=_wechat_csv(_income_row(external_id="refresh-file-001")),
                    source_hint="auto",
                )

        batch = self.db.query(FinancialImportBatch).filter_by(user_id=self.user_id).one()
        self.assertIsNone(batch.attachment_version_id)
        self.assertEqual(
            2,
            self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id).count(),
        )
        self.assertEqual([], [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()])

    def test_file_import_ambiguous_commit_reconciles_artifacts_without_original(self):
        real_commit = self.db.commit

        def commit_then_lose_ack():
            real_commit()
            raise RuntimeError("synthetic lost commit acknowledgement")

        with patch.object(self.db, "commit", side_effect=commit_then_lose_ack):
            batch, reused = create_file_import(
                self.db,
                user_id=self.user_id,
                filename="提交结果不确定.csv",
                content=_wechat_csv(_income_row(external_id="ambiguous-file-001")),
                source_hint="auto",
            )

        self.assertFalse(reused)
        self.assertIsNone(batch.attachment_version_id)
        self.assertEqual(
            2,
            self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id).count(),
        )
        self.assertEqual([], [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()])
        self.assertEqual(1, self.db.query(FinancialImportBatch).count())

    def test_generated_import_refresh_failure_keeps_ocr_text_without_original(self):
        with patch.object(self.db, "refresh", side_effect=RuntimeError("synthetic refresh failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic refresh failure"):
                create_generated_import(
                    self.db,
                    user_id=self.user_id,
                    origin_type="ocr",
                    source_type="ocr_image",
                    content_hash="b" * 64,
                    parser_version="cashflow-ocr-test-v1",
                    parsed=[],
                    original_filename="已提交小票.png",
                    original_content_type="image/png",
                    original_file_size=len(b"synthetic-private-image"),
                    ocr_text="2026-08-22 午餐 32.00 元",
                )

        batch = self.db.query(FinancialImportBatch).filter_by(user_id=self.user_id).one()
        artifact = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="ocr_text",
        ).one()
        self.assertIsNone(batch.attachment_version_id)
        self.assertEqual("2026-08-22 午餐 32.00 元", artifact.content_text)
        self.assertEqual([], [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()])

    def test_generated_import_ambiguous_commit_reconciles_ocr_artifact(self):
        real_commit = self.db.commit

        def commit_then_lose_ack():
            real_commit()
            raise RuntimeError("synthetic lost commit acknowledgement")

        with patch.object(self.db, "commit", side_effect=commit_then_lose_ack):
            batch, reused = create_generated_import(
                self.db,
                user_id=self.user_id,
                origin_type="ocr",
                source_type="receipt",
                content_hash="c" * 64,
                parser_version="cashflow-ocr-ambiguous-v1",
                parsed=[],
                original_filename="提交结果不确定.png",
                original_content_type="image/png",
                original_file_size=len(b"synthetic-private-image"),
                ocr_text="2026-08-22 咖啡 28.00 元",
            )

        self.assertFalse(reused)
        self.assertIsNone(batch.attachment_version_id)
        self.assertEqual(
            "2026-08-22 咖啡 28.00 元",
            self.db.query(FinancialRecognitionArtifact).filter_by(
                batch_id=batch.id,
                artifact_type="ocr_text",
            ).one().content_text,
        )
        self.assertEqual([], [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()])
        self.assertEqual(1, self.db.query(FinancialImportBatch).count())

    def test_ocr_reupload_repairs_corrupt_text_artifact_without_original(self):
        batch, reused = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="receipt",
            content_hash="e" * 64,
            parser_version="cashflow-ocr-repair-v1",
            parsed=[],
            original_filename="待修复小票.png",
            original_content_type="image/png",
            original_file_size=128,
            ocr_text="2026-08-22 午餐 36.50 元",
        )
        self.assertFalse(reused)
        artifact = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="ocr_text",
        ).one()
        artifact.content_text = "已损坏"
        self.db.commit()

        repaired, reused = create_generated_import(
            self.db,
            user_id=self.user_id,
            origin_type="ocr",
            source_type="receipt",
            content_hash="e" * 64,
            parser_version="cashflow-ocr-repair-v1",
            parsed=[],
            original_filename="待修复小票.png",
            original_content_type="image/png",
            original_file_size=128,
            ocr_text="2026-08-22 午餐 36.50 元",
        )

        self.assertTrue(reused)
        self.assertEqual(batch.id, repaired.id)
        self.assertIsNone(repaired.attachment_version_id)
        self.assertEqual(
            "2026-08-22 午餐 36.50 元",
            self.db.query(FinancialRecognitionArtifact).filter_by(
                batch_id=batch.id,
                artifact_type="ocr_text",
            ).one().content_text,
        )
        self.assertEqual(0, self.db.query(PersonalAttachmentVersion).count())

    def test_private_attachment_creates_fresh_root_with_0700_directories_and_0600_file(self):
        fresh_root = (Path(self.upload_directory.name) / "fresh" / "uploads").resolve()
        settings.UPLOAD_DIR = str(fresh_root)
        attachment = save_personal_attachment(
            self.db,
            user_id=self.user_id,
            document_type="cashflow_import",
            logical_key="private-mode",
            display_name="私有账单",
            original_filename="private.csv",
            content_type="text/csv",
            content=b"private",
            version_number=1,
        )
        path = resolve_attachment_path(attachment)

        self.assertTrue(fresh_root.is_dir())
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        current = path.parent
        while current != fresh_root:
            self.assertEqual(0o700, current.stat().st_mode & 0o777)
            current = current.parent

    def test_orphan_scan_repairs_permissions_for_referenced_legacy_file(self):
        attachment = save_personal_attachment(
            self.db,
            user_id=self.user_id,
            document_type="cashflow_import",
            logical_key="legacy-mode",
            display_name="legacy",
            original_filename="legacy.csv",
            content_type="text/csv",
            content=b"legacy",
            version_number=1,
        )
        self.db.commit()
        path = resolve_attachment_path(attachment)
        path.chmod(0o644)
        path.parent.chmod(0o755)

        created = enqueue_orphaned_attachment_cleanup(self.db, grace_seconds=0)

        self.assertEqual([], created)
        self.assertEqual(0o600, path.stat().st_mode & 0o777)
        self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)

    def test_orphan_scan_hard_caps_and_resumes_without_rglob(self):
        orphan_directory = (
            Path(self.upload_directory.name)
            / "personal"
            / str(self.user_id)
            / "cashflow_import"
            / "orphan-page"
        )
        orphan_directory.mkdir(parents=True)
        expected_paths: set[str] = set()
        for index in range(205):
            path = orphan_directory / f"orphan-{index}.part"
            path.write_bytes(f"private-orphan-{index}".encode())
            expected_paths.add(path.relative_to(self.upload_directory.name).as_posix())

        scanner = _BoundedAttachmentTreeScanner()
        try:
            with patch.object(Path, "rglob", side_effect=AssertionError("unbounded rglob")):
                first_created = enqueue_orphaned_attachment_cleanup(
                    self.db,
                    grace_seconds=0,
                    limit=999,
                    scanner=scanner,
                )
                second_created = enqueue_orphaned_attachment_cleanup(
                    self.db,
                    grace_seconds=0,
                    limit=999,
                    scanner=scanner,
                )
                third_created = enqueue_orphaned_attachment_cleanup(
                    self.db,
                    grace_seconds=0,
                    limit=999,
                    scanner=scanner,
                )
        finally:
            scanner.close()

        jobs = self.db.query(PersonalAttachmentCleanupJob).order_by(
            PersonalAttachmentCleanupJob.id.asc(),
        ).all()
        self.assertEqual(200, len(first_created))
        self.assertEqual(5, len(second_created))
        self.assertEqual([], third_created)
        self.assertEqual(205, len(jobs))
        self.assertEqual(expected_paths, {job.storage_path for job in jobs})
        self.assertTrue(all(job.status == "pending" for job in jobs))

    def test_orphan_scan_skips_symlinked_personal_root(self):
        outside_directory = Path(self.upload_directory.name).parent / (
            f"cashflow-import-outside-{time.time_ns()}"
        )
        outside_directory.mkdir()
        outside_file = outside_directory / "must-not-touch.csv"
        outside_file.write_bytes(b"outside-private-file")
        outside_file.chmod(0o644)
        personal_root = Path(self.upload_directory.name) / "personal"
        personal_root.symlink_to(outside_directory, target_is_directory=True)
        try:
            created = enqueue_orphaned_attachment_cleanup(
                self.db,
                grace_seconds=0,
            )
            self.assertEqual([], created)
            self.assertEqual(0o644, outside_file.stat().st_mode & 0o777)
            self.assertEqual(0, self.db.query(PersonalAttachmentCleanupJob).count())
        finally:
            personal_root.unlink(missing_ok=True)
            outside_file.unlink(missing_ok=True)
            outside_directory.rmdir()

    def test_orphan_cleanup_race_recognizes_only_storage_path_constraint(self):
        mysql_race = IntegrityError(
            "INSERT",
            {},
            Exception(
                1062,
                "Duplicate entry for key 'uq_attachment_cleanup_storage_path'",
            ),
        )
        sqlite_race = IntegrityError(
            "INSERT",
            {},
            Exception(
                "UNIQUE constraint failed: "
                "personal_attachment_cleanup_jobs.storage_path"
            ),
        )
        unrelated = IntegrityError(
            "INSERT",
            {},
            Exception("Duplicate entry for key 'some_other_constraint'"),
        )
        not_null_failure = IntegrityError(
            "INSERT",
            {},
            Exception(
                "NOT NULL constraint failed: "
                "personal_attachment_cleanup_jobs.storage_path"
            ),
        )

        self.assertTrue(_is_cleanup_path_conflict(mysql_race))
        self.assertTrue(_is_cleanup_path_conflict(sqlite_race))
        self.assertFalse(_is_cleanup_path_conflict(unrelated))
        self.assertFalse(_is_cleanup_path_conflict(not_null_failure))

    def test_pending_cleanup_is_claimed_before_many_older_failed_jobs(self):
        for index in range(50):
            self.db.add(PersonalAttachmentCleanupJob(
                user_id=self.user_id,
                storage_path=f"personal/{self.user_id}/failed/{index}",
                content_hash="0" * 64,
                status="failed",
                last_error="CleanupTargetNotFile",
            ))
        pending = PersonalAttachmentCleanupJob(
            user_id=self.user_id,
            storage_path=f"personal/{self.user_id}/pending/target",
            content_hash="1" * 64,
            status="pending",
        )
        self.db.add(pending)
        self.db.commit()

        claimed = claim_attachment_cleanup_jobs(self.db, limit=50)

        self.assertIn(pending.id, claimed)

    def test_reupload_repairs_missing_recognition_artifacts_before_mapping(self):
        content = (
            "流水日,数额,流向值\n"
            "2026/08/08,42.50,支出\n"
        ).encode()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="repair.csv",
            content=content,
            source_hint="generic",
        )
        self.db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.batch_id == batch.id,
            FinancialRecognitionArtifact.artifact_type == "normalized_rows",
        ).delete(synchronize_session=False)
        self.db.commit()

        repaired, reused = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="repair.csv",
            content=content,
            source_hint="generic",
        )

        self.assertTrue(reused)
        self.assertIsNone(repaired.attachment_version_id)
        self.assertEqual(
            2,
            self.db.query(FinancialRecognitionArtifact).filter_by(
                batch_id=repaired.id,
            ).count(),
        )
        self.assertEqual(0, self.db.query(PersonalAttachmentVersion).count())
        self.assertEqual([], [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()])
        mapped = apply_mapping(
            self.db,
            user_id=self.user_id,
            batch_id=repaired.id,
            expected_batch_version=repaired.version,
            mapping={
                "transaction_date": "流水日",
                "amount": "数额",
                "direction": "流向值",
            },
        )
        self.assertEqual("review_ready", mapped.status)

    def test_mapping_rejects_corrupt_recognition_artifact(self):
        content = "流水日,数额,流向值\n2026/08/08,42.50,支出\n".encode()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="corrupt.csv",
            content=content,
            source_hint="generic",
        )
        artifact = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="normalized_rows",
        ).one()
        artifact.content_json = {"schema_version": 1, "rows": []}
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            apply_mapping(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                expected_batch_version=batch.version,
                mapping={
                    "transaction_date": "流水日",
                    "amount": "数额",
                    "direction": "流向值",
                },
            )
        self.assertEqual("cashflow_import_artifact_corrupt", raised.exception.detail["code"])

    def test_mapping_reports_missing_artifacts_as_recoverable_conflict(self):
        content = "流水日,数额,流向值\n2026/08/08,42.50,支出\n".encode()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="missing.csv",
            content=content,
            source_hint="generic",
        )
        self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
        ).delete(synchronize_session=False)
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            apply_mapping(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                expected_batch_version=batch.version,
                mapping={
                    "transaction_date": "流水日",
                    "amount": "数额",
                    "direction": "流向值",
                },
            )
        self.assertEqual(409, raised.exception.status_code)
        self.assertEqual(
            "cashflow_import_artifact_missing",
            raised.exception.detail["code"],
        )

    def test_mapping_never_reads_original_file_after_artifacts_exist(self):
        content = "流水日,数额,流向值\n2026/08/08,42.50,支出\n".encode()
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="unreadable.csv",
            content=content,
            source_hint="generic",
        )

        with patch.object(Path, "read_bytes", side_effect=AssertionError("original file must not be read")):
            mapped = apply_mapping(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                expected_batch_version=batch.version,
                mapping={
                    "transaction_date": "流水日",
                    "amount": "数额",
                    "direction": "流向值",
                },
            )
        self.assertEqual("review_ready", mapped.status)

    def test_confirmation_rechecks_containment_similar_siblings_in_selection(self):
        content = _wechat_csv(
            _expense_row(
                external_id="fuzzy-selection-a-001",
                merchant="星巴克",
                description="咖啡",
            ),
            _expense_row(
                external_id="fuzzy-selection-b-001",
                merchant="星 巴 克咖啡店",
                description="",
            ),
        )
        batch, _ = create_file_import(
            self.db,
            user_id=self.user_id,
            filename="fuzzy-selection.csv",
            content=content,
            source_hint="wechat",
        )
        candidates = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).order_by(FinancialTransactionCandidate.id).all()
        self.assertEqual(["ready", "possible_duplicate"], [item.status for item in candidates])

        # Simulate a stale/legacy preview that failed to expose the second-row
        # sibling warning. Confirmation must still refuse both formal writes.
        candidates[1].status = "ready"
        candidates[1].warnings = []
        candidates[1].evidence = {}
        self.db.commit()
        self.db.refresh(batch)
        for candidate in candidates:
            self.db.refresh(candidate)
        request = FinancialImportConfirmRequest(
            expected_batch_version=batch.version,
            candidates=[
                {"candidate_id": item.id, "expected_version": item.version}
                for item in candidates
            ],
        )
        with self.assertRaises(HTTPException) as raised:
            confirm_candidates(
                self.db,
                user_id=self.user_id,
                batch_id=batch.id,
                data=request,
            )
        self.assertEqual("cashflow_import_possible_duplicate", raised.exception.detail["code"])
        self.assertEqual(0, self.db.query(FinancialTransaction).count())


if __name__ == "__main__":
    unittest.main()
