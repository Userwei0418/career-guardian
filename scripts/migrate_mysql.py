#!/usr/bin/env python3
"""Create and migrate the self-contained Career Guardian MySQL runtime."""

from __future__ import annotations

import argparse
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

from mysql_runtime import BACKEND_DIR, DATABASES, MARKET_DIR, domain_url, mysql_base_url, runtime_environment


BACKEND_PYTHON = BACKEND_DIR / ".venv/bin/python"
MARKET_PYTHON = MARKET_DIR / ".venv/bin/python"


def run(command: list[str], cwd: Path, environment: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=environment, check=True)


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


def import_company_channel_catalog(environment: dict[str, str]) -> None:
    """Idempotently load the self-contained Career Guardian channel catalog."""
    run(
        [
            str(MARKET_PYTHON),
            "scripts/import_company_channel_catalog.py",
            "--apply",
        ],
        MARKET_DIR,
        environment,
    )


def import_school_channel_catalog(environment: dict[str, str]) -> None:
    """Idempotently load school sources without enabling them automatically."""
    run(
        [
            str(MARKET_PYTHON),
            "scripts/import_school_channel_catalog.py",
            "--apply",
        ],
        MARKET_DIR,
        environment,
    )


def print_summary() -> None:
    default_policy_version = json.loads(
        (MARKET_DIR / "policies/job_core_v1.json").read_text(encoding="utf-8")
    )["policy_version"]
    policy_version = scalar(
        "zhihu",
        "SELECT policy_version FROM market_quality_gate_policies "
        "WHERE status='active' ORDER BY id DESC LIMIT 1",
    ) or default_policy_version
    metrics = {
        "knowledge_articles": scalar("zhihu", "SELECT COUNT(*) FROM knowledge_articles"),
        "knowledge_categories": scalar(
            "zhihu", "SELECT COUNT(DISTINCT category) FROM knowledge_articles"
        ),
        "staging_jobs": scalar(
            "pin_legacy_staging", "SELECT COUNT(*) FROM legacy_job_records"
        ),
        "core_companies": scalar("zhihu", "SELECT COUNT(*) FROM market_companies"),
        "core_jobs": scalar("zhihu", "SELECT COUNT(*) FROM market_jobs"),
        "core_certified": scalar(
            "zhihu",
            "SELECT COUNT(*) FROM market_jobs WHERE gate_policy_version<>'uncertified'",
        ),
        "core_current_policy": scalar(
            "zhihu",
            "SELECT COUNT(*) FROM market_jobs WHERE gate_policy_version=:policy_version",
            {"policy_version": policy_version},
        ),
        "core_uncertified": scalar(
            "zhihu",
            "SELECT COUNT(*) FROM market_jobs WHERE gate_policy_version='uncertified'",
        ),
        "core_sources": scalar("zhihu", "SELECT COUNT(*) FROM market_job_sources"),
        "core_rejected": scalar(
            "zhihu", "SELECT COUNT(*) FROM market_rejected_legacy_jobs"
        ),
        "collection_companies": scalar(
            "market_raw", "SELECT COUNT(*) FROM recruitment_companies"
        ),
        "collection_channels": scalar(
            "market_raw", "SELECT COUNT(*) FROM data_sources WHERE source_kind='company_channel'"
        ),
        "school_sources": scalar(
            "market_raw", "SELECT COUNT(*) FROM data_sources WHERE source_kind='school_announcement'"
        ),
        "collection_templates": scalar(
            "market_raw", "SELECT COUNT(*) FROM collection_templates"
        ),
    }
    print(
        f"mysql_unified_migration gate_policy={policy_version} "
        + " ".join(f"{key}={value}" for key, value in metrics.items())
    )


def refresh_market_insights(environment: dict[str, str]) -> None:
    run(
        [str(MARKET_PYTHON), "scripts/refresh_market_insights.py"],
        MARKET_DIR,
        environment,
    )


def main() -> None:
    argparse.ArgumentParser().parse_args()
    if not BACKEND_PYTHON.exists() or not MARKET_PYTHON.exists():
        raise RuntimeError("后端或市场数据 Python 虚拟环境不存在")
    environment = runtime_environment()
    create_databases()
    migrate(environment)
    import_company_channel_catalog(environment)
    import_school_channel_catalog(environment)
    refresh_market_insights(environment)
    print_summary()


if __name__ == "__main__":
    main()
