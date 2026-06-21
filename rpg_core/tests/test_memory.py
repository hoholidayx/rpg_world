from __future__ import annotations

import asyncio
from types import SimpleNamespace

import json

import pytest

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.llm.manager import LLMManager
from rpg_world.rpg_core.llm.openai_provider import OpenAIProvider
from rpg_world.rpg_core.memory.memory_manager import MemoryManager, RecallItem
from rpg_world.rpg_core.memory import run as memory_run
from rpg_world.rpg_core.memory.storage.types import ChunkRecord
from rpg_world.rpg_core.memory.storage.vector_store import VectorStore
from rpg_world.rpg_core.memory.storage import vector_store as vector_store_module
from rpg_world.rpg_core.memory.planning.openai_planner import OpenAIQueryPlanner
from rpg_world.rpg_core.memory.retrieval.bigram_retriever import BigramRetriever
from rpg_world.rpg_core.memory.retrieval.hybrid_retriever import HybridRetriever
from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retrieval.raw_md_retriever import RawMarkdownRetriever
from rpg_world.rpg_core.memory.retrieval.sqlvec_retriever import SqlVecRetriever
from rpg_world.rpg_core.memory.rerank import MemoryReranker, PointwiseMemoryReranker
from rpg_world.rpg_core.memory.rerank.common import blend_pointwise_scores, parse_pointwise_output
from rpg_world.rpg_core.memory.rerank import service as rerank_service_module
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
    chat_contents: list[str] | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.embeddings = SimpleNamespace(create=self._create_embeddings)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat))
        self.instances.append(self)

    async def _create_embeddings(self, **kwargs):  # noqa: ANN003
        data = [SimpleNamespace(embedding=list(vec)) for vec in self.embedding_vectors[: len(kwargs.get("input", []))]]
        return SimpleNamespace(data=data)

    async def _create_chat(self, **kwargs):  # noqa: ANN003
        if self.chat_contents:
            content = self.chat_contents.pop(0)
        else:
            content = self.chat_content
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice], usage=None, model="dummy-model", id="dummy-id", created=0)


def _provider_cfg(provider: str, *, openai: dict[str, object] | None = None, llama: dict[str, object] | None = None):
    return SimpleNamespace(
        provider=provider,
        openai=openai or {},
        llama=llama or {},
    )


def test_memory_manager_create_disabled(fake_recalled_store):
    mem_cfg = SimpleNamespace(enabled=False)
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir="/tmp/session",
        get_vector_db_path="/tmp/session/memory_vectors.db",
        mem_cfg=mem_cfg,
    )

    assert manager is None


