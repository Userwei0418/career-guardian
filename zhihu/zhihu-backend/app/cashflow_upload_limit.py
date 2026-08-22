from __future__ import annotations

import re

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.cashflow_import_parser import MAX_IMPORT_FILE_SIZE
from app.services.cashflow_ai_intake_service import MAX_OCR_FILE_SIZE


MAX_CASHFLOW_MULTIPART_BODY_SIZE = MAX_IMPORT_FILE_SIZE + 512 * 1024
MAX_CASHFLOW_OCR_MULTIPART_BODY_SIZE = MAX_OCR_FILE_SIZE + 512 * 1024
MAX_CASHFLOW_TEXT_JSON_SIZE = 16 * 1024
MAX_CASHFLOW_MAPPING_JSON_SIZE = 16 * 1024
MAX_CASHFLOW_CANDIDATE_JSON_SIZE = 8 * 1024
MAX_CASHFLOW_CONFIRM_JSON_SIZE = 128 * 1024


class _CashflowBodyTooLarge(Exception):
    pass


class CashflowUploadBodyLimitMiddleware:
    """Stop oversized cashflow multipart bodies before Starlette spools them.

    ``UploadFile`` size checks run only after multipart parsing. This outer ASGI
    receive wrapper enforces the actual byte stream limit first; Content-Length
    is used only as an early rejection and is never trusted as the sole guard.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_body_size: int | None = None,
    ) -> None:
        self.app = app
        self.max_body_size = max_body_size

    def _request_limit(self, scope: Scope) -> tuple[int, str] | None:
        if scope.get("type") != "http":
            return None
        method = str(scope.get("method") or "").upper()
        path = str(scope.get("path") or "").rstrip("/") or "/"
        limit: tuple[int, str] | None = None
        if method == "POST" and path == "/api/cashflow/imports":
            limit = (
                MAX_CASHFLOW_MULTIPART_BODY_SIZE,
                "上传请求过大，账单文件不能超过 10MB",
            )
        elif method == "POST" and path == "/api/cashflow/imports/ocr":
            limit = (
                MAX_CASHFLOW_OCR_MULTIPART_BODY_SIZE,
                "上传请求过大，OCR 图片不能超过 30MB",
            )
        elif method == "POST" and path == "/api/payslips/recognize":
            limit = (
                MAX_CASHFLOW_OCR_MULTIPART_BODY_SIZE,
                "上传请求过大，工资条文件不能超过 30MB",
            )
        elif method == "POST" and path == "/api/cashflow/imports/text":
            limit = (MAX_CASHFLOW_TEXT_JSON_SIZE, "文本识别请求过大")
        elif method == "PUT" and re.fullmatch(r"/api/cashflow/imports/\d+/mapping", path):
            limit = (MAX_CASHFLOW_MAPPING_JSON_SIZE, "字段映射请求过大")
        elif method == "PATCH" and re.fullmatch(
            r"/api/cashflow/imports/\d+/candidates/\d+",
            path,
        ):
            limit = (MAX_CASHFLOW_CANDIDATE_JSON_SIZE, "候选编辑请求过大")
        elif method == "POST" and re.fullmatch(r"/api/cashflow/imports/\d+/confirm", path):
            limit = (MAX_CASHFLOW_CONFIRM_JSON_SIZE, "确认入账请求过大")
        if limit is None:
            return None
        if self.max_body_size is not None:
            return self.max_body_size, limit[1]
        return limit

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        message: str,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "cashflow_import_too_large",
                    "message": message,
                    "status": 413,
                }
            },
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_limit = self._request_limit(scope)
        if request_limit is None:
            await self.app(scope, receive, send)
            return
        max_body_size, rejection_message = request_limit

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
        }
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                if int(raw_content_length) > max_body_size:
                    await self._reject(scope, receive, send, rejection_message)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > max_body_size:
                    raise _CashflowBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _CashflowBodyTooLarge:
            await self._reject(scope, receive, send, rejection_message)
