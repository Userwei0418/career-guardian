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

from market_data.company_channel_catalog import (
    CATALOG_PATH,
    load_company_channel_catalog,
    migrate_company_channel_catalog,
)
from market_data.db import make_engine, make_session_factory


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Career Guardian company-channel catalog")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    catalog = load_company_channel_catalog(args.catalog)
    channels = sum(
        len((row.get("configuration") or {}).get("urls") or {})
        for row in catalog["companies"]
    )
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "catalog_version": catalog["schema_version"],
                    "company_configs": len(catalog["companies"]),
                    "channels": channels,
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
            result = migrate_company_channel_catalog(session, catalog)
    finally:
        engine.dispose()
    print(json.dumps({"mode": "applied", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