def test_memory_manager_falls_back_when_llm_manager_fails(monkeypatch):
    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    mem_cfg = SimpleNamespace(
        enabled=True,
        embedding_provider=_provider_cfg("llama"),
        query_planner_provider=_provider_cfg("llama"),
        rerank_provider=_provider_cfg("llama"),
        hybrid_enabled=True,
        rerank_enabled=False,
        top_k=5,
        bigram_k=50,
        hybrid_vector_weight=0.60,
        hybrid_bigram_weight=0.25,
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


def test_memory_manager_uses_llm_manager_for_embedding(monkeypatch):
    embedding = FakeEmbedding([[0.11, 0.22, 0.33]])
    calls: list[str] = []

    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        calls.append(biz_key)
        return embedding

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    mem_cfg = SimpleNamespace(enabled=True, embedding_provider=_provider_cfg("llama"))
    result = MemoryManager._build_embedding(mem_cfg)

    assert result is embedding
    assert calls == ["memory.embed"]


def test_openai_memory_sync_apis_work_inside_running_loop(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.embedding_vectors = [[0.11, 0.22, 0.33]]
    DummyAsyncOpenAI.chat_contents = [
        json.dumps(
            {
                "bigram_queries": ["查找线索"],
                "expanded_queries": [],
                "raw_md_terms": ["线索"],
                "query_type": "general",
            },
            ensure_ascii=False,
        ),
        "20\t弱相关",
        "95\t强相关",
    ]
    monkeypatch.setattr(
        "rpg_world.rpg_core.llm.openai_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    async def _run() -> tuple[int, tuple[int, int], str]:
        embedding = OpenAIProvider(model="embed-model", api_key="embed-key")
        planner_provider = OpenAIProvider(model="planner-model", api_key="planner-key")
        planner = OpenAIQueryPlanner(planner_provider)
        rerank_provider = OpenAIProvider(model="rerank-model", api_key="rerank-key")
        reranker = PointwiseMemoryReranker(rerank_provider, provider_label="openai")

        dimension = embedding.dimension()
        plan = planner.plan("查找线索")
        candidates = [
            MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
            MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
        ]
        result = reranker.rerank("查找线索", candidates)
        return dimension, tuple(item.memory_id for item in result), plan.planner_source

    try:
        dimension, order, planner_source = asyncio.run(_run())
    finally:
        pass

    assert dimension == 3
    assert order == (2, 1)
    assert planner_source == "openai"


def test_memory_manager_uses_llm_manager_for_query_planner(monkeypatch):
    planner = RuleBasedQueryPlanner()

    class FakeLLMProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            return SimpleNamespace(
                content='{"bigram_queries":["查找线索"],"expanded_queries":[],"raw_md_terms":["线索"],"query_type":"general"}',
            )

        def get_default_model(self):  # noqa: ANN001
            return "test-model"

    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        return FakeLLMProvider()

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    mem_cfg = SimpleNamespace(
        enabled=True,
        query_planner_enabled=True,
        jieba_dict="",
        query_planner_provider=_provider_cfg("llama"),
    )
    result = MemoryManager._build_query_planner(mem_cfg, planner)

    assert result.plan("查找线索").planner_source == "llama"


def test_memory_manager_query_planner_respects_disabled_flag(monkeypatch):
    planner = RuleBasedQueryPlanner()

    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        raise AssertionError(f"query planner should not resolve provider {biz_key}")

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    mem_cfg = SimpleNamespace(
        enabled=True,
        query_planner_enabled=False,
        jieba_dict="",
        query_planner_provider=_provider_cfg("llama"),
    )
    result = MemoryManager._build_query_planner(mem_cfg, planner)

    assert result.plan("查找线索").planner_source == "rule_based"


def test_memory_manager_query_planner_falls_back_on_manager_failure(monkeypatch):
    planner = RuleBasedQueryPlanner()

    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        raise RuntimeError("planner boom")

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    mem_cfg = SimpleNamespace(
        enabled=True,
        query_planner_enabled=True,
        jieba_dict="",
        query_planner_provider=_provider_cfg("llama"),
    )
    result = MemoryManager._build_query_planner(mem_cfg, planner)

    assert result.plan("查找线索").planner_source == "rule_based"


def test_openai_reranker_path(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.chat_contents = [
        "20\t弱相关",
        "95\t强相关",
        "5\t无关",
    ]
    monkeypatch.setattr(
        "rpg_world.rpg_core.llm.openai_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    provider = OpenAIProvider(
        model="rerank-model",
        api_key="rerank-key",
        base_url="https://rerank.example",
    )
    reranker = PointwiseMemoryReranker(provider, provider_label="openai")
    candidates = [
        MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
        MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
        MemoryCandidate(memory_id=3, content="three", hybrid_score=0.1),
    ]

    result = reranker.rerank("查找线索", candidates)

    assert [item.memory_id for item in result] == [2, 1, 3]
    assert result[0].debug["openai_score_norm"] == 0.95
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "rerank-key",
        "base_url": "https://rerank.example",
    }


def test_openai_reranker_requires_model(monkeypatch):
    def fake_get_provider(_self, biz_key):  # noqa: ANN001
        raise ValueError("memory.rerank.openai.model is required")

    monkeypatch.setattr(LLMManager, "get_provider", fake_get_provider)

    # noinspection PyTypeChecker
    mem_cfg = SimpleNamespace(rerank_enabled=True)
    with pytest.raises(ValueError, match="memory.rerank.openai.model"):
        MemoryManager._build_reranker(mem_cfg)


def test_memory_manager_reranker_uses_settings_rerank_score_weight(monkeypatch):
    class FakeProvider:
        pass

    class FakeManager:
        def get_provider(self, biz_key):  # noqa: ANN001
            return FakeProvider()

    class FakeLLMManager:
        @classmethod
        def get(cls) -> FakeManager:  # noqa: ANN101
            return FakeManager()

    monkeypatch.setattr("rpg_world.rpg_core.llm.manager.LLMManager", FakeLLMManager)
    reranker = MemoryManager._build_reranker(
        SimpleNamespace(
            rerank_enabled=True,
            rerank_score_weight=0.42,
            rerank_provider=_provider_cfg("openai"),
        )
    )

    assert isinstance(reranker, PointwiseMemoryReranker)
    assert reranker._rerank_weight == 0.42


def test_pointwise_rerank_core_parses_and_blends_scores():
    score, reason = parse_pointwise_output("90 | strong match")
    assert score == 90.0
    assert reason == "strong match"

    candidates = [
        MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
        MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
    ]
    result = blend_pointwise_scores(
        candidates,
        {1: 20.0, 2: 95.0},
        {1: "weak", 2: "strong"},
        0.7,
        "rerank_score_norm",
        "rerank_reason",
    )

    assert [item.memory_id for item in result] == [2, 1]
    assert result[0].debug["rerank_score_norm"] == 0.95
    assert result[0].debug["rerank_reason"] == "strong"


def test_rerank_package_exports_unified_interface_only():
    assert MemoryReranker.__name__ == "MemoryReranker"
    assert PointwiseMemoryReranker.__name__ == "PointwiseMemoryReranker"


def test_hybrid_retriever_merges_sources_and_falls_back():
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "vector-one", {"source": "vec"}), 0.0),
        (FakeChunkRecord(2, "vector-two", {"source": "vec"}), 0.1),
    ]
    store.bigram_rows = {
        "寻找 线索": [
            MemoryCandidate(memory_id=2, content="vector-two", metadata={"source": "bg"}, bigram_score=0.1),
            MemoryCandidate(memory_id=3, content="bigram-three", metadata={"source": "bg"}, bigram_score=0.05),
        ]
    }

    class FakeRawSearch:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int = 50):
            self.calls.append((query, limit))
            return [
                MemoryCandidate(memory_id=4, content="raw-four", metadata={"source": "md"}, bigram_score=0.01),
            ][:limit]

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.calls.append((plan.normalized_query, limit))
            return [
                MemoryCandidate(memory_id=4, content="raw-four", metadata={"source": "md"}, bigram_score=0.01),
            ][:limit]

    raw_search = FakeRawSearch()
    retriever = HybridRetriever(
        sqlvec_retriever=SqlVecRetriever(store=store, embedding=FakeEmbedding([[0.1, 0.2, 0.3]])),
        bigram_retriever=BigramRetriever(store=store, limit=2),
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        reranker=None,
    )

    result = retriever.hybrid_search("寻找 线索", top_k=2)

    assert [item.content for item in result] == ["vector-one", "vector-two"]
    assert store.search_calls
    assert store.bigram_calls
    assert raw_search.calls


