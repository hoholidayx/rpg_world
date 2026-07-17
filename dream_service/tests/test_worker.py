from __future__ import annotations

import asyncio
import threading
import time

import pytest

from dream_service.contracts import DreamProposalListView
from dream_service.worker import DreamRepositoryWorker


class _ThreadTrackingRepository:
    def __init__(
        self,
        *,
        started: threading.Event | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self.created_thread = threading.get_ident()
        self.started = started
        self.release = release
        self.call_threads: list[int] = []
        self.close_thread: int | None = None
        self.active_calls = 0
        self.max_active_calls = 0
        self._counter_lock = threading.Lock()

    def list_proposals(self, session_id: str) -> DreamProposalListView:
        assert session_id == "s1"
        with self._counter_lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        self.call_threads.append(threading.get_ident())
        if self.started is not None:
            self.started.set()
        if self.release is not None:
            assert self.release.wait(timeout=2)
        else:
            time.sleep(0.02)
        with self._counter_lock:
            self.active_calls -= 1
        return DreamProposalListView(())

    def close(self) -> None:
        self.close_thread = threading.get_ident()


async def _wait_for_thread_event(event: threading.Event) -> None:
    for _ in range(100):
        if event.is_set():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("repository worker did not start in time")


async def test_repository_worker_keeps_blocking_io_off_loop_and_owns_repository() -> None:
    started = threading.Event()
    release = threading.Event()
    repositories: list[_ThreadTrackingRepository] = []

    def factory() -> _ThreadTrackingRepository:
        repository = _ThreadTrackingRepository(started=started, release=release)
        repositories.append(repository)
        return repository

    worker = DreamRepositoryWorker(factory)  # type: ignore[arg-type]
    call = asyncio.create_task(worker.list_proposals("s1"))
    await _wait_for_thread_event(started)

    loop_advanced = False
    await asyncio.sleep(0.01)
    loop_advanced = True
    assert loop_advanced is True
    assert call.done() is False

    release.set()
    await call
    await worker.close()

    repository = repositories[0]
    assert repository.created_thread != threading.get_ident()
    assert repository.call_threads == [repository.created_thread]
    assert repository.close_thread == repository.created_thread


async def test_repository_worker_serializes_calls() -> None:
    repositories: list[_ThreadTrackingRepository] = []

    def factory() -> _ThreadTrackingRepository:
        repository = _ThreadTrackingRepository()
        repositories.append(repository)
        return repository

    worker = DreamRepositoryWorker(factory)  # type: ignore[arg-type]
    await asyncio.gather(
        worker.list_proposals("s1"),
        worker.list_proposals("s1"),
    )
    await worker.close()

    repository = repositories[0]
    assert repository.max_active_calls == 1
    assert repository.call_threads == [
        repository.created_thread,
        repository.created_thread,
    ]


async def test_repository_worker_rejects_calls_once_close_begins() -> None:
    started = threading.Event()
    release = threading.Event()
    repositories: list[_ThreadTrackingRepository] = []

    def factory() -> _ThreadTrackingRepository:
        repository = _ThreadTrackingRepository(started=started, release=release)
        repositories.append(repository)
        return repository

    worker = DreamRepositoryWorker(factory)  # type: ignore[arg-type]
    in_flight = asyncio.create_task(worker.list_proposals("s1"))
    await _wait_for_thread_event(started)
    closing = asyncio.create_task(worker.close())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="closing or closed"):
        await worker.list_proposals("s1")

    release.set()
    await in_flight
    await closing
    await worker.close()
    assert len(repositories) == 1
    assert repositories[0].close_thread == repositories[0].created_thread
