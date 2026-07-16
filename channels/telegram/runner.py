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
from commons.process_logging import configure_process_logging


class _BotRuntime:
    def __init__(
        self,
        bot_name: str,
        adapter: TelegramAdapter,
        start_task: asyncio.Task[None],
        client: AgentClient | None = None,
    ) -> None:
        self.bot_name = bot_name
        self.adapter = adapter
        self.start_task = start_task
        self.client = client


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

    try:
        for bot in enabled_bots:
            client = AgentClient()
            try:
                ensure_kwargs = {}
                if bot.player_character_id > 0:
                    ensure_kwargs["player_character_id"] = bot.player_character_id
                session = await client.ensure_session(
                    bot.workspace_id,
                    bot.story_id,
                    session_id=bot.session_id or None,
                    title=bot.session_title,
                    **ensure_kwargs,
                )
            except BaseException:
                await client.aclose()
                raise
            adapter = TelegramAdapter(
                bot_name=bot.name,
                token=bot.token,
                streaming=bot.streaming,
                proxy=bot.proxy,
                stream_edit_interval_ms=bot.stream_edit_interval_ms,
                stream_edit_min_chars=bot.stream_edit_min_chars,
                request_timeout_ms=bot.request_timeout_ms,
                workspace=str(session["workspace"]),
                workspace_id=bot.workspace_id,
                story_id=bot.story_id,
                player_character_id=bot.player_character_id,
                session_id=str(session["session_id"]),
                session_title=str(session.get("title") or bot.session_title),
                agent_client=client,
            )
            start_task = asyncio.create_task(adapter.start(), name=f"telegram:{bot.name}")
            start_task.add_done_callback(_on_start_done)
            runtimes.append(_BotRuntime(bot.name, adapter, start_task, client))
            logger.info(
                "Telegram bot started task registered bot={} workspace_id={} story_id={} session_id={}",
                bot.name,
                bot.workspace_id,
                bot.story_id,
                session["session_id"],
            )
    except BaseException:
        await _close_runtimes(runtimes)
        raise

    return runtimes


async def _close_runtimes(runtimes: list[_BotRuntime]) -> None:
    """Close every owned resource even if one adapter/client fails."""
    pending_starts = [runtime.start_task for runtime in runtimes if not runtime.start_task.done()]
    for task in pending_starts:
        task.cancel()
    if pending_starts:
        await asyncio.gather(*pending_starts, return_exceptions=True)
    for runtime in runtimes:
        try:
            await runtime.adapter.stop()
        except Exception:
            logger.exception("telegram adapter shutdown failed bot={}", runtime.bot_name)
    for runtime in runtimes:
        client = getattr(runtime, "client", None)
        if client is None:
            continue
        try:
            await client.aclose()
        except Exception:
            logger.exception("telegram AgentClient shutdown failed bot={}", runtime.bot_name)


def _install_stop_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass


async def main() -> int:
    configure_process_logging("telegram", channels_settings.logging)
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
        await _close_runtimes(runtimes)
        logger.info("Telegram runner 已关闭")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
