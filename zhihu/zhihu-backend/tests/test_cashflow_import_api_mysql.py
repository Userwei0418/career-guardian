from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

try:
    from mysql_test_support import mysql_test
except ModuleNotFoundError:  # Support both discovery and dotted-module invocation.
    from tests.mysql_test_support import mysql_test

# mysql_test_support must be imported before application settings so this module
# can never fall back to the normal DATABASE_URL.
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import Base, engine
from app.main import app


def _wechat_csv(*, external_id: str, description: str, metadata: str) -> bytes:
    return (
        f"{metadata}\n"
        "交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号\n"
        f"2026-08-18 09:30:00,转账,公司财务,{description},收入,12000.00,银行卡,支付成功,{external_id}\n"
    ).encode("utf-8-sig")


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
