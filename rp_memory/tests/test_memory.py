from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from llm_client.keys import MEMORY_EMBED_BIZ_KEY, MEMORY_QUERY_PLANNER_BIZ_KEY
from llm_client.manager import LLMClientManager
from llm_service.manager import LLMManager as ServerLLMManager
from llm_service.keys import (
    MEMORY_RERANK_BIZ_KEY,
    RERANK_MODEL_TYPE_CHAT_POINTWISE,
    RERANK_MODEL_TYPE_QWEN3_LOGIT,
)
from llm_service.openai_provider import OpenAIProvider
from llm_service.llama_provider import LlamaLogitRerankProvider
from rp_memory.candidate import MemoryCandidate
from rp_memory.memory_manager import MemoryManager, RecallItem
from rp_memory import run as memory_run
from rp_memory.storage.types import ChunkRecord, IndexedFileState
from rp_memory.storage.vector_store import VectorStore
from rp_memory.storage import vector_store as vector_store_module
from rp_memory.keyword_tokenizer import (
    BigramKeywordTokenizer,
    CombinedKeywordTokenizer,
    JiebaKeywordTokenizer,
)
from rp_memory.planning.openai_planner import OpenAIQueryPlanner
from rp_memory.planning.plan import QueryPlan
from rp_memory.retrieval.keyword_retriever import KeywordRetriever
from rp_memory.retrieval.hybrid_retriever import HybridRetriever
from rp_memory.retrieval.hybrid_retriever import _build_rerank_query
from rp_memory.retrieval.priority import granularity_score, resolve_memory_granularity
from rp_memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch, _frontmatter_metadata
from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever
from rp_memory.retrieval.sqlvec_retriever import SqlVecRetriever
from rp_memory.rerank import (
    ChatPointwiseScoreProvider,
    LogitRerankProvider,
    MemoryReranker,
    MemoryScore,
    MemoryScoreProvider,
    PointwiseMemoryReranker,
)
from rp_memory.rerank.common import build_pointwise_prompt, blend_pointwise_scores, parse_pointwise_output
from rp_memory.rerank import service as rerank_service_module
from rp_memory.planning.planner import RuleBasedQueryPlanner
from rp_memory.storage.text_index import _keyword_relevance
from rp_memory.vector_index_manager import VectorIndexManager, WatchSource
from rp_memory.tests.conftest import FakeEmbedding, FakeFallbackSearch, FakeRetriever, FakeStore
from rpg_core.settings import MemorySettings


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


def test_memory_manager_create_disabled(fake_recalled_store):
    mem_cfg = SimpleNamespace(enabled=False)
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir="/tmp/session",
        get_vector_db_path="/tmp/session/memory_vectors.db",
        mem_cfg=mem_cfg,
    )

    assert manager is None


async def test_memory_manager_create_and_initialize_do_not_contact_llm(
    tmp_path,
    monkeypatch,
    fake_recalled_store,
):
    calls: list[str] = []
    embedding = FakeEmbedding([[0.11, 0.22, 0.33]])

    async def fake_get_provider(_self, biz_key):  # noqa: ANN001
        calls.append(biz_key)
        return embedding

    monkeypatch.setattr(LLMClientManager, "get_provider", fake_get_provider)
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    (summaries / "one.md").write_text("alpha memory clue", encoding="utf-8")
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir=str(tmp_path),
        get_vector_db_path=str(tmp_path / "memory_vectors.db"),
        mem_cfg=MemorySettings(enabled=True, raw_md_mode="always"),
    )

    assert manager is not None
    assert calls == []
    await manager.initialize()
    assert calls == []

    items = await manager.recall("alpha memory")

    assert calls == [MEMORY_EMBED_BIZ_KEY]
    assert embedding.calls
    assert items
    await manager.close()


async def test_memory_manager_remote_failure_keeps_fallback_and_retries(
    tmp_path,
    monkeypatch,
    fake_recalled_store,
):
    attempts = 0
    embedding = FakeEmbedding([[0.1, 0.2, 0.3]])

    async def fake_get_provider(_self, biz_key):  # noqa: ANN001
        nonlocal attempts
        assert biz_key == MEMORY_EMBED_BIZ_KEY
        attempts += 1
        if attempts == 1:
            raise RuntimeError("embedding unavailable")
        return embedding

    monkeypatch.setattr(LLMClientManager, "get_provider", fake_get_provider)
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    (summaries / "one.md").write_text("alpha memory clue", encoding="utf-8")
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir=str(tmp_path),
        get_vector_db_path=str(tmp_path / "memory_vectors.db"),
        mem_cfg=MemorySettings(enabled=True, raw_md_mode="always"),
    )
    assert manager is not None

    first = await manager.recall("alpha memory")
    second = await manager.recall("alpha memory")

    assert first
    assert second
    assert attempts == 2
    assert manager._embedding_ready is True  # noqa: SLF001
    await manager.close()


