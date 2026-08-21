from __future__ import annotations

import asyncio
import json
import unittest

from app.cashflow_upload_limit import CashflowUploadBodyLimitMiddleware


def _scope(
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
    *,
    method: str = "POST",
) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "root_path": "",
    }


class CashflowUploadBodyLimitTest(unittest.TestCase):
    def test_chunked_body_is_stopped_before_the_remaining_stream_is_spooled(self):
        received_calls = 0
        downstream_completed = False
        messages = [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": True},
            {"type": "http.request", "body": b"must-not-be-read", "more_body": False},
        ]
        sent: list[dict] = []

        async def receive():
            nonlocal received_calls
            message = messages[received_calls]
            received_calls += 1
            return message

        async def send(message):
            sent.append(message)

        async def downstream(_scope, limited_receive, downstream_send):
            nonlocal downstream_completed
            while True:
                message = await limited_receive()
                if not message.get("more_body"):
                    break
            downstream_completed = True
            await downstream_send({"type": "http.response.start", "status": 204, "headers": []})
            await downstream_send({"type": "http.response.body", "body": b""})

        middleware = CashflowUploadBodyLimitMiddleware(downstream, max_body_size=10)
        asyncio.run(middleware(_scope("/api/cashflow/imports"), receive, send))

        self.assertEqual(2, received_calls)
        self.assertFalse(downstream_completed)
        self.assertEqual(413, sent[0]["status"])
        payload = json.loads(sent[1]["body"])
        self.assertEqual("cashflow_import_too_large", payload["error"]["code"])

    def test_content_length_is_only_an_early_rejection(self):
        receive_called = False
        downstream_called = False
        sent: list[dict] = []

        async def receive():
            nonlocal receive_called
            receive_called = True
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        async def downstream(_scope, _receive, _send):
            nonlocal downstream_called
            downstream_called = True

        middleware = CashflowUploadBodyLimitMiddleware(downstream, max_body_size=10)
        asyncio.run(middleware(
            _scope("/api/cashflow/imports/ocr", [(b"content-length", b"11")]),
            receive,
            send,
        ))

        self.assertFalse(receive_called)
        self.assertFalse(downstream_called)
        self.assertEqual(413, sent[0]["status"])

    def test_chunked_json_routes_are_limited_before_pydantic_reads_the_body(self):
        for path, method in (
            ("/api/cashflow/imports/text", "POST"),
            ("/api/cashflow/imports/7/mapping", "PUT"),
            ("/api/cashflow/imports/7/candidates/9", "PATCH"),
            ("/api/cashflow/imports/7/confirm", "POST"),
        ):
            with self.subTest(path=path):
                messages = [
                    {"type": "http.request", "body": b"123456", "more_body": True},
                    {"type": "http.request", "body": b"789012", "more_body": False},
                ]
                sent: list[dict] = []
                calls = 0

                async def receive():
                    nonlocal calls
                    message = messages[calls]
                    calls += 1
                    return message

                async def send(message):
                    sent.append(message)

                async def downstream(_scope, limited_receive, _send):
                    while True:
                        message = await limited_receive()
                        if not message.get("more_body"):
                            break

                middleware = CashflowUploadBodyLimitMiddleware(downstream, max_body_size=10)
                asyncio.run(middleware(_scope(path, method=method), receive, send))

                self.assertEqual(413, sent[0]["status"])
                self.assertEqual(
                    "cashflow_import_too_large",
                    json.loads(sent[1]["body"])["error"]["code"],
                )


if __name__ == "__main__":
    unittest.main()
