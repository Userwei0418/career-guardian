#!/usr/bin/env python3
"""Refresh user-facing market overview snapshots after Core data changes."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_data.db import make_engine
from market_data.models.core import Job, JobFamily, MarketInsightSnapshot
from market_data.providers import CoreMarketProvider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-database-url", default=os.getenv("MARKET_CORE_DATABASE_URL"))
    args = parser.parse_args()
    if not args.core_database_url:
        parser.error("MARKET_CORE_DATABASE_URL or --core-database-url is required")

    engine = make_engine(args.core_database_url)
    provider = CoreMarketProvider(args.core_database_url)
    try:
        with Session(engine) as session:
            family_names = list(session.scalars(select(JobFamily.name).order_by(JobFamily.id)))
            source_updated_at = session.scalar(select(func.max(Job.updated_at)))
        scopes: list[str | None] = [None, *family_names]
        for family in scopes:
            overview = provider.compute_overview(family)
            scope_key = f"job_family:{family.strip()}" if family else "market"
            with Session(engine) as session:
                snapshot = session.scalar(
                    select(MarketInsightSnapshot).where(
                        MarketInsightSnapshot.scope_key == scope_key
                    )
                )
                if snapshot is None:
                    snapshot = MarketInsightSnapshot(scope_key=scope_key)
                    session.add(snapshot)
                snapshot.payload = overview.model_dump(mode="json")
                snapshot.source_updated_at = source_updated_at
                snapshot.generated_at = overview.generated_at.replace(tzinfo=None)
                session.commit()
            print(f"refreshed {scope_key}: {overview.job_count}", flush=True)
    finally:
        provider.close()
        engine.dispose()


if __name__ == "__main__":
    main()
