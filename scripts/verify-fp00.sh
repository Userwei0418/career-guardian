#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_dir/zhihu/zhihu-backend"
frontend_dir="$repo_dir/zhihu/zhihu-frontend"
python_bin="$backend_dir/.venv/bin/python"

if [ ! -x "$python_bin" ]; then
  echo "后端虚拟环境不存在。" >&2
  exit 1
fi

if [ ! -d "$frontend_dir/node_modules" ]; then
  echo "前端依赖不存在。" >&2
  exit 1
fi

if [ -z "${CAREER_GUARDIAN_TEST_DATABASE_URL:-}" ]; then
  echo "请先设置 CAREER_GUARDIAN_TEST_DATABASE_URL；快速验收不会回落到 SQLite，也不会连接正式业务库。" >&2
  exit 1
fi

"$python_bin" -c '
import os
from sqlalchemy.engine import make_url

value = os.environ["CAREER_GUARDIAN_TEST_DATABASE_URL"]
url = make_url(value)
database = (url.database or "").lower()
if url.drivername not in {"mysql", "mysql+pymysql"}:
    raise SystemExit("CAREER_GUARDIAN_TEST_DATABASE_URL 必须使用 MySQL/PyMySQL")
if database in {"zhihu", "market_raw", "pin_legacy_staging"} or "test" not in database:
    raise SystemExit("测试库名必须包含 test，且不能是正式业务库")
'

cd "$backend_dir"
APP_ENV=test \
DATABASE_URL="$CAREER_GUARDIAN_TEST_DATABASE_URL" \
JWT_SECRET=fp00-test-secret-only-not-for-production \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=.:tests \
"$python_bin" -m unittest discover -s tests -v

cd "$frontend_dir"
npm run lint
npm run build