async def test_openai_memory_async_apis_work_inside_running_loop(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.embedding_vectors = [[0.11, 0.22, 0.33]]
    DummyAsyncOpenAI.chat_contents = [
        json.dumps(
            {
                "keyword_queries": ["查找线索"],
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
        "llm_service.openai_provider.AsyncOpenAI",
        DummyAsyncOpenAI,
    )
    embedding = OpenAIProvider(model="embed-model", api_key="embed-key")
    planner_provider = OpenAIProvider(model="planner-model", api_key="planner-key")
    planner = OpenAIQueryPlanner(planner_provider)
    rerank_provider = OpenAIProvider(model="rerank-model", api_key="rerank-key")
    reranker = PointwiseMemoryReranker(rerank_provider, provider_label="openai")

    dimension = await embedding.dimension()
    plan = await planner.plan("查找线索")
    candidates = [
        MemoryCandidate(memory_id=1, content="one", hybrid_score=0.2),
        MemoryCandidate(memory_id=2, content="two", hybrid_score=0.8),
    ]
    result = await reranker.rerank("查找线索", candidates)
    order = tuple(item.memory_id for item in result)
    planner_source = plan.planner_source

    assert dimension == 3
    assert order == (2, 1)
    assert planner_source == "openai"


async def test_memory_manager_lazily_resolves_query_planner(
    tmp_path,
    monkeypatch,
    fake_recalled_store,
):
    calls: list[str] = []
    embedding = FakeEmbedding([[0.1, 0.2, 0.3]])

    class FakeLLMProvider:
        def __init__(self) -> None:
            self.chat_calls = 0

        async def chat(self, messages, tools=None):  # noqa: ANN001
            self.chat_calls += 1
            return SimpleNamespace(
                content='{"keyword_queries":["查找线索"],"expanded_queries":[],"raw_md_terms":["线索"],"query_type":"general"}',
            )

        def get_default_model(self):  # noqa: ANN001
            return "test-model"

    planner_provider = FakeLLMProvider()

    async def fake_get_provider(_self, biz_key):  # noqa: ANN001
        calls.append(biz_key)
        if biz_key == MEMORY_EMBED_BIZ_KEY:
            return embedding
        assert biz_key == MEMORY_QUERY_PLANNER_BIZ_KEY
        return planner_provider

    monkeypatch.setattr(LLMClientManager, "get_provider", fake_get_provider)

    summaries = tmp_path / "summaries"
    summaries.mkdir()
    (summaries / "one.md").write_text("查找线索", encoding="utf-8")
    manager = MemoryManager.create(
        recalled_store=fake_recalled_store,
        session_dir=str(tmp_path),
        get_vector_db_path=str(tmp_path / "memory_vectors.db"),
        mem_cfg=MemorySettings(
            enabled=True,
            query_planner_enabled=True,
            raw_md_mode="always",
        ),
    )
    assert manager is not None

    await manager.initialize()
    assert calls == []
    await manager.recall("查找线索")

    assert set(calls) == {MEMORY_EMBED_BIZ_KEY, MEMORY_QUERY_PLANNER_BIZ_KEY}
    assert planner_provider.chat_calls == 1
    await manager.close()


async def test_openai_reranker_path(monkeypatch):
    DummyAsyncOpenAI.instances = []
    DummyAsyncOpenAI.chat_contents = [
        "20\t弱相关",
        "95\t强相关",
        "5\t无关",
    ]
    monkeypatch.setattr(
        "llm_service.openai_provider.AsyncOpenAI",
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

    result = await reranker.rerank("查找线索", candidates)

    assert [item.memory_id for item in result] == [2, 1, 3]
    assert result[0].debug["openai_score_norm"] == 0.95
    assert DummyAsyncOpenAI.instances[0].kwargs == {
        "api_key": "rerank-key",
        "base_url": "https://rerank.example",
    }


def test_memory_manager_reranker_uses_settings_rerank_score_weight():
    class FakeProvider:
        pass

    reranker = MemoryManager._build_reranker_with_provider(
        SimpleNamespace(
            rerank_score_weight=0.42,
        ),
        FakeProvider(),
    )

    assert isinstance(reranker, PointwiseMemoryReranker)
    assert reranker._rerank_weight == 0.42


def test_llm_manager_builds_logit_provider_for_llama_rerank(monkeypatch):
    class FakeCfg:
        provider_key = "memory_rerank"
        provider = "llama"
        kind = "rerank"
        rerank_model_type = RERANK_MODEL_TYPE_QWEN3_LOGIT
        llama_model_path = "/tmp/qwen-rerank.gguf"
        llama_n_ctx = 512
        llama_max_length = 256
        llama_n_gpu_layers = 0
        llama_verbose = False
        llama_request_timeout_ms = 1234

    class FakeRerankModel:
        def __init__(self, model_path, **kwargs):  # noqa: ANN001
            self.model_path = model_path
            self.kwargs = kwargs

        async def rerank_async(self, query, documents, *, instruction, max_length):  # noqa: ANN001
            return [{"score": 0.9, "yes_logit": 2.0, "no_logit": 0.0} for _ in documents]

    monkeypatch.setattr("llm_service.manager.resolve_biz_config", lambda _key: FakeCfg())
    monkeypatch.setattr("llm_service.manager.DirectLlamaRerankModel", FakeRerankModel)

    provider = ServerLLMManager().get_provider(MEMORY_RERANK_BIZ_KEY)

    assert isinstance(provider, LlamaLogitRerankProvider)
    assert provider.get_default_model() == "/tmp/qwen-rerank.gguf"


def test_llm_manager_builds_chat_score_provider_for_openai_rerank(monkeypatch):
    class FakeCfg:
        provider_key = "memory_rerank"
        provider = "openai"
        kind = "rerank"
        rerank_model_type = RERANK_MODEL_TYPE_CHAT_POINTWISE
        openai_model = "rerank-model"
        openai_api_key = "rerank-key"
        openai_base_url = "https://rerank.example"
        openai_max_tokens = 8
        openai_temperature = 0.0

    class FakeManager(ServerLLMManager):
        def _build_openai_client(self, **_kwargs):  # noqa: ANN003
            return SimpleNamespace()

    monkeypatch.setattr("llm_service.manager.resolve_biz_config", lambda _key: FakeCfg())

    provider = FakeManager().get_provider(MEMORY_RERANK_BIZ_KEY)

    assert isinstance(provider, OpenAIProvider)
    assert provider.get_default_model() == "rerank-model"


def test_llm_manager_rejects_rerank_model_type_backend_mismatch(monkeypatch):
    class FakeCfg:
        provider_key = "memory_rerank"
        provider = "openai"
        kind = "rerank"
        rerank_model_type = RERANK_MODEL_TYPE_QWEN3_LOGIT

    monkeypatch.setattr("llm_service.manager.resolve_biz_config", lambda _key: FakeCfg())

    with pytest.raises(ValueError, match="rerank_model_type"):
        ServerLLMManager().get_provider(MEMORY_RERANK_BIZ_KEY)


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


async def test_pointwise_reranker_uses_score_provider_and_writes_logit_debug():
    class FakeScoreProvider(MemoryScoreProvider):
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[int]]] = []

        async def score(self, query, candidates):  # noqa: ANN001
            self.calls.append((query, [candidate.memory_id for candidate in candidates]))
            return [
                MemoryScore(
                    score=0.9,
                    reason="yes/no logits",
                    debug={"source": "logits", "yes_logit": 3.0, "no_logit": 1.0},
                ),
                MemoryScore(
                    score=0.1,
                    reason="yes/no logits",
                    debug={"source": "logits", "yes_logit": 0.0, "no_logit": 4.0},
                ),
            ]

    provider = FakeScoreProvider()
    reranker = PointwiseMemoryReranker(provider, provider_label="qwen_rerank")
    candidates = [
        MemoryCandidate(memory_id=1, content="wolf", hybrid_score=0.2),
        MemoryCandidate(memory_id=2, content="tavern", hybrid_score=0.8),
    ]

    result = await reranker.rerank("monster", candidates)

    assert provider.calls == [("monster", [1, 2])]
    assert [item.memory_id for item in result] == [1, 2]
    assert result[0].debug["qwen_rerank_score_norm"] == 0.9
    assert result[0].debug["qwen_rerank_source"] == "logits"
    assert result[0].debug["qwen_rerank_yes_logit"] == 3.0
    assert result[0].debug["qwen_rerank_no_logit"] == 1.0


async def test_qwen_reranker_provider_scores_without_chat():
    class FakeRerankModel:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def rerank_async(self, query, documents, *, instruction, max_length):  # noqa: ANN001
            self.calls.append(
                {
                    "query": query,
                    "documents": documents,
                    "instruction": instruction,
                    "max_length": max_length,
                }
            )
            return [
                {"score": 0.9, "yes_logit": 2.0, "no_logit": 0.0},
                {"score": 0.1, "yes_logit": -1.0, "no_logit": 1.0},
            ]

    model = FakeRerankModel()
    document_provider = LlamaLogitRerankProvider(
        model_path="/tmp/qwen-rerank.gguf",
        n_ctx=256,
        instruction="match memories",
        model=model,
    )
    provider = LogitRerankProvider(document_provider)

    scores = await provider.score(
        "query",
        [
            MemoryCandidate(memory_id=1, content="one"),
            MemoryCandidate(memory_id=2, content="two"),
        ],
    )

    assert [score.score for score in scores] == [0.9, 0.1]
    assert scores[0].debug == {"source": "logits", "yes_logit": 2.0, "no_logit": 0.0}
    assert model.calls == [
        {
            "query": "query",
            "documents": ["one", "two"],
            "instruction": "match memories",
            "max_length": 256,
        }
    ]


def test_pointwise_rerank_prompt_is_short_and_strict():
    prompt = build_pointwise_prompt(
        "查找酒馆老板",
        MemoryCandidate(memory_id=1, content="酒馆老板格里姆给了Bob一袋烈酒。"),
    )

    assert "输出格式" in prompt
    assert "评分：" in prompt
    assert "候选：" in prompt
    assert len(prompt) < 180


def test_rerank_package_exports_unified_interface_only():
    assert MemoryReranker.__name__ == "MemoryReranker"
    assert PointwiseMemoryReranker.__name__ == "PointwiseMemoryReranker"


async def test_hybrid_retriever_merges_sources_and_falls_back():
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "vector-one", {"source": "vec"}), 0.0),
        (FakeChunkRecord(2, "vector-two", {"source": "vec"}), 0.1),
    ]
    store.keyword_rows = {
        "寻找 线索": [
            MemoryCandidate(memory_id=2, content="vector-two", metadata={"source": "kw"}, keyword_score=0.1),
            MemoryCandidate(memory_id=3, content="keyword-three", metadata={"source": "kw"}, keyword_score=0.05),
        ]
    }

    class FakeRawSearch:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, query: str, limit: int = 50):
            self.calls.append((query, limit))
            return [
                MemoryCandidate(memory_id=4, content="raw-four", metadata={"source": "md"}, raw_md_score=0.5),
            ][:limit]

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.calls.append((plan.normalized_query, limit))
            return [
                MemoryCandidate(memory_id=4, content="raw-four", metadata={"source": "md"}, raw_md_score=0.5),
            ][:limit]

    raw_search = FakeRawSearch()
    retriever = HybridRetriever(
        sqlvec_retriever=SqlVecRetriever(store=store, embedding=FakeEmbedding([[0.1, 0.2, 0.3]])),
        keyword_retriever=KeywordRetriever(store=store, limit=2),
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        reranker=None,
        raw_md_mode="fallback_only",
        raw_md_min_results=4,
    )

    result = await retriever.hybrid_search("寻找 线索", top_k=2)

    assert [item.content for item in result] == ["vector-one", "vector-two"]
    assert store.search_calls
    assert store.keyword_calls
    assert raw_search.calls


