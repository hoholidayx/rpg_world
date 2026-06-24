"""批量启动快捷入口。

用于与 ``run.py`` 同级快速查找统一 supervisor 入口。
"""

from __future__ import annotations

import asyncio

from run import main as _supervisor_main


async def main() -> int:
    """启动批量 supervisor 快捷入口。"""
    return await _supervisor_main()


def cli() -> int:
    """Console script wrapper for the async batch entrypoint."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
