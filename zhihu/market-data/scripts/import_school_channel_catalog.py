#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from market_data.db import make_engine, make_session_factory
from market_data.school_channel_catalog import (
    CATALOG_PATH,
    load_school_channel_catalog,
    migrate_school_channel_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Career Guardian school announcement catalog"
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--approve-and-enable",
        action="store_true",
        help="Record administrator approval and enable only ready sources",
    )
    parser.add_argument("--actor", default="school-catalog-import")
    args = parser.parse_args()
    catalog = load_school_channel_catalog(args.catalog)
    sources = sum(
        len((row.get("configuration") or {}).get("urls") or {})
        for row in catalog["schools"]
    )
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "catalog_version": catalog["schema_version"],
                    "school_configs": len(catalog["schools"]),
                    "sources": sources,
                    "governance": (
                        "approved-ready-enabled-unified-job-pipeline"
                        if args.approve_and_enable
                        else "disabled-pending-unified-job-pipeline"
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0
    database_url = os.getenv("MARKET_RAW_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("MARKET_RAW_DATABASE_URL is required with --apply")
    engine = make_engine(database_url)
    try:
        with make_session_factory(engine)() as session:
            result = migrate_school_channel_catalog(
                session,
                catalog,
                approve_and_enable=args.approve_and_enable,
                actor=args.actor,
            )
    finally:
        engine.dispose()
    print(json.dumps({"mode": "applied", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
