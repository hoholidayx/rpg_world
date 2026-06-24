"""Dashboard API 快捷入口。

用于与 ``run.py`` 同级快速查找和单独调试 Dashboard API。
"""

from __future__ import annotations

import uvicorn

from dashboard_api.settings import api_settings
from channels.config import settings as channels_settings


def main() -> None:
    """启动独立 API 进程。"""
    uvicorn.run(
        "dashboard_api.main:app",
        host=channels_settings.dashboard_api_host,
        port=channels_settings.dashboard_api_port,
        log_level=api_settings.log_level.lower(),
        reload=channels_settings.dashboard_api_reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
