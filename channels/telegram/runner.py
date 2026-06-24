"""Telegram 独立入口。

在独立进程中启动所有 enabled=true 的 Telegram bot。
通过 ``AgentClient`` 访问独立 Agent 服务。
"""

from __future__ import annotations

import asyncio
import signal

from loguru import logger

from agent_service.client import AgentClient
from channels.config import settings as channels_settings
from channels.telegram.adapter import TelegramAdapter


class _BotRuntime:
    def __init__(self, bot_name: str, adapter: TelegramAdapter, start_task: asyncio.Task[None]) -> None:
        self.bot_name = bot_name
        self.adapter = adapter
        self.start_task = start_task


async def _start_enabled_bots(
    stop_event: asyncio.Event,
    fatal_error: asyncio.Event | None = None,
) -> list[_BotRuntime]:
    runtimes: list[_BotRuntime] = []
    enabled_bots = [bot for bot in channels_settings.telegram_bots if bot.enabled]
    if not enabled_bots:
        logger.warning("Telegram 模块启动时没有 enabled=true 的 bot")
        return runtimes

    def _on_start_done(task: asyncio.Task[None]) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.opt(exception=exc).error("telegram bot 启动失败")
            if fatal_error is not None:
                fatal_error.set()
            stop_event.set()

    for bot in enabled_bots:
        adapter = TelegramAdapter(
            bot_name=bot.name,
            token=bot.token,
            streaming=bot.streaming,
            proxy=bot.proxy,
            stream_edit_interval_ms=bot.stream_edit_interval_ms,
            stream_edit_min_chars=bot.stream_edit_min_chars,
            request_timeout_ms=bot.request_timeout_ms,
            workspace=bot.workspace,
            agent_client=AgentClient(),
        )
        start_task = asyncio.create_task(adapter.start(), name=f"telegram:{bot.name}")
        start_task.add_done_callback(_on_start_done)
        runtimes.append(_BotRuntime(bot.name, adapter, start_task))
        logger.info("Telegram bot started task registered bot={} workspace={}", bot.name, bot.workspace)

    return runtimes


def _install_stop_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass


async def main() -> int:
    stop_event = asyncio.Event()
    fatal_error = asyncio.Event()
    runtimes: list[_BotRuntime] = []
    try:
        runtimes = await _start_enabled_bots(stop_event, fatal_error)
        if not runtimes:
            return 0

        _install_stop_handlers(stop_event)
        await stop_event.wait()
        return 1 if fatal_error.is_set() else 0
    finally:
        for runtime in runtimes:
            await runtime.adapter.stop()
        for runtime in runtimes:
            runtime.start_task.cancel()
        await asyncio.gather(*(runtime.start_task for runtime in runtimes), return_exceptions=True)
        logger.info("Telegram runner 已关闭")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
