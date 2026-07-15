"""Async-first memory facade with one coordinator per Agent session."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from commons.types import Metadata
from loguru import logger

if TYPE_CHECKING:
    from llm_client.types import LLMProvider
    from rp_memory.planning.planner import BaseQueryPlanner
    from rp_memory.recalled_memory import RecalledMemoryStore
    from rp_memory.rerank.base import MemoryReranker
    from rp_memory.retrieval.retriever import BaseRetriever
    from rp_memory.storage.vector_store import VectorStore
    from rp_memory.vector_index_manager import VectorIndexManager
    from rpg_core.settings import MemorySettings


@dataclass
class RecallItem:
    text: str
    score: float
    source: str = ""
    file_path: str = ""
    chunk_idx: int = 0
    metadata: Metadata = field(default_factory=dict)


def format_recall_item(idx: int, item: RecallItem) -> str:
    lines = [
        f"  [{idx}] score={item.score:.4f}",
        f"       source={item.source}  file={item.file_path}[{item.chunk_idx}]",
    ]
    non_text_keys = {"source", "file", "chunk_idx", "file_path"}
    extra = {key: value for key, value in item.metadata.items() if key not in non_text_keys}
    if extra:
        lines.append(f"       meta: {extra}")
    lines.append("       ---")
    lines.extend(f"       {line}" for line in item.text.splitlines())
    return "\n".join(lines)


class MemoryManager:
    """Own lazy remote capabilities and serialized local memory state."""

    @classmethod
    def create(
        cls,
        recalled_store: "RecalledMemoryStore",
        session_dir: str,
        get_vector_db_path: str,
        mem_cfg: "MemorySettings",
    ) -> "MemoryManager | None":
        """Build a local shell without contacting LLM Service."""
        if not mem_cfg.enabled:
            logger.info("[MemoryManager] disabled by config")
            return None
        sources = cls._build_sources(session_dir)
        rule_planner = cls._build_rule_based_query_planner(mem_cfg)
        fallback_search = cls._build_raw_md_search(sources, rule_planner)
        logger.info(
            "[MemoryManager] local shell ready — session_dir={} db_path={} hybrid={} top_k={}",
            session_dir,
            get_vector_db_path,
            mem_cfg.hybrid_enabled,
            mem_cfg.top_k,
        )
        return cls(
            recalled_store=recalled_store,
            top_k=mem_cfg.top_k,
            query_planner=rule_planner,
            session_dir=session_dir,
            db_path=get_vector_db_path,
            mem_cfg=mem_cfg,
            sources=sources,
            fallback_search=fallback_search,
        )

    def __init__(
        self,
        recalled_store: "RecalledMemoryStore",
        index_manager: "VectorIndexManager | None" = None,
        retriever: "BaseRetriever | None" = None,
        top_k: int = 5,
        store: "VectorStore | None" = None,
        query_planner: "BaseQueryPlanner | None" = None,
        *,
        session_dir: str | None = None,
        db_path: str | None = None,
        mem_cfg: "MemorySettings | None" = None,
        sources: list | None = None,
        fallback_search: object | None = None,
    ) -> None:
        from rp_memory.planning.planner import RuleBasedQueryPlanner

        self._recalled_store = recalled_store
        self._index_manager = index_manager
        self._retriever = retriever
        self._top_k = top_k
        self._store = store
        self._query_planner = query_planner or RuleBasedQueryPlanner()
        self._session_dir = session_dir
        self._db_path = db_path
        self._mem_cfg = mem_cfg
        self._sources = list(sources or [])
        self._fallback_search = fallback_search
        self._embedding: LLMProvider | None = None
        self._reranker: MemoryReranker | None = None
        self._embedding_ready = False
        self._planner_ready = not bool(
            mem_cfg and getattr(mem_cfg, "query_planner_enabled", False)
        )
        self._reranker_ready = not bool(
            mem_cfg and getattr(mem_cfg, "rerank_enabled", False)
        )
        self._initialized = False
        self._closed = False
        self._operation_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._remote_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize text-only storage and watcher coordination without LLM I/O."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self._ensure_open()
            if self._store is None and self._mem_cfg is not None and self._db_path:
                self._store = await asyncio.to_thread(
                    self._build_store,
                    self._db_path,
                    None,
                    self._mem_cfg,
                )
            if self._retriever is None and self._mem_cfg is not None:
                self._retriever = self._build_retriever(
                    self._store,
                    None,
                    self._mem_cfg,
                    self._fallback_search,
                    self._query_planner,
                    reranker=None,
                )
            if (
                self._index_manager is None
                and self._store is not None
                and self._mem_cfg is not None
            ):
                self._index_manager = self._build_index_manager(
                    self._store,
                    None,
                    self._sources,
                    self._build_chunker(self._mem_cfg),
                    operation_lock=self._operation_lock,
                )
            if self._index_manager is not None:
                await self._index_manager.initialize()
            self._initialized = True
            logger.info("[MemoryManager] initialized in text-index-first mode")

    async def recall(self, query: str) -> list[RecallItem]:
        await self.initialize()
        await self._refresh_remote_capabilities()
        async with self._operation_lock:
            self._ensure_open()
            if self._retriever is None:
                self._recalled_store.set_items([])
                return []
            logger.info(
                "[MemoryManager] recall start — query={!r} top_k={}",
                query,
                self._top_k,
            )
            try:
                plan = await self._query_planner.plan(query)
            except Exception as exc:
                logger.warning("[MemoryManager] recall planner failed: {}", exc)
                self._recalled_store.set_items([])
                return []
            _log_query_plan("recall", plan)
            try:
                retrieve_plan = getattr(self._retriever, "retrieve_plan", None)
                if retrieve_plan is not None:
                    raw = await retrieve_plan(plan, self._top_k)
                else:
                    raw = await self._retriever.retrieve(
                        plan.normalized_query or query,
                        self._top_k,
                    )
            except Exception as exc:
                logger.warning("[MemoryManager] recall retriever failed: {}", exc)
                self._recalled_store.set_items([])
                return []
            items = self._items(raw)
            self._recalled_store.set_items([item.text for item in items])
        logger.info(
            "[MemoryManager] recall done — query={!r} items={}",
            query,
            len(items),
        )
        for index, item in enumerate(items):
            for line in format_recall_item(index, item).splitlines():
                logger.info("[MemoryManager] {}", line)
        return items

    async def hybrid_search(self, query: str, top_k: int = 20) -> list[RecallItem]:
        await self.initialize()
        await self._refresh_remote_capabilities()
        async with self._operation_lock:
            if self._retriever is None:
                return []
            try:
                plan = await self._query_planner.plan(query)
                _log_query_plan("hybrid_search", plan)
                search = getattr(self._retriever, "hybrid_search", None)
                if search is None:
                    retrieve_plan = getattr(self._retriever, "retrieve_plan", None)
                    if retrieve_plan is not None:
                        raw = await retrieve_plan(plan, top_k)
                    else:
                        raw = await self._retriever.retrieve(
                            plan.normalized_query or query,
                            top_k,
                        )
                    return self._items(raw)
                candidates = await search(plan, top_k)
            except Exception as exc:
                logger.warning("[MemoryManager] hybrid_search failed: {}", exc)
                return []
            return self._items_from_candidates(candidates)

    async def reindex(self) -> None:
        await self.initialize()
        await self._refresh_remote_capabilities()
        if self._index_manager is None:
            logger.warning("[MemoryManager] reindex skipped: index manager unavailable")
            return
        await self._index_manager.reindex_all()

    async def rebuild_fts_index(self) -> None:
        await self.initialize()
        async with self._operation_lock:
            if self._store is not None:
                await asyncio.to_thread(self._store.rebuild_fts_index)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._index_manager is not None:
            await self._index_manager.close()
        async with self._operation_lock:
            self._recalled_store.clear()
            if self._store is not None:
                await asyncio.to_thread(self._store.close)
                self._store = None
            self._initialized = False

    @property
    def recalled_items(self) -> list[str]:
        return list(self._recalled_store.get_items())

    def _get_db_path(self) -> Path | None:
        return Path(self._db_path) if self._db_path else None

    async def _refresh_remote_capabilities(self) -> None:
        cfg = self._mem_cfg
        if cfg is None:
            return
        if self._embedding_ready and self._planner_ready and self._reranker_ready:
            return
        async with self._remote_lock:
            if self._embedding_ready and self._planner_ready and self._reranker_ready:
                return
            from llm_client.keys import (
                MEMORY_EMBED_BIZ_KEY,
                MEMORY_QUERY_PLANNER_BIZ_KEY,
                MEMORY_RERANK_BIZ_KEY,
            )
            from llm_client.manager import LLMClientManager

            manager = LLMClientManager.get()
            requests: list[tuple[str, str]] = []
            if not self._embedding_ready:
                requests.append(("embedding", MEMORY_EMBED_BIZ_KEY))
            if not self._planner_ready:
                requests.append(("planner", MEMORY_QUERY_PLANNER_BIZ_KEY))
            if not self._reranker_ready:
                requests.append(("reranker", MEMORY_RERANK_BIZ_KEY))

            async def resolve(label: str, biz_key: str):
                try:
                    return label, await manager.get_provider(biz_key)
                except Exception as exc:
                    logger.warning(
                        "[MemoryManager] {} provider unavailable; keep fallback: {}",
                        label,
                        exc,
                    )
                    return label, None

            resolved = await asyncio.gather(
                *(resolve(label, key) for label, key in requests)
            )
            providers = {label: provider for label, provider in resolved}
            embedding = providers.get("embedding")
            dimension = 0
            if embedding is not None:
                try:
                    dimension = await embedding.dimension()
                except Exception as exc:
                    logger.warning(
                        "[MemoryManager] embedding dimension unavailable; keep text fallback: {}",
                        exc,
                    )

            vector_upgraded = False
            async with self._operation_lock:
                if dimension > 0 and self._store is not None:
                    vector_upgraded = await asyncio.to_thread(
                        self._store.enable_vector_index,
                        dimension,
                    )
                    if vector_upgraded:
                        self._embedding = embedding
                        self._embedding_ready = True
                        if self._index_manager is not None:
                            self._index_manager.set_embedding(embedding)

                planner_provider = providers.get("planner")
                if planner_provider is not None:
                    self._query_planner = self._build_query_planner_with_provider(
                        cfg,
                        planner_provider,
                    )
                    self._planner_ready = True

                rerank_provider = providers.get("reranker")
                if rerank_provider is not None:
                    self._reranker = self._build_reranker_with_provider(
                        cfg,
                        rerank_provider,
                    )
                    self._reranker_ready = True

                self._retriever = self._build_retriever(
                    self._store,
                    self._embedding,
                    cfg,
                    self._fallback_search,
                    self._query_planner,
                    reranker=self._reranker,
                )
            if vector_upgraded and self._index_manager is not None:
                await self._index_manager.reindex_all()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("memory manager is closed")

    @staticmethod
    def _build_sources(session_dir: str):
        from rp_memory.vector_index_manager import WatchSource

        return [
            WatchSource(
                path=Path(session_dir) / "summaries",
                source_id="summaries",
                file_filter=lambda path: path.suffix in (".md", ".json"),
            )
        ]

    @staticmethod
    def _build_raw_md_search(sources, rule_based_planner=None):
        from rp_memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch

        return RawMarkdownGrepSearch(
            source_paths=[source.path for source in sources],
            rule_based_planner=rule_based_planner,
        )

    @staticmethod
    def _build_store(
        db_path: str,
        dimension: int | None,
        mem_cfg: "MemorySettings",
    ):
        from rp_memory.storage.vector_store import VectorStore

        try:
            return VectorStore(
                db_path=db_path,
                dimension=dimension,
                keyword_tokenizer=mem_cfg.keyword_tokenizer,
                jieba_dict=mem_cfg.jieba_dict,
            )
        except Exception as exc:
            logger.warning("[MemoryManager] store init failed: {}", exc)
            return None

    @staticmethod
    def _build_chunker(mem_cfg: "MemorySettings"):
        from rp_memory.chunker import Chunker

        return Chunker(
            max_file_chars=mem_cfg.chunk_size,
            overlap=mem_cfg.chunk_overlap,
        )

    @staticmethod
    def _build_index_manager(
        store,
        embedding,
        sources,
        chunker,
        *,
        operation_lock: asyncio.Lock | None = None,
    ):
        if store is None:
            return None
        from rp_memory.vector_index_manager import VectorIndexManager

        return VectorIndexManager(
            store=store,
            embedding=embedding,
            sources=sources,
            chunker=chunker,
            operation_lock=operation_lock,
        )

    @staticmethod
    def _build_sqlvec_retriever(store, embedding):
        if store is None or embedding is None or not store.vector_enabled:
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
        if fallback_search is None:
            return None
        from rp_memory.retrieval.raw_md_retriever import RawMarkdownRetriever

        return RawMarkdownRetriever(fallback_search)

    @classmethod
    def _build_retriever(
        cls,
        store,
        embedding,
        mem_cfg: "MemorySettings",
        fallback_search,
        rule_based_planner=None,
        *,
        reranker=None,
    ):
        from rp_memory.retrieval.hybrid_retriever import HybridRetriever

        raw_md_retriever = cls._build_raw_md_retriever(fallback_search)
        if store is None:
            return None if mem_cfg.raw_md_mode == "disabled" else raw_md_retriever
        sqlvec_retriever = cls._build_sqlvec_retriever(store, embedding)
        keyword_retriever = cls._build_keyword_retriever(store, mem_cfg.keyword_k)
        if mem_cfg.hybrid_enabled or embedding is None:
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
        return sqlvec_retriever

    @staticmethod
    def _build_rule_based_query_planner(mem_cfg: "MemorySettings"):
        from rp_memory.planning.planner import RuleBasedQueryPlanner

        return RuleBasedQueryPlanner(
            jieba_dict=getattr(mem_cfg, "jieba_dict", "") or None
        )

    @classmethod
    def _build_query_planner_with_provider(cls, mem_cfg, provider):
        from rp_memory.planning.openai_planner import OpenAIQueryPlanner
        from rp_memory.planning.planner import FallbackQueryPlanner

        fallback = cls._build_rule_based_query_planner(mem_cfg)
        return FallbackQueryPlanner(
            OpenAIQueryPlanner(
                provider,
                fallback_planner=fallback,
                planner_source="llm_service",
            ),
            fallback,
        )

    @staticmethod
    def _build_reranker_with_provider(mem_cfg, provider):
        from rp_memory.rerank.service import PointwiseMemoryReranker

        return PointwiseMemoryReranker(
            provider,
            rerank_weight=mem_cfg.rerank_score_weight,
            provider_label="llm_service",
        )

    @staticmethod
    def _items(raw: list[tuple[str, float, dict]]) -> list[RecallItem]:
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

    @staticmethod
    def _items_from_candidates(candidates) -> list[RecallItem]:
        raw: list[tuple[str, float, dict]] = []
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
        return MemoryManager._items(raw)


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
