from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base
from app.models.cashflow import FinancialCategory
from app.models.cashflow_import import (
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.services.cashflow_ai_intake_service import AIIntakeResult
from app.services.cashflow_import_parser import ParsedCandidate, build_candidate_fingerprint
from app.services.cashflow_import_service import import_error
from app.services.cashflow_long_image_service import (
    _detect_transaction_rows,
    _normalization_scale,
    create_image_sequence_ocr_batch,
    create_segmented_ocr_batch,
    process_ocr_slice,
    render_long_image_slices,
    render_sequence_image_slices,
    should_use_segmented_ocr,
)


@compiles(MEDIUMBLOB, "sqlite")
def _compile_mediumblob_for_sqlite(_type, _compiler, **_kwargs):
    return "BLOB"


def _png_stub(width: int, height: int, payload: bytes = b"") -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + payload
    )


def _rendered_slices() -> list[dict]:
    return [
        {
            "sequence_number": sequence,
            "content": f"private-derived-slice-{sequence}".encode(),
            "content_hash": hashlib.sha256(f"private-derived-slice-{sequence}".encode()).hexdigest(),
            "byte_size": len(f"private-derived-slice-{sequence}".encode()),
            "source_locator": {
                "source_pixel_top": (sequence - 1) * 1800,
                "source_pixel_bottom": sequence * 2200,
                "source_pixel_width": 1080,
                "source_pixel_height": 4200,
                "normalized_top": (sequence - 1) * 2080,
                "normalized_bottom": sequence * 2400,
                "normalized_width": 1440,
                "normalized_height": 2400,
                "overlap_pixels": 320 if sequence > 1 else 0,
            },
        }
        for sequence in (1, 2)
    ]


def _candidate(
    content_hash: str,
    *,
    confidence: float = 0.95,
    amount: Decimal = Decimal("36.50"),
    transaction_date: date | None = date(2026, 8, 21),
    merchant: str = "午饭商户",
    description: str = "工作午饭",
) -> ParsedCandidate:
    fingerprint = build_candidate_fingerprint(
        direction="expense",
        amount=amount,
        transaction_date=transaction_date,
        merchant=merchant,
        description=description,
    )
    return ParsedCandidate(
        row_number=1,
        direction="expense",
        amount=amount,
        currency="CNY",
        transaction_date=transaction_date,
        occurred_at=None,
        category_name="餐饮",
        merchant=merchant,
        description=description,
        nature="flexible",
        external_key=f"ocr:{content_hash[:24]}",
        fingerprint=fingerprint,
        original_payload={
            "amount": format(amount, "f"),
            "merchant": merchant,
            "transaction_date": transaction_date.isoformat() if transaction_date else "",
        },
        evidence={"confidence": confidence, "review_tier": "high", "evidence_quote": "午饭 36.50"},
        validation_errors=(
            []
            if transaction_date is not None
            else [{"field": "transaction_date", "code": "DATE_INVALID", "message": "请补充交易日期"}]
        ),
        warnings=[],
    )