async def test_sqlvec_retriever_async(fake_token_counter):
    store = FakeStore()
    store.vector_rows = [
        (FakeChunkRecord(1, "dense-one", {"source": "vec"}), 0.0),
    ]
    retriever = SqlVecRetriever(store=store, embedding=FakeEmbedding([[1.0, 0.0, 0.0]]))

    result = await retriever.retrieve("query", top_k=1)
    assert result[0][0] == "dense-one"
    assert result[0][1] == 1.0


def test_inspect_vector_store_loads_sqlite_vec_backend(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / 'memory_vectors.db'
    store = VectorStore(db_path=db_path, dimension=3)
    store.upsert([ChunkRecord(id=1, text='vector chunk', metadata={'source': 'vec', 'file': 'a.md', 'chunk_idx': 0})], [[0.1, 0.2, 0.3]])
    store.close()

    monkeypatch.setattr(memory_run, '_vector_db_path', lambda session: db_path)

    memory_run.inspect_vector_store('ws', 'sess')

    out = capsys.readouterr().out
    assert '向量后端:' in out
    assert '向量 row 数: 1' in out


async def test_memory_run_initialize_manager_starts_file_watcher(monkeypatch, capsys):
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

    monkeypatch.setattr(memory_run, "get_watcher", lambda: DummyWatcher())

    await memory_run.initialize_manager(DummyManager(), "sess")

    assert calls == ["initialize", "start"]
    assert "FileWatcher: running" in capsys.readouterr().out


def test_vector_store_logs_backend(tmp_path, monkeypatch):
    messages: list[str] = []

    def capture(message, *args, **kwargs):  # noqa: ANN001
        messages.append(message.format(*args))

    monkeypatch.setattr(vector_store_module.logger, 'info', capture)

    store = VectorStore(db_path=tmp_path / 'vectors.db', dimension=3)
    store.close()

    assert any('backend=' in msg for msg in messages)
    assert any('[VectorStore] ready:' in msg for msg in messages)


def test_keyword_tokenizers_support_jieba_bigram_and_both():
    jieba_tokens = JiebaKeywordTokenizer().tokenize("猎人的尸体在哪发现")
    bigram_tokens = BigramKeywordTokenizer().tokenize("猎人的尸体")
    both_tokens = CombinedKeywordTokenizer().tokenize("猎人的尸体")

    assert "猎人" in jieba_tokens
    assert "猎人" in bigram_tokens
    assert "尸体" in both_tokens
    assert both_tokens.count("猎人") == 1


def test_vector_store_keyword_search_uses_configured_tokenizer(tmp_path):
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None, keyword_tokenizer="bigram")
    store.upsert([
        ChunkRecord(id=1, text="猎人的尸体在旧井旁发现", metadata={"source": "vec", "file": "a.md", "chunk_idx": 0})
    ])

    result = store.keyword_search("猎人的尸体", limit=5)

    assert result
    assert result[0].keyword_score > 0
    assert result[0].keyword_score <= 1.0
    assert result[0].debug["keyword_tokenizer"] == "bigram"
    assert "keyword_bm25" in result[0].debug
    assert "keyword_relevance" in result[0].debug
    store.close()


