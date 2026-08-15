#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$repo_dir/zhihu/zhihu-backend/.venv/bin/python"

if [ ! -x "$python_bin" ]; then
  echo "后端虚拟环境不存在，请先按 zhihu/docs/development.md 安装依赖。" >&2
  exit 1
fi

exec "$python_bin" "$repo_dir/scripts/run-backend.py"