class CashflowLongImageServiceTest(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory(prefix="cashflow-long-image-test-")
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
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(username="long-image-user", password_hash="test-only", is_active=True)
        self.db.add(self.user)
        self.db.flush()
        self.db.add(FinancialCategory(user_id=None, direction="expense", name="餐饮", is_system=True, is_active=True))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        settings.UPLOAD_DIR = self.original_upload_dir
        self.upload_directory.cleanup()

    def _create_batch(self, marker: bytes = b"first"):
        with patch(
            "app.services.cashflow_long_image_service.render_long_image_slices",
            return_value=_rendered_slices(),
        ):
            return create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=_png_stub(1080, 4200, marker),
                content_type="image/png",
                original_filename="微信支付长截图.png",
                expected_data_epoch=self.user.business_data_epoch,
            )

    def _success_result(self, content_hash: str) -> AIIntakeResult:
        return AIIntakeResult(
            parsed=[_candidate(content_hash)],
            parser_version="cashflow-candidate-v2:test:2026-08-23",
            content_hash=content_hash,
            provider_name="test-provider",
            model="test-model",
            ocr_text="2026-08-21 午饭商户 支出 36.50",
        )

    def test_real_renderer_creates_overlapping_png_slices(self):
        import fitz

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="390" height="3878"><rect width="390" height="3878" fill="white"/><text x="20" y="120" font-size="40">36.50</text></svg>'
        document = fitz.open(stream=svg, filetype="svg")
        png = document[0].get_pixmap(alpha=False).tobytes("png")
        document.close()
        parts = render_long_image_slices(
            png,
            detected_type="image/png",
            dimensions=(390, 3878),
        )
        self.assertEqual(3, len(parts))
        self.assertTrue(all(item["content"].startswith(b"\x89PNG") for item in parts))
        self.assertEqual(0, parts[0]["source_locator"]["normalized_top"])
        self.assertEqual(320, parts[1]["source_locator"]["overlap_pixels"])

    def test_program_detector_counts_aligned_wallet_transaction_icons(self):
        import fitz

        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="900">
          <rect width="400" height="900" fill="white"/>
          <rect x="10" y="20" width="180" height="32" fill="#1677ff"/>
          <circle cx="48" cy="180" r="24" fill="#07c160"/>
          <circle cx="48" cy="430" r="24" fill="#ff9f00"/>
          <circle cx="48" cy="680" r="24" fill="#1677ff"/>
        </svg>'''
        document = fitz.open(stream=svg, filetype="svg")
        pixmap = document[0].get_pixmap(colorspace=fitz.csRGB, alpha=False)
        result = _detect_transaction_rows(pixmap)
        document.close()

        self.assertTrue(result["reliable"])
        self.assertEqual(3, result["expected_transaction_rows"])
        self.assertEqual(3, len(result["row_centers"]))

    def test_program_detector_does_not_treat_single_coloured_logo_as_a_bill_row(self):
        import fitz

        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500">
          <rect width="400" height="500" fill="white"/>
          <circle cx="48" cy="100" r="24" fill="#07c160"/>
        </svg>'''
        document = fitz.open(stream=svg, filetype="svg")
        pixmap = document[0].get_pixmap(colorspace=fitz.csRGB, alpha=False)
        result = _detect_transaction_rows(pixmap)
        document.close()

        self.assertFalse(result["reliable"])
        self.assertIsNone(result["expected_transaction_rows"])

    def test_ultra_long_narrow_image_is_scaled_to_readable_slice_budget(self):
        scale = _normalization_scale(1080, 90_000)

        self.assertTrue(should_use_segmented_ocr((1080, 90_000)))
        self.assertGreaterEqual(1080 * scale, 960)
        self.assertLessEqual(round(90_000 * scale), 83_520)

        with self.assertRaises(HTTPException) as raised:
            _normalization_scale(1080, 120_000)
        self.assertEqual(
            "cashflow_vision_too_tall_for_readable_slices",
            raised.exception.detail["code"],
        )

    def test_sequence_renderer_splits_short_image_without_retaining_whole_original(self):
        import fitz

        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="white"/><text x="20" y="120" font-size="40">36.50</text></svg>'
        document = fitz.open(stream=svg, filetype="svg")
        png = document[0].get_pixmap(alpha=False).tobytes("png")
        document.close()
        parts = render_sequence_image_slices(
            png,
            detected_type="image/png",
            dimensions=(400, 500),
        )
        self.assertEqual(2, len(parts))
        self.assertLess(parts[0]["source_locator"]["source_pixel_bottom"], 500)
        self.assertGreater(parts[1]["source_locator"]["source_pixel_top"], 0)
        self.assertGreater(parts[1]["source_locator"]["overlap_pixels"], 0)

    def test_long_image_keeps_only_slices_and_processes_each_with_progress(self):
        batch, reused = self._create_batch()
        self.assertFalse(reused)
        self.assertIsNone(batch.attachment_version_id)
        self.assertEqual("processing", batch.status)
        self.assertEqual(2, batch.parse_hints["recognition_progress"]["pending_slices"])
        self.assertEqual(2, self.db.query(PersonalAttachmentVersion).filter_by(user_id=self.user.id).count())
        self.assertEqual(2, self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id, artifact_type="image_slice").count())

        def parse_slice(*, content_hash: str, **_kwargs):
            return self._success_result(content_hash)

        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 午饭商户 支出 36.50"),
            patch("app.services.cashflow_long_image_service.parse_ocr_text_intake", side_effect=parse_slice),
        ):
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            self.assertEqual(1, batch.parse_hints["recognition_progress"]["completed_slices"])
            self.assertEqual(1, batch.parse_hints["recognition_progress"]["pending_slices"])
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        progress = batch.parse_hints["recognition_progress"]
        self.assertEqual(2, progress["completed_slices"])
        self.assertEqual(0, progress["pending_slices"])
        self.assertEqual(0, progress["failed_slices"])
        self.assertEqual("review_ready", batch.status)
        self.assertTrue(progress["slices"][0]["ocr_text_fully_processed"])
        self.assertEqual(1, progress["slices"][0]["ocr_chunk_count"])
        candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).order_by(FinancialTransactionCandidate.row_number).all()
        self.assertEqual(1, len(candidates))
        self.assertEqual("ready", candidates[0].status)
        self.assertEqual([1, 2], [item["slice_sequence"] for item in candidates[0].evidence["source_slices"]])
        self.assertEqual("同一截图相邻片段的日期、金额、方向和交易文本完全一致", candidates[0].evidence["overlap_merge_reason"])
        self.assertEqual(2, self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id, artifact_type="ocr_text").count())
        stored_files = [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()]
        self.assertEqual(2, len(stored_files))

    def test_progress_exposes_possible_missing_transaction_rows(self):
        rendered = _rendered_slices()
        rendered[0]["source_locator"]["transaction_row_detection"] = {
            "version": "colored-icon-v1",
            "reliable": True,
            "expected_transaction_rows": 3,
            "row_centers": [200, 800, 1400],
        }
        with patch(
            "app.services.cashflow_long_image_service.render_long_image_slices",
            return_value=rendered,
        ):
            batch, _ = create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=_png_stub(1080, 4200, b"coverage-warning"),
                content_type="image/png",
                original_filename="微信支付长截图.png",
                expected_data_epoch=self.user.business_data_epoch,
            )

        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 午饭商户 支出 36.50"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=lambda *, content_hash, **_kwargs: self._success_result(content_hash),
            ),
        ):
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        first_slice = batch.parse_hints["recognition_progress"]["slices"][0]
        self.assertEqual(3, first_slice["expected_transaction_rows"])
        self.assertEqual(1, first_slice["recognized_candidate_count"])
        self.assertEqual(2, first_slice["missing_transaction_rows"])
        self.assertEqual("partial", first_slice["row_coverage_status"])

    def test_image_sequence_keeps_order_skips_identical_source_and_merges_cross_image_overlap(self):
        images = [
            {
                "content": _png_stub(1080, 2200, b"image-one"),
                "content_type": "image/png",
                "original_filename": "01.png",
            },
            {
                "content": _png_stub(1080, 2200, b"image-two"),
                "content_type": "image/png",
                "original_filename": "02.png",
            },
            {
                "content": _png_stub(1080, 2200, b"image-one"),
                "content_type": "image/png",
                "original_filename": "03-duplicate.png",
            },
        ]
        with patch(
            "app.services.cashflow_long_image_service.render_sequence_image_slices",
            return_value=_rendered_slices(),
        ):
            batch, reused = create_image_sequence_ocr_batch(
                self.db,
                user_id=self.user.id,
                images=images,
                expected_data_epoch=self.user.business_data_epoch,
            )

        self.assertFalse(reused)
        self.assertEqual("screenshot_sequence", batch.source_type)
        self.assertIsNone(batch.attachment_version_id)
        progress = batch.parse_hints["recognition_progress"]
        self.assertEqual("image_sequence", progress["mode"])
        self.assertEqual(3, progress["submitted_images"])
        self.assertEqual(2, progress["unique_images"])
        self.assertEqual(4, progress["total_slices"])
        self.assertEqual(3, progress["duplicate_images"][0]["image_sequence"])
        self.assertEqual(1, progress["duplicate_images"][0]["duplicate_of_image_sequence"])
        self.assertEqual(
            [1, 1, 2, 2],
            [item["source_image_sequence"] for item in progress["slices"]],
        )

        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 午饭商户 支出 36.50"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=lambda *, content_hash, **_kwargs: self._success_result(content_hash),
            ),
        ):
            for _ in range(4):
                batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).all()
        self.assertEqual(1, len(candidates))
        self.assertEqual(
            [1, 2, 3, 4],
            [item["slice_sequence"] for item in candidates[0].evidence["source_slices"]],
        )
        self.assertEqual(
            "相邻截图交界处的日期、金额、方向和交易文本完全一致",
            candidates[0].evidence["overlap_merge_reason"],
        )
        self.assertEqual(
            4,
            self.db.query(PersonalAttachmentVersion).filter_by(user_id=self.user.id).count(),
        )
        stored_files = [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()]
        self.assertEqual(4, len(stored_files))

    def test_next_image_missing_date_inherits_unique_adjacent_context_as_review_required(self):
        images = [
            {"content": _png_stub(1080, 2200, b"context-one"), "content_type": "image/png"},
            {"content": _png_stub(1080, 2200, b"context-two"), "content_type": "image/png"},
        ]
        with patch(
            "app.services.cashflow_long_image_service.render_sequence_image_slices",
            return_value=_rendered_slices(),
        ):
            batch, _ = create_image_sequence_ocr_batch(
                self.db,
                user_id=self.user.id,
                images=images,
                expected_data_epoch=self.user.business_data_epoch,
            )
        results = [
            self._success_result("slice-one"),
            AIIntakeResult(
                parsed=[_candidate("slice-two", amount=Decimal("18.00"), merchant="水果店")],
                parser_version="cashflow-candidate-v2:test:2026-08-23",
                content_hash="slice-two",
                provider_name="test-provider",
                model="test-model",
                ocr_text="2026-08-21 水果店 支出 18.00",
            ),
            AIIntakeResult(
                parsed=[
                    _candidate(
                        "slice-three",
                        amount=Decimal("25.00"),
                        transaction_date=None,
                        merchant="交通卡充值",
                        description="交通卡充值",
                    )
                ],
                parser_version="cashflow-candidate-v2:test:2026-08-23",
                content_hash="slice-three",
                provider_name="test-provider",
                model="test-model",
                ocr_text="交通卡充值 支出 25.00",
            ),
        ]
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch("app.services.cashflow_long_image_service.parse_ocr_text_intake", side_effect=results),
        ):
            for _ in range(3):
                batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        inherited = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=3001,
        ).one()
        self.assertEqual(date(2026, 8, 21), inherited.transaction_date)
        self.assertEqual("needs_review", inherited.status)
        self.assertEqual("DATE_CONTEXT_INHERITED", inherited.warnings[0]["code"])
        self.assertTrue(inherited.evidence["date_context_inherited"])
        self.assertEqual(2, inherited.evidence["date_context"]["source_slice_sequence"])
        self.assertEqual(1, inherited.evidence["date_context"]["source_image_sequence"])

    def test_multiple_dates_in_previous_slice_do_not_guess_missing_date(self):
        batch, _ = self._create_batch(marker=b"ambiguous-date-context")
        first_result = AIIntakeResult(
            parsed=[
                _candidate("first-a", amount=Decimal("10.00"), transaction_date=date(2026, 8, 20)),
                _candidate("first-b", amount=Decimal("11.00"), transaction_date=date(2026, 8, 21), merchant="便利店"),
            ],
            parser_version="cashflow-candidate-v2:test:2026-08-23",
            content_hash="first-multiple-dates",
            provider_name="test-provider",
            model="test-model",
            ocr_text="2026-08-20 / 2026-08-21",
        )
        second_result = AIIntakeResult(
            parsed=[_candidate("second-no-date", amount=Decimal("12.00"), transaction_date=None, merchant="药店")],
            parser_version="cashflow-candidate-v2:test:2026-08-23",
            content_hash="second-no-date",
            provider_name="test-provider",
            model="test-model",
            ocr_text="药店 支出 12.00",
        )
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=[first_result, second_result],
            ),
        ):
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        unresolved = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=2001,
        ).one()
        self.assertIsNone(unresolved.transaction_date)
        self.assertEqual("invalid", unresolved.status)
        self.assertFalse(unresolved.evidence.get("date_context_inherited", False))

    def test_ambiguous_cross_image_overlap_calls_existing_ai_and_still_requires_human(self):
        images = [
            {"content": _png_stub(1080, 2200, b"ai-overlap-one"), "content_type": "image/png"},
            {"content": _png_stub(1080, 2200, b"ai-overlap-two"), "content_type": "image/png"},
        ]
        with patch(
            "app.services.cashflow_long_image_service.render_sequence_image_slices",
            return_value=_rendered_slices(),
        ):
            batch, _ = create_image_sequence_ocr_batch(
                self.db,
                user_id=self.user.id,
                images=images,
                expected_data_epoch=self.user.business_data_epoch,
            )
        first = _candidate(
            "ai-overlap-first",
            merchant="星巴克",
            description="星巴克咖啡",
        )
        third = _candidate(
            "ai-overlap-third",
            merchant="星巴克微信支付",
            description="星巴克咖啡门店",
        )
        results = [
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="one", provider_name="test", model="test", ocr_text="one"),
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="two", provider_name="test", model="test", ocr_text="two"),
            AIIntakeResult(parsed=[third], parser_version="test", content_hash="three", provider_name="test", model="test", ocr_text="three"),
        ]

        def ai_reply(*_args, **_kwargs):
            self.assertFalse(self.db.in_transaction())
            return json.dumps(
                {
                    "assessments": [
                        {
                            "current_row_number": 3001,
                            "prior_candidate_id": 1,
                            "assessment": "likely_same",
                            "reason": "商户主体、日期和金额一致，文本只多了支付渠道",
                        }
                    ]
                },
                ensure_ascii=False,
            )

        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch("app.services.cashflow_long_image_service.parse_ocr_text_intake", side_effect=results),
            patch("app.services.payslip_intake_service._call_payslip_llm", side_effect=ai_reply) as ai_mock,
        ):
            for _ in range(3):
                batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        ai_mock.assert_called_once()
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=3001,
        ).one()
        self.assertEqual("possible_duplicate", candidate.status)
        self.assertEqual("CROSS_IMAGE_DUPLICATE_AI_REVIEW", candidate.warnings[0]["code"])
        assessment = candidate.evidence["cross_image_duplicate_assessments"][0]
        self.assertEqual("likely_same", assessment["assessment"])
        self.assertEqual("completed", assessment["ai_status"])
        self.assertIn("不会自动合并或入账", candidate.warnings[0]["message"])

    def test_unavailable_cross_image_ai_falls_back_to_manual_review(self):
        images = [
            {"content": _png_stub(1080, 2200, b"ai-unavailable-one"), "content_type": "image/png"},
            {"content": _png_stub(1080, 2200, b"ai-unavailable-two"), "content_type": "image/png"},
        ]
        with patch(
            "app.services.cashflow_long_image_service.render_sequence_image_slices",
            return_value=_rendered_slices(),
        ):
            batch, _ = create_image_sequence_ocr_batch(
                self.db,
                user_id=self.user.id,
                images=images,
                expected_data_epoch=self.user.business_data_epoch,
            )
        first = _candidate("unavailable-first", merchant="某便利店", description="某便利店支出")
        third = _candidate("unavailable-third", merchant="某便利店微信", description="某便利店支出交易")
        results = [
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="one", provider_name="test", model="test", ocr_text="one"),
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="two", provider_name="test", model="test", ocr_text="two"),
            AIIntakeResult(parsed=[third], parser_version="test", content_hash="three", provider_name="test", model="test", ocr_text="three"),
        ]
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch("app.services.cashflow_long_image_service.parse_ocr_text_intake", side_effect=results),
            patch("app.services.payslip_intake_service._call_payslip_llm", return_value=None),
        ):
            for _ in range(3):
                batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        candidate = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=3001,
        ).one()
        self.assertEqual("possible_duplicate", candidate.status)
        assessment = candidate.evidence["cross_image_duplicate_assessments"][0]
        self.assertEqual("uncertain", assessment["assessment"])
        self.assertEqual("unavailable", assessment["ai_status"])
        self.assertIn("需要人工核对", candidate.warnings[0]["message"])

    def test_failed_slice_is_preserved_and_can_be_retried(self):
        batch, _ = self._create_batch(marker=b"retry")
        with patch(
            "app.services.cashflow_long_image_service._local_ocr",
            side_effect=import_error(422, "cashflow_vision_ocr_failed", "该片段文字不清晰"),
        ):
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
        progress = batch.parse_hints["recognition_progress"]
        self.assertEqual(1, progress["failed_slices"])
        self.assertEqual(1, progress["pending_slices"])
        self.assertEqual("该片段文字不清晰", progress["slices"][0]["error_message"])

        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 午饭商户 支出 36.50"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=lambda *, content_hash, **_kwargs: self._success_result(content_hash),
            ),
        ):
            batch = process_ocr_slice(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                sequence_number=1,
                retry_failed=True,
            )
        progress = batch.parse_hints["recognition_progress"]
        self.assertEqual(0, progress["failed_slices"])
        self.assertEqual(1, progress["completed_slices"])
        self.assertEqual(1, progress["pending_slices"])


if __name__ == "__main__":
    unittest.main()
