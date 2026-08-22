from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from mysql_test_support import mysql_test
except ModuleNotFoundError:  # Support both discovery and dotted-module invocation.
    from tests.mysql_test_support import mysql_test

# mysql_test_support must be imported before application settings so this module
# can never fall back to the normal DATABASE_URL.
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.api.routes import cashflow_imports as cashflow_import_routes
from app.models.ai_configuration import AIInvocationLog
from app.models.personal_attachment import PersonalAttachmentVersion
from app.services import cashflow_ai_intake_service as intake
from app.services.personal_attachment_service import resolve_attachment_path


def _wechat_csv(*, external_id: str, description: str, metadata: str) -> bytes:
    return (
        f"{metadata}\n"
        "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号\n"
        f"2026-08-18 09:30:00,转账,公司财务,{description},收入,12000.00,银行卡,支付成功,{external_id}\n"
    ).encode("utf-8-sig")


def _ai_configuration() -> SimpleNamespace:
    return SimpleNamespace(
        setting_id=None,
        provider_name="test-provider",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="test-text-model",
        api_key="test-only-key",
    )


def _model_response(transaction: dict) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {"transactions": [transaction]},
                        ensure_ascii=False,
                    )
                },
            }
        ],
        "usage": {
            "prompt_tokens": 30,
            "completion_tokens": 20,
            "total_tokens": 50,
        },
    }
    return response


def _expense_model_transaction(*, evidence_quote: str) -> dict:
    return {
        "occurrence": "occurred",
        "direction": "expense",
        "amount": "36.50",
        "currency": "CNY",
        "transaction_date": "2026-08-21",
        "merchant": "午饭商户",
        "description": "工作午饭",
        "category_name": "餐饮",
        "nature": "flexible",
        "evidence_quote": evidence_quote,
        "confidence": 0.94,
    }


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


