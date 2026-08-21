from __future__ import annotations

import logging
from threading import Event, Thread

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.personal_attachment_service import (
    claim_attachment_cleanup_jobs,
    enqueue_orphaned_attachment_cleanup,
    process_attachment_cleanup_jobs,
)


logger = logging.getLogger(__name__)


class PersonalAttachmentCleanupWorker:
    """Recover durable cleanup jobs and aged filesystem orphans after crashes."""

    def __init__(self, interval_seconds: float | None = None) -> None:
        self._interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.ATTACHMENT_CLEANUP_INTERVAL_SECONDS
        )
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="personal-attachment-cleanup",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:  # pragma: no cover - daemon protection
                logger.exception("personal attachment cleanup loop failed")
            self._stop.wait(self._interval_seconds)

    def run_once(self) -> int:
        with SessionLocal() as db:
            enqueue_orphaned_attachment_cleanup(
                db,
                grace_seconds=settings.ATTACHMENT_ORPHAN_GRACE_SECONDS,
            )
            job_ids = claim_attachment_cleanup_jobs(db)
            if not job_ids:
                return 0
            report = process_attachment_cleanup_jobs(db, job_ids)
            return len(report["completed_ids"])
