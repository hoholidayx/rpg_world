"""Hybrid vector + FTS retriever for memory recall."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.planning.plan import QueryPlan
from rpg_world.rpg_core.memory.planning.planner import RuleBasedQueryPlanner
from rpg_world.rpg_core.memory.rerank.llama_reranker import LlamaReranker
from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retrieval.retriever import BaseRetriever, _similarity
from rpg_world.rpg_core.memory.retrieval.scoring import apply_hybrid_scores, exact_and_fuzzy_scores

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.embedding_provider import EmbeddingProvider
    from rpg_world.rpg_core.memory.storage.vector_store import VectorStore


class HybridRetriever(BaseRetriever):
    """Combine dense vector search, bigram FTS, string boosts, and optional rerank."""

    def __init__(
        self,
        store: VectorStore,
        embedding: EmbeddingProvider | None,
        vector_k: int = 50,
        keyword_k: int = 50,
        reranker: LlamaReranker | None = None,
        fallback_search: RawMarkdownGrepSearch | None = None,
    ) -> None:
        self._store = store
        self._embedding = embedding
        self._vector_k = vector_k
        self._keyword_k = keyword_k
        self._reranker = reranker
        self._fallback_search = fallback_search or RawMarkdownGrepSearch([])

    async def retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        try:
            plan = RuleBasedQueryPlanner().plan(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        return self._format(await self._search_plan_candidates_async(plan, top_k))

    def retrieve_sync(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        try:
            return self._format(self._search_candidates_sync(query, top_k))
        except Exception as exc:
            self._log_stage_error("retrieve", exc)
            return []

    def retrieve_plan_sync(
        self, plan: QueryPlan, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        try:
            return self._format(self._search_plan_candidates_sync(plan, top_k))
        except Exception as exc:
            self._log_stage_error("retrieve_plan", exc)
            return []

    def hybrid_search(self, query: str | QueryPlan, top_k: int = 20) -> list[MemoryCandidate]:
        """Public sync API returning structured hybrid candidates."""
        from loguru import logger

        try:
            plan = query if isinstance(query, QueryPlan) else RuleBasedQueryPlanner().plan(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        logger.info(
            "[HybridRetriever] search start — query={!r} planner={} top_k={} vector_k={} keyword_k={}",
            plan.normalized_query,
            plan.planner_source,
            top_k,
            self._vector_k,
            self._keyword_k,
        )
        return self._search_plan_candidates_sync(plan, top_k)

    async def _search_candidates_async(self, query: str, top_k: int) -> list[MemoryCandidate]:
        plan = RuleBasedQueryPlanner().plan(query)
        return await self._search_plan_candidates_async(plan, top_k)

    def _search_candidates_sync(self, query: str, top_k: int) -> list[MemoryCandidate]:
        plan = RuleBasedQueryPlanner().plan(query)
        return self._search_plan_candidates_sync(plan, top_k)

    async def _search_plan_candidates_async(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        query_vector = await self._safe_embed_async(plan.normalized_query)
        return self._merge_sources(plan, query_vector, top_k)

    def _search_plan_candidates_sync(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        query_vector = self._safe_embed_sync(plan.normalized_query)
        return self._merge_sources(plan, query_vector, top_k)

    def _merge_sources(
        self,
        plan: QueryPlan,
        query_vector: list[float] | None,
        top_k: int,
    ) -> list[MemoryCandidate]:
        merged: dict[int, MemoryCandidate] = {}

        vector_candidates = self._safe_vector_candidates(query_vector)
        keyword_candidates = self._safe_keyword_candidates(plan)
        fallback_candidates = self._safe_fallback_candidates(plan)

        for candidate in vector_candidates:
            merged[candidate.memory_id] = candidate

        for candidate in keyword_candidates:
            existing = merged.get(candidate.memory_id)
            if existing is None:
                merged[candidate.memory_id] = candidate
            else:
                existing.keyword_score = max(existing.keyword_score, candidate.keyword_score)
                existing.debug.update(candidate.debug)

        for candidate in fallback_candidates:
            existing = merged.get(candidate.memory_id)
            if existing is None:
                merged[candidate.memory_id] = candidate
            else:
                existing.keyword_score = max(existing.keyword_score, candidate.keyword_score)
                existing.debug.update(candidate.debug)

        candidates = list(merged.values())
        from loguru import logger

        logger.info(
            "[HybridRetriever] candidate merge done — vector={} keyword={} fallback={} merged={} planner={}",
            len(vector_candidates),
            len(keyword_candidates),
            len(fallback_candidates),
            len(candidates),
            plan.planner_source,
        )
        return self._finalize(plan.normalized_query, candidates, top_k)

    def _safe_embed_sync(self, query: str) -> list[float] | None:
        if self._embedding is None:
            return None
        try:
            vecs = self._embedding.embed_sync([query])
        except Exception as exc:
            self._log_stage_error("vector embed", exc)
            return None
        if not vecs:
            return None
        return vecs[0]

    async def _safe_embed_async(self, query: str) -> list[float] | None:
        if self._embedding is None:
            return None
        try:
            vecs = await self._embedding.embed([query])
        except Exception as exc:
            self._log_stage_error("vector embed", exc)
            return None
        if not vecs:
            return None
        return vecs[0]

    def _safe_vector_candidates(self, query_vector: list[float] | None) -> list[MemoryCandidate]:
        if query_vector is None:
            return []
        try:
            rows = self._store.search(query_vector, top_k=self._vector_k)
        except Exception as exc:
            self._log_stage_error("vector search", exc)
            return []

        candidates: list[MemoryCandidate] = []
        for record, distance in rows:
            candidates.append(
                MemoryCandidate(
                    memory_id=record.id,
                    content=record.text,
                    metadata=dict(record.metadata),
                    vector_score=_similarity(distance),
                )
            )
        return candidates

    def _safe_keyword_candidates(self, plan: QueryPlan) -> list[MemoryCandidate]:
        candidates: dict[int, MemoryCandidate] = {}
        queries = _dedupe_queries([*plan.keyword_queries, *plan.expanded_queries])
        for query in queries:
            try:
                rows = self._store.keyword_search(query, limit=self._keyword_k)
            except Exception as exc:
                self._log_stage_error("keyword search", exc)
                continue
            for candidate in rows:
                candidate.debug.setdefault("keyword_queries", []).append(query)
                existing = candidates.get(candidate.memory_id)
                if existing is None or candidate.keyword_score > existing.keyword_score:
                    candidates[candidate.memory_id] = candidate
        return list(candidates.values())

    def _safe_fallback_candidates(self, plan: QueryPlan) -> list[MemoryCandidate]:
        try:
            search_plan = getattr(self._fallback_search, "search_plan", None)
            if search_plan is not None:
                return search_plan(plan, limit=self._keyword_k)
            return self._fallback_search.search(plan.normalized_query, limit=self._keyword_k)
        except Exception as exc:
            self._log_stage_error("string fallback", exc)
            return []

    def _finalize(
        self,
        query: str,
        candidates: list[MemoryCandidate],
        top_k: int,
    ) -> list[MemoryCandidate]:
        now = time.time()
        for candidate in candidates:
            exact, fuzzy = exact_and_fuzzy_scores(query, candidate.content)
            candidate.exact_score = exact
            candidate.fuzzy_score = fuzzy
            created_at = _as_float(candidate.metadata.get("created_at"))
            candidate.recency_score = 1.0 / (1.0 + max(0.0, (now - created_at) / 86400.0)) if created_at else 0.0

        apply_hybrid_scores(candidates)
        candidates = sorted(candidates, key=lambda item: item.hybrid_score, reverse=True)
        candidates = candidates[: max(top_k, 1)]
        if not candidates:
            from loguru import logger

            logger.info("[HybridRetriever] rerank skipped — no candidates")
            return candidates
        if self._reranker is not None:
            from loguru import logger

            logger.info("[HybridRetriever] rerank start — candidates={}", len(candidates))
            try:
                candidates = self._reranker.rerank(query, candidates)
            except Exception as exc:
                self._log_stage_error("rerank", exc)
            else:
                logger.info("[HybridRetriever] rerank done — candidates={}", len(candidates))
        else:
            from loguru import logger

            logger.info("[HybridRetriever] rerank skipped — disabled or unavailable")
        return candidates[:top_k]

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        result: list[tuple[str, float, dict]] = []
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
            result.append((candidate.content, candidate.final_score, metadata))
        return result

    def _log_stage_error(self, stage: str, exc: Exception) -> None:
        from loguru import logger

        logger.warning("[HybridRetriever] {} failed: {}", stage, exc)


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for query in queries:
        normalized = " ".join((query or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
