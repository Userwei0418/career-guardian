from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.core.config import settings
from app.models.user import User
from app.schemas.market_admin import (
    MarketCrawlTask,
    MarketCrawlTaskList,
    MarketDataSourceList,
    MarketGateDraftRequest,
    MarketGateSettings,
)
from app.services.market_admin_client import MarketAdminClient, MarketAdminError


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


@router.get("/tasks", response_model=MarketCrawlTaskList)
def list_tasks(
    limit: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.list_tasks(limit))


@router.post("/sources/{source_code}/runs", response_model=MarketCrawlTask)
def run_source(
    source_code: str,
    _admin: User = Depends(require_admin),
    market_client: MarketAdminClient = Depends(get_market_admin_client),
):
    return _call(lambda: market_client.run_source(source_code))


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
