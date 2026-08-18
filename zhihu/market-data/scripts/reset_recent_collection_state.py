#!/usr/bin/env python3
"""Preview or reset recent collection acceptance data in formal MySQL.

The command is intentionally MySQL-only and defaults to a dry run. It removes
new collection records created during the requested local-date window, resets
derived collection state, and returns sources to a non-running governance
state without deleting source configuration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT / "zhihu-backend" / ".env"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if BACKEND_ENV.exists():
        for raw_line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, candidate = line.split("=", 1)
            if key.strip() == name:
                return candidate.strip().strip('"').strip("'")
    return ""


def _mysql_url(raw_value: str, label: str) -> URL:
    if not raw_value:
        raise SystemExit(f"missing {label}")
    url = make_url(raw_value)
    if not url.drivername.startswith("mysql"):
        raise SystemExit(f"{label} must use MySQL, got {url.drivername}")
    if not url.database or not SAFE_IDENTIFIER.fullmatch(url.database):
        raise SystemExit(f"{label} has an unsafe or missing database name")
    return url


def _derive_raw_url(core_url: URL) -> URL:
    configured = _env_value("MARKET_RAW_DATABASE_URL")
    if configured:
        return _mysql_url(configured, "MARKET_RAW_DATABASE_URL")
    return core_url.set(database="market_raw")


def _cutoff_utc_naive(days: int) -> datetime:
    local_now = datetime.now(LOCAL_TZ)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_cutoff = local_midnight - timedelta(days=days - 1)
    return local_cutoff.astimezone(timezone.utc).replace(tzinfo=None)


def _scalar(connection, sql: str, params: dict | None = None) -> int:
    return int(connection.execute(text(sql), params or {}).scalar_one())


def _preview(connection, raw_db: str, core_db: str, cutoff: datetime) -> dict:
    params = {"cutoff": cutoff}
    return {
        "cutoff_utc": cutoff.isoformat(sep=" "),
        "cutoff_local": cutoff.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).isoformat(),
        "recent": {
            "crawl_tasks": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.crawl_tasks WHERE created_at >= :cutoff", params),
            "crawl_batches": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.crawl_batches WHERE created_at >= :cutoff", params),
            "raw_records": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.raw_records WHERE created_at >= :cutoff", params),
            "raw_processing_attempts": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.raw_processing_attempts WHERE created_at >= :cutoff", params),
            "crawl_log_entries": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.crawl_log_entries WHERE created_at >= :cutoff", params),
            "strategy_repair_candidates": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.strategy_repair_candidates WHERE created_at >= :cutoff", params),
            "market_jobs": _scalar(connection, f"SELECT COUNT(*) FROM `{core_db}`.market_jobs WHERE created_at >= :cutoff", params),
            "market_job_sources": _scalar(connection, f"SELECT COUNT(*) FROM `{core_db}`.market_job_sources WHERE created_at >= :cutoff", params),
            "ai_invocation_logs": _scalar(connection, f"SELECT COUNT(*) FROM `{core_db}`.ai_invocation_logs WHERE created_at >= :cutoff", params),
        },
        "reset_state": {
            "active_tasks": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.crawl_tasks WHERE status IN ('pending', 'running', 'cancelling')"),
            "enabled_sources": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.data_sources WHERE enabled = 1"),
            "enabled_companies": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.recruitment_companies WHERE enabled = 1"),
            "collection_checkpoints": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.source_collection_checkpoints"),
            "operational_states": _scalar(connection, f"SELECT COUNT(*) FROM `{raw_db}`.source_operational_states"),
            "market_insight_snapshots": _scalar(connection, f"SELECT COUNT(*) FROM `{core_db}`.market_insight_snapshots"),
        },
    }


def _apply(connection, raw_db: str, core_db: str, cutoff: datetime) -> dict:
    params = {"cutoff": cutoff}
    statements = [
        ("cancel_active_tasks", f"UPDATE `{raw_db}`.crawl_tasks SET status = 'cancelled', completed_at = COALESCE(completed_at, UTC_TIMESTAMP()), error_type = 'AdminReset', error_message = 'Reset before a new acceptance run' WHERE status IN ('pending', 'running', 'cancelling')"),
        ("delete_recent_job_sources", f"DELETE s FROM `{core_db}`.market_job_sources s LEFT JOIN `{core_db}`.market_jobs j ON j.id = s.job_id WHERE s.created_at >= :cutoff OR j.created_at >= :cutoff"),
        ("delete_recent_job_skills", f"DELETE s FROM `{core_db}`.market_job_skills s JOIN `{core_db}`.market_jobs j ON j.id = s.job_id WHERE j.created_at >= :cutoff"),
        ("delete_recent_jobs", f"DELETE FROM `{core_db}`.market_jobs WHERE created_at >= :cutoff"),
        ("delete_market_insight_snapshots", f"DELETE FROM `{core_db}`.market_insight_snapshots"),
        ("delete_recent_ai_logs", f"DELETE FROM `{core_db}`.ai_invocation_logs WHERE created_at >= :cutoff"),
        ("delete_recent_repair_candidates", f"DELETE FROM `{raw_db}`.strategy_repair_candidates WHERE created_at >= :cutoff"),
        ("delete_recent_processing_attempts", f"DELETE FROM `{raw_db}`.raw_processing_attempts WHERE created_at >= :cutoff OR crawl_task_id IN (SELECT id FROM `{raw_db}`.crawl_tasks WHERE created_at >= :cutoff)"),
        ("delete_recent_crawl_logs", f"DELETE FROM `{raw_db}`.crawl_log_entries WHERE created_at >= :cutoff OR crawl_task_id IN (SELECT id FROM `{raw_db}`.crawl_tasks WHERE created_at >= :cutoff)"),
        ("clear_checkpoints", f"DELETE FROM `{raw_db}`.source_collection_checkpoints"),
        ("clear_operational_states", f"DELETE FROM `{raw_db}`.source_operational_states"),
        ("delete_recent_raw_records", f"DELETE FROM `{raw_db}`.raw_records WHERE created_at >= :cutoff OR crawl_task_id IN (SELECT id FROM `{raw_db}`.crawl_tasks WHERE created_at >= :cutoff)"),
        ("delete_recent_tasks", f"DELETE FROM `{raw_db}`.crawl_tasks WHERE created_at >= :cutoff"),
        ("delete_recent_batches", f"DELETE FROM `{raw_db}`.crawl_batches WHERE created_at >= :cutoff"),
        ("disable_sources", f"UPDATE `{raw_db}`.data_sources SET enabled = 0, terms_review_status = CASE WHEN terms_review_status = 'rejected' THEN 'rejected' ELSE 'pending' END, terms_reviewed_by = CASE WHEN terms_review_status = 'rejected' THEN terms_reviewed_by ELSE NULL END, terms_reviewed_at = CASE WHEN terms_review_status = 'rejected' THEN terms_reviewed_at ELSE NULL END, terms_review_note = CASE WHEN terms_review_status = 'rejected' THEN terms_review_note ELSE NULL END WHERE enabled = 1 OR terms_review_status = 'approved'"),
        ("disable_companies", f"UPDATE `{raw_db}`.recruitment_companies SET enabled = 0 WHERE enabled = 1"),
    ]
    changed: dict[str, int] = {}
    for name, sql in statements:
        result = connection.execute(text(sql), params)
        changed[name] = max(0, int(result.rowcount or 0))
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2, help="Local calendar days to clear; default: 2")
    parser.add_argument("--apply", action="store_true", help="Apply the reset; otherwise preview only")
    args = parser.parse_args()
    if args.days < 1 or args.days > 31:
        raise SystemExit("--days must be between 1 and 31")

    core_url = _mysql_url(_env_value("DATABASE_URL") or _env_value("MARKET_CORE_DATABASE_URL"), "DATABASE_URL")
    raw_url = _derive_raw_url(core_url)
    if (core_url.host, core_url.port, core_url.username) != (raw_url.host, raw_url.port, raw_url.username):
        raise SystemExit("core and raw databases must use the same MySQL connection for an atomic reset")

    cutoff = _cutoff_utc_naive(args.days)
    engine = create_engine(core_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            before = _preview(connection, raw_url.database, core_url.database, cutoff)
            changed = _apply(connection, raw_url.database, core_url.database, cutoff) if args.apply else {}
            after = _preview(connection, raw_url.database, core_url.database, cutoff) if args.apply else before
        print(json.dumps({"mode": "apply" if args.apply else "preview", "before": before, "changed": changed, "after": after}, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
