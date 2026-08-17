from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, RootModel, ValidationError

from app.schemas.market_admin import (
    MarketCrawlTask,
    MarketCrawlTaskDetail,
    MarketCrawlTaskList,
    MarketDataSourceList,
    MarketDataSource,
    MarketGateSettings,
    MarketStrategyRepairCandidate,
    MarketStrategyRepairEvidence,
    MarketCollectionCompany,
    MarketCollectionCompanyList,
    MarketCrawlBatch,
)


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class _StrategyRepairCandidateList(RootModel[list[MarketStrategyRepairCandidate]]):
    pass


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
        json_data: dict | None = None,
    ) -> ResponseModel:
        if not self.internal_token:
            raise MarketAdminError(503, "市场采集管理令牌尚未配置")
        headers = {"X-Market-Admin-Token": self.internal_token}
        try:
            if self.client is not None:
                response = self.client.request(
                    method, path, params=params, json=json_data, headers=headers
                )
            else:
                with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                    response = client.request(
                        method, path, params=params, json=json_data, headers=headers
                    )
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

    def get_task_detail(self, task_id: int, limit: int = 100) -> MarketCrawlTaskDetail:
        return self._request(
            "GET",
            f"/internal/admin/tasks/{task_id}",
            MarketCrawlTaskDetail,
            params={"limit": limit},
        )

    def list_companies(self, query: str | None = None) -> MarketCollectionCompanyList:
        return self._request(
            "GET",
            "/internal/admin/collection/companies",
            MarketCollectionCompanyList,
            params={"query": query} if query else None,
        )

    def update_company(self, company_code: str, enabled: bool, review_note: str, actor: str) -> MarketCollectionCompany:
        return self._request(
            "PUT",
            f"/internal/admin/collection/companies/{company_code}/governance",
            MarketCollectionCompany,
            json_data={"enabled": enabled, "review_note": review_note, "actor": actor},
        )

    def run_company(
        self, company_code: str, actor: str, browser_mode: str = "default"
    ) -> MarketCrawlBatch:
        return self._request(
            "POST",
            f"/internal/admin/collection/companies/{company_code}/runs",
            MarketCrawlBatch,
            params={"actor": actor},
            json_data={"browser_mode": browser_mode},
        )

    def update_source(
        self,
        source_code: str,
        terms_review_status: str,
        enabled: bool,
        review_note: str,
        actor: str,
    ) -> MarketDataSource:
        return self._request(
            "PUT",
            f"/internal/admin/sources/{source_code}",
            MarketDataSource,
            json_data={
                "terms_review_status": terms_review_status,
                "enabled": enabled,
                "review_note": review_note,
                "actor": actor,
            },
        )

    def run_source(
        self, source_code: str, browser_mode: str = "default"
    ) -> MarketCrawlTask:
        return self._request(
            "POST",
            f"/internal/admin/sources/{source_code}/runs",
            MarketCrawlTask,
            json_data={"browser_mode": browser_mode},
        )

    def update_source_configuration(
        self, source_code: str, configuration: dict, actor: str
    ) -> MarketDataSource:
        return self._request(
            "PUT",
            f"/internal/admin/sources/{source_code}/configuration",
            MarketDataSource,
            json_data={**configuration, "actor": actor},
        )

    def list_strategy_repairs(
        self, source_code: str | None = None, limit: int = 50
    ) -> list[MarketStrategyRepairCandidate]:
        params: dict[str, str | int] = {"limit": limit}
        if source_code:
            params["source_code"] = source_code
        return self._request(
            "GET",
            "/internal/admin/strategy-repairs",
            _StrategyRepairCandidateList,
            params=params,
        ).root

    def create_strategy_repair(
        self,
        source_code: str,
        proposed_strategy: dict,
        actor: str,
        origin: str = "admin",
        failure_task_id: int | None = None,
    ) -> MarketStrategyRepairCandidate:
        return self._request(
            "POST",
            f"/internal/admin/sources/{source_code}/strategy-repairs",
            MarketStrategyRepairCandidate,
            json_data={
                "proposed_strategy": proposed_strategy,
                "actor": actor,
                "origin": origin,
                "failure_task_id": failure_task_id,
            },
        )

    def get_strategy_repair_evidence(
        self, source_code: str
    ) -> MarketStrategyRepairEvidence:
        return self._request(
            "GET",
            f"/internal/admin/sources/{source_code}/strategy-repair-evidence",
            MarketStrategyRepairEvidence,
        )

    def replay_strategy_repair(self, candidate_id: int) -> MarketStrategyRepairCandidate:
        return self._request(
            "POST",
            f"/internal/admin/strategy-repairs/{candidate_id}/replay",
            MarketStrategyRepairCandidate,
        )

    def approve_strategy_repair(
        self, candidate_id: int, actor: str
    ) -> MarketStrategyRepairCandidate:
        return self._request(
            "POST",
            f"/internal/admin/strategy-repairs/{candidate_id}/approve",
            MarketStrategyRepairCandidate,
            json_data={"actor": actor},
        )

    def rollback_strategy_repair(
        self, candidate_id: int, actor: str
    ) -> MarketStrategyRepairCandidate:
        return self._request(
            "POST",
            f"/internal/admin/strategy-repairs/{candidate_id}/rollback",
            MarketStrategyRepairCandidate,
            json_data={"actor": actor},
        )

    def get_gate_settings(self) -> MarketGateSettings:
        return self._request("GET", "/internal/admin/gate", MarketGateSettings)

    def save_gate_draft(
        self, configuration: dict, change_note: str, actor: str
    ) -> MarketGateSettings:
        return self._request(
            "PUT",
            "/internal/admin/gate/draft",
            MarketGateSettings,
            json_data={
                "configuration": configuration,
                "change_note": change_note,
                "actor": actor,
            },
        )

    def preview_gate_draft(self) -> MarketGateSettings:
        return self._request(
            "POST", "/internal/admin/gate/draft/preview", MarketGateSettings
        )

    def publish_gate_draft(self, actor: str) -> MarketGateSettings:
        return self._request(
            "POST",
            "/internal/admin/gate/draft/publish",
            MarketGateSettings,
            json_data={"actor": actor},
        )
