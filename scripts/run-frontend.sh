#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$repo_dir/zhihu/zhihu-frontend"

if [ ! -d "$frontend_dir/node_modules" ]; then
  echo "前端依赖不存在，请先按 zhihu/docs/development.md 执行 npm ci。" >&2
  exit 1
fi

cd "$frontend_dir"
exec npm run dev -- --hostname 127.0.0.1 --port "${GUARDIAN_WEB_PORT:-3000}"

