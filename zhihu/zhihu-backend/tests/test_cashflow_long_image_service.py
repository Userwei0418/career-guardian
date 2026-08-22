from __future__ import annotations

import tempfile
import unittest
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

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
    create_segmented_ocr_batch,
    process_ocr_slice,
    render_long_image_slices,
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


def _candidate(content_hash: str, *, confidence: float = 0.95) -> ParsedCandidate:
    fingerprint = build_candidate_fingerprint(
        direction="expense",
        amount=Decimal("36.50"),
        transaction_date=date(2026, 8, 21),
        merchant="午饭商户",
        description="工作午饭",
    )
    return ParsedCandidate(
        row_number=1,
        direction="expense",
        amount=Decimal("36.50"),
        currency="CNY",
        transaction_date=date(2026, 8, 21),
        occurred_at=None,
        category_name="餐饮",
        merchant="午饭商户",
        description="工作午饭",
        nature="flexible",
        external_key=f"ocr:{content_hash[:24]}",
        fingerprint=fingerprint,
        original_payload={"amount": "36.50", "merchant": "午饭商户"},
        evidence={"confidence": confidence, "review_tier": "high", "evidence_quote": "午饭 36.50"},
        validation_errors=[],
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
        candidates = self.db.query(FinancialTransactionCandidate).filter_by(batch_id=batch.id).order_by(FinancialTransactionCandidate.row_number).all()
        self.assertEqual(1, len(candidates))
        self.assertEqual("ready", candidates[0].status)
        self.assertEqual([1, 2], [item["slice_sequence"] for item in candidates[0].evidence["source_slices"]])
        self.assertEqual("日期、金额、方向和交易文本完全一致", candidates[0].evidence["overlap_merge_reason"])
        self.assertEqual(2, self.db.query(FinancialRecognitionArtifact).filter_by(batch_id=batch.id, artifact_type="ocr_text").count())
        stored_files = [path for path in Path(self.upload_directory.name).rglob("*") if path.is_file()]
        self.assertEqual(2, len(stored_files))

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
