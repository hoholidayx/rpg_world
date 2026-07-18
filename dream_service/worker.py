"""Serialized thread owner for the synchronous Dream data repository."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, TypeVar

from dream_service.contracts import (
    AsyncDreamRepository,
    DreamMemoryListView,
    DreamMemoryView,
    DreamProposalItemUpdate,
    DreamProposalListView,
    DreamProposalView,
    DreamRepository,
)
from rp_memory.dream.types import (
    DreamProposalItemDraft,
    DreamSelection,
    DreamSourceSnapshot,
)

_ResultT = TypeVar("_ResultT")


class DreamRepositoryWorker(AsyncDreamRepository):
    """Create, use, and close one repository on a dedicated actor thread."""

    def __init__(self, factory: Callable[[], DreamRepository]) -> None:
        self._factory = factory
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="dream-repository",
        )
        self._repository: DreamRepository | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._close_complete = asyncio.Event()
        self._closing = False
        self._closed = False

    async def start(self) -> None:
        await self._submit(lambda _repository: None)

    async def build_source_snapshot(self, session_id: str) -> DreamSourceSnapshot:
        return await self._submit(
            lambda repository: repository.build_source_snapshot(session_id)
        )

    async def create_proposal(self, selection: DreamSelection) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.create_proposal(selection)
        )

    async def get_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView | None:
        return await self._submit(
            lambda repository: repository.get_proposal(session_id, proposal_id)
        )

    async def list_proposals(self, session_id: str) -> DreamProposalListView:
        return await self._submit(
            lambda repository: repository.list_proposals(session_id)
        )

    async def set_proposal_ready(
        self,
        proposal_id: str,
        items: tuple[DreamProposalItemDraft, ...],
    ) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.set_proposal_ready(proposal_id, items)
        )

    async def set_proposal_failed(
        self,
        proposal_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.set_proposal_failed(
                proposal_id,
                error_code=error_code,
                error_message=error_message,
            )
        )

    async def interrupt_generating(
        self,
        session_id: str | None = None,
        *,
        proposal_id: str | None = None,
    ) -> tuple[DreamProposalView, ...]:
        return await self._submit(
            lambda repository: repository.interrupt_generating(
                session_id,
                proposal_id=proposal_id,
            )
        )

    async def update_proposal_items(
        self,
        session_id: str,
        proposal_id: str,
        updates: tuple[DreamProposalItemUpdate, ...],
    ) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.update_proposal_items(
                session_id,
                proposal_id,
                updates,
            )
        )

    async def reject_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.reject_proposal(session_id, proposal_id)
        )

    async def apply_proposal(
        self,
        session_id: str,
        proposal_id: str,
    ) -> DreamProposalView:
        return await self._submit(
            lambda repository: repository.apply_proposal(session_id, proposal_id)
        )

    async def list_memories(
        self,
        session_id: str,
        *,
        lifecycle: str | None = None,
    ) -> DreamMemoryListView:
        return await self._submit(
            lambda repository: repository.list_memories(
                session_id,
                lifecycle=lifecycle,
            )
        )

    async def restore_memory(
        self,
        session_id: str,
        memory_id: str,
    ) -> DreamMemoryView:
        return await self._submit(
            lambda repository: repository.restore_memory(session_id, memory_id)
        )

    async def close(self) -> None:
        owns_close = False
        async with self._lifecycle_lock:
            if self._closed:
                return
            if not self._closing:
                self._closing = True
                owns_close = True
        if not owns_close:
            await self._close_complete.wait()
            return
        try:
            try:
                # This operation queues behind every repository call accepted
                # before `_closing` was set.
                await self._run(self._close_repository)
            finally:
                # Joining a thread is not repository I/O, but it can still wait
                # for a cancelled caller's already-running operation.
                await asyncio.to_thread(
                    self._executor.shutdown,
                    wait=True,
                    cancel_futures=True,
                )
        finally:
            async with self._lifecycle_lock:
                self._closed = True
                self._close_complete.set()

    async def _submit(
        self,
        operation: Callable[[DreamRepository], _ResultT],
    ) -> _ResultT:
        async with self._lifecycle_lock:
            if self._closing or self._closed:
                raise RuntimeError("Dream repository worker is closing or closed")
            future = self._schedule(partial(self._execute, operation))
        return await future

    async def _run(self, operation: Callable[[], _ResultT]) -> _ResultT:
        return await self._schedule(operation)

    def _schedule(self, operation: Callable[[], _ResultT]) -> asyncio.Future[_ResultT]:
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(self._executor, operation)

    def _execute(
        self,
        operation: Callable[[DreamRepository], _ResultT],
    ) -> _ResultT:
        if self._repository is None:
            self._repository = self._factory()
        return operation(self._repository)

    def _close_repository(self) -> None:
        if self._repository is None:
            return
        try:
            self._repository.close()
        finally:
            self._repository = None
