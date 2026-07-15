"""Standalone LLM service entrypoint."""

from __future__ import annotations

import uvicorn

from llm_service.settings import settings


def main() -> None:
    uvicorn.run(
        "llm_service.main:app",
        host=settings.service.host,
        port=settings.service.port,
        log_level=settings.logging.log_level.lower(),
        reload=settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
