from __future__ import annotations

from types import SimpleNamespace

from rp_memory.persist_memory import PersistentMemoryStore


async def test_persistent_memory_store_reads_typed_context_projection(
) -> None:
    bundle = SimpleNamespace(
        memory=SimpleNamespace(id="memory-1"),
        current_revision=SimpleNamespace(
            revision_number=2,
            text="北境森林仍被永夜笼罩。",
            memory_kind="world_fact",
            epistemic_status="confirmed",
            salience=0.9,
        ),
    )
    service = SimpleNamespace(
        list_context_memories=lambda session_id: (
            [bundle] if session_id == "s_memory" else []
        )
    )
    store = PersistentMemoryStore("s_memory", service)
    items = await store.load_snapshot()

    assert len(items) == 1
    assert items[0].memory_id == "memory-1"
    assert items[0].revision_number == 2
    assert items[0].text == "北境森林仍被永夜笼罩。"


async def test_persistent_memory_store_empty_ledger(
) -> None:
    service = SimpleNamespace(list_context_memories=lambda _session_id: [])

    store = PersistentMemoryStore("s_empty_memory", service)
    assert await store.load_snapshot() == ()


async def test_persistent_memory_store_retains_last_snapshot_after_refresh_error(
) -> None:
    bundle = SimpleNamespace(
        memory=SimpleNamespace(id="memory-stale"),
        current_revision=SimpleNamespace(
            revision_number=1,
            text="旧快照仍可用于下一轮 Context。",
            memory_kind="event",
            epistemic_status="confirmed",
            salience=0.7,
        ),
    )
    calls = 0

    def list_context_memories(_session_id: str):  # noqa: ANN202
        nonlocal calls
        calls += 1
        if calls == 1:
            return [bundle]
        raise RuntimeError("temporary SQL failure")

    store = PersistentMemoryStore(
        "s_stale_memory",
        SimpleNamespace(list_context_memories=list_context_memories),
    )
    first = await store.load_snapshot()

    assert await store.load_snapshot() == first
    assert first[0].memory_id == "memory-stale"
