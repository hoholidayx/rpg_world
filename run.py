"""rpg_world 统一启动入口。

按 ``channels/channels.json`` 配置，在单一进程中启动指定的模块。
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
import logging
import os
import signal

from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.manager import AgentManager

logger = logging.getLogger("rpg_world.launcher")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World 统一启动器")
    parser.add_argument(
        "--modules",
        default=None,
        help="要启动的模块列表，逗号分隔，如 'api,telegram'。"
             "默认从 channels.json 读取",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    # 确定要启动的模块列表
    modules_str = args.modules or os.environ.get("MODULES", "")
    if modules_str:
        enabled_modules = [m.strip() for m in modules_str.split(",") if m.strip()]
    else:
        cfg = channels_settings
        enabled_modules = [
            name for name in ("api", "telegram", "cli")
            if cfg.is_module_enabled(name)
        ]

    if not enabled_modules:
        print("未启用任何模块（在 channels.json 中设置 modules.{name}.enabled=true）")
        print("或通过 MODULES=api,telegram uv run python -m rpg_world.run 指定")
        return

    print(f"启动模块: {', '.join(enabled_modules)}")

    # 初始化 agent（触发 FileWatcher、BaseManager 等全局资源）
    await AgentManager.ensure_initialized()

    tasks: list[asyncio.Task] = []

    # ── 启动 API ───────────────────────────────────────────────────────
    if "api" in enabled_modules:
        cfg = channels_settings.get_module_config("api")
        import uvicorn

        api_host = cfg.get("host", "127.0.0.1")
        api_port = cfg.get("port", 8000)
        api_reload = cfg.get("reload", False)

        # 标记 lifespan 中不需要再启动 Telegram（由 launcher 统一管理）
        from rpg_world.api import main as api_main
        api_main._launcher_managed = True

        config = uvicorn.Config(
            "rpg_world.api.main:app",
            host=api_host,
            port=api_port,
            reload=api_reload,
            log_level="info",
        )
        server = uvicorn.Server(config)
        tasks.append(asyncio.create_task(server.serve(), name="api"))

    # ── 启动 Telegram ──────────────────────────────────────────────────
    if "telegram" in enabled_modules:
        cfg = channels_settings.get_module_config("telegram")
        from rpg_world.channels.telegram import TelegramAdapter

        agent = AgentManager.get_or_create()
        adapter = TelegramAdapter(
            token=cfg["bot_token"],
            streaming=cfg.get("streaming", True),
            agent=agent,
        )
        tasks.append(asyncio.create_task(adapter.start(), name="telegram"))

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
