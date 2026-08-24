from __future__ import annotations

import os
import hashlib
import hmac
from pathlib import Path

from sqlalchemy.engine import URL, make_url


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "zhihu/zhihu-backend"
MARKET_DIR = REPO_ROOT / "zhihu/market-data"
BACKEND_ENV = BACKEND_DIR / ".env"
DATABASES = ("zhihu", "pin_legacy_staging", "market_raw")


def load_env_file(path: Path = BACKEND_ENV) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise RuntimeError(f"配置文件不存在：{path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def mysql_base_url() -> URL:
    configured = os.getenv("DATABASE_URL") or load_env_file().get("DATABASE_URL", "")
    url = make_url(configured)
    if not url.drivername.startswith("mysql"):
        raise RuntimeError("职护运行时 DATABASE_URL 必须使用 MySQL；数据库集成测试也必须使用独立的 MySQL 测试库")
    return url


def domain_url(database: str) -> str:
    if database not in DATABASES:
        raise ValueError(f"未知数据库域：{database}")
    return mysql_base_url().set(database=database).render_as_string(hide_password=False)


def runtime_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(load_env_file())
    if not environment.get("MARKET_INTERNAL_TOKEN"):
        jwt_secret = environment.get("JWT_SECRET", "")
        if not jwt_secret:
            raise RuntimeError("JWT_SECRET 未配置，无法派生市场管理内部令牌")
        environment["MARKET_INTERNAL_TOKEN"] = hmac.new(
            jwt_secret.encode("utf-8"),
            b"career-guardian-market-admin-v1",
            hashlib.sha256,
        ).hexdigest()
    environment.update(
        {
            "DATABASE_URL": domain_url("zhihu"),
            "MARKET_STAGING_DATABASE_URL": domain_url("pin_legacy_staging"),
            "MARKET_RAW_DATABASE_URL": domain_url("market_raw"),
            # 清洗后的市场事实属于职护产品主数据，以 market_* 表名隔离。
            "MARKET_CORE_DATABASE_URL": domain_url("zhihu"),
            "MARKET_PROVIDER": "core",
            "PYTHONPATH": os.pathsep.join((str(MARKET_DIR), str(BACKEND_DIR))),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


if __name__ == "__main__":
    mysql_base_url()
