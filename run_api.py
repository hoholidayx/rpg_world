"""API 快捷入口。

用于与 ``run.py`` 同级快速查找和单独调试 API。
"""

from __future__ import annotations

import uvicorn

from rpg_world.api.settings import api_settings
from rpg_world.channels.config import settings as channels_settings


def main() -> None:
    """启动独立 API 进程。"""
    uvicorn.run(
        "rpg_world.api.main:app",
        host=channels_settings.api_host,
        port=channels_settings.api_port,
        log_level=api_settings.log_level.lower(),
        reload=channels_settings.api_reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
