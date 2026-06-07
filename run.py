"""rpg_world 统一启动入口。

按 ``channels.json`` 配置，在单一进程中启动指定的模块。
所有模块共享同一 ``AgentManager`` 实例池，避免多进程文件冲突。

用法::

    # 读取 channels.json 按配置启动
    uv run python -m rpg_world.run

    # 仅启动 API
    MODULES=api uv run python -m rpg_world.run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal

from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.manager import AgentManager


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World 统一启动器")
    parser.add_argument(
        "--modules",
        default=None,
        help="要启动的模块列表，逗号分隔，如 'api,telegram'。"
             "默认从 channels.json 读取",
    )
    return parser.parse_args()


def _resolve_modules(args: argparse.Namespace) -> list[str]:
    """确定要启动的模块列表：命令行 > 环境变量 > channels.json 配置。"""
    modules_str = args.modules or os.environ.get("MODULES", "")
    if modules_str:
        return [m.strip() for m in modules_str.split(",") if m.strip()]
    return channels_settings.enabled_module_names


async def main() -> None:
    enabled_modules = _resolve_modules(_parse_args())

    if not enabled_modules:
        print("未启用任何模块（在 channels.json 中设置 modules.{name}.enabled=true）")
        print("或通过 MODULES=api,telegram uv run python -m rpg_world.run 指定")
        return

    print(f"启动模块: {', '.join(enabled_modules)}")

    tasks: list[asyncio.Task] = []

    # ── 启动 API ───────────────────────────────────────────────────────
    if "api" in enabled_modules and channels_settings.api_enabled:
        import uvicorn

        if channels_settings.api_reload:
            uvicorn.run(
                "rpg_world.api.main:app",
                host=channels_settings.api_host,
                port=channels_settings.api_port,
                reload=True,
                reload_dirs=["rpg_world"],
                reload_excludes=["*/node_modules/*"],
            )
        else:
            config = uvicorn.Config(
                "rpg_world.api.main:app",
                host=channels_settings.api_host,
                port=channels_settings.api_port,
                log_level="info",
            )
            server = uvicorn.Server(config)
            tasks.append(asyncio.create_task(server.serve(), name="api"))

    # ── 启动 Telegram ──────────────────────────────────────────────────
    if "telegram" in enabled_modules and channels_settings.telegram_enabled:
        from rpg_world.channels.telegram import TelegramAdapter

        adapter = TelegramAdapter(
            token=channels_settings.telegram_token,
            streaming=channels_settings.telegram_streaming,
            agent=AgentManager.get_or_create(),
        )
        tasks.append(asyncio.create_task(adapter.start(), name="telegram"))

    # ── 启动 CLI ───────────────────────────────────────────────────────
    if "cli" in enabled_modules and channels_settings.cli_enabled:
        from rpg_world.channels.cli import CLIAdapter

        adapter = CLIAdapter(agent=AgentManager.get_or_create())
        tasks.append(asyncio.create_task(adapter.start(), name="cli"))

    # ── 等待退出信号 ──────────────────────────────────────────────────
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    print(f"已启动 {len(tasks)} 个模块，按 Ctrl+C 停止")
    await stop_event.wait()

    # ── 优雅关闭 ──────────────────────────────────────────────────────
    print("\n正在关闭...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