def test_keyword_relevance_is_bounded_for_sqlite_rank_signs():
    assert _keyword_relevance(-2.0) == pytest.approx(2.0 / 3.0)
    assert _keyword_relevance(3.0) == pytest.approx(0.25)
    assert _keyword_relevance(0.0) == 1.0


def _chunk_rows(store: VectorStore):
    return store._repo.conn.execute(  # noqa: SLF001
        "SELECT text, source, file, chunk_idx FROM chunks ORDER BY file, chunk_idx"
    ).fetchall()


def _manifest_rows(store: VectorStore):
    return store._repo.conn.execute(  # noqa: SLF001
        "SELECT file, source_id, status, chunk_count, last_error FROM indexed_files ORDER BY file"
    ).fetchall()


async def test_vector_index_manager_incremental_sync_skips_unchanged_files(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    first = source_dir / "a.md"
    second = source_dir / "b.md"
    first.write_text("alpha memory", encoding="utf-8")
    second.write_text("beta memory", encoding="utf-8")
    embedding = FakeEmbedding([[0.1, 0.2, 0.3]])
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=3)
    manager = VectorIndexManager(
        store=store,
        embedding=embedding,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )

    await manager.sync_all()
    await manager.sync_all()

    assert len(embedding.calls) == 2
    assert [row[0] for row in _chunk_rows(store)] == ["alpha memory", "beta memory"]
    assert [row[2] for row in _manifest_rows(store)] == ["indexed", "indexed"]
    store.close()


async def test_vector_index_manager_skips_hash_read_for_stat_unchanged_files(tmp_path, monkeypatch):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    file_path = source_dir / "a.md"
    file_path.write_text("alpha memory", encoding="utf-8")
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None)
    manager = VectorIndexManager(
        store=store,
        embedding=None,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )
    path_cls = type(file_path)
    original_read_bytes = path_cls.read_bytes
    read_count = 0

    def counting_read_bytes(self):  # noqa: ANN001
        nonlocal read_count
        read_count += 1
        return original_read_bytes(self)

    monkeypatch.setattr(path_cls, "read_bytes", counting_read_bytes)

    await manager.sync_all()
    await manager.sync_all()

    assert read_count == 1
    store.close()


async def test_vector_index_manager_incremental_sync_reindexes_only_changed_file(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    first = source_dir / "a.md"
    second = source_dir / "b.md"
    first.write_text("alpha memory", encoding="utf-8")
    second.write_text("beta memory", encoding="utf-8")
    embedding = FakeEmbedding([[0.1, 0.2, 0.3]])
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=3)
    manager = VectorIndexManager(
        store=store,
        embedding=embedding,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )
    await manager.sync_all()

    first.write_text("alpha memory changed", encoding="utf-8")
    await manager.sync_all()

    assert len(embedding.calls) == 3
    assert embedding.calls[-1] == ["alpha memory changed"]
    assert [row[0] for row in _chunk_rows(store)] == ["alpha memory changed", "beta memory"]
    store.close()


