"""Raw markdown retriever fallback for memory recall."""

from __future__ import annotations

import asyncio

from rp_memory.candidate import MemoryCandidate
from rp_memory.planning.plan import QueryPlan
from rp_memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rp_memory.retrieval.retriever import BaseRetriever


class RawMarkdownRetriever(BaseRetriever):
    """Retriever that only scans raw markdown files."""

    def __init__(self, searcher: RawMarkdownGrepSearch) -> None:
        self._searcher = searcher

    async def retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        return await asyncio.to_thread(self.retrieve_sync, query, top_k)

    def retrieve_sync(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        candidates = self.search(query, top_k=top_k)
        return self._format(candidates)

    def retrieve_plan_sync(
        self, plan: QueryPlan, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        candidates = self.search_plan(plan, top_k=top_k)
        return self._format(candidates)

    def search(self, query: str, top_k: int = 5) -> list[MemoryCandidate]:
        return self._searcher.search(query, limit=top_k)

    def search_plan(self, plan: QueryPlan, top_k: int = 5) -> list[MemoryCandidate]:
        return self._searcher.search_plan(plan, limit=top_k)

    def _format(self, candidates: list[MemoryCandidate]):
        return [
            (
                candidate.content,
                candidate.final_score or candidate.raw_md_score or candidate.exact_score,
                dict(candidate.metadata),
            )
            for candidate in candidates
        ]
