#!/usr/bin/env python3
"""Run the explicit Pin staging-to-Core cleaning and quality gate."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.db import make_engine
from market_data.models.staging import LegacyImportBatch
from market_data.services.legacy_promotion import promote_legacy_batch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--staging-database-url", default=os.getenv("MARKET_STAGING_DATABASE_URL")
    )
    parser.add_argument("--core-database-url", default=os.getenv("MARKET_CORE_DATABASE_URL"))
    parser.add_argument("--staging-batch-id", type=int)
    parser.add_argument("--chunk-size", type=int, default=500)
    args = parser.parse_args()
    if not args.staging_database_url or not args.core_database_url:
        parser.error("staging/core database URL arguments or environment variables are required")

    staging_engine = make_engine(args.staging_database_url)
    core_engine = make_engine(args.core_database_url)
    with Session(staging_engine) as staging_session, Session(
        core_engine, expire_on_commit=False
    ) as core_session:
        staging_batch_id = args.staging_batch_id
        if staging_batch_id is None:
            staging_batch_id = staging_session.scalar(
                select(LegacyImportBatch.id)
                .where(LegacyImportBatch.status == "completed")
                .order_by(LegacyImportBatch.id.desc())
                .limit(1)
            )
        if staging_batch_id is None:
            raise RuntimeError("no completed staging batch found")
        result = promote_legacy_batch(
            staging_session,
            core_session,
            staging_batch_id,
            chunk_size=args.chunk_size,
        )
        print(
            f"promotion_batch={result.id} staging_batch={result.staging_batch_id} "
            f"promoted={result.promoted_count} rejected={result.rejected_count} "
            f"duplicates={result.duplicate_count} pipeline={result.pipeline_version}"
        )
    staging_engine.dispose()
    core_engine.dispose()


if __name__ == "__main__":
    main()
