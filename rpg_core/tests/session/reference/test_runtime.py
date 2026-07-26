from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from rpg_core.session.reference import (
    SessionReferenceLocator,
    SessionReferenceReaderClosedError,
    ThreadedSessionReferenceReader,
)


LOCATOR = SessionReferenceLocator("s_runtime", "workspace", 1)


async def test_threaded_reader_bounds_workers_and_closes_each_connection() -> None:
    active = 0
    peak = 0
    calls = 0
    lock = threading.Lock()
    release = threading.Event()

    def get_scope(_locator):  # noqa: ANN001, ANN202
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        release.wait(timeout=3)
        with lock:
            active -= 1
        return "scope"

    def close_worker_connection() -> None:
        nonlocal calls
        with lock:
            calls += 1

    reader = ThreadedSessionReferenceReader(
        SimpleNamespace(get_scope=get_scope),
        max_concurrency=2,
        close_worker_connection=close_worker_connection,
    )
    tasks = [asyncio.create_task(reader.get_scope(LOCATOR)) for _ in range(5)]
    await asyncio.sleep(0.05)
    assert peak == 2
    release.set()

    assert await asyncio.gather(*tasks) == ["scope"] * 5
    assert calls == 5
    await reader.aclose()
    with pytest.raises(SessionReferenceReaderClosedError):
        await reader.get_scope(LOCATOR)


async def test_aclose_waits_for_worker_after_caller_cancellation() -> None:
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    def get_scope(_locator):  # noqa: ANN001, ANN202
        started.set()
        release.wait(timeout=3)
        return "scope"

    reader = ThreadedSessionReferenceReader(
        SimpleNamespace(get_scope=get_scope),
        close_worker_connection=closed.set,
    )
    caller = asyncio.create_task(reader.get_scope(LOCATOR))
    assert await asyncio.to_thread(started.wait, 1)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    closing = asyncio.create_task(reader.aclose())
    await asyncio.sleep(0.05)
    assert not closing.done()
    release.set()
    await closing
    assert closed.is_set()


async def test_cancelled_aclose_still_drains_worker_before_propagating() -> None:
    started = threading.Event()
    release = threading.Event()
    connection_closed = threading.Event()

    def get_scope(_locator):  # noqa: ANN001, ANN202
        started.set()
        release.wait(timeout=3)
        return "scope"

    reader = ThreadedSessionReferenceReader(
        SimpleNamespace(get_scope=get_scope),
        close_worker_connection=connection_closed.set,
    )
    caller = asyncio.create_task(reader.get_scope(LOCATOR))
    assert await asyncio.to_thread(started.wait, 1)

    closing = asyncio.create_task(reader.aclose())
    await asyncio.sleep(0)
    closing.cancel()
    await asyncio.sleep(0.05)
    assert not closing.done()
    assert not connection_closed.is_set()

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert connection_closed.is_set()
    assert await caller == "scope"


async def test_worker_connection_close_failure_does_not_hide_read_result() -> None:
    def fail_to_close() -> None:
        raise RuntimeError("close failed")

    reader = ThreadedSessionReferenceReader(
        SimpleNamespace(get_scope=lambda _locator: "scope"),
        close_worker_connection=fail_to_close,
    )

    assert await reader.get_scope(LOCATOR) == "scope"
    await reader.aclose()


async def test_reader_can_be_composed_off_loop_before_first_use() -> None:
    reader = await asyncio.to_thread(
        ThreadedSessionReferenceReader,
        SimpleNamespace(get_scope=lambda _locator: "scope"),
    )

    assert await reader.get_scope(LOCATOR) == "scope"
    await reader.aclose()
