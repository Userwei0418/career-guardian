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
from market_data.pin_migration import migrate_pin_company_rows, read_crawl_company_rows


ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Pin company recruitment channels")
    parser.add_argument("--backup", type=Path, default=ROOT / "Pin" / "db" / "backup.sql")
    parser.add_argument("--schema", type=Path, default=ROOT / "Pin" / "db" / "database_init.sql")
    parser.add_argument(
        "--parser-root",
        type=Path,
        default=ROOT / "Pin" / "crawler" / "auto_gen_com" / "gen",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = read_crawl_company_rows(args.backup, args.schema)
    urls = sum(len((json.loads(row["json_config"]) if isinstance(row.get("json_config"), str) else row.get("json_config") or {}).get("urls") or {}) for row in rows)
    if not args.apply:
        print(json.dumps({"mode": "preview", "company_configs": len(rows), "channels": urls}, ensure_ascii=False))
        return 0
    database_url = os.getenv("MARKET_RAW_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("MARKET_RAW_DATABASE_URL is required with --apply")
    engine = make_engine(database_url)
    try:
        with make_session_factory(engine)() as session:
            result = migrate_pin_company_rows(session, rows, parser_root=args.parser_root)
    finally:
        engine.dispose()
    print(json.dumps({"mode": "applied", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
