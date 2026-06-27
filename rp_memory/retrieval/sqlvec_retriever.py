"""SQL-backed vector retriever for memory recall."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.retrieval.retriever import BaseRetriever, _similarity

if TYPE_CHECKING:
    from llm_service.base_provider import LLMProvider as EmbeddingProvider
    from rp_memory.storage.vector_store import VectorStore


class SqlVecRetriever(BaseRetriever):
    """Pure SQL vector retrieval via embedding + VectorStore search."""

    def __init__(self, store: VectorStore, embedding: EmbeddingProvider) -> None:
        self._store = store
        self._embedding = embedding

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search(query, top_k=top_k)
        return self._format(candidates)

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = self.search_plan(plan, top_k=top_k)
        return self._format(candidates)

    def search(self, query: str, top_k: int = 5) -> list[MemoryCandidate]:
        vecs = self._embedding.embed_sync([query])
        if not vecs:
            return []
        raw = self._store.search(vecs[0], top_k=top_k)
        candidates: list[MemoryCandidate] = []
        for record, distance in raw:
            candidates.append(
                MemoryCandidate(
                    memory_id=record.id,
                    content=record.text,
                    metadata=dict(record.metadata),
                    vector_score=_similarity(distance),
                )
            )
        return candidates

    def search_plan(self, plan: QueryPlan, top_k: int = 5) -> list[MemoryCandidate]:
        return self.search(plan.normalized_query or plan.original_query, top_k=top_k)

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        return [
            (candidate.content, candidate.final_score or candidate.vector_score, dict(candidate.metadata))
            for candidate in candidates
        ]
