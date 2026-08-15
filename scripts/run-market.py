#!/usr/bin/env python3
"""Start the market API against MySQL Raw/Core domains only."""

from __future__ import annotations

import os

from mysql_runtime import MARKET_DIR, runtime_environment


def main() -> None:
    environment = runtime_environment()
    market_python = MARKET_DIR / ".venv/bin/python"
    if not market_python.exists():
        raise RuntimeError("市场数据服务虚拟环境不存在")
    os.chdir(MARKET_DIR)
    os.execve(
        str(market_python),
        [str(market_python), "scripts/run_market_api.py"],
        environment,
    )


if __name__ == "__main__":
    main()
