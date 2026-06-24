"""CLI 独立进程入口。"""

from __future__ import annotations

import asyncio

from channels.cli.repl import main as _cli_main


async def main() -> int:
    """启动 CLI 快捷入口。"""
    return await _cli_main()


def cli() -> int:
    """Console script wrapper for the async CLI entrypoint."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
