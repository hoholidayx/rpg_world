"""SQL-backed vector retriever for memory recall."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.retrieval.filters import excluded_from_recall
from rp_memory.retrieval.retriever import BaseRetriever, _similarity

if TYPE_CHECKING:
    from llm_client.types import LLMProvider as EmbeddingProvider
    from rp_memory.storage.vector_store import VectorStore


class SqlVecRetriever(BaseRetriever):
    """Pure SQL vector retrieval via embedding + VectorStore search."""

    def __init__(self, store: VectorStore, embedding: EmbeddingProvider) -> None:
        self._store = store
        self._embedding = embedding

    async def retrieve(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        candidates = await self.search(query, top_k=top_k)
        return self._format(candidates)

    async def retrieve_plan(
        self,
        plan: QueryPlan,
        top_k: int = 5,
    ) -> list[tuple[str, float, dict]]:
        candidates = await self.search_plan(plan, top_k=top_k)
        return self._format(candidates)

    def retrieve_sync(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        raise RuntimeError("SqlVecRetriever is async-only; await retrieve()")

    def retrieve_plan_sync(self, plan: QueryPlan, top_k: int = 5) -> list[tuple[str, float, dict]]:
        raise RuntimeError("SqlVecRetriever is async-only; await retrieve_plan()")

    async def search(self, query: str, top_k: int = 5) -> list[MemoryCandidate]:
        vecs = await self._embedding.embed([query])
        if not vecs:
            return []
        raw = await asyncio.to_thread(self._store.search, vecs[0], top_k)
        candidates: list[MemoryCandidate] = []
        for record, distance in raw:
            if excluded_from_recall(record.metadata):
                continue
            candidates.append(
                MemoryCandidate(
                    memory_id=record.id,
                    content=record.text,
                    metadata=dict(record.metadata),
                    vector_score=_similarity(distance),
                )
            )
        return candidates

    async def search_plan(self, plan: QueryPlan, top_k: int = 5) -> list[MemoryCandidate]:
        queries = _dedupe_queries([
            plan.normalized_query or plan.original_query,
            *plan.expanded_queries,
        ])
        if not queries:
            return []
        vectors = await self._embedding.embed(queries)
        if len(vectors) != len(queries):
            raise ValueError(
                "embedding response count does not match contextual queries: "
                f"queries={len(queries)} vectors={len(vectors)}"
            )
        merged: dict[int, MemoryCandidate] = {}
        for query, vector in zip(queries, vectors, strict=True):
            raw = await asyncio.to_thread(self._store.search, vector, top_k)
            for record, distance in raw:
                if excluded_from_recall(record.metadata):
                    continue
                score = _similarity(distance)
                existing = merged.get(record.id)
                if existing is None:
                    merged[record.id] = MemoryCandidate(
                        memory_id=record.id,
                        content=record.text,
                        metadata=dict(record.metadata),
                        vector_score=score,
                        debug={"vector_best_query": query},
                    )
                elif score > existing.vector_score:
                    existing.vector_score = score
                    existing.debug["vector_best_query"] = query
        return sorted(
            merged.values(),
            key=lambda candidate: candidate.vector_score,
            reverse=True,
        )[: max(1, int(top_k))]

    def _format(self, candidates: list[MemoryCandidate]) -> list[tuple[str, float, dict]]:
        return [
            (candidate.content, candidate.vector_score, dict(candidate.metadata))
            for candidate in candidates
        ]


def _dedupe_queries(queries: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for query in queries:
        value = " ".join(str(query or "").split())
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
