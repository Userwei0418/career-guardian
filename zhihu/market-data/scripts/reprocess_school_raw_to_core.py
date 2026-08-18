#!/usr/bin/env python3
"""Replay school Raw records through the unified MySQL Core pipeline.

The command is MySQL-only and defaults to a read-only preview.  It is intended
for school collection tasks produced by the former Raw-only compatibility
path.  Existing HTML, text and processing evidence stay in Raw; apply mode only
changes gate/processing state and creates the normal Core lineage or quarantine
result.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import URL, make_url


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
BACKEND_ENV = PROJECT_ROOT / "zhihu-backend" / ".env"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from market_data.db import make_engine, make_session_factory
from market_data.models.raw import CrawlLogEntry, CrawlTask, DataSource, RawRecord
from market_data.services.raw_processing import BackendSemanticNormalizer
from market_data.services.raw_promotion import promote_task_records


SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def env_value(name: str) -> str:
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


def mysql_url(value: str, label: str) -> URL:
    if not value:
        raise SystemExit(f"missing {label}")
    url = make_url(value)
    if not url.drivername.startswith("mysql"):
        raise SystemExit(f"{label} must use MySQL, got {url.drivername}")
    if not url.database or not SAFE_IDENTIFIER.fullmatch(url.database):
        raise SystemExit(f"{label} has an unsafe or missing database name")
    return url


def raw_url(core_url: URL) -> URL:
    configured = env_value("MARKET_RAW_DATABASE_URL")
    return mysql_url(configured, "MARKET_RAW_DATABASE_URL") if configured else core_url.set(database="market_raw")


def semantic_normalizer():
    enabled = env_value("MARKET_SEMANTIC_NORMALIZATION_ENABLED") or "true"
    token = env_value("MARKET_INTERNAL_TOKEN")
    if enabled.lower() not in {"1", "true", "yes", "on"} or not token:
        return None
    return BackendSemanticNormalizer(
        env_value("MARKET_SEMANTIC_NORMALIZATION_URL")
        or "http://127.0.0.1:8000/api/internal/market/semantic-normalize",
        token,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a school Raw task through the unified Core pipeline")
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor", default="admin-school-raw-reprocess")
    args = parser.parse_args()

    core_database_url = mysql_url(
        env_value("MARKET_CORE_DATABASE_URL") or env_value("DATABASE_URL"),
        "MARKET_CORE_DATABASE_URL or DATABASE_URL",
    )
    raw_database_url = raw_url(core_database_url)
    raw_engine = make_engine(raw_database_url.render_as_string(hide_password=False))
    core_engine = make_engine(core_database_url.render_as_string(hide_password=False))
    raw_factory = make_session_factory(raw_engine)
    core_factory = make_session_factory(core_engine)
    try:
        with raw_factory() as raw_session:
            task = raw_session.get(CrawlTask, args.task_id)
            if task is None:
                raise SystemExit(f"unknown crawl task: {args.task_id}")
            source = raw_session.get(DataSource, task.source_id)
            if source is None or source.source_kind != "school_announcement":
                raise SystemExit("task does not belong to a school announcement source")
            if not isinstance((source.config or {}).get("promotion_mapping"), dict):
                raise SystemExit("school source has no promotion_mapping")
            status_counts = dict(
                raw_session.execute(
                    select(RawRecord.validation_status, func.count(RawRecord.id))
                    .where(RawRecord.crawl_task_id == task.id)
                    .group_by(RawRecord.validation_status)
                ).all()
            )
            candidates = list(
                raw_session.scalars(
                    select(RawRecord)
                    .where(
                        RawRecord.crawl_task_id == task.id,
                        RawRecord.validation_status.in_(["raw_only", "pending_gate"]),
                    )
                    .order_by(RawRecord.id)
                )
            )
            preview = {
                "mode": "apply" if args.apply else "preview",
                "task_id": task.id,
                "source_code": source.code,
                "source_name": source.name,
                "task_status": task.status,
                "status_counts": status_counts,
                "candidate_records": len(candidates),
                "semantic_normalization": bool(semantic_normalizer()),
            }
            if not args.apply:
                print(json.dumps(preview, ensure_ascii=False, indent=2))
                return 0
            if not candidates:
                print(json.dumps({**preview, "result": "no_candidates"}, ensure_ascii=False, indent=2))
                return 0
            raw_session.add(
                CrawlLogEntry(
                    crawl_task_id=task.id,
                    level="info",
                    event_code="school_raw_reprocessing_started",
                    message="school Raw records are being replayed through the unified quality gate",
                    context={"actor": args.actor, "candidates": len(candidates)},
                )
            )
            for record in candidates:
                if record.validation_status == "raw_only":
                    record.validation_status = "pending_gate"
                    record.validation_error = None
                    record.processing_status = "pending"
                    record.processing_version = None
            raw_session.commit()
            with core_factory() as core_session:
                summary = promote_task_records(
                    raw_session,
                    core_session,
                    source,
                    task.id,
                    semantic_normalizer=semantic_normalizer(),
                )
            task = raw_session.get(CrawlTask, task.id)
            assert task is not None
            snapshot = dict(task.progress_snapshot or {})
            stages = dict(snapshot.get("stages") or {})
            stages["standardization_gate"] = {
                "status": "completed",
                "total": len(candidates),
                "completed": len(candidates),
                "promoted": summary.promoted,
                "quarantined": summary.quarantined,
            }
            snapshot.update({"stage": "completed", "overall_percent": 100, "indeterminate": False, "stages": stages})
            task.progress_snapshot = snapshot
            raw_session.add(
                CrawlLogEntry(
                    crawl_task_id=task.id,
                    level="info" if summary.quarantined == 0 else "warning",
                    event_code="school_raw_reprocessing_completed",
                    message="school Raw records completed the unified quality gate replay",
                    context={
                        "actor": args.actor,
                        "candidates": len(candidates),
                        "promoted": summary.promoted,
                        "quarantined": summary.quarantined,
                    },
                )
            )
            raw_session.commit()
            print(json.dumps({**preview, "promoted": summary.promoted, "quarantined": summary.quarantined}, ensure_ascii=False, indent=2))
            return 0
    finally:
        raw_engine.dispose()
        core_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
