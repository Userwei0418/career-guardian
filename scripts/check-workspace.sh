#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_dir/zhihu/zhihu-backend"
frontend_dir="$repo_dir/zhihu/zhihu-frontend"
market_dir="$repo_dir/zhihu/market-data"

failed=0

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    printf 'ok command=%s path=%s\n' "$1" "$(command -v "$1")"
  else
    printf 'missing command=%s\n' "$1"
    failed=1
  fi
}

check_path() {
  if [ -e "$1" ]; then
    printf 'ok path=%s\n' "$1"
  else
    printf 'missing path=%s\n' "$1"
    failed=1
  fi
}

check_command node
check_command npm
check_command python3
check_command mysql
check_path "$backend_dir/.env"
check_path "$backend_dir/.venv/bin/python"
check_path "$market_dir/.venv/bin/python"
check_path "$frontend_dir/node_modules"

printf 'expected_ports web=%s api=%s market=8100 crawler_admin=8101 mysql=3306\n' \
  "${GUARDIAN_WEB_PORT:-3000}" "${GUARDIAN_API_PORT:-8000}"

exit "$failed"