def test_sqlvec_retriever_sync(fake_token_counter):
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "dense-one", {"source": "vec"}), 0.0),
    ]
    retriever = SqlVecRetriever(store=store, embedding=FakeEmbedding([[1.0, 0.0, 0.0]]))

    result = retriever.retrieve_sync("query", top_k=1)
    assert result[0][0] == "dense-one"
    assert result[0][1] == 1.0


def test_inspect_vector_store_loads_sqlite_vec_backend(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / 'memory_vectors.db'
    store = VectorStore(db_path=db_path, dimension=3)
    store.upsert([ChunkRecord(id=1, text='vector chunk', metadata={'source': 'vec', 'file': 'a.md', 'chunk_idx': 0})], [[0.1, 0.2, 0.3]])
    store.close()

    monkeypatch.setattr(memory_run.settings, 'get_vector_db_path', lambda workspace, session: db_path)

    memory_run.inspect_vector_store('ws', 'sess')

    out = capsys.readouterr().out
    assert '向量后端:' in out
    assert '向量 row 数: 1' in out


def test_vector_store_logs_backend(tmp_path, monkeypatch):
    messages: list[str] = []

    def capture(message, *args, **kwargs):  # noqa: ANN001
        messages.append(message.format(*args))

    monkeypatch.setattr(vector_store_module.logger, 'info', capture)

    store = VectorStore(db_path=tmp_path / 'vectors.db', dimension=3)
    store.close()

    assert any('backend=' in msg for msg in messages)
    assert any('[VectorStore] ready:' in msg for msg in messages)

def test_pointwise_reranker_logs_failed_preview(monkeypatch):
    messages: list[str] = []

    def capture(message, *args, **kwargs):  # noqa: ANN001
        messages.append(message.format(*args))

    monkeypatch.setattr(rerank_service_module.logger, 'warning', capture)

    class FakeProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            return SimpleNamespace(content='plain text output')

    reranker = PointwiseMemoryReranker(FakeProvider(), provider_label='llama')
    result = reranker.rerank('怪兽', [MemoryCandidate(memory_id=1, content='a')])

    assert [item.memory_id for item in result] == [1]
    assert any('pointwise score failed' in msg for msg in messages)
    assert any('preview=' in msg for msg in messages)


def test_pointwise_reranker_accepts_pointwise_output(monkeypatch):
    outputs = iter(['90\tstrong match', '10\tweak match'])

    class FakeProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            return SimpleNamespace(content=next(outputs))

    reranker = PointwiseMemoryReranker(FakeProvider(), provider_label='llama')
    result = reranker.rerank(
        '怪兽',
        [
            MemoryCandidate(memory_id=1, content='a', hybrid_score=0.2),
            MemoryCandidate(memory_id=2, content='b', hybrid_score=0.8),
        ],
    )

    assert [item.memory_id for item in result] == [1, 2]
    assert result[0].rerank_score > result[1].rerank_score

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
        bigram_retriever=BigramRetriever(store=store, limit=2),
        raw_md_retriever=RawMarkdownRetriever(RawMarkdownGrepSearch([])),
        reranker=None,
    )

    def boom(_self, _query):
        raise RuntimeError("planner boom")

    monkeypatch.setattr(
        "rpg_world.rpg_core.memory.retrieval.hybrid_retriever.RuleBasedQueryPlanner.plan",
        boom,
    )

    assert retriever.hybrid_search("查找线索") == []
