"""MemoryManager — 统一记忆管理入口，封装所有记忆实现细节。

所有操作同步执行，不依赖事件循环。

初始化策略：
  1. ``create()`` — 加载模型 + 建 DB
  2. ``init()`` — 注册 FileWatcher，避免启动时执行全量重建
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from rpg_world.rpg_core.agent.agent_types import (
    LLM_PROVIDER_LLAMA,
    LLM_PROVIDER_MODES,
    LLM_PROVIDER_OPENAI,
    LLM_PROVIDER_SHARED,
)

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.planning.planner import BaseQueryPlanner
    from rpg_world.rpg_core.memory.recalled_memory import RecalledMemoryStore
    from rpg_world.rpg_core.memory.retrieval.retriever import BaseRetriever
    from rpg_world.rpg_core.memory.storage.vector_store import VectorStore
    from rpg_world.rpg_core.memory.vector_index_manager import VectorIndexManager
    from rpg_world.rpg_core.settings import MemorySettings


@dataclass
class RecallItem:
    """一条召回结果的结构化数据。"""

    text: str
    """匹配到的文本内容。"""

    score: float
    """相似度分数（0~1，越高越相关）。"""

    source: str = ""
    """来源标识（如 ``"summaries"``）。"""

    file_path: str = ""
    """来源文件路径。"""

    chunk_idx: int = 0
    """在文件内的分块索引。"""

    metadata: dict[str, object] = field(default_factory=dict)
    """扩展元信息。"""


def format_recall_item(idx: int, item: RecallItem) -> str:
    """格式化一条 RecallItem 为完整可读文本（无截断）。

    与 ``run.py`` 共享同一格式，确保 CLI / 日志输出一致。
    """
    lines: list[str] = []
    lines.append(f"  [{idx}] score={item.score:.4f}")
    lines.append(f"       source={item.source}  file={item.file_path}[{item.chunk_idx}]")
    non_text_keys = {"source", "file", "chunk_idx", "file_path"}
    extra = {k: v for k, v in item.metadata.items() if k not in non_text_keys}
    if extra:
        lines.append(f"       meta: {extra}")
    lines.append("       ---")
    for line in item.text.splitlines():
        lines.append(f"       {line}")
    return "\n".join(lines)


class MemoryManager:
    """记忆管理器 — 所有操作同步。"""

    # ── 工厂方法 ───────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        recalled_store: RecalledMemoryStore,
        session_dir: str,
        get_vector_db_path: str,
        mem_cfg: MemorySettings,
    ) -> MemoryManager | None:
        """构造 MemoryManager（同步：尽力加载模型并建立检索链路）。"""
        if not mem_cfg.enabled:
            logger.info("[MemoryManager] disabled by config")
            return None
        logger.info(
            "[MemoryManager] create start — session_dir={} db_path={} hybrid={} top_k={}",
            session_dir,
            get_vector_db_path,
            mem_cfg.hybrid_enabled,
            mem_cfg.top_k,
        )

        sources = cls._build_sources(session_dir)
        rule_based_planner = cls._build_rule_based_query_planner(mem_cfg)
        fallback_search = cls._build_raw_md_search(sources, rule_based_planner)
        embedding = cls._build_embedding(mem_cfg)
        store = cls._build_store(get_vector_db_path, embedding)
        chunker = cls._build_chunker(mem_cfg)
        index_mgr = cls._build_index_manager(store, embedding, sources, chunker)
        retriever = cls._build_retriever(store, embedding, mem_cfg, fallback_search, rule_based_planner)
        query_planner = cls._build_query_planner(mem_cfg, rule_based_planner)

        mm = cls(
            recalled_store=recalled_store,
            index_manager=index_mgr,
            retriever=retriever,
            top_k=mem_cfg.top_k,
            store=store,
            query_planner=query_planner,
        )
        mm._db_path = get_vector_db_path
        logger.info(
            "[MemoryManager] create done — retriever={} store={} index={} embedding={}",
            type(retriever).__name__ if retriever is not None else "None",
            "ready" if store is not None else "none",
            "ready" if index_mgr is not None else "none",
            "ready" if embedding is not None else "none",
        )
        if embedding is None:
            logger.warning("[MemoryManager] embedding unavailable — bigram/raw markdown fallback mode")
        return mm

    # ── 实例初始化 ─────────────────────────────────────────────────────

    def __init__(
        self,
        recalled_store: RecalledMemoryStore,
        index_manager: VectorIndexManager | None = None,
        retriever: BaseRetriever | None = None,
        top_k: int = 5,
        store: VectorStore | None = None,
        query_planner: BaseQueryPlanner | None = None,
    ) -> None:
        from rpg_world.rpg_core.memory.planning.planner import RuleBasedQueryPlanner

        self._recalled_store = recalled_store
        self._index_manager = index_manager
        self._retriever = retriever
        self._top_k = top_k
        self._store = store
        self._query_planner = query_planner or RuleBasedQueryPlanner()
        self._inited = False
        self._db_path: str | None = None

    def init(self) -> None:
        """同步初始化：仅注册 watcher，不执行全量重建。"""
        logger.info("[MemoryManager] init() called — _inited={} index_manager={}", self._inited, self._index_manager is not None)
        if self._inited:
            return
        if self._index_manager is None:
            logger.info("[MemoryManager] init skipped — index manager unavailable")
            self._inited = True
            return

        self._index_manager.start()
        self._inited = True
        logger.info("[MemoryManager] init done")

    @staticmethod
    def _build_sources(session_dir: str):
        from rpg_world.rpg_core.memory.vector_index_manager import WatchSource

        sources = [
            WatchSource(
                path=Path(session_dir) / "summaries",
                source_id="summaries",
                file_filter=lambda p: p.suffix in (".md", ".json"),
            ),
        ]
        logger.info("[MemoryManager] watch sources ready — count={} root={}", len(sources), sources[0].path)
        return sources

    @staticmethod
    def _build_raw_md_search(sources, rule_based_planner=None):
        from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch

        logger.info("[MemoryManager] raw markdown fallback roots={}", len(sources))
        return RawMarkdownGrepSearch(
            source_paths=[src.path for src in sources],
            rule_based_planner=rule_based_planner,
        )

    @staticmethod
    def _build_embedding(mem_cfg: MemorySettings):
        if not hasattr(mem_cfg, "embedding_provider"):
            embed_path = mem_cfg.embedding_model_path
            if not embed_path:
                logger.warning("[MemoryManager] embedding_model_path not configured")
                return None
            if not mem_cfg.llama_process_enabled:
                logger.warning("[MemoryManager] embedding disabled — llama_process_enabled=false")
                return None
            try:
                from rpg_world.rpg_core.memory.embedding_provider import LlamaClientEmbeddingProvider

                logger.info(
                    "[MemoryManager] loading embedding model: {} (n_ctx={}, n_gpu_layers={})",
                    embed_path, mem_cfg.n_ctx, mem_cfg.n_gpu_layers,
                )
                embedding = LlamaClientEmbeddingProvider(
                    gguf_model_path=embed_path,
                    n_ctx=mem_cfg.n_ctx,
                    n_gpu_layers=mem_cfg.n_gpu_layers,
                    n_threads=mem_cfg.embedding_n_threads,
                    verbose=mem_cfg.embedding_verbose,
                    request_timeout_ms=mem_cfg.llama_request_timeout_ms,
                )
                logger.info("[MemoryManager] model loaded — dim={}", embedding.dimension())
                return embedding
            except Exception as exc:
                logger.warning("[MemoryManager] embedding init failed: {}", exc)
                return None

        provider_cfg = mem_cfg.embedding_provider
        mode = MemoryManager._provider_mode(provider_cfg, "embedding")
        if mode == LLM_PROVIDER_SHARED:
            raise ValueError("memory.embedding_provider=shared is not supported")

        if mode == LLM_PROVIDER_OPENAI:
            openai_cfg = provider_cfg.openai
            model = MemoryManager._require_non_empty(openai_cfg.get("model"), "memory.embedding_provider.openai.model")
            if not model:
                raise ValueError("memory.embedding_provider.openai.model is required")
            try:
                from rpg_world.rpg_core.memory.embedding_provider import OpenAIEmbeddingProvider

                embedding = OpenAIEmbeddingProvider(
                    model=model,
                    api_key=MemoryManager._resolve_memory_openai_api_key(openai_cfg),
                    base_url=MemoryManager._optional_str(openai_cfg.get("base_url")),
                    timeout_ms=MemoryManager._optional_int(openai_cfg.get("timeout_ms"), None),
                )
                try:
                    logger.info("[MemoryManager] loading openai embedding model: {}", model)
                    logger.info("[MemoryManager] openai embedding dim={}", embedding.dimension())
                except Exception as exc:
                    logger.warning("[MemoryManager] openai embedding probe failed: {}", exc)
                    return None
                return embedding
            except Exception as exc:
                logger.warning("[MemoryManager] openai embedding init failed: {}", exc)
                return None

        embed_path = MemoryManager._optional_str(provider_cfg.llama.get("model_path")) or mem_cfg.embedding_model_path
        if not embed_path:
            raise ValueError("memory.embedding_provider.llama.model_path is required")
        if not mem_cfg.llama_process_enabled:
            logger.warning("[MemoryManager] embedding disabled — llama_process_enabled=false")
            return None

        try:
            from rpg_world.rpg_core.memory.embedding_provider import LlamaClientEmbeddingProvider

            logger.info(
                "[MemoryManager] loading embedding model: {} (n_ctx={}, n_gpu_layers={})",
                embed_path,
                MemoryManager._optional_int(provider_cfg.llama.get("n_ctx"), mem_cfg.n_ctx),
                MemoryManager._optional_int(provider_cfg.llama.get("n_gpu_layers"), mem_cfg.n_gpu_layers),
            )
            embedding = LlamaClientEmbeddingProvider(
                gguf_model_path=embed_path,
                n_ctx=MemoryManager._optional_int(provider_cfg.llama.get("n_ctx"), mem_cfg.n_ctx) or mem_cfg.n_ctx,
                n_gpu_layers=MemoryManager._optional_int(provider_cfg.llama.get("n_gpu_layers"), mem_cfg.n_gpu_layers) or mem_cfg.n_gpu_layers,
                n_threads=MemoryManager._optional_int(provider_cfg.llama.get("n_threads"), mem_cfg.embedding_n_threads) or mem_cfg.embedding_n_threads,
                verbose=provider_cfg.llama.get("verbose") if provider_cfg.llama.get("verbose") is not None else mem_cfg.embedding_verbose,
                request_timeout_ms=MemoryManager._optional_int(provider_cfg.llama.get("request_timeout_ms"), mem_cfg.llama_request_timeout_ms) or mem_cfg.llama_request_timeout_ms,
            )
            logger.info("[MemoryManager] model loaded — dim={}", embedding.dimension())
            return embedding
        except Exception as exc:
            logger.warning("[MemoryManager] embedding init failed: {}", exc)
            return None

    @staticmethod
    def _build_store(
        get_vector_db_path: str,
        embedding: object | None,
    ):
        from rpg_world.rpg_core.memory.storage.types import VectorStoreError
        from rpg_world.rpg_core.memory.storage.vector_store import VectorStore

        dimension = None
        if embedding is not None:
            dimension = embedding.dimension()  # type: ignore[union-attr]

        try:
            store = VectorStore(db_path=get_vector_db_path, dimension=dimension)
            logger.info(
                "[MemoryManager] vector store ready: {} (vector_mode={})",
                get_vector_db_path,
                dimension is not None,
            )
            return store
        except VectorStoreError as exc:
            if dimension is None:
                logger.warning("[MemoryManager] text index init failed: {}", exc)
                return None
            logger.warning("[MemoryManager] vector store init failed, retry text-index-only: {}", exc)
            try:
                store = VectorStore(db_path=get_vector_db_path, dimension=None)
                logger.info(
                    "[MemoryManager] text-index-only store ready: {}",
                    get_vector_db_path,
                )
                return store
            except Exception as retry_exc:
                logger.warning("[MemoryManager] text index retry failed: {}", retry_exc)
                return None
        except Exception as exc:
            logger.warning("[MemoryManager] store init failed: {}", exc)
            return None

    @staticmethod
    def _build_chunker(mem_cfg: MemorySettings):
        from rpg_world.rpg_core.memory.chunker import Chunker

        return Chunker(
            max_file_chars=mem_cfg.chunk_size,
            overlap=mem_cfg.chunk_overlap,
        )

    @classmethod
    def _build_index_manager(
        cls,
        store,
        embedding,
        sources,
        chunker,
    ):
        if store is None:
            logger.warning("[MemoryManager] index manager skipped — store unavailable")
            return None
        if embedding is None:
            logger.info("[MemoryManager] index manager will operate in text-index-only mode")

        try:
            from rpg_world.rpg_core.memory.vector_index_manager import VectorIndexManager

            index_manager = VectorIndexManager(
                store=store,
                embedding=embedding,
                sources=sources,
                chunker=chunker,
            )
            logger.info("[MemoryManager] index manager ready")
            return index_manager
        except Exception as exc:
            logger.warning("[MemoryManager] index manager init failed: {}", exc)
            return None

    @staticmethod
    def _build_sqlvec_retriever(store, embedding):
        if store is None or embedding is None:
            return None
        from rpg_world.rpg_core.memory.retrieval.sqlvec_retriever import SqlVecRetriever

        return SqlVecRetriever(store=store, embedding=embedding)

    @staticmethod
    def _build_bigram_retriever(store, bigram_limit: int):
        if store is None:
            return None
        from rpg_world.rpg_core.memory.retrieval.bigram_retriever import BigramRetriever

        return BigramRetriever(store=store, limit=bigram_limit)

    @staticmethod
    def _build_raw_md_retriever(fallback_search):
        from rpg_world.rpg_core.memory.retrieval.raw_md_retriever import RawMarkdownRetriever

        return RawMarkdownRetriever(fallback_search)

    @staticmethod
    def _build_retriever(store, embedding, mem_cfg: MemorySettings, fallback_search, rule_based_planner=None):
        from rpg_world.rpg_core.memory.rerank import LlamaRerankConfig, LlamaReranker, OpenAIReranker
        from rpg_world.rpg_core.memory.retrieval.hybrid_retriever import HybridRetriever
        from rpg_world.rpg_core.memory.retrieval.raw_md_retriever import RawMarkdownRetriever

        raw_md_retriever = MemoryManager._build_raw_md_retriever(fallback_search)
        if store is None:
            logger.info("[MemoryManager] retriever fallback — raw markdown only")
            return raw_md_retriever

        bigram_k = mem_cfg.bigram_k
        hybrid_bigram_weight = mem_cfg.hybrid_bigram_weight
        sqlvec_retriever = MemoryManager._build_sqlvec_retriever(store, embedding)
        bigram_retriever = MemoryManager._build_bigram_retriever(store, bigram_k)

        if mem_cfg.hybrid_enabled or embedding is None:
            logger.info(
                "[MemoryManager] retriever mode — hybrid (sqlvec={} bigram={} rerank={})",
                sqlvec_retriever is not None,
                bigram_retriever is not None,
                mem_cfg.rerank_enabled,
            )
            reranker = MemoryManager._build_reranker(mem_cfg)
            return HybridRetriever(
                sqlvec_retriever=sqlvec_retriever,
                bigram_retriever=bigram_retriever,
                raw_md_retriever=raw_md_retriever,
                query_planner=rule_based_planner,
                reranker=reranker,
                hybrid_vector_weight=mem_cfg.hybrid_vector_weight,
                hybrid_bigram_weight=hybrid_bigram_weight,
                hybrid_exact_weight=mem_cfg.hybrid_exact_weight,
                hybrid_recency_weight=mem_cfg.hybrid_recency_weight,
            )

        logger.info("[MemoryManager] retriever mode — sqlvec")
        return sqlvec_retriever

    @staticmethod
    def _build_rule_based_query_planner(mem_cfg: MemorySettings):
        from rpg_world.rpg_core.memory.planning.planner import RuleBasedQueryPlanner

        return RuleBasedQueryPlanner(jieba_dict=getattr(mem_cfg, "jieba_dict", "") or None)

    @staticmethod
    def _build_query_planner(mem_cfg: MemorySettings, rule_based_planner=None):
        if rule_based_planner is None:
            rule_based_planner = MemoryManager._build_rule_based_query_planner(mem_cfg)
        if not hasattr(mem_cfg, "query_planner_provider"):
            from rpg_world.rpg_core.memory.planning.planner import (
                FallbackQueryPlanner,
                LlamaQueryPlanner,
                RuleBasedQueryPlanner,
            )

            fallback = rule_based_planner
            if not mem_cfg.query_planner_enabled:
                logger.info("[MemoryManager] query planner mode — rule-based (disabled)")
                return fallback
            if not mem_cfg.llama_process_enabled:
                logger.info("[MemoryManager] query planner mode — rule-based (llama_process_enabled=false)")
                return fallback
            if not mem_cfg.query_planner_model_path:
                logger.warning("[MemoryManager] query planner model_path not configured — rule-based fallback")
                return fallback
            try:
                planner = LlamaQueryPlanner(
                    model_path=mem_cfg.query_planner_model_path,
                    n_ctx=mem_cfg.query_planner_n_ctx,
                    n_gpu_layers=mem_cfg.query_planner_n_gpu_layers,
                    temperature=mem_cfg.query_planner_temperature,
                    max_tokens=mem_cfg.query_planner_max_tokens,
                    request_timeout_ms=mem_cfg.llama_request_timeout_ms,
                )
                logger.info("[MemoryManager] query planner mode — llama")
                return FallbackQueryPlanner(planner, fallback)
            except Exception as exc:
                logger.warning("[MemoryManager] query planner init failed — rule-based fallback: {}", exc)
                return fallback

        from rpg_world.rpg_core.memory.planning import (
            FallbackQueryPlanner,
            LlamaQueryPlanner,
            OpenAIQueryPlanner,
            RuleBasedQueryPlanner,
        )

        fallback = rule_based_planner
        if not mem_cfg.query_planner_enabled:
            logger.info("[MemoryManager] query planner mode — rule-based (disabled)")
            return fallback
        provider_cfg = mem_cfg.query_planner_provider
        mode = MemoryManager._provider_mode(provider_cfg, "query_planner")
        if mode == LLM_PROVIDER_SHARED:
            raise ValueError("memory.query_planner_provider=shared is not supported")

        openai_model = None
        if mode == LLM_PROVIDER_OPENAI:
            openai_cfg = provider_cfg.openai
            openai_model = MemoryManager._require_non_empty(openai_cfg.get("model"), "memory.query_planner_provider.openai.model")

        try:
            if mode == LLM_PROVIDER_OPENAI:
                openai_cfg = provider_cfg.openai
                planner = OpenAIQueryPlanner(
                    model=openai_model or "",
                    api_key=MemoryManager._resolve_memory_openai_api_key(openai_cfg),
                    base_url=MemoryManager._optional_str(openai_cfg.get("base_url")),
                    max_tokens=MemoryManager._optional_int(openai_cfg.get("max_tokens"), mem_cfg.query_planner_max_tokens) or mem_cfg.query_planner_max_tokens,
                    temperature=MemoryManager._optional_float(openai_cfg.get("temperature"), mem_cfg.query_planner_temperature) or mem_cfg.query_planner_temperature,
                    fallback_planner=rule_based_planner,
                )
                logger.info("[MemoryManager] query planner mode — openai")
                return FallbackQueryPlanner(planner, fallback)

            if not mem_cfg.llama_process_enabled:
                logger.info("[MemoryManager] query planner mode — rule-based (llama_process_enabled=false)")
                return fallback

            model_path = MemoryManager._optional_str(provider_cfg.llama.get("model_path")) or mem_cfg.query_planner_model_path
            if not model_path:
                raise ValueError("memory.query_planner_provider.llama.model_path is required")
            planner = LlamaQueryPlanner(
                model_path=model_path,
                n_ctx=MemoryManager._optional_int(provider_cfg.llama.get("n_ctx"), mem_cfg.query_planner_n_ctx) or mem_cfg.query_planner_n_ctx,
                n_gpu_layers=MemoryManager._optional_int(provider_cfg.llama.get("n_gpu_layers"), mem_cfg.query_planner_n_gpu_layers) or mem_cfg.query_planner_n_gpu_layers,
                temperature=MemoryManager._optional_float(provider_cfg.llama.get("temperature"), mem_cfg.query_planner_temperature) or mem_cfg.query_planner_temperature,
                max_tokens=MemoryManager._optional_int(provider_cfg.llama.get("max_tokens"), mem_cfg.query_planner_max_tokens) or mem_cfg.query_planner_max_tokens,
                request_timeout_ms=MemoryManager._optional_int(provider_cfg.llama.get("request_timeout_ms"), mem_cfg.llama_request_timeout_ms) or mem_cfg.llama_request_timeout_ms,
                fallback_planner=rule_based_planner,
            )
            logger.info("[MemoryManager] query planner mode — llama")
            return FallbackQueryPlanner(planner, fallback)
        except Exception as exc:
            logger.warning("[MemoryManager] query planner init failed — rule-based fallback: {}", exc)
            return fallback

    @staticmethod
    def _build_reranker(mem_cfg: MemorySettings):
        if not hasattr(mem_cfg, "rerank_provider"):
            if not mem_cfg.rerank_enabled:
                logger.info("[MemoryManager] reranker mode — disabled")
                return None
            if not mem_cfg.llama_process_enabled:
                logger.info("[MemoryManager] reranker mode — disabled (llama_process_enabled=false)")
                return None
            from rpg_world.rpg_core.memory.rerank.llama_reranker import (
                LlamaRerankConfig,
                LlamaReranker,
            )

            return LlamaReranker(
                LlamaRerankConfig(
                    enabled=True,
                    model_path=mem_cfg.rerank_model_path,
                    max_candidates=mem_cfg.rerank_max_candidates,
                    n_ctx=mem_cfg.rerank_n_ctx,
                    n_gpu_layers=mem_cfg.rerank_n_gpu_layers,
                    temperature=mem_cfg.rerank_temperature,
                    request_timeout_ms=mem_cfg.llama_request_timeout_ms,
                    llama_weight=mem_cfg.rerank_llama_weight,
                )
            )

        from rpg_world.rpg_core.memory.rerank import LlamaRerankConfig, LlamaReranker, OpenAIReranker

        if not mem_cfg.rerank_enabled:
            logger.info("[MemoryManager] reranker mode — disabled")
            return None

        provider_cfg = mem_cfg.rerank_provider
        mode = MemoryManager._provider_mode(provider_cfg, "rerank")
        if mode == LLM_PROVIDER_SHARED:
            raise ValueError("memory.rerank_provider=shared is not supported")

        openai_model = None
        if mode == LLM_PROVIDER_OPENAI:
            openai_cfg = provider_cfg.openai
            openai_model = MemoryManager._require_non_empty(openai_cfg.get("model"), "memory.rerank_provider.openai.model")

        try:
            if mode == LLM_PROVIDER_OPENAI:
                openai_cfg = provider_cfg.openai
                logger.info("[MemoryManager] reranker mode — openai")
                return OpenAIReranker(
                    model=openai_model or "",
                    api_key=MemoryManager._resolve_memory_openai_api_key(openai_cfg),
                    base_url=MemoryManager._optional_str(openai_cfg.get("base_url")),
                    max_candidates=MemoryManager._optional_int(openai_cfg.get("max_candidates"), mem_cfg.rerank_max_candidates) or mem_cfg.rerank_max_candidates,
                    max_tokens=MemoryManager._optional_int(openai_cfg.get("max_tokens"), 1024) or 1024,
                    temperature=MemoryManager._optional_float(openai_cfg.get("temperature"), mem_cfg.rerank_temperature) or mem_cfg.rerank_temperature,
                    rerank_weight=MemoryManager._optional_float(openai_cfg.get("rerank_weight"), mem_cfg.rerank_llama_weight) or mem_cfg.rerank_llama_weight,
                )

            model_path = MemoryManager._optional_str(provider_cfg.llama.get("model_path")) or mem_cfg.rerank_model_path
            logger.info(
                "[MemoryManager] reranker mode — llama (enabled={} model_path={})",
                mem_cfg.rerank_enabled and mem_cfg.llama_process_enabled,
                model_path,
            )
            return LlamaReranker(
                LlamaRerankConfig(
                    enabled=mem_cfg.rerank_enabled and mem_cfg.llama_process_enabled,
                    model_path=model_path,
                    max_candidates=MemoryManager._optional_int(provider_cfg.llama.get("max_candidates"), mem_cfg.rerank_max_candidates) or mem_cfg.rerank_max_candidates,
                    n_ctx=MemoryManager._optional_int(provider_cfg.llama.get("n_ctx"), mem_cfg.rerank_n_ctx) or mem_cfg.rerank_n_ctx,
                    n_gpu_layers=MemoryManager._optional_int(provider_cfg.llama.get("n_gpu_layers"), mem_cfg.rerank_n_gpu_layers) or mem_cfg.rerank_n_gpu_layers,
                    temperature=MemoryManager._optional_float(provider_cfg.llama.get("temperature"), mem_cfg.rerank_temperature) or mem_cfg.rerank_temperature,
                    request_timeout_ms=MemoryManager._optional_int(provider_cfg.llama.get("request_timeout_ms"), mem_cfg.llama_request_timeout_ms) or mem_cfg.llama_request_timeout_ms,
                    llama_weight=MemoryManager._optional_float(provider_cfg.llama.get("llama_weight"), mem_cfg.rerank_llama_weight) or mem_cfg.rerank_llama_weight,
                )
            )
        except Exception as exc:
            logger.warning("[MemoryManager] reranker init failed — disable rerank: {}", exc)
            return None

    @staticmethod
    def _provider_mode(provider_cfg: Any, label: str) -> str:
        mode = str(getattr(provider_cfg, "provider", "") or LLM_PROVIDER_LLAMA).strip()
        if not mode:
            mode = LLM_PROVIDER_LLAMA
        if mode not in LLM_PROVIDER_MODES:
            raise ValueError(f"memory.{label}_provider must be one of {', '.join(LLM_PROVIDER_MODES)}; got {mode!r}")
        return mode

    @staticmethod
    def _require_non_empty(value: Any, label: str) -> str:
        text = MemoryManager._optional_str(value)
        if not text:
            raise ValueError(f"{label} is required")
        return text

    @staticmethod
    def _optional_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _optional_int(value: Any, default: int | None) -> int | None:
        if value is None or value == "":
            return default
        return int(value)

    @staticmethod
    def _optional_float(value: Any, default: float | None) -> float | None:
        if value is None or value == "":
            return default
        return float(value)

    @staticmethod
    def _resolve_memory_openai_api_key(openai_cfg: dict[str, Any]) -> str | None:
        from rpg_world.rpg_core.settings import settings

        return settings.resolve_openai_api_key(
            explicit=MemoryManager._optional_str(openai_cfg.get("api_key")) or None,
            explicit_env=MemoryManager._optional_str(openai_cfg.get("api_key_env")) or None,
            fallback_to_agent=False,
        )

    def reindex(self) -> None:
        """手动触发一次全量重建。"""
        if self._index_manager is None:
            logger.warning("[MemoryManager] reindex skipped: index manager unavailable")
            return

        logger.info("[MemoryManager] manual reindex start ...")
        self._index_manager.reindex_all()
        if not self._inited:
            self._index_manager.start()
            self._inited = True
        logger.info("[MemoryManager] manual reindex done")

    def _get_db_path(self) -> Path | None:
        """返回 create() 时保存的 DB 路径，用于 init() 检查。"""
        if self._db_path:
            return Path(self._db_path)
        return None

    @property
    def recalled_items(self) -> list[str]:
        """当前缓存的召回结果文本列表（供上下文构建器读取）。"""
        return list(self._recalled_store.get_items())

    # ── 检索 ───────────────────────────────────────────────────────────

    def recall(self, query: str) -> list[RecallItem]:
        """检索与 *query* 相关的记忆（同步，无事件循环依赖）。

        返回结构化 ``RecallItem`` 列表（含文本、分数、来源信息）。
        同时将文本列表写入 ``RecalledMemoryStore``（供上下文构建器读取）。
        """
        if self._retriever is None:
            self._recalled_store.set_items([])
            return []

        logger.info("[MemoryManager] recall start — query={!r} top_k={}", query, self._top_k)
        try:
            plan = self._query_planner.plan(query)
        except Exception as exc:
            logger.warning("[MemoryManager] recall planner failed: {}", exc)
            self._recalled_store.set_items([])
            return []

        try:
            retrieve_plan = getattr(self._retriever, "retrieve_plan_sync", None)
            if retrieve_plan is None:
                raw = self._retriever.retrieve_sync(plan.normalized_query or query, self._top_k)
            else:
                raw = retrieve_plan(plan, self._top_k)
        except Exception as exc:
            logger.warning("[MemoryManager] recall retriever failed: {}", exc)
            self._recalled_store.set_items([])
            return []

        items: list[RecallItem] = []
        for text, score, meta in raw:
            items.append(RecallItem(
                text=text,
                score=score,
                source=str(meta.get("source", "")),
                file_path=str(meta.get("file", "")),
                chunk_idx=int(meta.get("chunk_idx", 0)),
                metadata=meta,
            ))

        self._recalled_store.set_items([i.text for i in items])
        logger.info("[MemoryManager] recall done — query={!r} items={}", query, len(items))
        for i, it in enumerate(items):
            for line in format_recall_item(i, it).splitlines():
                logger.info("[MemoryManager] {}", line)
        return items

    def hybrid_search(self, query: str, top_k: int = 20) -> list[RecallItem]:
        """Run structured hybrid search when the active retriever supports it."""
        if self._retriever is None:
            return []
        logger.info("[MemoryManager] hybrid_search start — query={!r} top_k={}", query, top_k)
        try:
            plan = self._query_planner.plan(query)
        except Exception as exc:
            logger.warning("[MemoryManager] hybrid_search planner failed: {}", exc)
            return []

        try:
            search = getattr(self._retriever, "hybrid_search", None)
            if search is None:
                retrieve_plan = getattr(self._retriever, "retrieve_plan_sync", None)
                if retrieve_plan is None:
                    raw = self._retriever.retrieve_sync(plan.normalized_query or query, top_k)
                else:
                    raw = retrieve_plan(plan, top_k)
            else:
                candidates = search(plan, top_k)
                raw = []
                for candidate in candidates:
                    metadata = dict(candidate.metadata)
                    metadata.update(
                        {
                            "memory_id": candidate.memory_id,
                            "vector_score": candidate.vector_score,
                            "bigram_score": candidate.bigram_score,
                            "exact_score": candidate.exact_score,
                            "fuzzy_score": candidate.fuzzy_score,
                            "recency_score": candidate.recency_score,
                            "hybrid_score": candidate.hybrid_score,
                            "rerank_score": candidate.rerank_score,
                            "debug": candidate.debug,
                        }
                    )
                    raw.append((candidate.content, candidate.final_score, metadata))
        except Exception as exc:
            logger.warning("[MemoryManager] hybrid_search retriever failed: {}", exc)
            return []

        return [
            RecallItem(
                text=text,
                score=score,
                source=str(meta.get("source", "")),
                file_path=str(meta.get("file", "")),
                chunk_idx=int(meta.get("chunk_idx", 0)),
                metadata=meta,
            )
            for text, score, meta in raw
        ]

    def rebuild_fts_index(self) -> None:
        """Rebuild the bigram FTS index from stored chunks."""
        if self._store is not None:
            self._store.rebuild_fts_index()
