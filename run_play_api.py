"""Play API 独立进程入口。"""

from __future__ import annotations

import logging

import uvicorn

from play_api.settings import play_settings


def _configure_standard_logging() -> None:
    level_name = play_settings.logging.log_level.upper()
    level = getattr(logging, level_name, logging.DEBUG)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(levelname)s:%(name)s:%(message)s",
        )
    root.setLevel(level)
    logging.getLogger("play_api").setLevel(level)
    logging.getLogger("rpg_data").setLevel(level)


def main() -> None:
    """启动独立 Play API 进程。"""
    _configure_standard_logging()
    uvicorn.run(
        "play_api.main:app",
        host=play_settings.service.host,
        port=play_settings.service.port,
        log_level=play_settings.logging.log_level.lower(),
        reload=play_settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