async def test_vector_index_manager_incremental_sync_deletes_removed_file(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    first = source_dir / "a.md"
    second = source_dir / "b.md"
    first.write_text("alpha memory", encoding="utf-8")
    second.write_text("beta memory", encoding="utf-8")
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None)
    manager = VectorIndexManager(
        store=store,
        embedding=None,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )
    await manager.sync_all()

    second.unlink()
    await manager.sync_all()

    rows = _chunk_rows(store)
    assert len(rows) == 1
    assert rows[0][0] == "alpha memory"
    assert _manifest_rows(store)[0][0] == str(first.resolve())
    store.close()


async def test_vector_index_manager_sync_cleans_legacy_chunks_without_manifest(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    current = source_dir / "a.md"
    removed = source_dir / "b.md"
    current.write_text("alpha memory", encoding="utf-8")
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None)
    store.upsert([
        ChunkRecord(
            id=1,
            text="stale beta memory",
            metadata={"source": "summaries", "file": str(removed.resolve()), "chunk_idx": 0},
        )
    ])
    manager = VectorIndexManager(
        store=store,
        embedding=None,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )

    await manager.sync_all()

    assert [row[0] for row in _chunk_rows(store)] == ["alpha memory"]
    assert [row[0] for row in _manifest_rows(store)] == [str(current.resolve())]
    store.close()


async def test_vector_index_manager_empty_file_clears_old_index(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    file_path = source_dir / "a.md"
    file_path.write_text("alpha memory", encoding="utf-8")
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None)
    manager = VectorIndexManager(
        store=store,
        embedding=None,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )
    await manager.sync_all()

    file_path.write_text("", encoding="utf-8")
    await manager.sync_all()

    assert _chunk_rows(store) == []
    assert _manifest_rows(store)[0][2:4] == ("empty", 0)
    store.close()


async def test_vector_index_manager_embedding_failure_keeps_old_index(tmp_path):
    class FailingEmbedding(FakeEmbedding):
        def __init__(self) -> None:
            super().__init__([[0.1, 0.2, 0.3]])
            self.fail = False

        async def embed(self, queries: list[str]) -> list[list[float]]:
            if self.fail:
                raise RuntimeError("embed down")
            return await super().embed(queries)

    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    file_path = source_dir / "a.md"
    file_path.write_text("alpha memory", encoding="utf-8")
    embedding = FailingEmbedding()
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=3)
    manager = VectorIndexManager(
        store=store,
        embedding=embedding,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )
    await manager.sync_all()

    embedding.fail = True
    file_path.write_text("alpha memory changed", encoding="utf-8")
    await manager.sync_all()

    assert [row[0] for row in _chunk_rows(store)] == ["alpha memory"]
    manifest = _manifest_rows(store)
    assert manifest[0][2] == "error"
    assert "embed down" in manifest[0][4]
    store.close()


async def test_vector_index_manager_sync_source_warns_when_missing(tmp_path, caplog):
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None)
    manager = VectorIndexManager(store=store, embedding=None, sources=[])

    await manager.sync_source("missing")

    assert "source not found: missing" in caplog.text
    store.close()


async def test_vector_index_manager_sync_source_force_reindexes_unchanged_file(tmp_path):
    source_dir = tmp_path / "summaries"
    source_dir.mkdir()
    file_path = source_dir / "a.md"
    file_path.write_text("alpha memory", encoding="utf-8")
    embedding = FakeEmbedding([[0.1, 0.2, 0.3]])
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=3)
    manager = VectorIndexManager(
        store=store,
        embedding=embedding,
        sources=[WatchSource(source_dir, "summaries", lambda p: p.suffix == ".md")],
    )

    await manager.sync_source("summaries")
    await manager.sync_source("summaries", force=True)

    assert len(embedding.calls) == 2
    assert embedding.calls[-1] == ["alpha memory"]
    store.close()


def test_vector_store_replace_file_is_atomic_for_text_index(tmp_path):
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=None, keyword_tokenizer="bigram")
    state = IndexedFileState(
        file="a.md",
        source_id="summaries",
        mtime_ns=1,
        size=5,
        content_hash="old",
        chunk_count=1,
    )
    store.replace_file(
        "a.md",
        [ChunkRecord(id=1, text="猎人的尸体在旧井旁发现", metadata={"source": "summaries", "file": "a.md", "chunk_idx": 0})],
        None,
        state,
    )
    state.content_hash = "new"
    store.replace_file(
        "a.md",
        [ChunkRecord(id=2, text="酒馆线索在桌上", metadata={"source": "summaries", "file": "a.md", "chunk_idx": 0})],
        None,
        state,
    )

    assert [row[0] for row in _chunk_rows(store)] == ["酒馆线索在桌上"]
    assert store.keyword_search("尸体", limit=5) == []
    assert store.keyword_search("酒馆", limit=5)
    store.close()


def test_vector_store_replace_file_rolls_back_vector_insert_failure(tmp_path, monkeypatch):
    store = VectorStore(db_path=tmp_path / "vectors.db", dimension=3)
    old_state = IndexedFileState(
        file="a.md",
        source_id="summaries",
        mtime_ns=1,
        size=5,
        content_hash="old",
        chunk_count=1,
    )
    store.replace_file(
        "a.md",
        [ChunkRecord(id=1, text="old chunk", metadata={"source": "summaries", "file": "a.md", "chunk_idx": 0})],
        [[0.1, 0.2, 0.3]],
        old_state,
    )
    vector_index = store._vector_index  # noqa: SLF001
    assert vector_index is not None
    table = "vec_chunks" if vector_index.backend == "sqlite_vec" else "vec_embeddings"
    old_vector_count = store._repo.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: SLF001

    def fail_insert(rowid, embedding):  # noqa: ANN001
        raise RuntimeError("vector boom")

    monkeypatch.setattr(vector_index, "insert", fail_insert)
    new_state = IndexedFileState(
        file="a.md",
        source_id="summaries",
        mtime_ns=2,
        size=9,
        content_hash="new",
        chunk_count=1,
    )

    with pytest.raises(RuntimeError, match="vector boom"):
        store.replace_file(
            "a.md",
            [ChunkRecord(id=2, text="new chunk", metadata={"source": "summaries", "file": "a.md", "chunk_idx": 0})],
            [[0.4, 0.5, 0.6]],
            new_state,
        )

    assert [row[0] for row in _chunk_rows(store)] == ["old chunk"]
    assert store._repo.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == old_vector_count  # noqa: SLF001
    assert _manifest_rows(store)[0][4] == ""
    store.close()


