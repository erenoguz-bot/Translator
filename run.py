#!/usr/bin/env python3
"""Entry point: run the PDF Parser & Translator server.

Usage:
    python run.py                 # http://0.0.0.0:8000
    PORT=9000 python run.py
"""
import os
import sys

import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(
        "server.app:app",
        host=host,
        port=port,
        log_level="info",
        workers=1,  # in-memory job store → single worker
    )


if __name__ == "__main__":
    sys.exit(main())
