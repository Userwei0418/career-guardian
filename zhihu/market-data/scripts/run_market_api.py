#!/usr/bin/env python3
"""启动 V2 市场洞察 API。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_data.app import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.getenv("MARKET_API_PORT", "8100")),
        reload=False,
    )
