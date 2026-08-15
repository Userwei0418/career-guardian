#!/usr/bin/env python3
"""Import Pin jobs into the isolated staging model with an explicit safety gate."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import importlib.util
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.db import make_engine
from market_data.models.staging import (
    LegacyCompanyRecord,
    LegacyImportBatch,
    LegacyJobRecord,
    LegacyJobSourceRecord,
    LegacyRawRecord,
)


SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_SPEC = importlib.util.spec_from_file_location(
    "audit_pin_backup", SCRIPT_DIR / "audit_pin_backup.py"
)
assert AUDIT_SPEC and AUDIT_SPEC.loader
AUDIT = importlib.util.module_from_spec(AUDIT_SPEC)
AUDIT_SPEC.loader.exec_module(AUDIT)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def assert_import_allowed(mode: str, actual_sha: str, approval_sha: str | None) -> None:
    if mode == "fixture":
        return
    if os.getenv("PIN_LEGACY_IMPORT_APPROVED") != "true":
        raise RuntimeError("formal import requires PIN_LEGACY_IMPORT_APPROVED=true")
    if approval_sha != actual_sha:
        raise RuntimeError("formal import approval hash does not match the dump")


def import_jobs(
    dump_path: Path,
    schema_path: Path,
    database_url: str,
    mode: str,
    approval_sha: str | None,
) -> tuple[int, int]:
    actual_sha = sha256_file(dump_path)
    assert_import_allowed(mode, actual_sha, approval_sha)
    columns = AUDIT.load_columns(schema_path)
    engine = make_engine(database_url)
    counts: Counter[str] = Counter()

    with Session(engine) as session:
        existing = session.scalar(
            select(LegacyImportBatch).where(LegacyImportBatch.dump_sha256 == actual_sha)
        )
        if existing is not None:
            raise RuntimeError(f"dump already registered as batch {existing.id}")
        batch = LegacyImportBatch(
            dump_sha256=actual_sha,
            source_basename=dump_path.name,
            import_mode=mode,
            status="running",
            started_at=utc_now_naive(),
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)

        buffers: dict[str, list[dict]] = {
            "companies": [],
            "jobs": [],
            "job_sources": [],
            "raw_job_records": [],
        }
        models = {
            "companies": LegacyCompanyRecord,
            "jobs": LegacyJobRecord,
            "job_sources": LegacyJobSourceRecord,
            "raw_job_records": LegacyRawRecord,
        }

        def flush_buffer(table: str) -> None:
            if buffers[table]:
                session.bulk_insert_mappings(models[table], buffers[table])
                buffers[table].clear()

        def on_row(table: str, values: list) -> None:
            if table not in buffers:
                return
            names = columns.get(table, [])
            if len(names) != len(values):
                raise RuntimeError(f"{table} column count does not match dump DDL")
            row = dict(zip(names, values))
            if table == "companies":
                mapping = {
                    "batch_id": batch.id,
                    "legacy_company_id": row["id"],
                    "name": str(row.get("name") or "").strip(),
                    "status": row.get("status"),
                    "legacy_payload": row,
                }
            elif table == "jobs":
                mapping = {
                    "batch_id": batch.id,
                    "legacy_job_id": row["id"],
                    "title": row.get("title"),
                    "company_id": row.get("company_id"),
                    "source_site": row.get("source_site"),
                    "source_job_id": row.get("source_job_id"),
                    "published_at": AUDIT.parse_time(row.get("published_at")),
                    "legacy_payload": row,
                }
            elif table == "job_sources":
                mapping = {
                    "batch_id": batch.id,
                    "legacy_source_id": row["id"],
                    "legacy_job_id": row["job_id"],
                    "source_site": row.get("source_site"),
                    "source_job_id": row.get("source_job_id"),
                    "source_url": row.get("source_url"),
                    "first_seen_at": AUDIT.parse_time(row.get("first_seen_at")),
                    "last_seen_at": AUDIT.parse_time(row.get("last_seen_at")),
                    "legacy_payload": row,
                }
            else:
                mapping = {
                    "batch_id": batch.id,
                    "legacy_raw_id": row["id"],
                    "source_site": row.get("source_site"),
                    "source_job_id": row.get("source_job_id"),
                    "source_url": row.get("source_url"),
                    "fetch_time": AUDIT.parse_time(row.get("fetch_time")),
                    "content_hash": row.get("content_hash"),
                    "raw_title": row.get("raw_title"),
                    "legacy_payload": row,
                }
            buffers[table].append(mapping)
            counts[table] += 1
            if len(buffers[table]) >= 500:
                flush_buffer(table)

        insert_parser = AUDIT.DumpInsertParser(on_row)
        schema_parser = AUDIT.DumpSchemaParser(columns)
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            with dump_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    decoded = decoder.decode(chunk)
                    schema_parser.feed(decoded)
                    insert_parser.feed(decoded)
                tail = decoder.decode(b"", final=True)
                if tail:
                    schema_parser.feed(tail)
                    insert_parser.feed(tail)
            for table in buffers:
                flush_buffer(table)
            batch.status = "completed"
            batch.table_counts = dict(counts)
            batch.completed_at = utc_now_naive()
            session.commit()
        except Exception as exc:
            session.rollback()
            failed_batch = session.get(LegacyImportBatch, batch.id)
            if failed_batch is not None:
                failed_batch.status = "failed"
                failed_batch.error_message = str(exc)[:2000]
                failed_batch.completed_at = utc_now_naive()
                session.commit()
            raise
        batch_id = batch.id
    engine.dispose()
    return batch_id, counts["jobs"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--database-url", default=os.getenv("MARKET_STAGING_DATABASE_URL"))
    parser.add_argument("--mode", choices=["fixture", "formal"], default="fixture")
    parser.add_argument("--approval-sha")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or MARKET_STAGING_DATABASE_URL is required")
    batch_id, count = import_jobs(
        args.dump,
        args.schema,
        args.database_url,
        args.mode,
        args.approval_sha,
    )
    print(f"staging_batch={batch_id} imported_jobs={count} mode={args.mode}")


if __name__ == "__main__":
    main()
