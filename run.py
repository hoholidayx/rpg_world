"""rpg_world 统一启动入口。

按 ``settings.yaml`` 配置，在单一进程中启动指定的模块。
所有模块共享同一 ``AgentManager`` 实例池，避免多进程文件冲突。

用法::

    # 读取 settings.yaml 按配置启动
    uv run python -m rpg_world.run

    # 仅启动 API
    MODULES=api uv run python -m rpg_world.run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from pathlib import Path

# tiktoken 首次加载需要从网络下载编码文件。
# 设置缓存目录为项目 data/，避免因 /tmp 被清理导致启动卡死。
os.environ.setdefault(
    "TIKTOKEN_CACHE_DIR",
    str(Path(__file__).resolve().parent / "data"),
)

from loguru import logger as _loguru_logger

from rpg_world.channels.config import settings as channels_settings
from rpg_world.rpg_core.agent.manager import AgentManager


# ── 日志配置（所有模块 INFO+ 输出到 stderr） ─────────────────────────
_loguru_logger.remove()
_loguru_logger.add(
    sink=lambda msg: __import__("sys").stderr.write(msg),
    format="{time:HH:mm:ss} | {level:<7} | {name}:{line} - {message}",
    level="INFO",
    colorize=False,
)


# ── 模块启动处理器注册表 ──────────────────────────────────────────────────
# 键为模块名，值为 async (task_list) -> None。
# 处理器负责初始化模块并往 task_list 追加 asyncio.Task。
_handlers: dict[str, Callable[[list[asyncio.Task]], Awaitable[None]]] = {}


def _track_task(task: asyncio.Task) -> None:
    """在后台任务完成时记录异常，避免静默失败。"""
    def _done(done_task: asyncio.Task) -> None:
        try:
            exc = done_task.exception()
        except asyncio.CancelledError:
            _loguru_logger.info("任务已取消: {}", done_task.get_name())
            return
        if exc is not None:
            _loguru_logger.opt(exception=exc).error("任务异常退出: {}", done_task.get_name())
        else:
            _loguru_logger.info("任务正常结束: {}", done_task.get_name())

    task.add_done_callback(_done)


def _register(name: str):
    """装饰器：注册模块启动处理器。"""
    def wrapper(fn: Callable[[list[asyncio.Task]], Awaitable[None]]):
        _handlers[name] = fn
        return fn
    return wrapper


@_register("api")
async def _start_api(tasks: list[asyncio.Task]) -> None:
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
        task = asyncio.create_task(server.serve(), name="api")
        _track_task(task)
        tasks.append(task)


@_register("telegram")
async def _start_telegram(tasks: list[asyncio.Task]) -> None:
    from rpg_world.channels.telegram import TelegramAdapter

    enabled_bots = [bot for bot in channels_settings.telegram_bots if bot.enabled]
    if not enabled_bots:
        _loguru_logger.warning("Telegram 模块已请求启动，但没有 enabled=true 的 bot")
        return

    for bot in enabled_bots:
        adapter = TelegramAdapter(
            bot_name=bot.name,
            token=bot.token,
            streaming=bot.streaming,
            proxy=bot.proxy,
            stream_edit_interval_ms=bot.stream_edit_interval_ms,
            stream_edit_min_chars=bot.stream_edit_min_chars,
            request_timeout_ms=bot.request_timeout_ms,
            # Telegram 启动时先用固定 bootstrap session 预热，真实聊天仍按 chat_id 分流。
            agent=AgentManager.get_or_create(
                workspace=bot.workspace,
                session_id=f"telegram_{bot.name}_default",
            ),
        )
        task = asyncio.create_task(adapter.start(), name=f"telegram:{bot.name}")
        _track_task(task)
        tasks.append(task)
        _loguru_logger.info(
            "Telegram bot started task registered bot={} workspace={}",
            bot.name,
            bot.workspace,
        )


@_register("cli")
async def _start_cli(tasks: list[asyncio.Task]) -> None:
    from rpg_world.channels.cli import CLIAdapter

    adapter = CLIAdapter(agent=AgentManager.get_or_create(workspace=channels_settings.cli_workspace))
    task = asyncio.create_task(adapter.start(), name="cli")
    _track_task(task)
    tasks.append(task)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RPG World 统一启动器")
    parser.add_argument(
        "--modules",
        default=None,
        help="要启动的模块列表，逗号分隔，如 'api,telegram'。"
             "默认从 settings.yaml 读取",
    )
    return parser.parse_args()


def _resolve_modules(args: argparse.Namespace) -> list[str]:
    """确定要启动的模块列表：命令行 > 环境变量 > settings.yaml 配置。"""
    modules_str = args.modules or os.environ.get("MODULES", "")
    if modules_str:
        return [m.strip() for m in modules_str.split(",") if m.strip()]
    return channels_settings.enabled_module_names


async def main() -> None:
    enabled_modules = _resolve_modules(_parse_args())

    if not enabled_modules:
        _loguru_logger.warning("未启用任何模块（在 settings.yaml 中设置 modules.{name}.enabled=true）")
        _loguru_logger.warning("或通过 MODULES=api,telegram uv run python -m rpg_world.run 指定")
        return

    _loguru_logger.info("启动模块: {}", ", ".join(enabled_modules))

    tasks: list[asyncio.Task] = []

    for module in enabled_modules:
        handler = _handlers.get(module)
        if handler is None:
            _loguru_logger.warning("未知模块，跳过: {}", module)
            continue
        _loguru_logger.info("启动模块处理器: {}", module)
        await handler(tasks)

    # ── 等待退出信号 ──────────────────────────────────────────────────
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    _loguru_logger.info("已启动 {} 个模块，按 Ctrl+C 停止", len(tasks))
    await stop_event.wait()

    # ── 优雅关闭 ──────────────────────────────────────────────────────
    _loguru_logger.info("正在关闭...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _loguru_logger.info("已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
