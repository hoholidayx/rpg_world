"""Dashboard API 独立进程入口。"""

from __future__ import annotations

import uvicorn

from dashboard_api.settings import api_settings


def main() -> None:
    """启动独立 API 进程。"""
    uvicorn.run(
        "dashboard_api.main:app",
        host=api_settings.service.host,
        port=api_settings.service.port,
        log_level=api_settings.log_level.lower(),
        reload=api_settings.service.reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
