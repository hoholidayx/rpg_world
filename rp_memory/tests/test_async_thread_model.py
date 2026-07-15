from __future__ import annotations

import asyncio
import threading
import time

from rp_memory.memory_manager import MemoryManager
from rp_memory.planning.planner import RuleBasedQueryPlanner
from rp_memory.retrieval.keyword_retriever import KeywordRetriever
from rp_memory.vector_index_manager import VectorIndexManager


class _RecalledStore:
    def __init__(self) -> None:
        self.items: list[str] = []

    def get_items(self) -> list[str]:
        return list(self.items)

    def set_items(self, items: list[str]) -> None:
        self.items = list(items)

    def clear(self) -> None:
        self.items.clear()


async def test_recall_moves_blocking_keyword_search_off_event_loop() -> None:
    class SlowStore:
        def keyword_search(self, _query: str, *, limit: int):  # noqa: ANN201
            del limit
            time.sleep(0.05)
            return []

    manager = MemoryManager(
        recalled_store=_RecalledStore(),
        retriever=KeywordRetriever(SlowStore()),  # type: ignore[arg-type]
        query_planner=RuleBasedQueryPlanner(),
    )
    stopped = asyncio.Event()
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while not stopped.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    ticker_task = asyncio.create_task(ticker())
    await manager.recall("slow sqlite lookup")
    stopped.set()
    await ticker_task

    assert ticks >= 5
    await manager.close()


async def test_same_session_memory_operations_are_serialized() -> None:
    class RecordingRetriever:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0

        async def retrieve_plan(self, _plan, _top_k):  # noqa: ANN001, ANN201
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.03)
            self.active -= 1
            return []

    retriever = RecordingRetriever()
    manager = MemoryManager(
        recalled_store=_RecalledStore(),
        retriever=retriever,  # type: ignore[arg-type]
        query_planner=RuleBasedQueryPlanner(),
    )

    await asyncio.gather(manager.recall("one"), manager.recall("two"))

    assert retriever.max_active == 1
    await manager.close()


async def test_different_session_memory_managers_can_run_concurrently() -> None:
    active = 0
    max_active = 0
    both_started = asyncio.Event()
    release = asyncio.Event()

    class CoordinatedRetriever:
        async def retrieve_plan(self, _plan, _top_k):  # noqa: ANN001, ANN201
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                both_started.set()
            await release.wait()
            active -= 1
            return []

    first = MemoryManager(
        recalled_store=_RecalledStore(),
        retriever=CoordinatedRetriever(),  # type: ignore[arg-type]
        query_planner=RuleBasedQueryPlanner(),
    )
    second = MemoryManager(
        recalled_store=_RecalledStore(),
        retriever=CoordinatedRetriever(),  # type: ignore[arg-type]
        query_planner=RuleBasedQueryPlanner(),
    )
    tasks = (
        asyncio.create_task(first.recall("one")),
        asyncio.create_task(second.recall("two")),
    )

    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()
    await asyncio.gather(*tasks)

    assert max_active == 2
    await asyncio.gather(first.close(), second.close())


async def test_watcher_callback_only_enqueues_loop_owned_work() -> None:
    manager = VectorIndexManager(
        store=object(),  # type: ignore[arg-type]
        embedding=None,
        sources=[],
    )
    sync_started = asyncio.Event()
    sync_finished = asyncio.Event()
    release = asyncio.Event()

    async def fake_sync_source(_source_id: str, *, force: bool = False) -> None:
        del force
        sync_started.set()
        await release.wait()
        sync_finished.set()

    manager.sync_source = fake_sync_source  # type: ignore[method-assign]
    await manager.start()

    callback_thread = threading.Thread(
        target=manager.on_source_change,
        args=("summaries",),
    )
    callback_thread.start()
    callback_thread.join(timeout=0.2)

    assert callback_thread.is_alive() is False
    await asyncio.wait_for(sync_started.wait(), timeout=1)
    assert sync_finished.is_set() is False

    release.set()
    await asyncio.wait_for(sync_finished.wait(), timeout=1)
    await manager.close()
