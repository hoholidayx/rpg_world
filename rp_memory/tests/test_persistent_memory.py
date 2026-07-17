from __future__ import annotations

from types import SimpleNamespace

from rp_memory.persist_memory import PersistentMemoryStore


class _ClosedDatabase:
    @staticmethod
    def is_closed() -> bool:
        return True


async def test_persistent_memory_store_reads_typed_context_projection(
    monkeypatch,
) -> None:
    bundle = SimpleNamespace(
        memory=SimpleNamespace(id="memory-1"),
        current_revision=SimpleNamespace(revision_number=2),
        text="北境森林仍被永夜笼罩。",
        memory_kind="world_fact",
        epistemic_status="confirmed",
        salience=0.9,
    )
    service = SimpleNamespace(
        list_context_memories=lambda session_id: (
            [bundle] if session_id == "s_memory" else []
        )
    )
    monkeypatch.setattr(
        "rpg_data.services.get_data_service_gateway",
        lambda: SimpleNamespace(dream=service, database=_ClosedDatabase()),
    )

    store = PersistentMemoryStore("s_memory")
    items = await store.load_snapshot()

    assert len(items) == 1
    assert items[0].memory_id == "memory-1"
    assert items[0].revision_number == 2
    assert items[0].text == "北境森林仍被永夜笼罩。"


async def test_persistent_memory_store_empty_ledger(
    monkeypatch,
) -> None:
    service = SimpleNamespace(list_context_memories=lambda _session_id: [])
    monkeypatch.setattr(
        "rpg_data.services.get_data_service_gateway",
        lambda: SimpleNamespace(dream=service, database=_ClosedDatabase()),
    )

    store = PersistentMemoryStore("s_empty_memory")
    assert await store.load_snapshot() == ()
