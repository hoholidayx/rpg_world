from __future__ import annotations

from types import SimpleNamespace

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.memory_manager import MemoryManager, RecallItem
from rpg_world.rpg_core.memory.retrieval.hybrid_retriever import HybridRetriever
from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retrieval.retriever import DenseRetriever
from rpg_world.rpg_core.memory.planning.planner import RuleBasedQueryPlanner
from rpg_world.rpg_core.tests.conftest import FakeEmbedding, FakeFallbackSearch, FakeRetriever, FakeStore


class FakeChunkRecord:
    def __init__(self, rid: int, text: str, metadata: dict[str, object]) -> None:
        self.id = rid
        self.text = text
        self.metadata = metadata


def test_memory_manager_create_disabled(fake_recalled_store):
    mem_cfg = SimpleNamespace(enabled=False)
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir="/tmp/session",
        get_vector_db_path="/tmp/session/memory_vectors.db",
        mem_cfg=mem_cfg,
    )

    assert manager is None


def test_hybrid_retriever_merges_sources_and_falls_back():
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "vector-one", {"source": "vec"}), 0.2),
        (FakeChunkRecord(2, "vector-two", {"source": "vec"}), 0.5),
    ]
    store.keyword_rows = {
        "寻找 线索": [
            MemoryCandidate(memory_id=2, content="vector-two", metadata={"source": "kw"}, keyword_score=0.9),
            MemoryCandidate(memory_id=3, content="keyword-three", metadata={"source": "kw"}, keyword_score=0.8),
        ]
    }
    fallback = FakeFallbackSearch([
        MemoryCandidate(memory_id=3, content="keyword-three", metadata={"source": "fb"}, keyword_score=0.7),
    ])
    retriever = HybridRetriever(
        store=store,
        embedding=FakeEmbedding([[0.1, 0.2, 0.3]]),
        vector_k=2,
        keyword_k=2,
        reranker=None,
        fallback_search=fallback,
    )

    result = retriever.hybrid_search("寻找 线索", top_k=2)

    assert [item.content for item in result] == ["vector-one", "vector-two"]
    assert store.search_calls
    assert "寻找 线索" in fallback.calls[0]


def test_dense_retriever_sync(fake_token_counter):
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "dense-one", {"source": "vec"}), 0.0),
    ]
    retriever = DenseRetriever(store=store, embedding=FakeEmbedding([[1.0, 0.0, 0.0]]))

    result = retriever.retrieve_sync("query", top_k=1)
    assert result[0][0] == "dense-one"
    assert result[0][1] == 1.0


def test_memory_manager_recall_and_hybrid_search(fake_recalled_store):
    retriever = FakeRetriever([
        ("记忆一", 0.9, {"source": "summaries", "file": "a.md", "chunk_idx": 1}),
        ("记忆二", 0.8, {"source": "summaries", "file": "b.md", "chunk_idx": 2}),
    ])
    planner = RuleBasedQueryPlanner()
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=retriever,
        top_k=2,
        query_planner=planner,
    )

    items = manager.recall("查找线索")
    assert [item.text for item in items] == ["记忆一", "记忆二"]
    assert fake_recalled_store.get_items() == ["记忆一", "记忆二"]
    assert isinstance(items[0], RecallItem)

    hybrid = manager.hybrid_search("查找线索", top_k=1)
    assert [item.text for item in hybrid] == ["记忆一"]


def test_memory_manager_recall_without_retriever(fake_recalled_store):
    manager = MemoryManager(recalled_store=fake_recalled_store, retriever=None)
    assert manager.recall("anything") == []
    assert fake_recalled_store.get_items() == []


def test_memory_manager_recall_gracefully_handles_planner_or_retriever_failure(fake_recalled_store):
    planner = SimpleNamespace(plan=lambda _query: (_ for _ in ()).throw(RuntimeError("planner boom")))
    retriever = FakeRetriever([("不会返回", 0.5, {"source": "summaries"})])
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=retriever,
        top_k=2,
        query_planner=planner,
    )

    assert manager.recall("查找线索") == []
    assert fake_recalled_store.get_items() == []

    planner_ok = RuleBasedQueryPlanner()
    failing_retriever = SimpleNamespace(
        retrieve_sync=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("retriever boom")),
    )
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=failing_retriever,
        top_k=2,
        query_planner=planner_ok,
    )

    assert manager.recall("查找线索") == []
    assert fake_recalled_store.get_items() == []


def test_hybrid_retriever_planner_failure_returns_empty(monkeypatch):
    store = FakeStore()
    retriever = HybridRetriever(
        store=store,
        embedding=None,
        vector_k=2,
        keyword_k=2,
        reranker=None,
        fallback_search=RawMarkdownGrepSearch([]),
    )

    def boom(_self, _query):
        raise RuntimeError("planner boom")

    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.retrieval.hybrid_retriever.RuleBasedQueryPlanner.plan",
        boom,
    )

    assert retriever.hybrid_search("查找线索") == []
