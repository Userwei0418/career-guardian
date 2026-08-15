#!/usr/bin/env python3
"""Migrate and start the backend with one validated MySQL runtime environment."""

from __future__ import annotations

import os
import subprocess

from mysql_runtime import BACKEND_DIR, runtime_environment


def main() -> None:
    environment = runtime_environment()
    backend_python = BACKEND_DIR / ".venv/bin/python"
    if not backend_python.exists():
        raise RuntimeError("后端虚拟环境不存在")
    subprocess.run(
        [str(backend_python), "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=environment,
        check=True,
    )
    os.chdir(BACKEND_DIR)
    os.execve(
        str(backend_python),
        [
            str(backend_python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            environment.get("GUARDIAN_API_PORT", "8000"),
        ],
        environment,
    )


if __name__ == "__main__":
    main()
