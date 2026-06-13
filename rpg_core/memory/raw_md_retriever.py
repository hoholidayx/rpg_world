"""Raw markdown retriever fallback for memory recall."""

from __future__ import annotations

import asyncio

from rpg_world.rpg_core.memory.raw_md_grep_search import RawMarkdownGrepSearch
from rpg_world.rpg_core.memory.retriever import BaseRetriever


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
        return [
            (
                candidate.content,
                candidate.final_score or candidate.keyword_score or candidate.exact_score,
                dict(candidate.metadata),
            )
            for candidate in candidates
        ]
