from __future__ import annotations

import json

from rp_memory.persist_memory import PersistentMemoryStore


def test_persistent_memory_store_reads_json_sections(tmp_path):
    path = tmp_path / "persistent_memory.json"
    path.write_text(
        json.dumps(
            [
                {"title": "地理", "content": "北境森林"},
                {"title": "人物", "content": "Alice"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = PersistentMemoryStore(path)

    assert store.get_sections() == [
        {"title": "地理", "content": "北境森林"},
        {"title": "人物", "content": "Alice"},
    ]


def test_persistent_memory_store_missing_file_is_empty(tmp_path):
    store = PersistentMemoryStore(tmp_path / "persistent_memory.json")

    assert store.get_sections() == []
