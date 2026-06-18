from __future__ import annotations

import asyncio
from types import SimpleNamespace

import json

import pytest

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.embedding_provider import OpenAIEmbeddingProvider
from rpg_world.rpg_core.memory.memory_manager import MemoryManager, RecallItem
from rpg_world.rpg_core.memory.planning.openai_planner import OpenAIQueryPlanner
from rpg_world.rpg_core.memory.retrieval.hybrid_retriever import HybridRetriever
from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retrieval.retriever import DenseRetriever
from rpg_world.rpg_core.memory.rerank.openai_reranker import OpenAIReranker
from rpg_world.rpg_core.memory.planning.planner import RuleBasedQueryPlanner
from rpg_world.rpg_core.tests.conftest import FakeEmbedding, FakeFallbackSearch, FakeRetriever, FakeStore


class FakeChunkRecord:
    def __init__(self, rid: int, text: str, metadata: dict[str, object]) -> None:
        self.id = rid
        self.text = text
        self.metadata = metadata


class DummyAsyncOpenAI:
    instances: list["DummyAsyncOpenAI"] = []
    embedding_vectors: list[list[float]] = [[0.1, 0.2, 0.3]]
    chat_content: str = "{}"

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.embeddings = SimpleNamespace(create=self._create_embeddings)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat))
        self.instances.append(self)

    async def _create_embeddings(self, **kwargs):  # noqa: ANN003
        data = [SimpleNamespace(embedding=list(vec)) for vec in self.embedding_vectors[: len(kwargs.get("input", []))]]
        return SimpleNamespace(data=data)

    async def _create_chat(self, **kwargs):  # noqa: ANN003
        content = self.chat_content
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


def _provider_cfg(provider: str, *, openai: dict[str, object] | None = None, llama: dict[str, object] | None = None):
    return SimpleNamespace(provider=provider, openai=openai or {}, llama=llama or {})


def test_memory_manager_create_disabled(fake_recalled_store):
    mem_cfg = SimpleNamespace(enabled=False)
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir="/tmp/session",
        get_vector_db_path="/tmp/session/memory_vectors.db",
        mem_cfg=mem_cfg,
    )

    assert manager is None


def test_llama_process_disabled_degrades_without_provider():
    mem_cfg = SimpleNamespace(
        embedding_model_path="/tmp/nonexistent-model.gguf",
        llama_process_enabled=False,
        query_planner_enabled=True,
        query_planner_model_path="/tmp/nonexistent-planner.gguf",
        rerank_enabled=True,
        rerank_model_path="/tmp/nonexistent-reranker.gguf",
        rerank_max_candidates=10,
        rerank_n_ctx=4096,
        rerank_n_gpu_layers=7,
        rerank_temperature=0.0,
        rerank_llama_weight=0.70,
        llama_request_timeout_ms=60000,
        hybrid_enabled=True,
        vector_k=50,
        keyword_k=50,
        hybrid_vector_weight=0.60,
        hybrid_keyword_weight=0.25,
        hybrid_exact_weight=0.10,
        hybrid_recency_weight=0.05,
    )

    assert MemoryManager._build_embedding(mem_cfg) is None
    assert MemoryManager._build_query_planner(mem_cfg).plan("查找").planner_source == "rule_based"

    retriever = MemoryManager._build_retriever(
        FakeStore(),
        None,
        mem_cfg,
        FakeFallbackSearch(),
    )
    assert isinstance(retriever, HybridRetriever)
    assert retriever._reranker is None


def test_openai_embedding_provider_path(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.embedding_vectors = [[0.11, 0.22, 0.33]]
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.embedding_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )

    mem_cfg = SimpleNamespace(
        embedding_provider=_provider_cfg(
            "openai",
            openai={
                "model": "embed-model",
                "api_key": "embed-key",
                "base_url": "https://embed.example",
            },
        ),
        embedding_model_path="",
        n_ctx=32768,
        n_gpu_layers=0,
        embedding_n_threads=4,
        embedding_verbose=False,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    embedding = MemoryManager._build_embedding(mem_cfg)

    assert embedding is not None
    assert embedding.dimension() == 3
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "embed-key",
        "base_url": "https://embed.example",
    }


