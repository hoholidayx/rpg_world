"""Standalone LLM service entrypoint."""

from __future__ import annotations

import uvicorn

from commons.process_logging import (
    build_uvicorn_log_config,
    configure_process_logging,
)
from llm_service.settings import settings


def main() -> None:
    configure_process_logging("llm", settings.logging)
    uvicorn.run(
        "llm_service.main:app",
        host=settings.service.host,
        port=settings.service.port,
        log_level=settings.logging.log_level.lower(),
        log_config=build_uvicorn_log_config("llm", settings.logging),
        reload=settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
