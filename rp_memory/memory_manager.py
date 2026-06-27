"""MemoryManager — 统一记忆管理入口，封装所有记忆实现细节。

所有操作同步执行，不依赖事件循环。

初始化策略：
  1. ``create()`` — 加载模型 + 建 DB
  2. ``init()`` — 增量同步索引并注册 FileWatcher
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rpg_core.common_types import Metadata

from loguru import logger

if TYPE_CHECKING:
    from llm_service.base_provider import LLMProvider
    from rp_memory.planning.planner import BaseQueryPlanner
    from rp_memory.recalled_memory import RecalledMemoryStore
    from rp_memory.retrieval.retriever import BaseRetriever
    from rp_memory.storage.vector_store import VectorStore
    from rp_memory.vector_index_manager import VectorIndexManager
    from rpg_core.settings import MemorySettings


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

    metadata: Metadata = field(default_factory=dict)
    """扩展元信息。"""


def format_recall_item(idx: int, item: RecallItem) -> str:
    """格式化一条 RecallItem 为完整可读文本（无截断）。

    与独立入口共享同一格式，确保 CLI / 日志输出一致。
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
        store = cls._build_store(get_vector_db_path, embedding, mem_cfg)
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
        from rp_memory.planning.planner import RuleBasedQueryPlanner

        self._recalled_store = recalled_store
        self._index_manager = index_manager
        self._retriever = retriever
        self._top_k = top_k
        self._store = store
        self._query_planner = query_planner or RuleBasedQueryPlanner()
        self._inited = False
        self._db_path: str | None = None

    def init(self) -> None:
        """同步初始化：增量补偿离线文件变化并注册 watcher。"""
        logger.info("[MemoryManager] init() called — _inited={} index_manager={}", self._inited, self._index_manager is not None)
        if self._inited:
            return
        if self._index_manager is None:
            logger.info("[MemoryManager] init skipped — index manager unavailable")
            self._inited = True
            return

        self._index_manager.sync_all(force=False)
        self._index_manager.start()
        self._inited = True
        logger.info("[MemoryManager] init done")

    @staticmethod
    def _build_sources(session_dir: str):
        from rp_memory.vector_index_manager import WatchSource

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
        from rp_memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch

        logger.info("[MemoryManager] raw markdown fallback roots={}", len(sources))
        return RawMarkdownGrepSearch(
            source_paths=[src.path for src in sources],
            rule_based_planner=rule_based_planner,
        )

    @staticmethod
    def _build_embedding(mem_cfg: MemorySettings):
        if not getattr(mem_cfg, "enabled", True):
            return None
        from llm_service.keys import MEMORY_EMBED_BIZ_KEY
        from llm_service.manager import LLMManager

        try:
            embedding = LLMManager.get().get_provider(MEMORY_EMBED_BIZ_KEY)
            logger.info("[MemoryManager] embedding provider ready: {}", type(embedding).__name__)
            return embedding
        except Exception as exc:
            logger.warning("[MemoryManager] embedding init failed: {}", exc)
            return None

    @staticmethod
    def _build_store(
        get_vector_db_path: str,
        embedding: LLMProvider | None,
        mem_cfg: MemorySettings,
    ):
        from rp_memory.storage.types import VectorStoreError
        from rp_memory.storage.vector_store import VectorStore

        dimension = None
        if embedding is not None:
            try:
                dimension = embedding.dimension()  # type: ignore[union-attr]
            except NotImplementedError:
                dimension = None

        try:
            store = VectorStore(
                db_path=get_vector_db_path,
                dimension=dimension,
                keyword_tokenizer=mem_cfg.keyword_tokenizer,
                jieba_dict=mem_cfg.jieba_dict,
            )
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
                store = VectorStore(
                    db_path=get_vector_db_path,
                    dimension=None,
                    keyword_tokenizer=mem_cfg.keyword_tokenizer,
                    jieba_dict=mem_cfg.jieba_dict,
                )
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
        from rp_memory.chunker import Chunker

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
            from rp_memory.vector_index_manager import VectorIndexManager

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
        from rp_memory.retrieval.sqlvec_retriever import SqlVecRetriever

        return SqlVecRetriever(store=store, embedding=embedding)

    @staticmethod
    def _build_keyword_retriever(store, keyword_limit: int):
        if store is None:
            return None
        from rp_memory.retrieval.keyword_retriever import KeywordRetriever

        return KeywordRetriever(store=store, limit=keyword_limit)

    @staticmethod
    def _build_raw_md_retriever(fallback_search):
        from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever

        return RawMarkdownRetriever(fallback_search)

    @staticmethod
    def _build_retriever(store, embedding, mem_cfg: MemorySettings, fallback_search, rule_based_planner=None):
        from rp_memory.retrieval.hybrid_retriever import HybridRetriever
        from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever

        raw_md_retriever = MemoryManager._build_raw_md_retriever(fallback_search)
        if store is None:
            if mem_cfg.raw_md_mode == "disabled":
                logger.info("[MemoryManager] retriever disabled — store unavailable and raw_md_mode=disabled")
                return None
            logger.info("[MemoryManager] retriever fallback — raw markdown only")
            return raw_md_retriever

        sqlvec_retriever = MemoryManager._build_sqlvec_retriever(store, embedding)
        keyword_retriever = MemoryManager._build_keyword_retriever(store, mem_cfg.keyword_k)

        if mem_cfg.hybrid_enabled or embedding is None:
            logger.info(
                "[MemoryManager] retriever mode — hybrid (sqlvec={} keyword={} rerank={} raw_md_mode={})",
                sqlvec_retriever is not None,
                keyword_retriever is not None,
                mem_cfg.rerank_enabled,
                mem_cfg.raw_md_mode,
            )
            reranker = MemoryManager._build_reranker(mem_cfg)
            return HybridRetriever(
                sqlvec_retriever=sqlvec_retriever,
                keyword_retriever=keyword_retriever,
                raw_md_retriever=raw_md_retriever,
                query_planner=rule_based_planner,
                reranker=reranker,
                hybrid_vector_weight=mem_cfg.hybrid_vector_weight,
                hybrid_keyword_weight=mem_cfg.hybrid_keyword_weight,
                hybrid_raw_md_weight=mem_cfg.hybrid_raw_md_weight,
                hybrid_exact_weight=mem_cfg.hybrid_exact_weight,
                hybrid_expanded_weight=mem_cfg.hybrid_expanded_weight,
                hybrid_recency_weight=mem_cfg.hybrid_recency_weight,
                hybrid_granularity_weight=mem_cfg.hybrid_granularity_weight,
                raw_md_mode=mem_cfg.raw_md_mode,
                raw_md_min_results=mem_cfg.raw_md_min_results,
                keyword_tokenizer=mem_cfg.keyword_tokenizer,
                rerank_candidate_k=mem_cfg.rerank_candidate_k,
            )

        logger.info("[MemoryManager] retriever mode — sqlvec")
        return sqlvec_retriever

    @staticmethod
    def _build_rule_based_query_planner(mem_cfg: MemorySettings):
        from rp_memory.planning.planner import RuleBasedQueryPlanner

        return RuleBasedQueryPlanner(jieba_dict=getattr(mem_cfg, "jieba_dict", "") or None)

    @staticmethod
    def _build_query_planner(mem_cfg: MemorySettings, rule_based_planner=None):
        if rule_based_planner is None:
            rule_based_planner = MemoryManager._build_rule_based_query_planner(mem_cfg)
        if not getattr(mem_cfg, "query_planner_enabled", False):
            logger.info("[MemoryManager] query planner mode — rule-based (disabled)")
            return rule_based_planner
        from llm_service.keys import MEMORY_QUERY_PLANNER_BIZ_KEY
        from llm_service.manager import LLMManager
        from llm_service.keys import PROVIDER_LLAMA
        from rp_memory.planning.openai_planner import OpenAIQueryPlanner
        from rp_memory.planning.planner import FallbackQueryPlanner, LlamaQueryPlanner

        try:
            provider = LLMManager.get().get_provider(MEMORY_QUERY_PLANNER_BIZ_KEY)
            if mem_cfg.query_planner_provider.provider == PROVIDER_LLAMA:
                primary = LlamaQueryPlanner(provider, fallback_planner=rule_based_planner)
            else:
                primary = OpenAIQueryPlanner(provider, fallback_planner=rule_based_planner)
            planner = FallbackQueryPlanner(primary, rule_based_planner)
            logger.info("[MemoryManager] query planner ready: {}", type(planner).__name__)
            return planner
        except Exception as exc:
            logger.warning("[MemoryManager] query planner init failed — rule-based fallback: {}", exc)
            return rule_based_planner

    @staticmethod
    def _build_reranker(mem_cfg: MemorySettings):
        try:
            if not mem_cfg.rerank_enabled:
                logger.info("[MemoryManager] reranker mode — disabled")
                return None
            from llm_service.keys import MEMORY_RERANK_BIZ_KEY
            from llm_service.manager import LLMManager
            from rp_memory.rerank.service import PointwiseMemoryReranker
            from llm_service.keys import PROVIDER_OPENAI, PROVIDER_LLAMA
            from llm_service.base_provider import DocumentScoreProvider

            provider = LLMManager.get().get_provider(MEMORY_RERANK_BIZ_KEY)
            rerank_weight = mem_cfg.rerank_score_weight
            if isinstance(provider, DocumentScoreProvider):
                provider_label = PROVIDER_LLAMA
            else:
                provider_label = PROVIDER_OPENAI if mem_cfg.rerank_provider.provider == PROVIDER_OPENAI else PROVIDER_LLAMA
            reranker = PointwiseMemoryReranker(
                provider,
                rerank_weight=rerank_weight,
                provider_label=provider_label,
            )
            logger.info("[MemoryManager] reranker ready: {}", type(reranker).__name__)
            return reranker
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("[MemoryManager] reranker init failed — disable rerank: {}", exc)
            return None

    def reindex(self) -> None:
        """手动触发一次全量重建。"""
        if self._index_manager is None:
            logger.warning("[MemoryManager] reindex skipped: index manager unavailable")
            return

        logger.info("[MemoryManager] manual reindex start ...")
        self._index_manager.sync_all(force=True)
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
        _log_query_plan("recall", plan)

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
        _log_query_plan("hybrid_search", plan)

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
                            "raw_md_score": candidate.raw_md_score,
                            "exact_score": candidate.exact_score,
                            "fuzzy_score": candidate.fuzzy_score,
                            "expanded_score": candidate.expanded_score,
                            "granularity_score": candidate.granularity_score,
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


def _log_query_plan(stage: str, plan) -> None:  # noqa: ANN001
    logger.info(
        "[MemoryManager] {} plan — planner={} type={} normalized={!r} keyword_queries={} raw_md_terms={} expanded_queries={}",
        stage,
        plan.planner_source,
        plan.query_type,
        plan.normalized_query,
        list(plan.keyword_queries),
        list(plan.raw_md_terms),
        list(plan.expanded_queries),
    )
