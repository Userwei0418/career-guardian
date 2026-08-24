from __future__ import annotations

import tempfile
import unittest
import hashlib
import importlib
import json
import pkgutil
from dataclasses import replace
from datetime import date, datetime
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
import app.models as application_models
from app.models.cashflow import FinancialCategory, FinancialTransaction
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.models.user import User
from app.services.cashflow_ai_intake_service import AIIntakeResult, _program_parse_ocr_text
from app.services.cashflow_import_parser import ParsedCandidate, build_candidate_fingerprint
from app.services.cashflow_import_service import import_error
from app.services.cashflow_tencent_ocr_service import TencentOCRLine, TencentOCRResult
from app.services.cashflow_long_image_service import (
    ADAPTIVE_MIN_OVERLAP,
    LONG_IMAGE_PARSER_VERSION,
    MAX_IMAGE_SLICES,
    SLICE_HEIGHT,
    SLICE_OVERLAP,
    _apply_adaptive_overlap_bounds,
    _detect_transaction_rows,
    _horizontal_row_activity,
    _layout_ordered_tencent_lines,
    _locate_candidate_ocr_lines,
    _normalization_scale,
    _normalized_ocr_lines,
    _select_adaptive_overlap_bounds,
    _slice_ranges,
    apply_batch_review_resolutions,
    create_image_sequence_ocr_batch,
    create_segmented_ocr_batch,
    get_candidate_evidence_payload,
    get_ocr_slice_detail_payload,
    get_ocr_slice_image,
    process_ocr_slice,
    render_long_image_slices,
    render_sequence_image_slices,
    should_use_segmented_ocr,
)
from app.schemas.cashflow_import import (
    FinancialImportBatchReviewResolutionRequest,
    FinancialImportBatchReviewResolutionResponse,
    FinancialImportCandidateEvidenceResponse,
)


