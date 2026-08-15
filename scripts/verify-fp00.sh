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

cd "$backend_dir"
APP_ENV=test \
DATABASE_URL=sqlite:///./fp00-test.sqlite3 \
JWT_SECRET=fp00-test-secret-only-not-for-production \
"$python_bin" -m unittest discover -s tests -v

cd "$frontend_dir"
npm run lint
npm run build

