#!/usr/bin/env python3
"""Create and migrate the single MySQL runtime, optionally importing Pin stock."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT_HINT = Path(__file__).resolve().parents[1]
BACKEND_PYTHON_HINT = REPO_ROOT_HINT / "zhihu/zhihu-backend/.venv/bin/python"

try:
    from sqlalchemy import create_engine, text
except ModuleNotFoundError as exc:
    backend_venv = BACKEND_PYTHON_HINT.parent.parent.resolve()
    if BACKEND_PYTHON_HINT.exists() and Path(sys.prefix).resolve() != backend_venv:
        os.execv(
            str(BACKEND_PYTHON_HINT),
            [str(BACKEND_PYTHON_HINT), str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    raise RuntimeError("缺少 SQLAlchemy，请先安装职护后端依赖") from exc

from mysql_runtime import BACKEND_DIR, DATABASES, MARKET_DIR, REPO_ROOT, domain_url, mysql_base_url, runtime_environment


BACKEND_PYTHON = BACKEND_DIR / ".venv/bin/python"
MARKET_PYTHON = MARKET_DIR / ".venv/bin/python"
PIN_DUMP = REPO_ROOT / "Pin/db/backup.sql"
PIN_SCHEMA = REPO_ROOT / "Pin/db/database_init.sql"


def run(command: list[str], cwd: Path, environment: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def create_databases() -> None:
    engine = create_engine(
        mysql_base_url().set(database="mysql"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as connection:
            for database in DATABASES:
                connection.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS `{database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
    finally:
        engine.dispose()


def migrate(environment: dict[str, str]) -> None:
    run([str(BACKEND_PYTHON), "-m", "alembic", "upgrade", "head"], BACKEND_DIR, environment)
    for domain in ("staging", "raw", "core"):
        run(
            [
                str(MARKET_PYTHON),
                "-m",
                "alembic",
                "-c",
                str(MARKET_DIR / "alembic.ini"),
                "-x",
                f"domain={domain}",
                "upgrade",
                "head",
            ],
            MARKET_DIR,
            environment,
        )


def scalar(database: str, sql: str, params: dict | None = None):
    engine = create_engine(domain_url(database), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return connection.scalar(text(sql), params or {})
    finally:
        engine.dispose()


def import_pin(environment: dict[str, str], approval_sha: str) -> None:
    actual_sha = sha256_file(PIN_DUMP)
    if actual_sha != approval_sha:
        raise RuntimeError("Pin 备份 SHA-256 与显式批准值不一致")
    batch_id = scalar(
        "pin_legacy_staging",
        "SELECT id FROM legacy_import_batches WHERE dump_sha256=:digest LIMIT 1",
        {"digest": actual_sha},
    )
    if batch_id is None:
        import_environment = {**environment, "PIN_LEGACY_IMPORT_APPROVED": "true"}
        run(
            [
                str(MARKET_PYTHON),
                "scripts/import_pin_legacy.py",
                "--dump",
                str(PIN_DUMP),
                "--schema",
                str(PIN_SCHEMA),
                "--mode",
                "formal",
                "--approval-sha",
                approval_sha,
            ],
            MARKET_DIR,
            import_environment,
        )
        batch_id = scalar(
            "pin_legacy_staging",
            "SELECT id FROM legacy_import_batches WHERE dump_sha256=:digest LIMIT 1",
            {"digest": actual_sha},
        )
    run(
        [
            str(MARKET_PYTHON),
            "scripts/promote_pin_legacy.py",
            "--staging-batch-id",
            str(batch_id),
        ],
        MARKET_DIR,
        environment,
    )


def print_summary() -> None:
    policy_version = json.loads(
        (MARKET_DIR / "policies/job_core_v1.json").read_text(encoding="utf-8")
    )["policy_version"]
    metrics = {
        "knowledge_articles": scalar("zhihu", "SELECT COUNT(*) FROM knowledge_articles"),
        "knowledge_categories": scalar(
            "zhihu", "SELECT COUNT(DISTINCT category) FROM knowledge_articles"
        ),
        "staging_jobs": scalar(
            "pin_legacy_staging", "SELECT COUNT(*) FROM legacy_job_records"
        ),
        "core_companies": scalar("market_core", "SELECT COUNT(*) FROM companies"),
        "core_jobs": scalar("market_core", "SELECT COUNT(*) FROM jobs"),
        "core_certified": scalar(
            "market_core",
            "SELECT COUNT(*) FROM jobs WHERE gate_policy_version=:policy_version",
            {"policy_version": policy_version},
        ),
        "core_uncertified": scalar(
            "market_core",
            "SELECT COUNT(*) FROM jobs WHERE gate_policy_version<>:policy_version",
            {"policy_version": policy_version},
        ),
        "core_sources": scalar("market_core", "SELECT COUNT(*) FROM job_sources"),
        "core_rejected": scalar(
            "market_core", "SELECT COUNT(*) FROM rejected_legacy_jobs"
        ),
    }
    print(
        f"mysql_unified_migration gate_policy={policy_version} "
        + " ".join(f"{key}={value}" for key, value in metrics.items())
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-pin", action="store_true")
    parser.add_argument("--approval-sha")
    args = parser.parse_args()
    if args.import_pin and not args.approval_sha:
        parser.error("--import-pin 必须同时提供 --approval-sha")
    if not BACKEND_PYTHON.exists() or not MARKET_PYTHON.exists():
        raise RuntimeError("后端或市场数据 Python 虚拟环境不存在")
    environment = runtime_environment()
    create_databases()
    migrate(environment)
    if args.import_pin:
        import_pin(environment, args.approval_sha)
    print_summary()


if __name__ == "__main__":
    main()
