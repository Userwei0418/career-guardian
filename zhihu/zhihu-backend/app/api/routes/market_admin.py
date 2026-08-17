from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.market_admin import (
    MarketCrawlTask,
    MarketCrawlTaskDetail,
    MarketCrawlTaskList,
    MarketDataSourceList,
    MarketDataSource,
    MarketSourceGovernanceRequest,
    MarketSourceConfigurationRequest,
    MarketGateDraftRequest,
    MarketGateSettings,
    MarketCollectionCompany,
    MarketCollectionCompanyList,
    MarketCompanyGovernanceRequest,
    MarketCollectionRunRequest,
    MarketCrawlBatch,
    MarketStrategyRepairCandidate,
    MarketStrategyRepairCreateRequest,
    MarketStrategyRepairEvidence,
)
from app.services.market_admin_client import MarketAdminClient, MarketAdminError
from app.services.strategy_repair_service import generate_strategy_document


router = APIRouter()
client = MarketAdminClient(
    settings.MARKET_API_URL,
    settings.MARKET_INTERNAL_TOKEN,
    max(settings.MARKET_API_TIMEOUT_SECONDS, 10),
)


def get_market_admin_client() -> MarketAdminClient:
    return client


def _call(operation):
    try:
        return operation()
    except MarketAdminError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/sources", response_model=MarketDataSourceList)
def list_sources(
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(market_client.list_sources)


@router.get("/collection/companies", response_model=MarketCollectionCompanyList)
def list_collection_companies(
    query: Optional[str] = None,
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.list_companies(query))


@router.put(
    "/collection/companies/{company_code}/governance",
    response_model=MarketCollectionCompany,
)
def update_collection_company(
    company_code: str,
    request: MarketCompanyGovernanceRequest,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.update_company(
            company_code, request.enabled, request.review_note, admin.username
        )
    )


@router.post("/collection/companies/{company_code}/runs", response_model=MarketCrawlBatch)
def run_collection_company(
    company_code: str,
    request: Optional[MarketCollectionRunRequest] = None,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    if request is None:
        return _call(lambda: market_client.run_company(company_code, admin.username))
    return _call(
        lambda: market_client.run_company(
            company_code, admin.username, request.browser_mode
        )
    )


@router.get("/tasks", response_model=MarketCrawlTaskList)
def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.list_tasks(limit))


@router.get("/tasks/{task_id}", response_model=MarketCrawlTaskDetail)
def get_task_detail(
    task_id: int,
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.get_task_detail(task_id, limit))


@router.put("/sources/{source_code}", response_model=MarketDataSource)
def update_source(
    source_code: str,
    request: MarketSourceGovernanceRequest,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.update_source(
            source_code,
            request.terms_review_status,
            request.enabled,
            request.review_note,
            admin.username,
        )
    )


@router.post("/sources/{source_code}/runs", response_model=MarketCrawlTask)
def run_source(
    source_code: str,
    request: Optional[MarketCollectionRunRequest] = None,
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    if request is None:
        return _call(lambda: market_client.run_source(source_code))
    return _call(lambda: market_client.run_source(source_code, request.browser_mode))


@router.put("/sources/{source_code}/configuration", response_model=MarketDataSource)
def update_source_configuration(
    source_code: str,
    request: MarketSourceConfigurationRequest,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.update_source_configuration(
            source_code, request.model_dump(), admin.username
        )
    )


@router.get(
    "/strategy-repairs", response_model=list[MarketStrategyRepairCandidate]
)
def list_strategy_repairs(
    source_code: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.list_strategy_repairs(source_code, limit))


@router.post(
    "/sources/{source_code}/strategy-repairs",
    response_model=MarketStrategyRepairCandidate,
)
def create_strategy_repair(
    source_code: str,
    request: MarketStrategyRepairCreateRequest,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.create_strategy_repair(
            source_code,
            request.proposed_strategy,
            admin.username,
            request.origin,
            request.failure_task_id,
        )
    )


@router.post(
    "/sources/{source_code}/strategy-repairs/generate",
    response_model=MarketStrategyRepairCandidate,
)
def generate_strategy_repair(
    source_code: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    evidence = MarketStrategyRepairEvidence.model_validate(
        _call(lambda: market_client.get_strategy_repair_evidence(source_code))
    )
    try:
        proposed_strategy = generate_strategy_document(
            evidence,
            db=db,
            user_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _call(
        lambda: market_client.create_strategy_repair(
            source_code,
            proposed_strategy,
            admin.username,
            "ai",
        )
    )


@router.post(
    "/strategy-repairs/{candidate_id}/replay",
    response_model=MarketStrategyRepairCandidate,
)
def replay_strategy_repair(
    candidate_id: int,
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.replay_strategy_repair(candidate_id))


@router.post(
    "/strategy-repairs/{candidate_id}/approve",
    response_model=MarketStrategyRepairCandidate,
)
def approve_strategy_repair(
    candidate_id: int,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.approve_strategy_repair(candidate_id, admin.username)
    )


@router.post(
    "/strategy-repairs/{candidate_id}/rollback",
    response_model=MarketStrategyRepairCandidate,
)
def rollback_strategy_repair(
    candidate_id: int,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.rollback_strategy_repair(candidate_id, admin.username)
    )


@router.get("/gate", response_model=MarketGateSettings)
def get_gate_settings(
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(market_client.get_gate_settings)


@router.put("/gate/draft", response_model=MarketGateSettings)
def save_gate_draft(
    request: MarketGateDraftRequest,
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(
        lambda: market_client.save_gate_draft(
            request.configuration, request.change_note, admin.username
        )
    )


@router.post("/gate/draft/preview", response_model=MarketGateSettings)
def preview_gate_draft(
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(market_client.preview_gate_draft)


@router.post("/gate/draft/publish", response_model=MarketGateSettings)
def publish_gate_draft(
    admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.publish_gate_draft(admin.username))
