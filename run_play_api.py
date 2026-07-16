"""Play API 独立进程入口。"""

from __future__ import annotations

import uvicorn

from commons.process_logging import (
    build_uvicorn_log_config,
    configure_process_logging,
)
from play_api.settings import play_settings


def main() -> None:
    """启动独立 Play API 进程。"""
    configure_process_logging("play_api", play_settings.logging)
    uvicorn.run(
        "play_api.main:app",
        host=play_settings.service.host,
        port=play_settings.service.port,
        log_level=play_settings.logging.log_level.lower(),
        log_config=build_uvicorn_log_config("play_api", play_settings.logging),
        reload=play_settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
