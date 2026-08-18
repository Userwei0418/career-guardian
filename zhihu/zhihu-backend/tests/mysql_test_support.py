"""Shared guardrails for tests that mutate a MySQL database.

Database integration tests are intentionally opt-in.  They only run when
``CAREER_GUARDIAN_TEST_DATABASE_URL`` points at an explicitly named test
schema; the normal application ``DATABASE_URL`` is never reused implicitly.
"""

from __future__ import annotations

import os
import unittest

from sqlalchemy.engine import make_url


_RAW_TEST_DATABASE_URL = os.getenv("CAREER_GUARDIAN_TEST_DATABASE_URL", "").strip()
_DISABLED_DATABASE_URL = (
    "mysql+pymysql://test_disabled:test_disabled@127.0.0.1:3306/"
    "career_guardian_test_disabled"
)
_FORBIDDEN_DATABASES = {"zhihu", "market_raw", "pin_legacy_staging"}


def _validate_test_database_url(value: str) -> tuple[bool, str]:
    if not value:
        return False, "未设置 CAREER_GUARDIAN_TEST_DATABASE_URL，跳过 MySQL 集成测试"
    try:
        parsed = make_url(value)
    except Exception as exc:  # pragma: no cover - defensive configuration guard
        return False, f"CAREER_GUARDIAN_TEST_DATABASE_URL 无效：{exc}"
    if parsed.drivername not in {"mysql", "mysql+pymysql"}:
        return False, "测试数据库必须使用 MySQL/PyMySQL"
    database = (parsed.database or "").lower()
    if database in _FORBIDDEN_DATABASES:
        return False, f"禁止对正式数据库 {database} 执行测试"
    if "test" not in database:
        return False, "测试数据库名称必须包含 test"
    return True, ""


MYSQL_TEST_ENABLED, MYSQL_TEST_REASON = _validate_test_database_url(
    _RAW_TEST_DATABASE_URL
)
MYSQL_TEST_DATABASE_URL = (
    _RAW_TEST_DATABASE_URL if MYSQL_TEST_ENABLED else _DISABLED_DATABASE_URL
)

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = MYSQL_TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "mysql-test-secret-only-not-for-production")
# Integration tests must never inherit local production AI credentials.  Individual
# tests that exercise an AI path install an explicit mock or database configuration.
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["IMAGE_API_KEY"] = ""
os.environ["MARKET_INTERNAL_TOKEN"] = ""
os.environ["MARKET_STRATEGY_AUTO_REPAIR_ENABLED"] = "false"

mysql_test = unittest.skipUnless(MYSQL_TEST_ENABLED, MYSQL_TEST_REASON)
