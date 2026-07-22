"""Tests for the developer-only RP recall CLI adapter."""

from __future__ import annotations

from channels.cli import memory_recall
from memory_retrieval.storage.types import ChunkRecord
from memory_retrieval.storage.vector_store import VectorStore


def test_inspect_vector_store_loads_sqlite_vec_backend(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "memory_vectors.db"
    store = VectorStore(db_path=db_path, dimension=3)
    store.upsert(
        [
            ChunkRecord(
                id=1,
                text="vector chunk",
                metadata={"source": "vec", "file": "a.md", "chunk_idx": 0},
            )
        ],
        [[0.1, 0.2, 0.3]],
    )
    store.close()

    monkeypatch.setattr(memory_recall, "_vector_db_path", lambda session: db_path)

    memory_recall.inspect_vector_store("ws", "sess")

    out = capsys.readouterr().out
    assert "向量后端:" in out
    assert "向量 row 数: 1" in out


async def test_initialize_manager_starts_file_watcher(monkeypatch, capsys):
    calls: list[str] = []

    class DummyManager:
        _initialized = False

        async def initialize(self):
            calls.append("initialize")
            self._initialized = True

    class DummyWatcher:
        def start(self):
            calls.append("start")
            return True

    monkeypatch.setattr(memory_recall, "get_watcher", lambda: DummyWatcher())

    await memory_recall.initialize_manager(DummyManager(), "sess")

    assert calls == ["initialize", "start"]
    assert "FileWatcher: running" in capsys.readouterr().out


def test_create_manager_injects_file_watcher(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    watcher = object()

    class DummyManager:
        _index_manager = None
        _retriever = None

    def fake_create(cls, **kwargs):  # noqa: ANN001
        del cls
        captured.update(kwargs)
        return DummyManager()

    monkeypatch.setattr(memory_recall, "get_watcher", lambda: watcher)
    monkeypatch.setattr(memory_recall, "_session_root", lambda _session: tmp_path)
    monkeypatch.setattr(
        memory_recall,
        "_vector_db_path",
        lambda _session: tmp_path / "memory_vectors.db",
    )
    monkeypatch.setattr(
        memory_recall.MemoryRecallManager,
        "create",
        classmethod(fake_create),
    )

    manager = memory_recall.create_manager("ignored", "session")

    assert isinstance(manager, DummyManager)
    assert captured["watcher"] is watcher
