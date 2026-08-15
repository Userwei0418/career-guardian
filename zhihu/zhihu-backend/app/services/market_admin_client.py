from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas.market_admin import MarketCrawlTask, MarketCrawlTaskList, MarketDataSourceList


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class MarketAdminError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class MarketAdminClient:
    """Server-side control gateway. The internal token never reaches the browser."""

    def __init__(
        self,
        base_url: str,
        internal_token: str | None,
        timeout_seconds: float = 10,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.internal_token = internal_token
        self.timeout_seconds = timeout_seconds
        self.client = client

    def _request(
        self,
        method: str,
        path: str,
        response_model: type[ResponseModel],
        params: dict | None = None,
    ) -> ResponseModel:
        if not self.internal_token:
            raise MarketAdminError(503, "市场采集管理令牌尚未配置")
        headers = {"X-Market-Admin-Token": self.internal_token}
        try:
            if self.client is not None:
                response = self.client.request(method, path, params=params, headers=headers)
            else:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                    response = client.request(method, path, params=params, headers=headers)
            response.raise_for_status()
            return response_model.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                message = str(exc.response.json().get("detail") or "市场采集管理请求失败")
            except (ValueError, AttributeError):
                message = "市场采集管理请求失败"
            raise MarketAdminError(status_code if status_code < 500 else 502, message) from exc
        except (httpx.HTTPError, ValidationError, ValueError, KeyError) as exc:
            raise MarketAdminError(503, f"市场采集管理服务暂时不可用：{type(exc).__name__}") from exc

    def list_sources(self) -> MarketDataSourceList:
        return self._request("GET", "/internal/admin/sources", MarketDataSourceList)

    def list_tasks(self, limit: int = 50) -> MarketCrawlTaskList:
        return self._request(
            "GET",
            "/internal/admin/tasks",
            MarketCrawlTaskList,
            params={"limit": limit},
        )

    def run_source(self, source_code: str) -> MarketCrawlTask:
        return self._request(
            "POST",
            f"/internal/admin/sources/{source_code}/runs",
            MarketCrawlTask,
        )