def test_keyword_retriever_weights_query_sources():
    store = FakeStore()
    store.keyword_rows = {
        "寻找 线索": [
            MemoryCandidate(
                memory_id=1,
                content="normalized",
                keyword_score=1.0,
                debug={"keyword_bm25": -2.0, "keyword_relevance": 0.66, "keyword_tokenizer": "jieba", "keyword_tokens": ["寻找", "线索"]},
            )
        ],
        "线索": [
            MemoryCandidate(
                memory_id=1,
                content="normalized",
                keyword_score=1.0,
                debug={"keyword_bm25": -1.0, "keyword_relevance": 0.50, "keyword_tokenizer": "jieba", "keyword_tokens": ["线索"]},
            )
        ],
        "寻找线索": [MemoryCandidate(memory_id=2, content="compact", keyword_score=1.0)],
    }
    plan = QueryPlan(
        original_query="寻找 线索",
        normalized_query="寻找 线索",
        keyword_queries=("寻找 线索", "线索", "寻找线索"),
        expanded_queries=(),
        raw_md_terms=(),
    )

    candidates = KeywordRetriever(store=store, limit=10).search_plan(plan, top_k=10)
    by_id = {candidate.memory_id: candidate for candidate in candidates}

    assert by_id[1].keyword_score == 1.0
    assert by_id[2].keyword_score == 0.70
    assert by_id[1].debug["keyword_best_query"] == "寻找 线索"
    assert by_id[1].debug["keyword_query_hits"]
    assert by_id[1].debug["keyword_query_hits"][0]["keyword_bm25"] == -2.0


async def test_hybrid_retriever_raw_md_disabled_skips_raw_search():
    class FakeRawSearch:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.calls.append(plan.normalized_query)
            return [MemoryCandidate(memory_id=10, content="raw", raw_md_score=1.0)]

    raw_search = FakeRawSearch()
    retriever = HybridRetriever(
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        raw_md_mode="disabled",
        reranker=None,
    )

    assert await retriever.hybrid_search("寻找线索", top_k=2) == []
    assert raw_search.calls == []


async def test_hybrid_retriever_raw_md_always_participates_in_scoring():
    class FakeRawSearch:
        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            return [MemoryCandidate(memory_id=10, content="猎人的尸体在旧井旁发现", raw_md_score=1.0)]

    retriever = HybridRetriever(
        raw_md_retriever=RawMarkdownRetriever(FakeRawSearch()),
        raw_md_mode="always",
        hybrid_vector_weight=0.0,
        hybrid_keyword_weight=0.0,
        hybrid_raw_md_weight=1.0,
        hybrid_exact_weight=0.0,
        hybrid_expanded_weight=0.0,
        hybrid_recency_weight=0.0,
        hybrid_granularity_weight=0.0,
        reranker=None,
    )

    result = await retriever.hybrid_search("猎人的尸体", top_k=1)

    assert result[0].content == "猎人的尸体在旧井旁发现"
    assert result[0].hybrid_score == 1.0


async def test_hybrid_retriever_raw_md_fallback_triggers_on_failure_and_uses_expanded_terms():
    class FailingKeywordRetriever:
        async def search_plan_async(self, plan, top_k: int = 5):  # noqa: ANN001
            raise RuntimeError("keyword down")

    class FakeRawSearch:
        def __init__(self) -> None:
            self.plan: QueryPlan | None = None

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.plan = plan
            return [
                MemoryCandidate(
                    memory_id=10,
                    content="猎人的尸体在旧井旁发现",
                    raw_md_score=0.5,
                    expanded_score=1.0,
                    debug={"raw_md_expanded_terms": ["旧井"]},
                )
            ]

    raw_search = FakeRawSearch()
    retriever = HybridRetriever(
        keyword_retriever=FailingKeywordRetriever(),
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        raw_md_mode="fallback_only",
        reranker=None,
    )
    plan = QueryPlan(
        original_query="猎人尸体",
        normalized_query="猎人尸体",
        keyword_queries=("猎人尸体",),
        expanded_queries=("旧井",),
        raw_md_terms=("猎人", "尸体"),
    )

    result = await retriever.hybrid_search(plan, top_k=1)

    assert raw_search.plan is plan
    assert result[0].expanded_score == 1.0


async def test_hybrid_retriever_uses_rerank_candidate_k_for_raw_md_limit():
    class RecordingRawSearch:
        def __init__(self) -> None:
            self.limits: list[int] = []

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.limits.append(limit)
            return [
                MemoryCandidate(memory_id=idx, content=f"raw-{idx}", raw_md_score=1.0)
                for idx in range(limit)
            ]

    class PassThroughReranker(MemoryReranker):
        def __init__(self) -> None:
            self.candidate_count = 0

        async def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
            self.candidate_count = len(candidates)
            for candidate in candidates:
                candidate.final_score = candidate.hybrid_score
            return candidates

    raw_search = RecordingRawSearch()
    reranker = PassThroughReranker()
    retriever = HybridRetriever(
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        raw_md_mode="always",
        reranker=reranker,
        rerank_candidate_k=5,
    )

    await retriever.hybrid_search("寻找线索", top_k=2)

    assert raw_search.limits == [5]
    assert reranker.candidate_count == 5


