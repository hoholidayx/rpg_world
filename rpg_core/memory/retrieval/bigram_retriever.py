"""Bigram FTS retriever for memory recall."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rpg_world.rpg_core.memory.candidate import MemoryCandidate
from rpg_world.rpg_core.memory.planning.plan import QueryPlan
from rpg_world.rpg_core.memory.retrieval.retriever import BaseRetriever

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.storage.vector_store import VectorStore


class BigramRetriever(BaseRetriever):
    """Bigram-based FTS retriever backed by the SQLite text index."""

    def __init__(self, store: VectorStore, limit: int = 50) -> None:
        self._store = store
        self._limit = limit

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search(query, top_k=top_k)
        return self._format(candidates)

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search_plan(plan, top_k=top_k)
        return self._format(candidates)

    def search(self, query: str, top_k: int = 5) -> list[MemoryCandidate]:
        return self._store.bigram_search(query, limit=top_k)

    def search_plan(self, plan: QueryPlan, top_k: int = 5) -> list[MemoryCandidate]:
        candidates: dict[int, MemoryCandidate] = {}
        queries = list(plan.bigram_queries)
        for query in queries:
            for candidate in self._store.bigram_search(query, limit=min(self._limit, top_k)):
                candidate.debug.setdefault("bigram_queries", []).append(query)
                existing = candidates.get(candidate.memory_id)
                if existing is None or candidate.bigram_score > existing.bigram_score:
                    candidates[candidate.memory_id] = candidate
        return list(candidates.values())

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        return [
            (
                candidate.content,
                candidate.final_score or candidate.bigram_score or candidate.exact_score,
                dict(candidate.metadata),
            )
            for candidate in candidates
        ]
