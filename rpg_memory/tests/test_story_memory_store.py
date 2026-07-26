from __future__ import annotations

from types import SimpleNamespace

from rpg_memory.story.store import StoryMemoryStore


def _context_item(memory_id: int, text: str):  # noqa: ANN202
    return SimpleNamespace(
        id=memory_id,
        turn_id=4,
        text=text,
        memory_kind=SimpleNamespace(value="event"),
        epistemic_status=SimpleNamespace(value="confirmed"),
        salience=0.8,
        source_turn_start=3,
        source_turn_end=4,
    )


async def test_story_memory_store_loads_typed_snapshot_off_loop() -> None:
    service = SimpleNamespace(
        get_context_items=lambda session_id: (
            [_context_item(3, "门厅的密道已经开启。")]
            if session_id == "s_story"
            else []
        )
    )
    closed = 0

    def close_worker_connection() -> None:
        nonlocal closed
        closed += 1

    store = StoryMemoryStore(
        "s_story",
        service,
        close_worker_connection=close_worker_connection,
    )
    items = await store.load_snapshot()

    assert len(items) == 1
    assert items[0].memory_id == 3
    assert items[0].text == "门厅的密道已经开启。"
    assert items[0].memory_kind == "event"
    assert closed == 1


async def test_story_memory_store_retains_stale_snapshot_after_refresh_error() -> None:
    calls = 0

    def get_context_items(_session_id: str):  # noqa: ANN202
        nonlocal calls
        calls += 1
        if calls == 1:
            return [_context_item(9, "旧快照仍可用于当前 turn。")]
        raise RuntimeError("temporary SQL failure")

    closed = 0

    def close_worker_connection() -> None:
        nonlocal closed
        closed += 1

    store = StoryMemoryStore(
        "s_story",
        SimpleNamespace(get_context_items=get_context_items),
        close_worker_connection=close_worker_connection,
    )
    first = await store.load_snapshot()

    assert await store.load_snapshot() == first
    assert first[0].memory_id == 9
    assert closed == 2