async def test_hybrid_retriever_fallback_raw_md_fills_rerank_pool():
    class FixedKeywordRetriever:
        async def search_plan_async(self, plan, top_k: int = 5):  # noqa: ANN001
            return [
                MemoryCandidate(memory_id=idx, content=f"keyword-{idx}", keyword_score=1.0)
                for idx in range(4)
            ]

    class RecordingRawSearch:
        def __init__(self) -> None:
            self.limits: list[int] = []

        def search_plan(self, plan, limit: int = 50):  # noqa: ANN001
            self.limits.append(limit)
            return [MemoryCandidate(memory_id=10, content="raw-fill", raw_md_score=1.0)]

    class PassThroughReranker(MemoryReranker):
        async def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
            for candidate in candidates:
                candidate.final_score = candidate.hybrid_score
            return candidates

    raw_search = RecordingRawSearch()
    retriever = HybridRetriever(
        keyword_retriever=FixedKeywordRetriever(),
        raw_md_retriever=RawMarkdownRetriever(raw_search),
        raw_md_mode="fallback_only",
        reranker=PassThroughReranker(),
        rerank_candidate_k=8,
    )

    await retriever.hybrid_search("猎人尸体", top_k=2)

    assert raw_search.limits == [8]


def test_raw_md_expanded_terms_fallback_planner_uses_jieba_dict(monkeypatch):
    seen: list[str | None] = []

    class CapturingPlanner:
        def __init__(self, jieba_dict: str | None = None) -> None:
            seen.append(jieba_dict)

        def plan_sync(self, query: str) -> QueryPlan:
            return QueryPlan(
                original_query=query,
                normalized_query=query,
                keyword_queries=(query,),
                expanded_queries=(),
                raw_md_terms=(f"dict:{seen[-1]}", query),
            )

    monkeypatch.setattr(
        "rp_memory.retrieval.raw_md_grep_search.RuleBasedQueryPlanner",
        CapturingPlanner,
    )

    search = RawMarkdownGrepSearch([], jieba_dict="/tmp/custom_jieba.txt")

    assert search._expanded_terms(["旧井"]) == ["dict:/tmp/custom_jieba.txt", "旧井"]


def test_raw_md_frontmatter_metadata_supports_granularity():
    text = '''---
batch_id: 2
type: overall
title: "北境森林追踪爪印"
active: true
score: 1.5
---
正文'''

    metadata = _frontmatter_metadata(text)

    assert metadata["batch_id"] == 2
    assert metadata["type"] == "overall"
    assert metadata["title"] == "北境森林追踪爪印"
    assert metadata["active"] is True
    assert metadata["score"] == 1.5
    assert resolve_memory_granularity(metadata) == "global"


def test_raw_md_search_uses_frontmatter_for_granularity(tmp_path):
    source = tmp_path / "summaries"
    source.mkdir()
    (source / "001.md").write_text(
        '''---
batch_id: 2
title: "遇害猎人"
---
猎人的尸体在森林深处被发现。''',
        encoding="utf-8",
    )

    plan = QueryPlan(
        original_query="猎人尸体",
        normalized_query="猎人尸体",
        keyword_queries=("猎人尸体",),
        expanded_queries=(),
        raw_md_terms=("猎人", "尸体"),
    )

    candidates = RawMarkdownGrepSearch([source]).search_plan(plan, limit=2)

    assert candidates
    assert candidates[0].metadata["batch_id"] == 2
    assert granularity_score(candidates[0].metadata) == ("batch", 1.0)


@pytest.mark.parametrize(
    ("metadata", "expected_granularity", "expected_score"),
    [
        ({"memory_granularity": "event"}, "event", 0.95),
        ({"granularity": "overall"}, "global", 0.55),
        ({"type": "summary"}, "batch", 1.00),
        ({"batch_id": "b1"}, "batch", 1.00),
        ({}, "unknown", 0.80),
        ({"type": "custom"}, "custom", 0.80),
    ],
)
def test_memory_granularity_resolution(metadata, expected_granularity, expected_score):  # noqa: ANN001
    assert resolve_memory_granularity(metadata) == expected_granularity
    assert granularity_score(metadata) == (expected_granularity, expected_score)


def test_build_rerank_query_includes_unique_expanded_queries():
    plan = QueryPlan(
        original_query="猎人尸体",
        normalized_query="猎人尸体",
        keyword_queries=("猎人尸体",),
        expanded_queries=("猎人尸体", "旧井", ""),
        raw_md_terms=("猎人", "尸体"),
    )

    assert _build_rerank_query(plan) == "猎人尸体\n扩展查询：旧井"


def test_build_rerank_query_uses_base_query_without_expansions():
    plan = QueryPlan(
        original_query="猎人尸体",
        normalized_query="",
        keyword_queries=(),
        expanded_queries=(),
        raw_md_terms=(),
    )

    assert _build_rerank_query(plan) == "猎人尸体"

async def test_pointwise_reranker_logs_failed_preview(monkeypatch):
    messages: list[str] = []

    def capture(message, *args, **kwargs):  # noqa: ANN001
        messages.append(message.format(*args))

    monkeypatch.setattr(rerank_service_module.logger, 'warning', capture)

    class FakeProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            return SimpleNamespace(content='plain text output')

    reranker = PointwiseMemoryReranker(FakeProvider(), provider_label='llama')
    result = await reranker.rerank('怪兽', [MemoryCandidate(memory_id=1, content='a')])

    assert [item.memory_id for item in result] == [1]
    assert any('pointwise score failed' in msg for msg in messages)
    assert any('preview=' in msg for msg in messages)


