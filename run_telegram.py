"""Telegram 快捷入口。

用于与 ``run.py`` 同级快速查找和单独调试 Telegram。
"""

from __future__ import annotations

import asyncio

from channels.telegram.runner import main as _telegram_main


async def main() -> int:
    """启动 Telegram 快捷入口。"""
    return await _telegram_main()


def cli() -> int:
    """Console script wrapper for the async Telegram entrypoint."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
