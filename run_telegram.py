"""Telegram 独立进程入口。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from channels.config import settings as channels_settings
from channels.session_reference import (
    SessionReferenceApplicationService,
    ThreadedSessionReferenceReader,
)
from channels.telegram.runner import main as _telegram_main
from commons.process_logging import configure_process_logging
from rpg_core.summary.reference import SessionSummaryReferenceProvider
from rpg_data.services import get_data_service_gateway
from rpg_memory.persistent.reference import PersistentMemoryReferenceService
from rpg_memory.story.application import StoryMemoryApplicationService

if TYPE_CHECKING:
    from channels.session_reference import SessionReferenceReader
    from rpg_data.services import DataServiceGateway


def _reference_menu_requested() -> bool:
    return any(
        bot.enabled and bot.reference_menu_enabled
        for bot in channels_settings.telegram_bots
    )


def _build_reference_reader(
    gateway: DataServiceGateway,
) -> ThreadedSessionReferenceReader:
    data = gateway.session_reference
    service = SessionReferenceApplicationService(
        data,
        summaries=SessionSummaryReferenceProvider(data),
        story_memories=StoryMemoryApplicationService(gateway.story_memory),
        persistent_memories=PersistentMemoryReferenceService(
            gateway.dream_memory
        ),
    )
    return ThreadedSessionReferenceReader(
        service,
        max_concurrency=4,
        close_worker_connection=gateway.close_thread_connection,
    )


def _build_reference_reader_in_worker(
    gateway: DataServiceGateway,
) -> ThreadedSessionReferenceReader:
    """Initialize database-backed providers off-loop and close that connection."""

    try:
        return _build_reference_reader(gateway)
    finally:
        gateway.close_thread_connection()


async def _initialize_reference_reader(
    gateway: DataServiceGateway,
) -> tuple[ThreadedSessionReferenceReader, asyncio.CancelledError | None]:
    """Drain non-cancellable initialization work before preserving cancellation."""

    task = asyncio.create_task(
        asyncio.to_thread(_build_reference_reader_in_worker, gateway),
        name="telegram:reference-reader-init",
    )
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            # ``to_thread`` cannot stop a running migration/service build.
            # Keep the result reachable so the caller can close it in order.
            cancellation = exc
    try:
        reader = task.result()
    except BaseException:
        if cancellation is not None:
            raise cancellation
        raise
    return reader, cancellation


async def main() -> int:
    """启动 Telegram 快捷入口。"""
    configure_process_logging("telegram", channels_settings.logging)

    gateway: DataServiceGateway | None = None
    reference_reader: SessionReferenceReader | None = None
    try:
        if _reference_menu_requested():
            try:
                gateway = get_data_service_gateway()
                reference_reader, initialization_cancellation = (
                    await _initialize_reference_reader(gateway)
                )
                if initialization_cancellation is not None:
                    raise initialization_cancellation
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Telegram 资料查询初始化失败，将以仅聊天模式继续启动"
                )
                if gateway is not None:
                    try:
                        gateway.close()
                    except Exception:
                        logger.exception(
                            "Telegram 资料查询降级时关闭数据 Gateway 失败"
                        )
                gateway = None
                reference_reader = None

        return await _telegram_main(
            reference_reader=reference_reader,
            configure_logging=False,
        )
    finally:
        try:
            if reference_reader is not None:
                try:
                    await reference_reader.aclose()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Telegram 资料查询 runtime 关闭失败")
        finally:
            if gateway is not None:
                try:
                    gateway.close()
                except Exception:
                    logger.exception("Telegram 数据 Gateway 关闭失败")


def cli() -> int:
    """Console script wrapper for the async Telegram entrypoint."""
    return asyncio.run(main())


if __name__ == "__main__":
    raise SystemExit(cli())