async def test_pointwise_reranker_accepts_pointwise_output(monkeypatch):
    outputs = iter(['90\tstrong match', '10\tweak match'])

    class FakeProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            return SimpleNamespace(content=next(outputs))

    reranker = PointwiseMemoryReranker(FakeProvider(), provider_label='llama')
    result = await reranker.rerank(
        '怪兽',
        [
            MemoryCandidate(memory_id=1, content='a', hybrid_score=0.2),
            MemoryCandidate(memory_id=2, content='b', hybrid_score=0.8),
        ],
    )

    assert [item.memory_id for item in result] == [1, 2]
    assert result[0].rerank_score > result[1].rerank_score


async def test_pointwise_reranker_skips_llm_for_exact_hits():
    class FailingProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            raise AssertionError("provider should not be called for exact matches")

    reranker = PointwiseMemoryReranker(FailingProvider(), provider_label='llama')
    result = await reranker.rerank(
        '酒馆老板',
        [
            MemoryCandidate(
                memory_id=1,
                content='Bob遇到酒馆老板格里姆。',
                exact_score=1.0,
                hybrid_score=0.4,
            )
        ],
    )

    assert [item.memory_id for item in result] == [1]
    assert result[0].debug['llama_score_norm'] == 1.0
    assert result[0].debug['llama_reason'] == 'deterministic exact/term match'


async def test_pointwise_reranker_uses_llm_for_raw_md_terms_only():
    calls: list[list[dict]] = []

    class FakeProvider:
        async def chat(self, messages, tools=None):  # noqa: ANN001
            calls.append(messages)
            return SimpleNamespace(content='30\tterms are broad')

    reranker = PointwiseMemoryReranker(FakeProvider(), provider_label='llama')
    result = await reranker.rerank(
        '酒馆老板',
        [
            MemoryCandidate(
                memory_id=1,
                content='酒馆里有很多客人，老板娘正在擦杯子。',
                metadata={'raw_md_terms': ['酒馆', '老板']},
                debug={'raw_md_terms': ['酒馆', '老板']},
                hybrid_score=0.4,
            )
        ],
    )

    assert len(calls) == 1
    assert result[0].debug['llama_score_norm'] == 0.3
    assert result[0].debug['llama_reason'] == 'terms are broad'
    assert result[0].debug['llama_raw'] == '30 terms are broad'


async def test_memory_manager_recall_and_hybrid_search(fake_recalled_store):
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

    items = await manager.recall("查找线索")
    assert [item.text for item in items] == ["记忆一", "记忆二"]
    assert fake_recalled_store.get_items() == ["记忆一", "记忆二"]
    assert isinstance(items[0], RecallItem)

    hybrid = await manager.hybrid_search("查找线索", top_k=1)
    assert [item.text for item in hybrid] == ["记忆一"]


async def test_memory_manager_recall_logs_raw_md_plan_terms(monkeypatch, fake_recalled_store):
    messages: list[str] = []

    def capture(message, *args, **kwargs):  # noqa: ANN001
        messages.append(message.format(*args))

    class FakePlanner:
        async def plan(self, query):  # noqa: ANN001
            return QueryPlan(
                original_query=query,
                normalized_query=query,
                keyword_queries=(query,),
                expanded_queries=(),
                raw_md_terms=("酒馆", "老板"),
                planner_source="test",
            )

    monkeypatch.setattr(
        "rp_memory.memory_manager.logger.info",
        capture,
    )
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=FakeRetriever([
            ("记忆一", 0.9, {"source": "summaries", "file": "a.md", "chunk_idx": 1}),
        ]),
        top_k=1,
        query_planner=FakePlanner(),
    )

    await manager.recall("酒馆老板")

    assert any("recall plan" in msg and "raw_md_terms=['酒馆', '老板']" in msg for msg in messages)
    assert all("bigram_queries" not in msg for msg in messages)
    assert any("keyword_queries" in msg for msg in messages)


async def test_rule_based_query_planner_filters_punctuation_terms():
    plan = await RuleBasedQueryPlanner().plan(
        "发现自己身处北境森林外围村庄。他前往小酒馆准备出发，遇到酒馆老板格里姆。"
    )

    assert "。" not in plan.raw_md_terms
    assert "，" not in plan.raw_md_terms
    assert "北境" in plan.raw_md_terms
    assert "酒馆" in plan.raw_md_terms


async def test_memory_manager_recall_without_retriever(fake_recalled_store):
    manager = MemoryManager(recalled_store=fake_recalled_store, retriever=None)
    assert await manager.recall("anything") == []
    assert fake_recalled_store.get_items() == []


async def test_memory_manager_recall_gracefully_handles_planner_or_retriever_failure(fake_recalled_store):
    class FailingPlanner:
        async def plan(self, _query):  # noqa: ANN001
            raise RuntimeError("planner boom")

    planner = FailingPlanner()
    retriever = FakeRetriever([("不会返回", 0.5, {"source": "summaries"})])
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=retriever,
        top_k=2,
        query_planner=planner,
    )

    assert await manager.recall("查找线索") == []
    assert fake_recalled_store.get_items() == []

    planner_ok = RuleBasedQueryPlanner()
    class FailingRetriever:
        async def retrieve(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("retriever boom")

    failing_retriever = FailingRetriever()
    manager = MemoryManager(
        recalled_store=fake_recalled_store,
        retriever=failing_retriever,
        top_k=2,
        query_planner=planner_ok,
    )

    assert await manager.recall("查找线索") == []
    assert fake_recalled_store.get_items() == []


async def test_hybrid_retriever_planner_failure_returns_empty(monkeypatch):
    store = FakeStore()
    retriever = HybridRetriever(
        keyword_retriever=KeywordRetriever(store=store, limit=2),
        raw_md_retriever=RawMarkdownRetriever(RawMarkdownGrepSearch([])),
        reranker=None,
    )

    async def boom(_self, _query):
        raise RuntimeError("planner boom")

    monkeypatch.setattr(
        "rp_memory.retrieval.hybrid_retriever.RuleBasedQueryPlanner.plan",
        boom,
    )

    assert await retriever.hybrid_search("查找线索") == []
