"""Bounded async adapter for the synchronous Session reference service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial
from typing import TypeVar

from channels.session_reference.errors import SessionReferenceReaderClosedError
from channels.session_reference.models import (
    CharacterCard,
    CharacterDetail,
    CharacterDetailSummary,
    CharacterSummary,
    PersistentMemoryDetail,
    PersistentMemorySummary,
    ReferencePage,
    SessionReferenceLocator,
    SessionReferenceScope,
    StatusTableDetail,
    StatusTableSummary,
    StoryMemoryDetail,
    StoryMemorySummary,
    SummaryDetail,
    SummarySummary,
)
from channels.session_reference.service import SessionReferenceApplicationService


T = TypeVar("T")
logger = logging.getLogger(__name__)


class ThreadedSessionReferenceReader:
    """Run blocking reference reads off-loop with one shared concurrency bound."""

    def __init__(
        self,
        service: SessionReferenceApplicationService,
        *,
        max_concurrency: int = 4,
        close_worker_connection: Callable[[], None] | None = None,
    ) -> None:
        if (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or max_concurrency <= 0
        ):
            raise ValueError("max_concurrency must be positive")
        self._service = service
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._close_worker_connection = close_worker_connection
        self._inflight: set[asyncio.Task[object]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def get_scope(
        self,
        locator: SessionReferenceLocator,
    ) -> SessionReferenceScope:
        return await self._invoke(self._service.get_scope, locator)

    async def list_characters(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterSummary]:
        return await self._invoke(
            self._service.list_characters,
            locator,
            page=page,
            page_size=page_size,
        )

    async def get_character(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
    ) -> CharacterCard:
        return await self._invoke(
            self._service.get_character,
            locator,
            character_id,
        )

    async def list_character_details(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[CharacterDetailSummary]:
        return await self._invoke(
            self._service.list_character_details,
            locator,
            character_id,
            page=page,
            page_size=page_size,
        )

    async def get_character_detail(
        self,
        locator: SessionReferenceLocator,
        character_id: int,
        detail_id: int,
    ) -> CharacterDetail:
        return await self._invoke(
            self._service.get_character_detail,
            locator,
            character_id,
            detail_id,
        )

    async def list_status_tables(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
        character_id: int | None = None,
    ) -> ReferencePage[StatusTableSummary]:
        return await self._invoke(
            self._service.list_status_tables,
            locator,
            page=page,
            page_size=page_size,
            character_id=character_id,
        )

    async def get_status_table(
        self,
        locator: SessionReferenceLocator,
        table_id: int,
    ) -> StatusTableDetail:
        return await self._invoke(
            self._service.get_status_table,
            locator,
            table_id,
        )

    async def list_summaries(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[SummarySummary]:
        return await self._invoke(
            self._service.list_summaries,
            locator,
            page=page,
            page_size=page_size,
        )

    async def get_summary(
        self,
        locator: SessionReferenceLocator,
        summary_id: str,
    ) -> SummaryDetail:
        return await self._invoke(
            self._service.get_summary,
            locator,
            summary_id,
        )

    async def list_story_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[StoryMemorySummary]:
        return await self._invoke(
            self._service.list_story_memories,
            locator,
            page=page,
            page_size=page_size,
        )

    async def get_story_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: int,
    ) -> StoryMemoryDetail:
        return await self._invoke(
            self._service.get_story_memory,
            locator,
            memory_id,
        )

    async def list_persistent_memories(
        self,
        locator: SessionReferenceLocator,
        *,
        page: int = 1,
        page_size: int = 8,
    ) -> ReferencePage[PersistentMemorySummary]:
        return await self._invoke(
            self._service.list_persistent_memories,
            locator,
            page=page,
            page_size=page_size,
        )

    async def get_persistent_memory(
        self,
        locator: SessionReferenceLocator,
        memory_id: str,
    ) -> PersistentMemoryDetail:
        return await self._invoke(
            self._service.get_persistent_memory,
            locator,
            memory_id,
        )

    async def aclose(self) -> None:
        """Reject new reads and wait for worker calls, including cancelled callers."""

        self._bind_loop()
        self._closed = True
        cancellation: asyncio.CancelledError | None = None
        while self._inflight:
            waiter = asyncio.gather(
                *tuple(self._inflight),
                return_exceptions=True,
            )
            while not waiter.done():
                try:
                    await asyncio.shield(waiter)
                except asyncio.CancelledError as exc:
                    # A native SQLite/file call cannot be cancelled once its
                    # worker thread starts. Preserve the caller's cancellation
                    # but do not let it cancel the tracking Tasks or allow the
                    # Gateway to close before those workers have drained.
                    cancellation = exc
            await asyncio.shield(waiter)
        if cancellation is not None:
            raise cancellation

    async def _invoke(
        self,
        operation: Callable[..., T],
        /,
        *args: object,
        **kwargs: object,
    ) -> T:
        loop = self._bind_loop()
        if self._closed:
            raise SessionReferenceReaderClosedError(
                "Session reference reader is closed"
            )

        task = loop.create_task(
            self._run_worker(partial(operation, *args, **kwargs))
        )
        self._inflight.add(task)
        task.add_done_callback(self._worker_finished)
        return await asyncio.shield(task)

    async def _run_worker(self, operation: Callable[[], T]) -> T:
        async with self._semaphore:
            return await asyncio.to_thread(self._call_in_worker, operation)

    def _call_in_worker(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        finally:
            if self._close_worker_connection is not None:
                try:
                    self._close_worker_connection()
                except Exception:
                    logger.warning(
                        "failed to close Session reference worker connection",
                        exc_info=True,
                    )

    def _bind_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError(
                "ThreadedSessionReferenceReader cannot be shared across event loops"
            )
        return loop

    def _worker_finished(self, task: asyncio.Task[object]) -> None:
        self._inflight.discard(task)
        if not task.cancelled():
            # Retrieve failures even when the awaiting caller was cancelled.
            task.exception()


__all__ = ["ThreadedSessionReferenceReader"]
