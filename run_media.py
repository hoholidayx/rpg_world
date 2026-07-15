"""Media service independent process entrypoint."""

from __future__ import annotations

import logging

import uvicorn

from media_service.settings import settings


def _configure_logging() -> None:
    level_name = settings.logging.log_level.upper()
    level = getattr(logging, level_name, logging.DEBUG)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")
    root.setLevel(level)
    logging.getLogger("media_service").setLevel(level)
    logging.getLogger("rpg_media").setLevel(level)


def main() -> None:
    _configure_logging()
    uvicorn.run(
        "media_service.main:app",
        host=settings.service.host,
        port=settings.service.port,
        log_level=settings.logging.log_level.lower(),
        reload=settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
