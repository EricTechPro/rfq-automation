#!/usr/bin/env python3
"""
Railway-compatible FastAPI launcher.
Reads PORT from environment variable and launches uvicorn.
"""
import os
import uvicorn

from utils.logging import get_logger

logger = get_logger(__name__)


def main():
    port = int(os.environ.get("PORT", 8000))
    logger.info("Starting FastAPI on port %d", port)
    uvicorn.run("api:app", host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
