"""Assembled memory retriever combining sqlvec, bigram, and raw markdown search."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.planning.plan import QueryPlan
from rpg_world.rpg_core.memory.planning.planner import BaseQueryPlanner, RuleBasedQueryPlanner
from rpg_world.rpg_core.memory.rerank.base import MemoryReranker
from rpg_world.rpg_core.memory.retrieval.bigram_retriever import BigramRetriever
from rpg_world.rpg_core.memory.retrieval.raw_md_retriever import RawMarkdownRetriever
from rpg_world.rpg_core.memory.retrieval.retriever import BaseRetriever
from rpg_world.rpg_core.memory.retrieval.scoring import apply_hybrid_scores, exact_and_fuzzy_scores
from rpg_world.rpg_core.memory.retrieval.sqlvec_retriever import SqlVecRetriever

if TYPE_CHECKING:
    from loguru import Logger


class HybridRetriever(BaseRetriever):
    """Assembled retriever that merges sqlvec, bigram, and raw markdown results."""

    def __init__(
        self,
        sqlvec_retriever: SqlVecRetriever | None = None,
        bigram_retriever: BigramRetriever | None = None,
        raw_md_retriever: RawMarkdownRetriever | None = None,
        query_planner: BaseQueryPlanner | None = None,
        reranker: MemoryReranker | None = None,
        hybrid_vector_weight: float = 0.60,
        hybrid_bigram_weight: float = 0.25,
        hybrid_exact_weight: float = 0.10,
        hybrid_recency_weight: float = 0.05,
    ) -> None:
        self._sqlvec_retriever = sqlvec_retriever
        self._bigram_retriever = bigram_retriever
        self._raw_md_retriever = raw_md_retriever
        self._query_planner = query_planner or RuleBasedQueryPlanner()
        self._reranker = reranker
        self._hybrid_vector_weight = hybrid_vector_weight
        self._hybrid_bigram_weight = hybrid_bigram_weight
        self._hybrid_exact_weight = hybrid_exact_weight
        self._hybrid_recency_weight = hybrid_recency_weight

    def _plan_query(self, query: str) -> QueryPlan:
        return self._query_planner.plan(query)

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        try:
            plan = self._plan_query(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        return self._format(self._search_plan_candidates(plan, top_k))

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        try:
            return self._format(self._search_plan_candidates(plan, top_k))
        except Exception as exc:
            self._log_stage_error("retrieve_plan", exc)
            return []

    def hybrid_search(self, query: str | QueryPlan, top_k: int = 20) -> list[MemoryCandidate]:
        try:
            plan = query if isinstance(query, QueryPlan) else self._plan_query(query)
        except Exception as exc:
            self._log_stage_error("plan", exc)
            return []
        from loguru import logger

        logger.info(
            "[HybridRetriever] search start — query={!r} planner={} top_k={} sqlvec={} bigram={} raw_md={}",
            plan.normalized_query,
            plan.planner_source,
            top_k,
            self._sqlvec_retriever is not None,
            self._bigram_retriever is not None,
            self._raw_md_retriever is not None,
        )
        return self._search_plan_candidates(plan, top_k)

    def _search_plan_candidates(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        if self._sqlvec_retriever is not None:
            try:
                sqlvec_candidates = self._sqlvec_retriever.search_plan(plan, top_k=top_k)
            except Exception as exc:
                self._log_stage_error("sqlvec search", exc)
                sqlvec_candidates = []
        else:
            sqlvec_candidates = []

        bigram_candidates = self._safe_bigram_candidates(plan, top_k)
        raw_md_candidates = self._safe_raw_md_candidates(plan, top_k)

        merged: dict[int, MemoryCandidate] = {}
        for candidate in sqlvec_candidates:
            merged[candidate.memory_id] = candidate
        for candidate in bigram_candidates:
            self._merge_candidate(merged, candidate, "bigram")
        for candidate in raw_md_candidates:
            self._merge_candidate(merged, candidate, "raw_md")

        candidates = list(merged.values())
        from loguru import logger

        logger.info(
            "[HybridRetriever] candidate merge done — sqlvec={} bigram={} raw_md={} merged={} planner={}",
            len(sqlvec_candidates),
            len(bigram_candidates),
            len(raw_md_candidates),
            len(candidates),
            plan.planner_source,
        )
        return self._finalize(plan.normalized_query, candidates, top_k)

    def _safe_bigram_candidates(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        if self._bigram_retriever is None:
            return []
        try:
            return self._bigram_retriever.search_plan(plan, top_k=top_k)
        except Exception as exc:
            self._log_stage_error("bigram search", exc)
            return []

    def _safe_raw_md_candidates(self, plan: QueryPlan, top_k: int) -> list[MemoryCandidate]:
        if self._raw_md_retriever is None:
            return []
        try:
            return self._raw_md_retriever.search_plan(plan, top_k=top_k)
        except Exception as exc:
            self._log_stage_error("raw markdown search", exc)
            return []

    def _merge_candidate(self, merged: dict[int, MemoryCandidate], candidate: MemoryCandidate, source_name: str) -> None:
        existing = merged.get(candidate.memory_id)
        if existing is None:
            merged[candidate.memory_id] = candidate
            return
        existing.vector_score = max(existing.vector_score, candidate.vector_score)
        existing.bigram_score = max(existing.bigram_score, candidate.bigram_score)
        existing.exact_score = max(existing.exact_score, candidate.exact_score)
        existing.fuzzy_score = max(existing.fuzzy_score, candidate.fuzzy_score)
        existing.hybrid_score = max(existing.hybrid_score, candidate.hybrid_score)
        existing.debug.update(candidate.debug)
        existing.debug.setdefault("sources", []).append(source_name)

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

        apply_hybrid_scores(
            candidates,
            vector_weight=self._hybrid_vector_weight,
            bigram_weight=self._hybrid_bigram_weight,
            exact_weight=self._hybrid_exact_weight,
            recency_weight=self._hybrid_recency_weight,
        )
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
                    "bigram_score": candidate.bigram_score,
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