# Match application startup model registration so isolated SQLite DDL sees
# every referenced table (for example career_cases).
for _model_module in pkgutil.iter_modules(
    application_models.__path__,
    application_models.__name__ + ".",
):
    importlib.import_module(_model_module.name)


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
                "transaction_row_detection": {
                    "version": "colored-icon-v1",
                    "reliable": True,
                    "expected_transaction_rows": 1,
                    "row_centers": [2200 if sequence == 1 else 120],
                },
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
    occurred_at: datetime | None = None,
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
        occurred_at=occurred_at,
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
        evidence={
            "confidence": confidence,
            "review_tier": "high",
            "evidence_quote": f"{merchant} {format(amount, 'f')}",
        },
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
        self.original_tencent_ocr_enabled = settings.TENCENT_OCR_ENABLED
        settings.UPLOAD_DIR = self.upload_directory.name
        settings.TENCENT_OCR_ENABLED = False
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
        settings.TENCENT_OCR_ENABLED = self.original_tencent_ocr_enabled
        self.upload_directory.cleanup()

    def test_tencent_layout_keeps_amount_with_same_visual_transaction(self):
        def line(text: str, *, x: int, y: int, width: int = 200) -> TencentOCRLine:
            return TencentOCRLine(
                text=text,
                confidence=99.0,
                polygon=[
                    {"x": x, "y": y},
                    {"x": x + width, "y": y},
                    {"x": x + width, "y": y + 44},
                    {"x": x, "y": y + 44},
                ],
            )

        ordered = _layout_ordered_tencent_lines([
            line("-2157.00", x=900, y=760),
            line("19:02|尔海麦经典面片", x=200, y=602, width=420),
            line("-23.00", x=960, y=526),
            line("餐饮", x=200, y=531),
            line("8月19日星期三", x=40, y=95, width=300),
            line("出", x=636, y=97),
            line("3307.00", x=686, y=95),
            line("转账", x=200, y=761),
            line("11:45|转账-转给gorgeous lady...", x=200, y=825, width=500),
        ])
        texts = [item.text for item in ordered]
        self.assertEqual("8月19日星期三 出 3307.00", texts[0])
        self.assertEqual("餐饮 19:02|尔海麦经典面片 -23.00", texts[1])
        self.assertEqual("转账 11:45|转账-转给gorgeous lady... -2157.00", texts[2])

        parsed = _program_parse_ocr_text(
            "\n".join(texts),
            content_hash="layout-regression",
            reference_date=date(2026, 8, 24),
        )
        self.assertEqual(2, len(parsed.parsed))
        self.assertEqual((Decimal("23.00"), "尔海麦经典面片", "expense"), (
            parsed.parsed[0].amount,
            parsed.parsed[0].merchant,
            parsed.parsed[0].direction,
        ))
        self.assertEqual(datetime(2026, 8, 19, 19, 2), parsed.parsed[0].occurred_at)
        self.assertEqual((Decimal("2157.00"), "gorgeous lady...", "transfer"), (
            parsed.parsed[1].amount,
            parsed.parsed[1].merchant,
            parsed.parsed[1].direction,
        ))
        self.assertEqual(datetime(2026, 8, 19, 11, 45), parsed.parsed[1].occurred_at)

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

    def _add_category_review_candidate(
        self,
        batch,
        *,
        row_number: int,
        direction: str = "expense",
        merchant: str = "待分类商户",
        extra_warnings: list[dict] | None = None,
    ) -> FinancialTransactionCandidate:
        amount = Decimal(f"{row_number + 10}.00")
        transaction_date = date(2026, 8, 20)
        fingerprint = build_candidate_fingerprint(
            direction=direction,
            amount=amount,
            transaction_date=transaction_date,
            merchant=merchant,
            description=merchant,
        )
        candidate = FinancialTransactionCandidate(
            user_id=self.user.id,
            batch_id=batch.id,
            row_number=row_number,
            direction=direction,
            amount=amount,
            currency="CNY",
            transaction_date=transaction_date,
            category_id=None,
            category_name="购物" if direction == "expense" else "其他收入",
            merchant=merchant,
            description=merchant,
            nature="flexible" if direction == "expense" else None,
            status="needs_review",
            external_key=f"category-review:{batch.id}:{row_number}",
            fingerprint=fingerprint,
            original_payload={"merchant": merchant},
            evidence={
                "origin": "ocr",
                "source_validation_errors": [],
                "category_suggestion": {
                    "category_name": "购物" if direction == "expense" else "其他收入",
                    "source": "program_rule",
                    "reason": "测试分类建议",
                    "requires_confirmation": True,
                },
            },
            validation_errors=[],
            warnings=[
                {
                    "field": "category_id",
                    "code": "PROGRAM_CATEGORY_REVIEW_REQUIRED",
                    "message": "请确认分类",
                },
                *(extra_warnings or []),
            ],
        )
        self.db.add(candidate)
        return candidate

    def _success_result(self, content_hash: str) -> AIIntakeResult:
        return AIIntakeResult(
            parsed=[_candidate(content_hash, occurred_at=datetime(2026, 8, 21, 12, 30))],
            parser_version="cashflow-candidate-v2:test:2026-08-23",
            content_hash=content_hash,
            provider_name="test-provider",
            model="test-model",
            ocr_text="2026-08-21 12:30 午饭商户 支出 36.50",
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
        self.assertGreaterEqual(parts[1]["source_locator"]["overlap_pixels"], ADAPTIVE_MIN_OVERLAP)
        self.assertIn(
            parts[1]["source_locator"]["adaptive_top_boundary"]["method"],
            {"horizontal_whitespace", "fixed_overlap_fallback"},
        )

    def test_adaptive_overlap_moves_fixed_cuts_to_gaps_on_both_sides(self):
        band_top = 1900
        activity = [0.42] * 700
        for index in range(145, 176):
            activity[index] = 0.0
        for index in range(515, 546):
            activity[index] = 0.0

        selected = _select_adaptive_overlap_bounds(
            activity,
            band_top=band_top,
            nominal_start=2080,
            nominal_end=2400,
        )

        self.assertTrue(selected["detected"])
        self.assertTrue(selected["adapted"])
        self.assertLess(selected["start"], 2080)
        self.assertGreater(selected["end"], 2400)
        self.assertGreaterEqual(selected["end"] - selected["start"], ADAPTIVE_MIN_OVERLAP)

    def test_adaptive_overlap_without_safe_gap_keeps_fixed_coordinates(self):
        selected = _select_adaptive_overlap_bounds(
            [0.45] * 700,
            band_top=1900,
            nominal_start=2080,
            nominal_end=2400,
        )

        self.assertFalse(selected["detected"])
        self.assertEqual((2080, 2400), (selected["start"], selected["end"]))
        self.assertEqual("fixed_overlap_fallback", selected["method"])

    def test_adaptive_overlap_avoids_detail_gap_inside_transaction_row(self):
        band_top = 12_320
        activity = [0.42] * 640
        for start, end in (
            (0, 86),
            (214, 259),
            (267, 317),
            (445, 490),
            (498, 548),
        ):
            for index in range(start, end + 1):
                activity[index] = 0.0

        selected = _select_adaptive_overlap_bounds(
            activity,
            band_top=band_top,
            nominal_start=12_480,
            nominal_end=12_800,
            transaction_row_centers=[150, 381, 613],
        )

        self.assertTrue(selected["transaction_row_aware"])
        self.assertGreaterEqual(selected["minimum_row_clearance"], 80)
        # The first whitespace band is between the transaction title and its
        # merchant detail.  Move to the inter-record gap instead of clipping
        # the latter half of the row.
        self.assertGreaterEqual(selected["start"], 12_590)
        self.assertGreaterEqual(
            min(abs(selected["start"] - (band_top + center)) for center in (150, 381, 613)),
            selected["minimum_row_clearance"],
        )

    def test_synthetic_card_image_exposes_safe_horizontal_gaps(self):
        import fitz

        svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="700">
          <rect width="400" height="700" fill="white"/>
          <rect x="35" y="160" width="330" height="72" rx="8" fill="#38423f"/>
          <rect x="35" y="430" width="330" height="82" rx="8" fill="#38423f"/>
        </svg>'''
        document = fitz.open(stream=svg, filetype="svg")
        pixmap = document[0].get_pixmap(colorspace=fitz.csRGB, alpha=False)
        activity = _horizontal_row_activity(pixmap)
        document.close()

        selected = _select_adaptive_overlap_bounds(
            activity,
            band_top=0,
            nominal_start=200,
            nominal_end=470,
        )
        self.assertTrue(selected["detected"])
        self.assertNotEqual(200, selected["start"])
        self.assertNotEqual(470, selected["end"])
        self.assertLess(activity[selected["start"]], 0.08)
        self.assertLess(activity[selected["end"]], 0.08)

    def test_adaptive_ranges_preserve_first_last_and_maximum_slice_count(self):
        maximum_height = SLICE_HEIGHT + (MAX_IMAGE_SLICES - 1) * (
            SLICE_HEIGHT - SLICE_OVERLAP
        )
        nominal = _slice_ranges(maximum_height)
        selections = [
            {
                "start": nominal[index + 1][0],
                "end": nominal[index][1],
                "detected": True,
            }
            for index in range(len(nominal) - 1)
        ]
        adjusted = _apply_adaptive_overlap_bounds(
            nominal,
            selections,
            normalized_height=maximum_height,
        )

        self.assertEqual(MAX_IMAGE_SLICES, len(adjusted))
        self.assertEqual(0, adjusted[0][0])
        self.assertEqual(maximum_height, adjusted[-1][1])
        with self.assertRaises(HTTPException) as raised:
            _slice_ranges(maximum_height + SLICE_HEIGHT)
        self.assertEqual("cashflow_vision_too_many_slices", raised.exception.detail["code"])

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

    def test_v13_batch_supersedes_same_image_v12_and_then_reuses_v13(self):
        content = _png_stub(1080, 4200, b"adaptive-parser-version")
        content_hash = hashlib.sha256(content).hexdigest()
        old = FinancialImportBatch(
            user_id=self.user.id,
            origin_type="ocr",
            source_type="long_screenshot",
            attachment_version_id=None,
            original_filename="old-v12.png",
            content_type="image/png",
            file_size=len(content),
            content_hash=content_hash,
            parser_version="cashflow-long-image-v12",
            status="review_ready",
            column_mapping={},
            parse_hints={},
        )
        self.db.add(old)
        self.db.commit()
        self.db.refresh(old)

        with patch(
            "app.services.cashflow_long_image_service.render_long_image_slices",
            return_value=_rendered_slices(),
        ):
            created, reused = create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=content,
                content_type="image/png",
                original_filename="same-image.png",
                expected_data_epoch=self.user.business_data_epoch,
            )
            reused_batch, reused_again = create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=content,
                content_type="image/png",
                original_filename="same-image.png",
                expected_data_epoch=self.user.business_data_epoch,
            )

        self.assertFalse(reused)
        self.assertEqual(LONG_IMAGE_PARSER_VERSION, created.parser_version)
        self.assertEqual(old.id, created.parse_hints["supersedes_batch_id"])
        self.assertTrue(reused_again)
        self.assertEqual(created.id, reused_batch.id)
        self.assertNotEqual(old.id, reused_batch.id)

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
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 12:30 午饭商户 36.50"),
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
        self.assertEqual("同一截图相邻片段的日期、时间、金额、方向与商户核心一致，且原图区域明显重合", candidates[0].evidence["overlap_merge_reason"])
        self.assertEqual(2, self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id, artifact_type="ocr_text").count())
        stored_files = [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()]
        self.assertEqual(2, len(stored_files))

    def test_same_image_overlap_merges_core_merchant_with_category_prefix(self):
        batch, _ = self._create_batch(marker=b"merchant-core-overlap")
        occurred_at = datetime(2026, 8, 21, 12, 30)
        first = _candidate(
            "merchant-core-first",
            merchant="午饭商户",
            occurred_at=occurred_at,
        )
        second = _candidate(
            "merchant-core-second",
            merchant="餐饮·午饭商户",
            occurred_at=occurred_at,
        )
        results = [
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="first", provider_name="test", model="test", ocr_text=""),
            AIIntakeResult(parsed=[second], parser_version="test", content_hash="second", provider_name="test", model="test", ocr_text=""),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "2026-08-21 12:30 午饭商户 36.50",
                    "2026-08-21 12:30 餐饮·午饭商户 36.50",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).all()
        self.assertEqual(1, len(candidates))
        self.assertEqual([1, 2], [source["slice_sequence"] for source in candidates[0].evidence["source_slices"]])
        self.assertIn("原图区域明显重合", candidates[0].evidence["overlap_merge_reason"])

    def test_same_image_overlap_uses_quote_time_and_can_merge_into_exact_duplicate(self):
        batch, _ = self._create_batch(marker=b"quote-time-exact-duplicate")
        first = _candidate(
            "quote-time-first",
            merchant="收 -来自金鑫",
            description="收 -来自金鑫",
        )
        second = _candidate(
            "quote-time-second",
            merchant="收 -来自金鑫",
            description="收 -来自金鑫",
        )
        first.evidence["evidence_quote"] = "收转账 19:19|转账-来自金鑫 +200.00"
        second.evidence["evidence_quote"] = "收转账 19:19|转账-来自金鑫 +200.00"
        results = [
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="first", provider_name="test", model="test", ocr_text=""),
            AIIntakeResult(parsed=[second], parser_version="test", content_hash="second", provider_name="test", model="test", ocr_text=""),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "收转账 19:19|转账-来自金鑫 +200.00",
                    "收转账 19:19|转账-来自金鑫 +200.00",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            stored = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()
            stored.status = "exact_duplicate"
            self.db.commit()
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).all()
        self.assertEqual(1, len(candidates))
        self.assertEqual("exact_duplicate", candidates[0].status)
        self.assertEqual([1, 2], [source["slice_sequence"] for source in candidates[0].evidence["source_slices"]])

    def test_same_image_overlap_with_missing_time_or_conflicting_merchant_stays_for_review(self):
        cases = [
            {
                "marker": b"missing-overlap-time",
                "first": _candidate("missing-time-first", merchant="同一商户", occurred_at=None),
                "second": _candidate("missing-time-second", merchant="同一商户", occurred_at=None),
                "first_text": "2026-08-21 同一商户 36.50",
                "second_text": "2026-08-21 同一商户 36.50",
            },
            {
                "marker": b"conflicting-overlap-merchant",
                "first": _candidate("merchant-a", merchant="便利店甲", occurred_at=datetime(2026, 8, 21, 12, 30)),
                "second": _candidate("merchant-b", merchant="便利店乙", occurred_at=datetime(2026, 8, 21, 12, 30)),
                "first_text": "2026-08-21 12:30 便利店甲 36.50",
                "second_text": "2026-08-21 12:30 便利店乙 36.50",
            },
            {
                "marker": b"conflicting-overlap-time",
                "first": _candidate("time-a", merchant="同一商户", occurred_at=None),
                "second": _candidate("time-b", merchant="同一商户", occurred_at=None),
                "first_text": "2026-08-21 19:19 同一商户 36.50",
                "second_text": "2026-08-21 19:20 同一商户 36.50",
            },
        ]
        for index, case in enumerate(cases, start=1):
            with self.subTest(case=index):
                batch, _ = self._create_batch(marker=case["marker"])
                results = [
                    AIIntakeResult(parsed=[case["first"]], parser_version="test", content_hash=f"first-{index}", provider_name="test", model="test", ocr_text=""),
                    AIIntakeResult(parsed=[case["second"]], parser_version="test", content_hash=f"second-{index}", provider_name="test", model="test", ocr_text=""),
                ]
                with (
                    patch(
                        "app.services.cashflow_long_image_service._local_ocr",
                        side_effect=[case["first_text"], case["second_text"]],
                    ),
                    patch(
                        "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                        side_effect=results,
                    ),
                ):
                    process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
                    process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

                candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).order_by(FinancialTransactionCandidate.row_number).all()
                self.assertEqual(2, len(candidates))
                self.assertEqual("possible_duplicate", candidates[1].status)
                self.assertNotIn("overlap_merge_reason", candidates[0].evidence)

    def test_long_image_uses_tencent_text_coordinates_without_calling_local_ocr(self):
        batch, _ = self._create_batch(marker=b"tencent-cloud")
        cloud = TencentOCRResult(
            text="2026-08-21\n午饭商户 36.50",
            lines=[
                TencentOCRLine(
                    text="2026-08-21",
                    confidence=99.0,
                    polygon=[{"x": 20, "y": 40}, {"x": 400, "y": 40}, {"x": 400, "y": 80}, {"x": 20, "y": 80}],
                ),
                TencentOCRLine(
                    text="午饭商户 36.50",
                    confidence=98.0,
                    polygon=[{"x": 20, "y": 300}, {"x": 900, "y": 300}, {"x": 900, "y": 350}, {"x": 20, "y": 350}],
                ),
            ],
            request_id="test-request-id",
        )

        with (
            patch.object(settings, "TENCENT_OCR_ENABLED", True),
            patch.object(settings, "TENCENT_OCR_MAX_CALLS_PER_BATCH", 40),
            patch("app.services.cashflow_long_image_service.recognize_with_tencent_cloud", return_value=cloud),
            patch("app.services.cashflow_long_image_service._local_ocr") as local_ocr,
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=lambda *, content_hash, **_kwargs: self._success_result(content_hash),
            ),
        ):
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        local_ocr.assert_not_called()
        self.assertEqual("processing", batch.status)
        first_slice = batch.parse_hints["recognition_progress"]["slices"][0]
        image_artifact = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="image_slice",
            sequence_number=1,
        ).one()
        self.assertEqual("tencent-cloud", image_artifact.artifact_metadata["ocr_provider"])
        self.assertEqual("tencent-cloud", first_slice["ocr_provider"])
        self.assertEqual("test-request-id", image_artifact.artifact_metadata["ocr_request_id"])
        candidate = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).one()
        self.assertEqual("tencent_ocr_text_polygon", candidate.evidence["candidate_region"]["method"])
        self.assertEqual(2, candidate.evidence["ocr_line_index"])
        evidence_payload = get_candidate_evidence_payload(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            candidate_id=candidate.id,
        )
        validated = FinancialImportCandidateEvidenceResponse.model_validate(evidence_payload)
        self.assertEqual("ocr_text_line", validated.sources[0].region.precision)
        slice_detail = get_ocr_slice_detail_payload(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            sequence_number=1,
        )
        self.assertEqual("tencent-cloud", slice_detail["slice"]["ocr_provider"])
        self.assertEqual("2026-08-21\n午饭商户 36.50", slice_detail["ocr_text"])
        self.assertTrue(slice_detail["image_available"])
        slice_path, media_type, filename = get_ocr_slice_image(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            sequence_number=1,
        )
        self.assertTrue(slice_path.exists())
        self.assertEqual("image/png", media_type)
        self.assertIn("slice-1", filename)

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
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 12:30 午饭商户 36.50"),
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
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 12:30 午饭商户 36.50"),
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
            "相邻截图交界处的日期、时间、金额、方向和交易文本完全一致",
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
        self.assertEqual(1, inherited.evidence["date_context"]["source_slice_sequence"])
        self.assertEqual(2, inherited.evidence["date_context"]["propagated_through_slice_sequence"])
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

    def test_ordered_last_date_anchor_propagates_across_same_image_slice(self):
        batch, _ = self._create_batch(marker=b"ordered-date-tail")
        undated_second = _candidate(
            "ordered-second",
            amount=Decimal("12.00"),
            transaction_date=None,
            merchant="药店",
        )
        undated_second = replace(
            undated_second,
            evidence={
                **undated_second.evidence,
                "evidence_quote": "药店 12:34 12.00",
            },
        )
        first_result = AIIntakeResult(
            parsed=[
                _candidate(
                    "ordered-first-a",
                    amount=Decimal("10.00"),
                    transaction_date=date(2026, 8, 20),
                    merchant="早餐店",
                ),
                _candidate(
                    "ordered-first-b",
                    amount=Decimal("11.00"),
                    transaction_date=date(2026, 8, 21),
                    merchant="便利店",
                ),
            ],
            parser_version="test",
            content_hash="ordered-first",
            provider_name="test",
            model="test",
            ocr_text="",
        )
        second_result = AIIntakeResult(
            parsed=[undated_second],
            parser_version="test",
            content_hash="ordered-second",
            provider_name="test",
            model="test",
            ocr_text="",
        )
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "2026年8月20日\n早餐店 10.00\n2026年8月21日\n便利店 11.00",
                    "药店 12:34 12.00",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=[first_result, second_result],
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        inherited = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=2001,
        ).one()
        self.assertEqual(date(2026, 8, 21), inherited.transaction_date)
        self.assertEqual(datetime(2026, 8, 21, 12, 34), inherited.occurred_at)
        self.assertEqual("ready", inherited.status)
        self.assertFalse(any(
            issue["code"] == "DATE_CONTEXT_INHERITED"
            for issue in inherited.warnings
        ))
        second_slice = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="image_slice",
            sequence_number=2,
        ).one()
        self.assertEqual(
            "2026-08-21",
            second_slice.artifact_metadata["active_trailing_date_context"]["transaction_date"],
        )

    def test_empty_ocr_noise_lines_do_not_block_shared_date_for_multiple_rows(self):
        batch, _ = self._create_batch(marker=b"empty-normalized-lines")
        missing_rows = [
            _candidate(
                f"august-ten-{index}",
                amount=Decimal(f"{10 + index}.00"),
                transaction_date=None,
                merchant=f"交易{index}",
            )
            for index in range(1, 4)
        ]
        results = [
            AIIntakeResult(
                parsed=missing_rows,
                parser_version="test",
                content_hash="august-ten",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="following-empty",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月10日 星期一\n|\n交易1 11.00\n|\n交易2 12.00\n交易3 13.00",
                    "无新交易",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        rows = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
        self.assertEqual(
            [date(2026, 8, 10)] * 3,
            [row.transaction_date for row in rows],
        )
        resolution = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                inferred_year=2026,
            ),
        )
        self.assertEqual(3, resolution["year_updated_count"])
        self.assertEqual(0, resolution["remaining_review_count"])

    def test_batch_resolution_keeps_missing_category_and_other_questions_reviewable(self):
        batch, _ = self._create_batch(marker=b"missing-category-stays-yellow")
        candidate = _candidate(
            "missing-category",
            amount=Decimal("18.00"),
            transaction_date=date(2026, 8, 20),
            merchant="待分类商户",
        )
        candidate = ParsedCandidate(**{
            **candidate.__dict__,
            "category_name": "未识别分类",
            "warnings": [
                {
                    "field": "transaction_date",
                    "code": "PROGRAM_YEAR_INFERRED",
                    "message": "请确认年份",
                },
                {
                    "field": "currency",
                    "code": "PROGRAM_CURRENCY_INFERRED",
                    "message": "请确认币种",
                },
                {
                    "field": "merchant",
                    "code": "MERCHANT_REVIEW_REQUIRED",
                    "message": "请核对交易对方",
                },
            ],
        })
        results = [
            AIIntakeResult(
                parsed=[candidate],
                parser_version="test",
                content_hash="missing-category-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="missing-category-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月20日 星期四\n待分类商户 18.00",
                    "无新交易",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                inferred_year=2026,
                confirm_currency="CNY",
            ),
        )
        refreshed = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).one()
        self.assertEqual("needs_review", refreshed.status)
        self.assertEqual([], refreshed.validation_errors)
        warning_codes = {issue.get("code") for issue in refreshed.warnings}
        self.assertIn("CATEGORY_REVIEW_REQUIRED", warning_codes)
        self.assertIn("MERCHANT_REVIEW_REQUIRED", warning_codes)
        self.assertNotIn("CATEGORY_INVALID", warning_codes)
        self.assertEqual(1, report["remaining_review_count"])
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_batch_category_resolution_is_atomic_and_only_clears_category_questions(self):
        shopping = FinancialCategory(
            user_id=None,
            direction="expense",
            name="购物",
            is_system=True,
            is_active=True,
        )
        self.db.add(shopping)
        batch, _ = self._create_batch(marker=b"batch-category-resolution")
        first = self._add_category_review_candidate(batch, row_number=1, merchant="Apple")
        second = self._add_category_review_candidate(
            batch,
            row_number=2,
            merchant="美团平台商户",
            extra_warnings=[
                {
                    "field": "merchant",
                    "code": "MERCHANT_REVIEW_REQUIRED",
                    "message": "请核对交易对方",
                }
            ],
        )
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, first, second, shopping):
            self.db.refresh(row)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                category_resolutions=[
                    {
                        "category_id": shopping.id,
                        "candidates": [
                            {"candidate_id": first.id, "expected_version": first.version},
                            {"candidate_id": second.id, "expected_version": second.version},
                        ],
                    }
                ],
            ),
        )
        FinancialImportBatchReviewResolutionResponse.model_validate(report)

        self.db.refresh(first)
        self.db.refresh(second)
        self.assertEqual(2, report["category_updated_count"])
        self.assertEqual([first.id, second.id], report["applied_candidate_ids"])
        self.assertEqual((shopping.id, "购物", "ready"), (first.category_id, first.category_name, first.status))
        self.assertEqual((shopping.id, "购物", "needs_review"), (second.category_id, second.category_name, second.status))
        self.assertNotIn(
            "PROGRAM_CATEGORY_REVIEW_REQUIRED",
            {issue["code"] for issue in second.warnings},
        )
        self.assertIn("MERCHANT_REVIEW_REQUIRED", {issue["code"] for issue in second.warnings})
        self.assertEqual(
            shopping.id,
            first.evidence["category_suggestion"]["confirmed_category_id"],
        )
        self.assertIn("category_id", first.evidence["user_modified_fields"])
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_batch_unknown_merchant_resolution_is_explicit_and_does_not_write_ledger(self):
        dining = FinancialCategory(
            user_id=None,
            direction="expense",
            name="餐饮",
            is_system=True,
            is_active=True,
        )
        self.db.add(dining)
        self.db.flush()
        batch, _ = self._create_batch(marker=b"batch-confirm-unknown-merchant")
        candidate = self._add_category_review_candidate(
            batch,
            row_number=1,
            merchant="",
        )
        candidate.description = ""
        candidate.category_id = dining.id
        candidate.category_name = dining.name
        candidate.warnings = [
            {
                "field": "merchant",
                "code": "PROGRAM_MERCHANT_REVIEW",
                "message": "程序没有稳定识别交易对方",
            },
            {
                "field": "candidate",
                "code": "AI_REVIEW_REQUIRED",
                "message": "这是 AI 识别候选，请核对后再入账",
            },
            {
                "field": "candidate",
                "code": "AI_PROGRAM_ALIGNMENT_REVIEW",
                "message": "AI 无法和未知交易对方稳定对齐",
            },
        ]
        candidate.evidence = {
            **candidate.evidence,
            "merchant_resolution": "program_value_retained",
            "ai_alignment_review_required": True,
        }
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, candidate):
            self.db.refresh(row)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                confirm_unknown_merchant_candidates=[
                    {
                        "candidate_id": candidate.id,
                        "expected_version": candidate.version,
                    }
                ],
            ),
        )
        FinancialImportBatchReviewResolutionResponse.model_validate(report)

        self.db.refresh(candidate)
        self.assertEqual(1, report["unknown_merchant_confirmed_count"])
        self.assertEqual([candidate.id], report["applied_candidate_ids"])
        self.assertEqual("ready", candidate.status)
        self.assertEqual([], candidate.validation_errors)
        self.assertEqual([], candidate.warnings)
        self.assertEqual("", candidate.merchant)
        self.assertEqual("", candidate.description)
        self.assertEqual("confirmed_unknown", candidate.evidence["merchant_resolution"])
        self.assertTrue(candidate.evidence["merchant_resolution_confirmed_at"])
        self.assertFalse(candidate.evidence["ai_alignment_review_required"])
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_batch_unknown_merchant_resolution_does_not_swallow_other_questions(self):
        dining = FinancialCategory(
            user_id=None,
            direction="expense",
            name="餐饮",
            is_system=True,
            is_active=True,
        )
        self.db.add(dining)
        self.db.flush()
        batch, _ = self._create_batch(marker=b"batch-confirm-unknown-merchant-fail-closed")
        eligible = self._add_category_review_candidate(batch, row_number=1, merchant="")
        ineligible = self._add_category_review_candidate(batch, row_number=2, merchant="")
        for candidate in (eligible, ineligible):
            candidate.description = ""
            candidate.category_id = dining.id
            candidate.category_name = dining.name
            candidate.warnings = [
                {
                    "field": "merchant",
                    "code": "PROGRAM_MERCHANT_REVIEW",
                    "message": "请核对交易对方",
                }
            ]
        ineligible.warnings = [
            *ineligible.warnings,
            {
                "field": "fingerprint",
                "code": "POSSIBLE_DUPLICATE",
                "message": "仍需核对是否重复",
            },
        ]
        ineligible.status = "possible_duplicate"
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, eligible, ineligible):
            self.db.refresh(row)

        with self.assertRaises(HTTPException) as raised:
            apply_batch_review_resolutions(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                data=FinancialImportBatchReviewResolutionRequest(
                    expected_batch_version=batch.version,
                    confirm_unknown_merchant_candidates=[
                        {
                            "candidate_id": eligible.id,
                            "expected_version": eligible.version,
                        },
                        {
                            "candidate_id": ineligible.id,
                            "expected_version": ineligible.version,
                        },
                    ],
                ),
            )

        self.assertEqual(
            "cashflow_import_unknown_merchant_selection_changed",
            raised.exception.detail["code"],
        )
        self.db.refresh(eligible)
        self.db.refresh(ineligible)
        self.assertEqual("needs_review", eligible.status)
        self.assertEqual("possible_duplicate", ineligible.status)
        self.assertNotEqual(
            "confirmed_unknown",
            eligible.evidence.get("merchant_resolution"),
        )
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_batch_category_resolution_refreshes_duplicate_summary_after_recompute(self):
        shopping = FinancialCategory(
            user_id=None,
            direction="expense",
            name="购物",
            is_system=True,
            is_active=True,
        )
        self.db.add(shopping)
        batch, _ = self._create_batch(marker=b"batch-category-duplicate-counts")
        candidate = self._add_category_review_candidate(
            batch,
            row_number=1,
            merchant="Apple",
        )
        existing = FinancialTransaction(
            user_id=self.user.id,
            category_id=None,
            direction="expense",
            amount=Decimal("11.00"),
            currency="CNY",
            transaction_date=date(2026, 8, 20),
            merchant="Apple",
            description="Apple",
            nature="flexible",
            source_type="manual",
            external_key="category-duplicate-existing",
            status="confirmed",
        )
        self.db.add(existing)
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, candidate, shopping, existing):
            self.db.refresh(row)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                category_resolutions=[
                    {
                        "category_id": shopping.id,
                        "candidates": [
                            {
                                "candidate_id": candidate.id,
                                "expected_version": candidate.version,
                            }
                        ],
                    }
                ],
            ),
        )

        self.db.refresh(candidate)
        self.assertEqual("possible_duplicate", candidate.status)
        self.assertEqual(existing.id, candidate.duplicate_transaction_id)
        self.assertEqual(0, report["batch"]["review_count"])
        self.assertEqual(1, report["batch"]["possible_duplicate_count"])
        self.assertEqual(1, report["remaining_review_count"])
        self.assertEqual(
            {"POSSIBLE_DUPLICATE"},
            {issue["code"] for issue in candidate.warnings},
        )

    def test_batch_category_resolution_rejects_stale_candidate_without_partial_update(self):
        shopping = FinancialCategory(
            user_id=None,
            direction="expense",
            name="购物",
            is_system=True,
            is_active=True,
        )
        self.db.add(shopping)
        batch, _ = self._create_batch(marker=b"batch-category-stale")
        first = self._add_category_review_candidate(batch, row_number=1)
        second = self._add_category_review_candidate(batch, row_number=2)
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, first, second, shopping):
            self.db.refresh(row)

        with self.assertRaises(HTTPException) as raised:
            apply_batch_review_resolutions(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                data=FinancialImportBatchReviewResolutionRequest(
                    expected_batch_version=batch.version,
                    category_resolutions=[
                        {
                            "category_id": shopping.id,
                            "candidates": [
                                {"candidate_id": first.id, "expected_version": first.version},
                                {"candidate_id": second.id, "expected_version": second.version + 1},
                            ],
                        }
                    ],
                ),
            )

        self.assertEqual("cashflow_import_stale_candidate", raised.exception.detail["code"])
        self.db.refresh(first)
        self.db.refresh(second)
        self.assertIsNone(first.category_id)
        self.assertIsNone(second.category_id)
        self.assertEqual("needs_review", first.status)
        self.assertEqual("needs_review", second.status)

    def test_batch_category_resolution_rejects_mixed_directions(self):
        shopping = FinancialCategory(
            user_id=None,
            direction="expense",
            name="购物",
            is_system=True,
            is_active=True,
        )
        self.db.add(shopping)
        batch, _ = self._create_batch(marker=b"batch-category-direction")
        expense = self._add_category_review_candidate(batch, row_number=1, direction="expense")
        income = self._add_category_review_candidate(batch, row_number=2, direction="income")
        batch.status = "review_ready"
        self.db.commit()
        for row in (batch, expense, income, shopping):
            self.db.refresh(row)

        with self.assertRaises(HTTPException) as raised:
            apply_batch_review_resolutions(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                data=FinancialImportBatchReviewResolutionRequest(
                    expected_batch_version=batch.version,
                    category_resolutions=[
                        {
                            "category_id": shopping.id,
                            "candidates": [
                                {"candidate_id": expense.id, "expected_version": expense.version},
                                {"candidate_id": income.id, "expected_version": income.version},
                            ],
                        }
                    ],
                ),
            )

        self.assertEqual("cashflow_import_category_direction_mismatch", raised.exception.detail["code"])

    def test_batch_category_resolution_schema_rejects_candidate_in_multiple_groups(self):
        with self.assertRaises(ValueError):
            FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=1,
                category_resolutions=[
                    {
                        "category_id": 10,
                        "candidates": [{"candidate_id": 7, "expected_version": 1}],
                    },
                    {
                        "category_id": 11,
                        "candidates": [{"candidate_id": 7, "expected_version": 1}],
                    },
                ],
            )

    def test_batch_resolution_preserves_manual_duplicate_decision_until_fingerprint_changes(self):
        batch, _ = self._create_batch(marker=b"preserve-manual-duplicate-review")
        candidate = _candidate(
            "manual-duplicate-review",
            amount=Decimal("28.00"),
            transaction_date=date(2026, 8, 20),
            merchant="人工已核对商户",
        )
        candidate = ParsedCandidate(**{
            **candidate.__dict__,
            "warnings": [
                {
                    "field": "currency",
                    "code": "PROGRAM_CURRENCY_INFERRED",
                    "message": "请确认币种",
                }
            ],
        })
        results = [
            AIIntakeResult(
                parsed=[candidate],
                parser_version="test",
                content_hash="manual-review-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="manual-review-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月20日 星期四\n人工已核对商户 28.00",
                    "无新交易",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        row = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).one()
        original_fingerprint = row.fingerprint
        evidence = dict(row.evidence or {})
        evidence.update(
            {
                "review_accepted_at": "2026-08-24T12:00:00",
                "duplicate_review_fingerprint": original_fingerprint,
                "duplicate_review_transaction_ids": [991],
                "possible_duplicate_transaction_ids": [991],
                "duplicate_override_at": "2026-08-24T12:00:00",
                "duplicate_override_reason": "用户确认这是另一笔真实交易",
                "duplicate_override_transaction_ids": [991],
                "duplicate_override_original_external_key_hash": "a" * 64,
                "economic_fact_merge": {
                    "target_transaction_id": 991,
                    "target_fact_id": 992,
                    "candidate_fingerprint": original_fingerprint,
                    "reviewed_at": "2026-08-24T12:00:00",
                },
            }
        )
        row.evidence = evidence
        self.db.commit()

        currency_only = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                confirm_currency="CNY",
            ),
        )
        self.db.refresh(row)
        self.assertEqual(1, currency_only["currency_confirmed_count"])
        self.assertEqual(original_fingerprint, row.fingerprint)
        self.assertEqual("2026-08-24T12:00:00", row.evidence["review_accepted_at"])
        self.assertEqual(991, row.evidence["economic_fact_merge"]["target_transaction_id"])
        self.assertEqual([991], row.evidence["duplicate_review_transaction_ids"])
        self.assertEqual("2026-08-24T12:00:00", row.evidence["duplicate_override_at"])

        row.warnings = [
            {
                "field": "transaction_date",
                "code": "PROGRAM_YEAR_INFERRED",
                "message": "请确认年份",
            }
        ]
        changed_evidence = dict(row.evidence or {})
        changed_evidence["date_year_inference"] = {
            "month": 8,
            "day": 20,
            "proposed_year": 2026,
            "status": "pending",
            "source_has_explicit_year": False,
        }
        row.evidence = changed_evidence
        row.status = "needs_review"
        self.db.commit()
        current = self.db.query(type(batch)).filter_by(id=batch.id).one()

        same_year = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=current.version,
                inferred_year=2026,
            ),
        )
        self.db.refresh(row)
        self.assertEqual(1, same_year["year_updated_count"])
        self.assertEqual(date(2026, 8, 20), row.transaction_date)
        self.assertEqual(original_fingerprint, row.fingerprint)
        self.assertIn("review_accepted_at", row.evidence)
        self.assertIn("economic_fact_merge", row.evidence)
        self.assertIn("duplicate_override_at", row.evidence)

        row.warnings = [
            {
                "field": "transaction_date",
                "code": "PROGRAM_YEAR_INFERRED",
                "message": "请确认年份",
            }
        ]
        changed_evidence = dict(row.evidence or {})
        changed_evidence["date_year_inference"] = {
            "month": 8,
            "day": 20,
            "proposed_year": 2026,
            "status": "pending",
            "source_has_explicit_year": False,
        }
        row.evidence = changed_evidence
        row.status = "needs_review"
        self.db.commit()
        current = self.db.query(type(batch)).filter_by(id=batch.id).one()

        changed_year = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=current.version,
                inferred_year=2025,
            ),
        )
        self.db.refresh(row)
        self.assertEqual(1, changed_year["year_updated_count"])
        self.assertEqual(date(2025, 8, 20), row.transaction_date)
        self.assertNotEqual(original_fingerprint, row.fingerprint)
        self.assertNotIn("review_accepted_at", row.evidence)
        self.assertNotIn("economic_fact_merge", row.evidence)
        self.assertNotIn("duplicate_review_fingerprint", row.evidence)
        self.assertNotIn("duplicate_override_at", row.evidence)
        self.assertNotIn("duplicate_override_reason", row.evidence)
        self.assertNotIn("duplicate_override_transaction_ids", row.evidence)
        self.assertNotIn("duplicate_override_original_external_key_hash", row.evidence)
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_batch_resolution_clears_stale_duplicate_scan_without_manual_decision(self):
        batch, _ = self._create_batch(marker=b"clear-stale-duplicate-scan")
        candidate = _candidate(
            "stale-duplicate-scan",
            amount=Decimal("19.00"),
            transaction_date=date(2026, 8, 20),
            merchant="无人工决定商户",
        )
        candidate = ParsedCandidate(**{
            **candidate.__dict__,
            "warnings": [
                {
                    "field": "currency",
                    "code": "PROGRAM_CURRENCY_INFERRED",
                    "message": "请确认币种",
                }
            ],
        })
        results = [
            AIIntakeResult(
                parsed=[candidate],
                parser_version="test",
                content_hash="stale-scan-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="stale-scan-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        row = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).one()
        evidence = dict(row.evidence or {})
        evidence.update(
            {
                "possible_duplicate_transaction_ids": [881],
                "possible_duplicate_fact_targets": [
                    {"transaction_id": 881, "fact_id": 882}
                ],
                "possible_duplicate_candidate_ids": [883],
                "possible_duplicate_bucket_watermark": {
                    "scan_mode": "bounded_coarse_bucket",
                    "count": 3,
                    "max_transaction_id": 881,
                },
                "formal_duplicate_ai_review": {"status": "completed"},
                "candidate_duplicate_ai_review": {"status": "completed"},
            }
        )
        row.evidence = evidence
        self.db.commit()

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                confirm_currency="CNY",
            ),
        )
        self.db.refresh(row)
        self.assertEqual(1, report["currency_confirmed_count"])
        self.assertEqual("ready", row.status)
        for key in (
            "possible_duplicate_transaction_ids",
            "possible_duplicate_fact_targets",
            "possible_duplicate_candidate_ids",
            "possible_duplicate_bucket_watermark",
            "formal_duplicate_ai_review",
            "candidate_duplicate_ai_review",
        ):
            self.assertNotIn(key, row.evidence)
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_candidate_above_new_bottom_date_heading_keeps_previous_group(self):
        batch, _ = self._create_batch(marker=b"bottom-date-heading")
        results = [
            AIIntakeResult(
                parsed=[_candidate("previous", amount=Decimal("10.00"), merchant="上一组")],
                parser_version="test",
                content_hash="previous",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[
                    ParsedCandidate(**{
                        **_candidate(
                            "above-heading",
                            amount=Decimal("12.00"),
                            transaction_date=None,
                            merchant="标题上方交易",
                        ).__dict__,
                        "evidence": {
                            "confidence": 0.95,
                            "review_tier": "high",
                            "evidence_quote": "标题上方交易 12.00",
                            "ocr_line_index": 1,
                        },
                    }),
                    ParsedCandidate(**{
                        **_candidate(
                            "below-heading",
                            amount=Decimal("13.00"),
                            transaction_date=date(2026, 8, 20),
                            merchant="标题下方交易",
                        ).__dict__,
                        "evidence": {
                            "confidence": 0.95,
                            "review_tier": "high",
                            "evidence_quote": "标题下方交易 13.00",
                            "ocr_line_index": 3,
                        },
                    }),
                ],
                parser_version="test",
                content_hash="current",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "2026年8月21日\n\n上一组 10.00",
                    "标题上方交易 12.00\n\n2026年8月20日\n\n标题下方交易 13.00",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        rows = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
        by_merchant = {row.merchant: row for row in rows}
        self.assertEqual(date(2026, 8, 21), by_merchant["标题上方交易"].transaction_date)
        self.assertEqual(date(2026, 8, 20), by_merchant["标题下方交易"].transaction_date)

    def test_closed_repeated_quote_group_uses_stable_order_across_date_heading(self):
        rendered = _rendered_slices()
        rendered[1]["source_locator"]["transaction_row_detection"] = {
            "version": "colored-icon-v1",
            "reliable": True,
            "expected_transaction_rows": 2,
            "row_centers": [240, 960],
        }
        with patch(
            "app.services.cashflow_long_image_service.render_long_image_slices",
            return_value=rendered,
        ):
            batch, _ = create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=_png_stub(1080, 4200, b"closed-repeated-quote"),
                content_type="image/png",
                original_filename="重复文本长截图.png",
                expected_data_epoch=self.user.business_data_epoch,
            )
        top = _candidate(
            "repeated-top",
            amount=Decimal("200.00"),
            transaction_date=None,
            merchant="发红包",
        )
        bottom = _candidate(
            "repeated-bottom",
            amount=Decimal("200.00"),
            transaction_date=None,
            merchant="发红包",
        )
        top = ParsedCandidate(**{
            **top.__dict__,
            "evidence": {**top.evidence, "detection_method": "program"},
        })
        bottom = ParsedCandidate(**{
            **bottom.__dict__,
            "evidence": {**bottom.evidence, "detection_method": "program"},
        })
        results = [
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="previous-date-only",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[top, bottom],
                parser_version="test",
                content_hash="repeated-rows",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月12日 星期三",
                    "发红包 200.00\n8月10日 星期一\n发红包 200.00",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        rows = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
        self.assertEqual(
            [date(2026, 8, 12), date(2026, 8, 10)],
            [row.transaction_date for row in rows],
        )
        regions = [
            get_candidate_evidence_payload(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                candidate_id=row.id,
            )["sources"][0]["region"]
            for row in rows
        ]
        self.assertTrue(all(
            region["method"] == "transaction_icon_row_alignment"
            for region in regions
        ))
        self.assertLess(regions[0]["top"], regions[1]["top"])

    def test_repeated_quote_group_rejects_mixed_detection_or_duplicate_order(self):
        first = _candidate("mixed-first", amount=Decimal("20.00"), merchant="同文案")
        second = _candidate("mixed-second", amount=Decimal("20.00"), merchant="同文案")
        lines = _normalized_ocr_lines("同文案 20.00\n8月10日 星期一\n同文案 20.00")

        mixed = [
            ParsedCandidate(**{
                **first.__dict__,
                "evidence": {
                    **first.evidence,
                    "detection_method": "program",
                    "slice_candidate_index": 1,
                },
            }),
            ParsedCandidate(**{
                **second.__dict__,
                "evidence": {
                    **second.evidence,
                    "detection_method": "program_ai",
                    "slice_candidate_index": 2,
                },
            }),
        ]
        self.assertEqual(
            [(None, "unlocated"), (None, "unlocated")],
            _locate_candidate_ocr_lines(mixed, lines=lines),
        )

        duplicate_order = [
            ParsedCandidate(**{
                **candidate.__dict__,
                "evidence": {
                    **candidate.evidence,
                    "detection_method": "program",
                    "slice_candidate_index": 1,
                },
            })
            for candidate in (first, second)
        ]
        self.assertEqual(
            [(None, "unlocated"), (None, "unlocated")],
            _locate_candidate_ocr_lines(duplicate_order, lines=lines),
        )

    def test_existing_batch_date_repair_and_batch_resolutions_are_atomic(self):
        batch, _ = self._create_batch(marker=b"existing-repair")
        first_result = AIIntakeResult(
            parsed=[
                _candidate("repair-a", amount=Decimal("10.00"), transaction_date=date(2026, 8, 20), merchant="A店"),
                _candidate("repair-b", amount=Decimal("11.00"), transaction_date=date(2026, 8, 21), merchant="B店"),
            ],
            parser_version="test",
            content_hash="repair-first",
            provider_name="test",
            model="test",
            ocr_text="",
        )
        missing = _candidate(
            "repair-missing",
            amount=Decimal("12.00"),
            transaction_date=None,
            merchant="C店",
        )
        second_result = AIIntakeResult(
            parsed=[missing],
            parser_version="test",
            content_hash="repair-second",
            provider_name="test",
            model="test",
            ocr_text="",
        )
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=[first_result, second_result],
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
        unresolved = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=2001,
        ).one()
        self.assertIsNone(unresolved.transaction_date)

        ocr_rows = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="ocr_text",
        ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
        ocr_rows[0].content_text = "8月20日 星期四\nA店 10.00\n2026年8月21日\nB店 11.00"
        ocr_rows[1].content_text = "C店 12.00"
        self.db.commit()
        self.db.refresh(batch)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                repair_date_context=True,
            ),
        )
        self.assertEqual(1, report["date_context_repaired_count"])
        repaired = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=2001,
        ).one()
        self.assertEqual(date(2026, 8, 21), repaired.transaction_date)
        self.assertEqual("ready", repaired.status)
        self.assertEqual(0, self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count())

        stale_version = batch.version
        current_batch = report["batch"]
        inferred = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=1001,
        ).one()
        inferred.warnings = [
            {"field": "transaction_date", "code": "PROGRAM_YEAR_INFERRED", "message": "请确认年份"},
            {"field": "currency", "code": "PROGRAM_CURRENCY_INFERRED", "message": "请确认币种"},
        ]
        inferred.status = "needs_review"
        evidence = dict(inferred.evidence or {})
        evidence["date_year_inference"] = {
            "month": 8,
            "day": 20,
            "proposed_year": 2026,
            "status": "pending",
            "source_has_explicit_year": False,
        }
        inferred.evidence = evidence
        unknown_currency = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=1002,
        ).one()
        unknown_currency.currency = "UNK"
        unknown_currency.validation_errors = [
            {
                "field": "currency",
                "code": "CURRENCY_REQUIRED",
                "message": "程序无法确定人民币币种",
            }
        ]
        unknown_currency.status = "invalid"
        unknown_evidence = dict(unknown_currency.evidence or {})
        unknown_evidence["source_validation_errors"] = list(
            unknown_currency.validation_errors
        )
        unknown_currency.evidence = unknown_evidence
        current_model = self.db.query(type(batch)).filter_by(id=batch.id).one()
        current_model.updated_at = current_model.updated_at
        self.db.flush()
        from app.services.cashflow_import_service import refresh_batch_counts
        refresh_batch_counts(self.db, current_model)
        self.db.commit()
        self.db.refresh(current_model)

        resolution = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=current_model.version,
                inferred_year=2026,
                confirm_currency="CNY",
            ),
        )
        self.assertEqual(1, resolution["year_updated_count"])
        self.assertEqual(2, resolution["currency_confirmed_count"])
        self.assertEqual(0, resolution["remaining_review_count"])
        self.assertTrue(all(row.status == "ready" for row in resolution["candidates"]))
        self.assertEqual("CNY", unknown_currency.currency)
        self.assertEqual(0, self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count())
        with self.assertRaises(HTTPException) as raised:
            apply_batch_review_resolutions(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                data=FinancialImportBatchReviewResolutionRequest(
                    expected_batch_version=stale_version,
                    inferred_year=2026,
                ),
            )
        self.assertEqual("cashflow_import_stale_batch", raised.exception.detail["code"])

    def test_year_only_does_not_fill_missing_date_until_date_repair_is_selected(self):
        batch, _ = self._create_batch(marker=b"year-only-date-isolation")
        inferred = _candidate(
            "year-only-inferred",
            amount=Decimal("10.00"),
            transaction_date=date(2026, 8, 20),
            merchant="A店",
        )
        inferred = ParsedCandidate(**{
            **inferred.__dict__,
            "warnings": [
                {
                    "field": "transaction_date",
                    "code": "PROGRAM_YEAR_INFERRED",
                    "message": "请确认年份",
                }
            ],
        })
        other_date = _candidate(
            "year-only-other-date",
            amount=Decimal("11.00"),
            transaction_date=date(2026, 8, 21),
            merchant="C店",
        )
        missing = _candidate(
            "year-only-missing",
            amount=Decimal("12.00"),
            transaction_date=None,
            merchant="B店",
        )
        results = [
            AIIntakeResult(
                parsed=[other_date, inferred],
                parser_version="test",
                content_hash="year-only-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[missing],
                parser_version="test",
                content_hash="year-only-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="ocr text"),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        ocr_rows = self.db.query(FinancialRecognitionArtifact).filter_by(
            batch_id=batch.id,
            artifact_type="ocr_text",
        ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
        ocr_rows[0].content_text = (
            "2026年8月21日\nC店 11.00\n8月20日 星期四\nA店 10.00"
        )
        ocr_rows[1].content_text = "B店 12.00"
        self.db.commit()
        current = self.db.query(type(batch)).filter_by(id=batch.id).one()

        year_only = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=current.version,
                inferred_year=2026,
            ),
        )
        still_missing = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
            row_number=2001,
        ).one()
        self.assertEqual(1, year_only["year_updated_count"])
        self.assertEqual(0, year_only["date_context_repaired_count"])
        self.assertIsNone(still_missing.transaction_date)
        self.assertEqual("invalid", still_missing.status)

        current = self.db.query(type(batch)).filter_by(id=batch.id).one()
        repaired = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=current.version,
                inferred_year=2026,
                repair_date_context=True,
            ),
        )
        self.db.refresh(still_missing)
        self.assertEqual(1, repaired["date_context_repaired_count"])
        self.assertEqual(date(2026, 8, 20), still_missing.transaction_date)
        self.assertEqual("ready", still_missing.status)
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_old_decimal_date_guess_is_not_accepted_by_batch_year_resolution(self):
        batch, _ = self._create_batch(marker=b"unsafe-old-date-guess")
        corroborated = _candidate(
            "corroborated-duplicate-quote",
            amount=Decimal("24.90"),
            transaction_date=date(2026, 8, 10),
            merchant="餐饮",
        )
        unsafe = _candidate(
            "unsafe-january-seven",
            amount=Decimal("200.00"),
            transaction_date=date(2026, 1, 7),
            merchant="发红包",
        )
        year_warning = {
            "field": "transaction_date",
            "code": "PROGRAM_YEAR_INFERRED",
            "message": "请确认年份",
        }
        corroborated = ParsedCandidate(**{
            **corroborated.__dict__,
            "warnings": [year_warning],
        })
        unsafe = ParsedCandidate(**{
            **unsafe.__dict__,
            "warnings": [year_warning],
        })
        results = [
            AIIntakeResult(
                parsed=[corroborated, unsafe],
                parser_version="cashflow-ocr-rules-v3",
                content_hash="unsafe-old-date-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="cashflow-ocr-rules-v3",
                content_hash="unsafe-old-date-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月10日 星期一\n餐饮 24.90\n餐饮 24.90\n发红包 200.00\n发红包 200.00\n| ELLA ™“Z1.7U",
                    "8月8日 星期六",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        report = apply_batch_review_resolutions(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            data=FinancialImportBatchReviewResolutionRequest(
                expected_batch_version=batch.version,
                inferred_year=2026,
            ),
        )
        candidates = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).all()
        by_merchant = {candidate.merchant: candidate for candidate in candidates}
        self.assertEqual(1, report["year_updated_count"])
        self.assertEqual(0, report["date_context_repaired_count"])
        self.assertEqual(1, report["remaining_review_count"])
        self.assertEqual(date(2026, 8, 10), by_merchant["餐饮"].transaction_date)
        self.assertEqual("ready", by_merchant["餐饮"].status)
        candidate = by_merchant["发红包"]
        self.assertIsNone(candidate.transaction_date)
        self.assertEqual("invalid", candidate.status)
        self.assertTrue(any(
            issue.get("code") == "DATE_INVALID"
            for issue in candidate.validation_errors
        ))
        self.assertEqual(
            "manual_date_required",
            candidate.evidence["date_context_repair"]["status"],
        )
        self.assertEqual(
            0,
            self.db.query(FinancialTransaction).filter_by(user_id=self.user.id).count(),
        )

    def test_evidence_region_uses_ocr_visual_order_not_parser_order(self):
        rendered = _rendered_slices()
        rendered[0]["source_locator"]["transaction_row_detection"] = {
            "version": "colored-icon-v1",
            "reliable": True,
            "expected_transaction_rows": 2,
            "row_centers": [200, 800],
        }
        with patch(
            "app.services.cashflow_long_image_service.render_long_image_slices",
            return_value=rendered,
        ):
            batch, _ = create_segmented_ocr_batch(
                self.db,
                user_id=self.user.id,
                content=_png_stub(1080, 4200, b"visual-order"),
                content_type="image/png",
                original_filename="visual-order.png",
                expected_data_epoch=self.user.business_data_epoch,
            )
        result = AIIntakeResult(
            # Deliberately reverse parser order relative to the OCR/image order.
            parsed=[
                _candidate("bottom", amount=Decimal("10.00"), merchant="底部交易"),
                _candidate("top", amount=Decimal("20.00"), merchant="顶部交易"),
            ],
            parser_version="test",
            content_hash="visual-order",
            provider_name="test",
            model="test",
            ocr_text="",
        )
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                return_value="顶部交易 20.00\n底部交易 10.00",
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                return_value=result,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        rows = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).all()
        by_merchant = {row.merchant: row for row in rows}
        top_payload = get_candidate_evidence_payload(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            candidate_id=by_merchant["顶部交易"].id,
        )
        bottom_payload = get_candidate_evidence_payload(
            self.db,
            user_id=self.user.id,
            batch_id=batch.id,
            candidate_id=by_merchant["底部交易"].id,
        )
        top_region = top_payload["sources"][0]["region"]
        bottom_region = bottom_payload["sources"][0]["region"]
        self.assertEqual("transaction_icon_row_alignment", top_region["method"])
        self.assertLess(top_region["top"], bottom_region["top"])

    def test_invalid_batch_year_rolls_back_every_candidate(self):
        batch, _ = self._create_batch(marker=b"invalid-batch-year")
        valid = _candidate(
            "valid-year",
            amount=Decimal("10.00"),
            transaction_date=date(2024, 8, 20),
            merchant="普通日期",
        )
        leap = _candidate(
            "leap-year",
            amount=Decimal("11.00"),
            transaction_date=date(2024, 2, 29),
            merchant="闰日交易",
        )
        year_warning = {
            "field": "transaction_date",
            "code": "PROGRAM_YEAR_INFERRED",
            "message": "请确认年份",
        }
        valid = ParsedCandidate(**{**valid.__dict__, "warnings": [year_warning]})
        leap = ParsedCandidate(**{**leap.__dict__, "warnings": [year_warning]})
        results = [
            AIIntakeResult(
                parsed=[valid, leap],
                parser_version="test",
                content_hash="invalid-year-first",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
            AIIntakeResult(
                parsed=[],
                parser_version="test",
                content_hash="invalid-year-second",
                provider_name="test",
                model="test",
                ocr_text="",
            ),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "8月20日 星期四\n普通日期 10.00\n2月29日 星期四\n闰日交易 11.00",
                    "无新交易",
                ],
            ),
            patch(
                "app.services.cashflow_long_image_service.parse_ocr_text_intake",
                side_effect=results,
            ),
        ):
            process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)
            batch = process_ocr_slice(self.db, user_id=self.user.id, batch_id=batch.id)

        with self.assertRaises(HTTPException) as raised:
            apply_batch_review_resolutions(
                self.db,
                user_id=self.user.id,
                batch_id=batch.id,
                data=FinancialImportBatchReviewResolutionRequest(
                    expected_batch_version=batch.version,
                    inferred_year=2025,
                ),
            )
        self.assertEqual(
            "cashflow_import_year_resolution_invalid",
            raised.exception.detail["code"],
        )
        rows = self.db.query(FinancialTransactionCandidate).filter_by(
            batch_id=batch.id,
        ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
        self.assertEqual([date(2024, 8, 20), date(2024, 2, 29)], [row.transaction_date for row in rows])
        self.assertTrue(all(
            any(issue.get("code") == "PROGRAM_YEAR_INFERRED" for issue in row.warnings)
            for row in rows
        ))

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
            occurred_at=datetime(2026, 8, 21, 12, 30),
            merchant="星巴克",
            description="星巴克咖啡",
        )
        third = _candidate(
            "ai-overlap-third",
            occurred_at=datetime(2026, 8, 21, 12, 30),
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
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "2026-08-21 12:30 星巴克 36.50",
                    "2026-08-21 12:30 星巴克 36.50",
                    "2026-08-21 12:30 星巴克微信支付 36.50",
                ],
            ),
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
        first = _candidate(
            "unavailable-first",
            occurred_at=datetime(2026, 8, 21, 12, 30),
            merchant="某便利店",
            description="某便利店支出",
        )
        third = _candidate(
            "unavailable-third",
            occurred_at=datetime(2026, 8, 21, 12, 30),
            merchant="某便利店微信",
            description="某便利店支出交易",
        )
        results = [
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="one", provider_name="test", model="test", ocr_text="one"),
            AIIntakeResult(parsed=[first], parser_version="test", content_hash="two", provider_name="test", model="test", ocr_text="two"),
            AIIntakeResult(parsed=[third], parser_version="test", content_hash="three", provider_name="test", model="test", ocr_text="three"),
        ]
        with (
            patch(
                "app.services.cashflow_long_image_service._local_ocr",
                side_effect=[
                    "2026-08-21 12:30 某便利店 36.50",
                    "2026-08-21 12:30 某便利店 36.50",
                    "2026-08-21 12:30 某便利店微信 36.50",
                ],
            ),
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
            patch("app.services.cashflow_long_image_service._local_ocr", return_value="2026-08-21 12:30 午饭商户 36.50"),
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
