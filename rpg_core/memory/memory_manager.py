"""MemoryManager — 统一记忆管理入口，封装所有记忆实现细节。

所有操作同步执行，不依赖事件循环。

初始化策略：
  1. ``create()`` — 加载模型 + 建 DB
  2. ``init()`` — 注册 FileWatcher，避免启动时执行全量重建
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

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
        fallback_search = cls._build_raw_md_search(sources)
        embedding = cls._build_embedding(mem_cfg)
        store = cls._build_store(get_vector_db_path, embedding)
        chunker = cls._build_chunker(mem_cfg)
        index_mgr = cls._build_index_manager(store, embedding, sources, chunker)
        retriever = cls._build_retriever(store, embedding, mem_cfg, fallback_search)
        query_planner = cls._build_query_planner(mem_cfg)

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
            logger.warning("[MemoryManager] embedding unavailable — keyword/raw markdown fallback mode")
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
    def _build_raw_md_search(sources):
        from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch

        logger.info("[MemoryManager] raw markdown fallback roots={}", len(sources))
        return RawMarkdownGrepSearch(source_paths=[src.path for src in sources])

    @staticmethod
    def _build_embedding(mem_cfg: MemorySettings):
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
                logger.warning("[MemoryManager] keyword store init failed: {}", exc)
                return None
            logger.warning("[MemoryManager] vector store init failed, retry keyword-only: {}", exc)
            try:
                store = VectorStore(db_path=get_vector_db_path, dimension=None)
                logger.info(
                    "[MemoryManager] keyword-only store ready: {}",
                    get_vector_db_path,
                )
                return store
            except Exception as retry_exc:
                logger.warning("[MemoryManager] keyword store retry failed: {}", retry_exc)
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
            logger.info("[MemoryManager] index manager will operate in keyword-only mode")

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
    def _build_retriever(store, embedding, mem_cfg: MemorySettings, fallback_search):
        from rpg_world.rpg_core.memory.rerank.llama_reranker import (
            LlamaRerankConfig,
            LlamaReranker,
        )
        from rpg_world.rpg_core.memory.retrieval.hybrid_retriever import HybridRetriever
        from rpg_world.rpg_core.memory.retrieval.raw_md_retriever import RawMarkdownRetriever
        from rpg_world.rpg_core.memory.retrieval.retriever import DenseRetriever

        if store is None:
            logger.info("[MemoryManager] retriever fallback — raw markdown only")
            return RawMarkdownRetriever(fallback_search)

        if mem_cfg.hybrid_enabled or embedding is None:
            logger.info(
                "[MemoryManager] retriever mode — hybrid (vector={} keyword={} rerank={})",
                embedding is not None,
                True,
                mem_cfg.rerank_enabled,
            )
            reranker = LlamaReranker(
                LlamaRerankConfig(
                    enabled=mem_cfg.rerank_enabled and mem_cfg.llama_process_enabled,
                    model_path=mem_cfg.rerank_model_path,
                    max_candidates=mem_cfg.rerank_max_candidates,
                    n_ctx=mem_cfg.rerank_n_ctx,
                    n_gpu_layers=mem_cfg.rerank_n_gpu_layers,
                    temperature=mem_cfg.rerank_temperature,
                    request_timeout_ms=mem_cfg.llama_request_timeout_ms,
                    llama_weight=mem_cfg.rerank_llama_weight,
                )
            )
            return HybridRetriever(
                store=store,
                embedding=embedding,
                vector_k=mem_cfg.vector_k,
                keyword_k=mem_cfg.keyword_k,
                reranker=reranker,
                fallback_search=fallback_search,
                hybrid_vector_weight=mem_cfg.hybrid_vector_weight,
                hybrid_keyword_weight=mem_cfg.hybrid_keyword_weight,
                hybrid_exact_weight=mem_cfg.hybrid_exact_weight,
                hybrid_recency_weight=mem_cfg.hybrid_recency_weight,
            )

        logger.info("[MemoryManager] retriever mode — dense vector")
        return DenseRetriever(store=store, embedding=embedding)

    @staticmethod
    def _build_query_planner(mem_cfg: MemorySettings):
        from rpg_world.rpg_core.memory.planning.planner import (
            FallbackQueryPlanner,
            LlamaQueryPlanner,
            RuleBasedQueryPlanner,
        )

        fallback = RuleBasedQueryPlanner()
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
                            "keyword_score": candidate.keyword_score,
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
        """Rebuild the keyword FTS index from stored chunks."""
        if self._store is not None:
            self._store.rebuild_fts_index()
