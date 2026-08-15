#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
market_dir="$repo_dir/zhihu/market-data"
python_bin="$market_dir/.venv/bin/python"

if [ ! -x "$python_bin" ]; then
  echo "市场数据虚拟环境不存在，请先按 zhihu/market-data/README.md 安装依赖。" >&2
  exit 1
fi

cd "$market_dir"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  "$python_bin" -m unittest discover -s tests -v