@mysql_test
class CashflowImportApiMysqlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.upload_directory = tempfile.TemporaryDirectory(
            prefix="cashflow-import-api-mysql-test-"
        )
        self.original_upload_dir = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = self.upload_directory.name
        self.alice = self._register("cashflow-import-alice", "alice-import-password")
        self.bob = self._register("cashflow-import-bob", "bob-import-password")

        category = self.client.post(
            "/api/cashflow/categories",
            headers=self._headers(self.alice),
            json={"direction": "income", "name": "工资"},
        )
        self.assertEqual(201, category.status_code, category.text)
        expense_category = self.client.post(
            "/api/cashflow/categories",
            headers=self._headers(self.alice),
            json={"direction": "expense", "name": "餐饮"},
        )
        self.assertEqual(201, expense_category.status_code, expense_category.text)

    def tearDown(self):
        settings.UPLOAD_DIR = self.original_upload_dir
        self.upload_directory.cleanup()
        Base.metadata.drop_all(bind=engine)

    def _register(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    @staticmethod
    def _headers(auth: dict) -> dict:
        return {"Authorization": f"Bearer {auth['access_token']}"}

    def _upload(self, *, filename: str, content: bytes):
        return self.client.post(
            "/api/cashflow/imports",
            headers=self._headers(self.alice),
            data={"source_hint": "auto"},
            files={"file": (filename, content, "text/csv")},
        )

    def test_capabilities_and_unfinished_batch_filter_are_truthful(self):
        with (
            patch.object(
                cashflow_import_routes,
                "effective_ai_configuration",
                return_value=_ai_configuration(),
            ),
            patch.object(
                cashflow_import_routes.shutil,
                "which",
                return_value="/test-only/tesseract",
            ),
        ):
            configured = self.client.get(
                "/api/cashflow/imports/capabilities",
                headers=self._headers(self.alice),
            )
        self.assertEqual(200, configured.status_code, configured.text)
        configured_body = configured.json()
        self.assertEqual("available", configured_body["file"]["state"])
        self.assertTrue(configured_body["file"]["enabled"])
        self.assertEqual("configured", configured_body["text"]["state"])
        self.assertTrue(configured_body["text"]["enabled"])
        self.assertEqual("configured", configured_body["ocr"]["state"])
        self.assertTrue(configured_body["ocr"]["enabled"])
        self.assertIn("提交时校验", configured_body["text"]["message"])

        with (
            patch.object(
                cashflow_import_routes,
                "effective_ai_configuration",
                return_value=None,
            ),
            patch.object(cashflow_import_routes.shutil, "which", return_value=None),
        ):
            unavailable = self.client.get(
                "/api/cashflow/imports/capabilities",
                headers=self._headers(self.alice),
            )
        self.assertEqual(200, unavailable.status_code, unavailable.text)
        unavailable_body = unavailable.json()
        self.assertTrue(unavailable_body["file"]["enabled"])
        self.assertFalse(unavailable_body["text"]["enabled"])
        self.assertFalse(unavailable_body["ocr"]["enabled"])
        self.assertEqual("unavailable", unavailable_body["text"]["state"])
        self.assertEqual("unavailable", unavailable_body["ocr"]["state"])

        with patch.object(
            cashflow_import_routes,
            "list_owned_batches",
            side_effect=RuntimeError("synthetic unavailable import storage"),
        ):
            storage_unavailable = self.client.get(
                "/api/cashflow/imports/capabilities",
                headers=self._headers(self.alice),
            )
        self.assertEqual(200, storage_unavailable.status_code, storage_unavailable.text)
        storage_body = storage_unavailable.json()
        self.assertFalse(storage_body["file"]["enabled"])
        self.assertFalse(storage_body["text"]["enabled"])
        self.assertFalse(storage_body["ocr"]["enabled"])
        self.assertIn("批次存储尚未就绪", storage_body["file"]["message"])

        completed_upload = self._upload(
            filename="已完成批次.csv",
            content=_wechat_csv(
                external_id="mysql-capability-completed-001",
                description="八月工资",
                metadata="微信支付账单明细",
            ),
        )
        self.assertEqual(200, completed_upload.status_code, completed_upload.text)
        completed_batch = completed_upload.json()
        completed_candidates = self.client.get(
            f"/api/cashflow/imports/{completed_batch['id']}/candidates",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, completed_candidates.status_code, completed_candidates.text)
        completed_candidate = completed_candidates.json()["items"][0]
        self.assertEqual("ready", completed_candidate["status"])
        completion = self.client.post(
            f"/api/cashflow/imports/{completed_batch['id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "expected_batch_version": completed_batch["version"],
                "candidates": [
                    {
                        "candidate_id": completed_candidate["id"],
                        "expected_version": completed_candidate["version"],
                    }
                ],
            },
        )
        self.assertEqual(200, completion.status_code, completion.text)
        self.assertEqual("completed", completion.json()["batch"]["status"])

        unfinished_upload = self._upload(
            filename="仍待核对批次.csv",
            content=_wechat_csv(
                external_id="mysql-capability-unfinished-002",
                description="九月工资",
                metadata="微信支付账单明细",
            ),
        )
        self.assertEqual(200, unfinished_upload.status_code, unfinished_upload.text)
        unfinished_batch = unfinished_upload.json()

        all_batches = self.client.get(
            "/api/cashflow/imports?offset=0&limit=20",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, all_batches.status_code, all_batches.text)
        self.assertEqual(2, all_batches.json()["total"])

        unfinished_batches = self.client.get(
            "/api/cashflow/imports?unfinished_only=true&offset=0&limit=20",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, unfinished_batches.status_code, unfinished_batches.text)
        unfinished_body = unfinished_batches.json()
        self.assertEqual(1, unfinished_body["total"])
        self.assertEqual([unfinished_batch["id"]], [item["id"] for item in unfinished_body["items"]])

    def test_owner_scoped_upload_preview_confirmation_and_deduplication(self):
        first_upload = self._upload(
            filename="微信收入账单.csv",
            content=_wechat_csv(
                external_id="mysql-api-external-001",
                description="八月工资",
                metadata="微信支付账单明细",
            ),
        )
        self.assertEqual(200, first_upload.status_code, first_upload.text)
        batch = first_upload.json()
        self.assertEqual("wechat", batch["source_type"])
        self.assertEqual("review_ready", batch["status"])
        self.assertEqual(1, batch["total_count"])
        self.assertEqual(1, batch["ready_count"])
        self.assertFalse(batch["reused"])

        preview = self.client.get(
            f"/api/cashflow/imports/{batch['id']}/candidates",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, preview.status_code, preview.text)
        preview_body = preview.json()
        self.assertEqual(1, preview_body["total"])
        self.assertEqual(1, len(preview_body["items"]))
        candidate = preview_body["items"][0]
        self.assertEqual("ready", candidate["status"])
        self.assertEqual("income", candidate["direction"])
        self.assertEqual("12000.00", candidate["amount"])
        self.assertEqual("工资", candidate["category_name"])

        transactions_before_confirmation = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(
            200,
            transactions_before_confirmation.status_code,
            transactions_before_confirmation.text,
        )
        self.assertEqual([], transactions_before_confirmation.json())

        bob_batch = self.client.get(
            f"/api/cashflow/imports/{batch['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, bob_batch.status_code, bob_batch.text)
        bob_candidates = self.client.get(
            f"/api/cashflow/imports/{batch['id']}/candidates",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, bob_candidates.status_code, bob_candidates.text)

        stale_update = self.client.patch(
            f"/api/cashflow/imports/{batch['id']}/candidates/{candidate['id']}",
            headers=self._headers(self.alice),
            json={
                "expected_version": candidate["version"] + 1,
                "merchant": "旧页面错误覆盖",
            },
        )
        self.assertEqual(409, stale_update.status_code, stale_update.text)
        self.assertEqual(
            "cashflow_import_stale_candidate",
            stale_update.json()["error"]["code"],
        )

        confirmation = self.client.post(
            f"/api/cashflow/imports/{batch['id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "expected_batch_version": batch["version"],
                "candidates": [
                    {
                        "candidate_id": candidate["id"],
                        "expected_version": candidate["version"],
                    }
                ],
            },
        )
        self.assertEqual(200, confirmation.status_code, confirmation.text)
        confirmation_body = confirmation.json()
        self.assertEqual(1, confirmation_body["confirmed_count"])
        self.assertEqual([candidate["id"]], confirmation_body["confirmed_candidate_ids"])
        self.assertEqual(1, len(confirmation_body["transaction_ids"]))

        transactions_after_confirmation = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(
            200,
            transactions_after_confirmation.status_code,
            transactions_after_confirmation.text,
        )
        transactions = transactions_after_confirmation.json()
        self.assertEqual(1, len(transactions))
        self.assertEqual("import_wechat", transactions[0]["source_type"])

        second_upload = self._upload(
            filename="微信收入账单重新下载.csv",
            content=_wechat_csv(
                external_id="mysql-api-external-001",
                description="八月工资重新下载",
                metadata="微信支付账单明细（重新下载）",
            ),
        )
        self.assertEqual(200, second_upload.status_code, second_upload.text)
        second_batch = second_upload.json()
        self.assertFalse(second_batch["reused"])
        self.assertNotEqual(batch["id"], second_batch["id"])
        self.assertEqual(1, second_batch["exact_duplicate_count"])
        self.assertEqual(0, second_batch["ready_count"])

        duplicate_preview = self.client.get(
            f"/api/cashflow/imports/{second_batch['id']}/candidates",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, duplicate_preview.status_code, duplicate_preview.text)
        duplicate = duplicate_preview.json()["items"][0]
        self.assertEqual("exact_duplicate", duplicate["status"])
        self.assertEqual(transactions[0]["id"], duplicate["duplicate_transaction_id"])

        final_transactions = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, final_transactions.status_code, final_transactions.text)
        self.assertEqual(1, len(final_transactions.json()))

    def test_ai_text_endpoint_requires_review_before_formal_ledger_write(self):
        source_text = "昨天午饭 36.50 元"
        model_response = _model_response(
            _expense_model_transaction(evidence_quote=source_text)
        )

        with (
            patch.object(
                intake,
                "effective_ai_configuration",
                return_value=_ai_configuration(),
            ),
            patch.object(intake.httpx, "post", return_value=model_response) as model_post,
        ):
            created = self.client.post(
                "/api/cashflow/imports/text",
                headers=self._headers(self.alice),
                json={"text": source_text},
            )

        self.assertEqual(200, created.status_code, created.text)
        batch = created.json()
        self.assertEqual("ai_text", batch["origin_type"])
        self.assertEqual("ai_text", batch["source_type"])
        self.assertEqual("review_ready", batch["status"])
        self.assertEqual(1, batch["review_count"])
        self.assertEqual(0, batch["ready_count"])
        model_post.assert_called_once()

        preview = self.client.get(
            f"/api/cashflow/imports/{batch['id']}/candidates",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, preview.status_code, preview.text)
        candidate = preview.json()["items"][0]
        self.assertEqual("needs_review", candidate["status"])
        self.assertEqual("expense", candidate["direction"])
        self.assertEqual("36.50", candidate["amount"])
        self.assertIn(
            "AI_REVIEW_REQUIRED",
            {warning["code"] for warning in candidate["warnings"]},
        )

        premature_confirmation = self.client.post(
            f"/api/cashflow/imports/{batch['id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "expected_batch_version": batch["version"],
                "candidates": [
                    {
                        "candidate_id": candidate["id"],
                        "expected_version": candidate["version"],
                    }
                ],
            },
        )
        self.assertEqual(
            409,
            premature_confirmation.status_code,
            premature_confirmation.text,
        )
        self.assertEqual(
            "cashflow_import_candidate_not_ready",
            premature_confirmation.json()["error"]["code"],
        )

        before_acceptance = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, before_acceptance.status_code, before_acceptance.text)
        self.assertEqual([], before_acceptance.json())

        accepted = self.client.patch(
            f"/api/cashflow/imports/{batch['id']}/candidates/{candidate['id']}",
            headers=self._headers(self.alice),
            json={
                "expected_version": candidate["version"],
                "action": "accept_review",
            },
        )
        self.assertEqual(200, accepted.status_code, accepted.text)
        accepted_candidate = accepted.json()
        self.assertEqual("ready", accepted_candidate["status"])
        self.assertEqual([], accepted_candidate["warnings"])

        accepted_batch = self.client.get(
            f"/api/cashflow/imports/{batch['id']}",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, accepted_batch.status_code, accepted_batch.text)
        accepted_batch_body = accepted_batch.json()
        self.assertEqual(1, accepted_batch_body["ready_count"])
        self.assertEqual(0, accepted_batch_body["review_count"])

        after_acceptance = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, after_acceptance.status_code, after_acceptance.text)
        self.assertEqual([], after_acceptance.json())

        confirmed = self.client.post(
            f"/api/cashflow/imports/{batch['id']}/confirm",
            headers=self._headers(self.alice),
            json={
                "expected_batch_version": accepted_batch_body["version"],
                "candidates": [
                    {
                        "candidate_id": accepted_candidate["id"],
                        "expected_version": accepted_candidate["version"],
                    }
                ],
            },
        )
        self.assertEqual(200, confirmed.status_code, confirmed.text)
        self.assertEqual(1, confirmed.json()["confirmed_count"])

        after_confirmation = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, after_confirmation.status_code, after_confirmation.text)
        transactions = after_confirmation.json()
        self.assertEqual(1, len(transactions))
        self.assertEqual("import_ai_text", transactions[0]["source_type"])

        with SessionLocal() as db:
            invocation = db.query(AIInvocationLog).one()
            self.assertEqual(self.alice["user_id"], invocation.user_id)
            self.assertEqual(intake.TEXT_FEATURE, invocation.feature)
            self.assertEqual("text", invocation.modality)
            self.assertEqual("success", invocation.status)
            self.assertEqual("test-provider", invocation.provider_name)
            self.assertEqual("test-text-model", invocation.model)
            self.assertEqual(50, invocation.total_tokens)

    def test_ocr_endpoint_requires_consent_and_keeps_image_local(self):
        image_marker = b"synthetic-image-must-stay-local"
        image = _png_stub(1200, 1800, image_marker)
        ocr_text = "昨天午饭 36.50 元"
        model_response = _model_response(
            _expense_model_transaction(evidence_quote=ocr_text)
        )

        with (
            patch.object(
                intake,
                "effective_ai_configuration",
                return_value=_ai_configuration(),
            ),
            patch.object(intake, "_local_ocr", return_value=ocr_text) as local_ocr,
            patch.object(intake.httpx, "post", return_value=model_response) as model_post,
        ):
            denied = self.client.post(
                "/api/cashflow/imports/ocr",
                headers=self._headers(self.alice),
                files={"file": ("receipt.png", image, "image/png")},
            )
            self.assertEqual(400, denied.status_code, denied.text)
            self.assertEqual(
                "cashflow_vision_consent_required",
                denied.json()["error"]["code"],
            )
            local_ocr.assert_not_called()
            model_post.assert_not_called()

            created = self.client.post(
                "/api/cashflow/imports/ocr",
                headers=self._headers(self.alice),
                data={"confirm_external_processing": "true"},
                files={"file": ("receipt.png", image, "image/png")},
            )

        self.assertEqual(200, created.status_code, created.text)
        batch = created.json()
        self.assertEqual("ocr", batch["origin_type"])
        self.assertEqual("receipt", batch["source_type"])
        self.assertEqual("review_ready", batch["status"])
        self.assertIsNotNone(batch["attachment_version_id"])
        local_ocr.assert_called_once()
        self.assertEqual(image, local_ocr.call_args.kwargs["content"])
        self.assertEqual("image/png", local_ocr.call_args.kwargs["detected_type"])
        model_post.assert_called_once()

        remote_messages = json.dumps(
            model_post.call_args.kwargs["json"]["messages"],
            ensure_ascii=False,
        )
        self.assertIn(ocr_text, remote_messages)
        self.assertNotIn(image_marker.decode("ascii"), remote_messages)
        self.assertNotIn("data:image", remote_messages)
        self.assertNotIn("base64", remote_messages.lower())

        preview = self.client.get(
            f"/api/cashflow/imports/{batch['id']}/candidates",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, preview.status_code, preview.text)
        candidate = preview.json()["items"][0]
        self.assertEqual("needs_review", candidate["status"])
        self.assertIn(
            "AI_REVIEW_REQUIRED",
            {warning["code"] for warning in candidate["warnings"]},
        )

        transactions = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, transactions.status_code, transactions.text)
        self.assertEqual([], transactions.json())

        bob_batch = self.client.get(
            f"/api/cashflow/imports/{batch['id']}",
            headers=self._headers(self.bob),
        )
        self.assertEqual(404, bob_batch.status_code, bob_batch.text)

        with SessionLocal() as db:
            attachment = db.query(PersonalAttachmentVersion).one()
            self.assertEqual(batch["attachment_version_id"], attachment.id)
            self.assertEqual(self.alice["user_id"], attachment.user_id)
            self.assertEqual("cashflow_import", attachment.document_type)
            self.assertEqual("image/png", attachment.content_type)
            self.assertEqual(len(image), attachment.file_size)
            self.assertEqual(hashlib.sha256(image).hexdigest(), attachment.content_hash)
            attachment_path = resolve_attachment_path(attachment)
            self.assertEqual(image, attachment_path.read_bytes())

            invocation = db.query(AIInvocationLog).one()
            self.assertEqual(self.alice["user_id"], invocation.user_id)
            self.assertEqual(intake.VISION_FEATURE, invocation.feature)
            self.assertEqual("text", invocation.modality)
            self.assertEqual("success", invocation.status)
            self.assertEqual(50, invocation.total_tokens)

    def test_concurrent_batches_with_same_fingerprint_are_serialized_for_review(self):
        batches: list[tuple[dict, dict]] = []
        for index in (1, 2):
            upload = self._upload(
                filename=f"并发账单-{index}.csv",
                content=_wechat_csv(
                    external_id=f"mysql-concurrent-external-{index}",
                    description="并发同指纹工资",
                    metadata=f"微信支付账单明细-{index}",
                ),
            )
            self.assertEqual(200, upload.status_code, upload.text)
            batch = upload.json()
            preview = self.client.get(
                f"/api/cashflow/imports/{batch['id']}/candidates",
                headers=self._headers(self.alice),
            )
            self.assertEqual(200, preview.status_code, preview.text)
            candidate = preview.json()["items"][0]
            self.assertEqual("ready", candidate["status"])
            batches.append((batch, candidate))

        barrier = Barrier(2)

        def confirm(item: tuple[dict, dict]):
            batch, candidate = item
            barrier.wait(timeout=5)
            response = self.client.post(
                f"/api/cashflow/imports/{batch['id']}/confirm",
                headers=self._headers(self.alice),
                json={
                    "expected_batch_version": batch["version"],
                    "candidates": [
                        {
                            "candidate_id": candidate["id"],
                            "expected_version": candidate["version"],
                        }
                    ],
                },
            )
            return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(confirm, batches))

        self.assertEqual([200, 409], sorted(status for status, _body in results))
        conflict_body = next(body for status, body in results if status == 409)
        self.assertEqual(
            "cashflow_import_possible_duplicate",
            conflict_body["error"]["code"],
        )
        transactions = self.client.get(
            "/api/cashflow/transactions?month=2026-08",
            headers=self._headers(self.alice),
        )
        self.assertEqual(200, transactions.status_code, transactions.text)
        self.assertEqual(1, len(transactions.json()))


if __name__ == "__main__":
    unittest.main()
