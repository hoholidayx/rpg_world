"""Raw markdown retriever fallback for memory recall."""

from __future__ import annotations

import asyncio

from rpg_world.rpg_core.memory.planning.plan import QueryPlan
from rpg_world.rpg_core.memory.retrieval.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retrieval.retriever import BaseRetriever


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
        candidates = self._searcher.search(query, limit=top_k)
        return self._format(candidates)

    def retrieve_plan_sync(
        self, plan: QueryPlan, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        candidates = self._searcher.search_plan(plan, limit=top_k)
        return self._format(candidates)

    def _format(self, candidates):
        return [
            (
                candidate.content,
                candidate.final_score or candidate.keyword_score or candidate.exact_score,
                dict(candidate.metadata),
            )
            for candidate in candidates
        ]
