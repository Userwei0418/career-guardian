#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_dir/zhihu/zhihu-backend"
python_bin="$backend_dir/.venv/bin/python"

if [ ! -x "$python_bin" ]; then
  echo "后端虚拟环境不存在，请先按 zhihu/docs/development.md 安装依赖。" >&2
  exit 1
fi

"$python_bin" "$repo_dir/scripts/mysql_runtime.py"
cd "$backend_dir"
"$python_bin" -m alembic upgrade head
exec "$python_bin" -m uvicorn app.main:app --host 127.0.0.1 --port "${GUARDIAN_API_PORT:-8000}"
