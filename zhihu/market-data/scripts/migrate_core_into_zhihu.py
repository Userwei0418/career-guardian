#!/usr/bin/env python3
"""Copy the certified legacy Core into zhihu.market_* without deleting the source.

The command is intentionally idempotent: rows keep their original primary keys and
are upserted in dependency order. Expanded product fields are restored from the
audited staging payload while certified/normalised fields continue to come from Core.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import Connection, Engine, make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_data.models import core as _core_models  # noqa: F401,E402
from market_data.db import CoreBase  # noqa: E402
from market_data.quality_gate import normalized_text, parse_time, valid_url  # noqa: E402


TABLES = (
    ("job_families", "market_job_families"),
    ("cities", "market_cities"),
    ("skills", "market_skills"),
    ("recruitment_types", "market_recruitment_types"),
    ("companies", "market_companies"),
    ("core_promotion_batches", "market_core_promotion_batches"),
    ("quality_gate_policies", "market_quality_gate_policies"),
    ("jobs", "market_jobs"),
    ("job_sources", "market_job_sources"),
    ("job_skills", "market_job_skills"),
    ("rejected_legacy_jobs", "market_rejected_legacy_jobs"),
)


def as_payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def text_value(payload: dict, key: str, limit: int | None = None) -> str | None:
    value = normalized_text(payload.get(key)) or None
    return value[:limit] if value and limit else value


def payload_map(
    staging: Connection, table_name: str, legacy_column: str, legacy_ids: list[int]
) -> dict[int, dict]:
    if not legacy_ids:
        return {}
    table = Table(table_name, MetaData(), autoload_with=staging)
    rows = staging.execute(
        select(table.c[legacy_column], table.c.legacy_payload).where(
            table.c[legacy_column].in_(legacy_ids)
        )
    )
    return {int(legacy_id): as_payload(payload) for legacy_id, payload in rows}


def enrich_company(row: dict, payload: dict) -> None:
    row.update(
        logo_url=valid_url(payload.get("logo_url")),
        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else [],
    )
    for target, source, limit in (
        ("industry", "industry", 100),
        ("company_type", "company_type", 100),
        ("size_range", "size_range", 100),
        ("headquarters", "headquarters", 255),
        ("description", "description", None),
    ):
        value = text_value(payload, source, limit)
        if value:
            row[target] = value


def enrich_job(row: dict, payload: dict) -> None:
    for target, source, limit in (
        ("department", "department", 255),
        ("job_category", "job_category", 255),
        ("employment_type", "employment_type", 100),
        ("province", "province", 100),
        ("district", "district", 100),
        ("address", "address", 500),
        ("education_requirement", "education_requirement", 255),
        ("education_level", "education_level", 100),
        ("experience_requirement", "experience_requirement", 255),
        ("responsibilities", "job_responsibilities", None),
        ("benefits", "benefits", None),
        ("major_requirement", "major_requirement", None),
        ("language_requirement", "language_requirement", 500),
        ("certificate_requirement", "certificate_requirement", 500),
        ("work_time", "work_time", 255),
        ("salary_payment", "salary_payment", 100),
        ("industry_requirement", "industry_requirement", 500),
        ("job_level", "job_level", 100),
        ("salary_text", "salary_text", 255),
    ):
        row[target] = text_value(payload, source, limit)
    row["experience_min_months"] = payload.get("experience_min_months")
    row["experience_max_months"] = payload.get("experience_max_months")
    row["apply_url"] = valid_url(payload.get("apply_url"))
    row["detail_url"] = valid_url(payload.get("detail_url"))
    row["deadline_at"] = parse_time(payload.get("deadline_at"))


def upsert(connection: Connection, table: Table, rows: list[dict]) -> None:
    if not rows:
        return
    statement = mysql_insert(table).values(rows)
    updates = {
        column.name: statement.inserted[column.name]
        for column in table.columns
        if not column.primary_key
    }
    connection.execute(statement.on_duplicate_key_update(**updates))


def copy_table(
    source_engine: Engine,
    target_engine: Engine,
    staging_engine: Engine,
    source_name: str,
    target_name: str,
    chunk_size: int,
) -> tuple[int, int]:
    source = Table(source_name, MetaData(), autoload_with=source_engine)
    target = CoreBase.metadata.tables[target_name]
    target_columns = {column.name for column in target.columns}
    last_id = 0
    while True:
        with source_engine.connect() as source_connection:
            chunk = [
                dict(item)
                for item in source_connection.execute(
                    select(source)
                    .where(source.c.id > last_id)
                    .order_by(source.c.id)
                    .limit(chunk_size)
                ).mappings()
            ]
        if not chunk:
            break
        last_id = int(chunk[-1]["id"])
        rows = [{key: value for key, value in item.items() if key in target_columns} for item in chunk]
        with staging_engine.connect() as staging:
            if source_name == "companies":
                payloads = payload_map(
                    staging,
                    "legacy_company_records",
                    "legacy_company_id",
                    [int(item["legacy_company_id"]) for item in rows if item.get("legacy_company_id")],
                )
                for item in rows:
                    enrich_company(item, payloads.get(int(item.get("legacy_company_id") or 0), {}))
            elif source_name == "jobs":
                payloads = payload_map(
                    staging,
                    "legacy_job_records",
                    "legacy_job_id",
                    [int(item["legacy_job_id"]) for item in rows if item.get("legacy_job_id")],
                )
                for item in rows:
                    enrich_job(item, payloads.get(int(item.get("legacy_job_id") or 0), {}))
        with target_engine.begin() as target_connection:
            upsert(target_connection, target, rows)

    with source_engine.connect() as source_connection, target_engine.connect() as target_connection:
        source_count = int(source_connection.scalar(select(func.count()).select_from(source)) or 0)
        target_count = int(target_connection.scalar(select(func.count()).select_from(target)) or 0)
    return source_count, target_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-core-url", default=os.getenv("LEGACY_MARKET_CORE_DATABASE_URL"))
    parser.add_argument("--target-zhihu-url", default=os.getenv("MARKET_CORE_DATABASE_URL"))
    parser.add_argument("--staging-url", default=os.getenv("MARKET_STAGING_DATABASE_URL"))
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not all((args.source_core_url, args.target_zhihu_url, args.staging_url)):
        parser.error("source Core, target zhihu and staging database URLs are required")
    if make_url(args.target_zhihu_url).database != "zhihu":
        parser.error("target database must be the zhihu primary database")
    if not args.execute:
        parser.error("pass --execute after confirming the target zhihu database")

    source_engine = create_engine(args.source_core_url, pool_pre_ping=True)
    target_engine = create_engine(args.target_zhihu_url, pool_pre_ping=True)
    staging_engine = create_engine(args.staging_url, pool_pre_ping=True)
    try:
        results = {}
        for source_name, target_name in TABLES:
            source_count, target_count = copy_table(
                source_engine,
                target_engine,
                staging_engine,
                source_name,
                target_name,
                args.chunk_size,
            )
            if source_count != target_count:
                raise RuntimeError(
                    f"count mismatch {source_name}={source_count} {target_name}={target_count}"
                )
            results[target_name] = target_count
            print(f"{source_name} -> {target_name}: {target_count}", flush=True)
        print(json.dumps({"status": "completed", "tables": results}, ensure_ascii=False))
    finally:
        source_engine.dispose()
        target_engine.dispose()
        staging_engine.dispose()


if __name__ == "__main__":
    main()