def test_openai_memory_sync_apis_work_inside_running_loop(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.embedding_vectors = [[0.11, 0.22, 0.33]]
    DummyAsyncOpenAI.chat_content = json.dumps(
        [
            {"id": "2", "score": 95, "reason": "强相关"},
            {"id": "1", "score": 20, "reason": "弱相关"},
        ],
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.embedding_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.planning.openai_planner.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.rerank.openai_reranker.AsyncOpenAI",
        DummyAsyncOpenAI,
    )

    async def _run() -> tuple[int, tuple[int, int], str]:
        embedding = OpenAIEmbeddingProvider(model="embed-model", api_key="embed-key")
        planner = OpenAIQueryPlanner(model="planner-model", api_key="planner-key")
        reranker = OpenAIReranker(model="rerank-model", api_key="rerank-key", max_candidates=2)
        DummyAsyncOpenAI.chat_content = json.dumps(
            {
                "keyword_queries": ["查找线索"],
                "expanded_queries": [],
                "raw_md_terms": ["线索"],
                "query_type": "general",
            },
            ensure_ascii=False,
        )
        dimension = embedding.dimension()
        plan = planner.plan("查找线索")
        DummyAsyncOpenAI.chat_content = json.dumps(
            [
                {"id": "1", "score": 20, "reason": "弱相关"},
                {"id": "2", "score": 95, "reason": "强相关"},
            ],
            ensure_ascii=False,
        )
        candidates = [
            MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
            MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
        ]
        result = reranker.rerank("查找线索", candidates)
        return dimension, tuple(item.memory_id for item in result), plan.planner_source

    dimension, order, planner_source = asyncio.run(_run())

    assert dimension == 3
    assert order == (2, 1)
    assert planner_source == "openai"


def test_openai_embedding_requires_model():
    mem_cfg = SimpleNamespace(
        embedding_provider=_provider_cfg("openai", openai={"model": None}),
        embedding_model_path="",
        n_ctx=32768,
        n_gpu_layers=0,
        embedding_n_threads=4,
        embedding_verbose=False,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    with pytest.raises(ValueError, match="embedding_provider.openai.model"):
        MemoryManager._build_embedding(mem_cfg)


def test_openai_query_planner_path(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.chat_content = json.dumps(
        {
            "keyword_queries": ["查找线索"],
            "expanded_queries": ["查找 线索"],
            "raw_md_terms": ["线索"],
            "query_type": "general",
        },
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.planning.openai_planner.AsyncOpenAI",
        DummyAsyncOpenAI,
    )

    mem_cfg = SimpleNamespace(
        query_planner_enabled=True,
        query_planner_provider=_provider_cfg(
            "openai",
            openai={
                "model": "planner-model",
                "api_key": "planner-key",
                "base_url": "https://planner.example",
                "max_tokens": 256,
                "temperature": 0.1,
            },
        ),
        query_planner_model_path="",
        query_planner_n_ctx=2048,
        query_planner_n_gpu_layers=0,
        query_planner_temperature=0.0,
        query_planner_max_tokens=128,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    planner = MemoryManager._build_query_planner(mem_cfg)
    plan = planner.plan("查找线索")

    assert plan.planner_source == "openai"
    assert plan.keyword_queries[0] == "查找线索"
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "planner-key",
        "base_url": "https://planner.example",
    }


def test_openai_query_planner_requires_model():
    mem_cfg = SimpleNamespace(
        query_planner_enabled=True,
        query_planner_provider=_provider_cfg("openai", openai={"model": None}),
        query_planner_model_path="",
        query_planner_n_ctx=2048,
        query_planner_n_gpu_layers=0,
        query_planner_temperature=0.0,
        query_planner_max_tokens=128,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    with pytest.raises(ValueError, match="query_planner_provider.openai.model"):
        MemoryManager._build_query_planner(mem_cfg)


def test_openai_reranker_path(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.chat_content = json.dumps(
        [
            {"id": "1", "score": 20, "reason": "弱相关"},
            {"id": "2", "score": 95, "reason": "强相关"},
        ],
        ensure_ascii=False,
    )
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.rerank.openai_reranker.AsyncOpenAI",
        DummyAsyncOpenAI,
    )

    mem_cfg = SimpleNamespace(
        rerank_enabled=True,
        rerank_provider=_provider_cfg(
            "openai",
            openai={
                "model": "rerank-model",
                "api_key": "rerank-key",
                "base_url": "https://rerank.example",
                "max_candidates": 2,
                "temperature": 0.0,
                "rerank_weight": 0.7,
            },
        ),
        rerank_model_path="",
        rerank_max_candidates=2,
        rerank_n_ctx=4096,
        rerank_n_gpu_layers=0,
        rerank_temperature=0.0,
        rerank_llama_weight=0.7,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    reranker = MemoryManager._build_reranker(mem_cfg)
    candidates = [
        MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
        MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
    ]

    result = reranker.rerank("查找线索", candidates)

    assert [item.memory_id for item in result] == [2, 1]
    assert result[0].debug["openai_reason"] == "强相关"
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "rerank-key",
        "base_url": "https://rerank.example",
    }


def test_openai_reranker_requires_model():
    mem_cfg = SimpleNamespace(
        rerank_enabled=True,
        rerank_provider=_provider_cfg("openai", openai={"model": None}),
        rerank_model_path="",
        rerank_max_candidates=2,
        rerank_n_ctx=4096,
        rerank_n_gpu_layers=0,
        rerank_temperature=0.0,
        rerank_llama_weight=0.7,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    with pytest.raises(ValueError, match="rerank_provider.openai.model"):
        MemoryManager._build_reranker(mem_cfg)


def test_memory_provider_shared_is_rejected():
    mem_cfg = SimpleNamespace(
        embedding_provider=_provider_cfg("shared"),
        query_planner_provider=_provider_cfg("llama"),
        rerank_provider=_provider_cfg("llama"),
        embedding_model_path="",
        n_ctx=32768,
        n_gpu_layers=0,
        embedding_n_threads=4,
        embedding_verbose=False,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    with pytest.raises(ValueError, match="shared"):
        MemoryManager._build_embedding(mem_cfg)


def test_build_embedding_resolves_memory_openai_api_key_env(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.embedding_vectors = [[0.11, 0.22, 0.33]]
    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.embedding_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    monkeypatch.setenv("MEMORY_EMBED_KEY", "env-embed-key")

    mem_cfg = SimpleNamespace(
        embedding_provider=_provider_cfg(
            "openai",
            openai={
                "model": "embed-model",
                "api_key_env": "MEMORY_EMBED_KEY",
                "base_url": "https://embed.example",
            },
        ),
        embedding_model_path="",
        n_ctx=32768,
        n_gpu_layers=0,
        embedding_n_threads=4,
        embedding_verbose=False,
        llama_process_enabled=True,
        llama_request_timeout_ms=60000,
    )

    embedding = MemoryManager._build_embedding(mem_cfg)

    assert embedding is not None
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "env-embed-key",
        "base_url": "https://embed.example",
    }


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
