#!/usr/bin/env python3
"""Import Pin jobs into the isolated staging model with an explicit safety gate."""

from __future__ import annotations

import argparse
import codecs
import hashlib
import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.db import make_engine
from market_data.models.staging import LegacyImportBatch, LegacyJobRecord


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
    imported = 0

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

        def on_row(table: str, values: list) -> None:
            nonlocal imported
            if table != "jobs":
                return
            names = columns.get(table, [])
            if len(names) != len(values):
                raise RuntimeError("jobs column count does not match dump DDL")
            row = dict(zip(names, values))
            session.add(
                LegacyJobRecord(
                    batch_id=batch.id,
                    legacy_job_id=row["id"],
                    title=row.get("title"),
                    company_id=row.get("company_id"),
                    source_site=row.get("source_site"),
                    source_job_id=row.get("source_job_id"),
                    published_at=AUDIT.parse_time(row.get("published_at")),
                    legacy_payload=row,
                )
            )
            imported += 1
            if imported % 500 == 0:
                session.flush()

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
            batch.status = "completed"
            batch.table_counts = {"jobs": imported}
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
    return batch_id, imported


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--mode", choices=["fixture", "formal"], default="fixture")
    parser.add_argument("--approval-sha")
    args = parser.parse_args()
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
