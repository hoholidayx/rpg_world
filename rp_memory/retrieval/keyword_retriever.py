"""Keyword FTS retriever for memory recall."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.retrieval.retriever import BaseRetriever

if TYPE_CHECKING:
    from rp_memory.storage.vector_store import VectorStore


class KeywordRetriever(BaseRetriever):
    """Keyword FTS retriever backed by the SQLite text index."""

    def __init__(self, store: VectorStore, limit: int = 50) -> None:
        self._store = store
        self._limit = limit

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    async def retrieve_plan(
        self,
        plan: QueryPlan,
        top_k: int = 5,
    ) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_plan_sync, plan, top_k)

    async def search_plan_async(
        self,
        plan: QueryPlan,
        top_k: int = 5,
    ) -> list[MemoryCandidate]:
        return await asyncio.to_thread(self.search_plan, plan, top_k)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search(query, top_k=top_k)
        return self._format(candidates)

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search_plan(plan, top_k=top_k)
        return self._format(candidates)

    def search(self, query: str, top_k: int = 5) -> list[MemoryCandidate]:
        return self._store.keyword_search(query, limit=top_k)

    def search_plan(self, plan: QueryPlan, top_k: int = 5) -> list[MemoryCandidate]:
        candidates: dict[int, MemoryCandidate] = {}
        queries = _weighted_queries(plan)
        for query, weight, source in queries:
            for candidate in self._store.keyword_search(query, limit=min(self._limit, top_k)):
                raw_score = candidate.keyword_score
                candidate.keyword_score = raw_score * weight
                hit = {
                    "query": query,
                    "source": source,
                    "weight": weight,
                    "raw_score": raw_score,
                    "weighted_score": candidate.keyword_score,
                    "keyword_bm25": candidate.debug.get("keyword_bm25"),
                    "keyword_relevance": candidate.debug.get("keyword_relevance"),
                    "keyword_tokenizer": candidate.debug.get("keyword_tokenizer"),
                    "keyword_tokens": candidate.debug.get("keyword_tokens"),
                }
                candidate.debug.setdefault("keyword_query_hits", []).append(hit)
                candidate.debug.setdefault("keyword_queries", []).append(query)
                existing = candidates.get(candidate.memory_id)
                if existing is None:
                    candidate.debug["keyword_best_query"] = query
                    candidate.debug["keyword_best_query_weight"] = weight
                    candidates[candidate.memory_id] = candidate
                else:
                    existing.debug.setdefault("keyword_query_hits", []).append(hit)
                    existing.debug.setdefault("keyword_queries", []).append(query)
                    if candidate.keyword_score > existing.keyword_score:
                        existing.keyword_score = candidate.keyword_score
                        existing.debug["keyword_bm25"] = candidate.debug.get("keyword_bm25")
                        existing.debug["keyword_relevance"] = candidate.debug.get("keyword_relevance")
                        existing.debug["keyword_tokenizer"] = candidate.debug.get("keyword_tokenizer")
                        existing.debug["keyword_tokens"] = candidate.debug.get("keyword_tokens")
                        existing.debug["keyword_best_query"] = query
                        existing.debug["keyword_best_query_weight"] = weight
        return list(candidates.values())

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        return [
            (
                candidate.content,
                candidate.keyword_score if candidate.keyword_score != 0.0 else candidate.exact_score,
                dict(candidate.metadata),
            )
            for candidate in candidates
        ]


def _weighted_queries(plan: QueryPlan) -> list[tuple[str, float, str]]:
    normalized = " ".join((plan.normalized_query or plan.original_query or "").split())
    compact = _compact(normalized)
    weighted: dict[str, tuple[float, str]] = {}

    def add(query: str, weight: float, source: str) -> None:
        value = " ".join((query or "").split())
        if not value:
            return
        existing = weighted.get(value)
        if existing is None or weight > existing[0]:
            weighted[value] = (weight, source)

    add(normalized, 1.0, "normalized")
    for query in plan.keyword_queries:
        value = " ".join((query or "").split())
        if not value:
            continue
        if value == normalized:
            add(value, 1.0, "normalized")
        elif value == compact:
            add(value, 0.70, "compact")
        else:
            add(value, 0.85, "planner")
    if compact and compact != normalized:
        add(compact, 0.70, "compact")
    return [(query, weight, source) for query, (weight, source) in weighted.items()]


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")
