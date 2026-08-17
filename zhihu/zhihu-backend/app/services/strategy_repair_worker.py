from __future__ import annotations

import logging
from threading import Event, Thread
from uuid import uuid4

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.market_admin import (
    MarketStrategyRepairCandidate,
    MarketStrategyRepairEvidence,
)
from app.services.market_admin_client import MarketAdminClient, MarketAdminError
from app.services.strategy_repair_service import generate_strategy_document


logger = logging.getLogger(__name__)


class StrategyRepairWorker:
    """Generate declarative parser candidates without activating them.

    Collection failures are queued by market-data. This worker only turns the
    captured page evidence into a candidate. Replay and activation remain
    explicit administrator actions.
    """

    def __init__(self) -> None:
        self._stop = Event()
        self._thread: Thread | None = None
        self._actor = f"system:auto-repair:{uuid4().hex[:12]}"
        self._client = MarketAdminClient(
            settings.MARKET_API_URL,
            settings.MARKET_INTERNAL_TOKEN,
            max(settings.MARKET_API_TIMEOUT_SECONDS, 70),
        )

    def start(self) -> None:
        if not settings.MARKET_STRATEGY_AUTO_REPAIR_ENABLED:
            logger.info("automatic strategy repair is disabled")
            return
        if not settings.MARKET_INTERNAL_TOKEN:
            logger.warning("automatic strategy repair skipped: market token is missing")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="market-strategy-repair",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:  # pragma: no cover - protects the daemon loop
                logger.exception("automatic strategy repair loop failed")
            self._stop.wait(settings.MARKET_STRATEGY_AUTO_REPAIR_INTERVAL_SECONDS)

    def run_once(self) -> int:
        try:
            self._client.backfill_strategy_repairs(limit=200)
        except MarketAdminError:
            logger.exception("failed to backfill strategy repair candidates")
        candidates = self._client.list_strategy_repairs(limit=200)
        queued = [
            item
            for item in reversed(candidates)
            if item.status in {"ai_pending", "ai_generating"}
            or (
                item.status == "ai_failed"
                and bool(item.replay_summary.get("generation_retryable"))
            )
        ][:3]
        processed = 0
        for candidate in queued:
            if self._process(candidate):
                processed += 1
        return processed

    def _process(self, candidate: MarketStrategyRepairCandidate) -> bool:
        try:
            current = self._client.claim_strategy_repair(
                candidate.id,
                self._actor,
                lease_seconds=settings.MARKET_STRATEGY_AUTO_REPAIR_LEASE_SECONDS,
                max_attempts=settings.MARKET_STRATEGY_AUTO_REPAIR_MAX_ATTEMPTS,
            )
        except MarketAdminError as exc:
            if exc.status_code != 409:
                logger.warning("failed to claim strategy repair %s: %s", candidate.id, exc.message)
            return False
        try:
            evidence = MarketStrategyRepairEvidence.model_validate(
                self._client.get_strategy_repair_evidence(
                    current.source_code,
                    current.failure_task_id,
                )
            )
            with SessionLocal() as db:
                proposed_strategy = generate_strategy_document(
                    evidence,
                    db=db,
                    user_id=None,
                )
            self._client.complete_strategy_repair(
                current.id,
                self._actor,
                proposed_strategy,
            )
            return True
        except Exception as exc:
            message = self._safe_error(exc)
            try:
                self._client.fail_strategy_repair(
                    current.id,
                    self._actor,
                    message,
                    retry_delay_seconds=settings.MARKET_STRATEGY_AUTO_REPAIR_RETRY_DELAY_SECONDS,
                    max_attempts=settings.MARKET_STRATEGY_AUTO_REPAIR_MAX_ATTEMPTS,
                )
            except MarketAdminError:
                logger.exception("failed to persist strategy repair failure")
            return True

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, MarketAdminError):
            return exc.message[:800]
        message = str(exc).strip() or type(exc).__name__
        return message[:800]
