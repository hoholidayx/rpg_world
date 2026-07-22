"""Public business-neutral reranker abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from memory_retrieval.candidate import MemoryCandidate


class MemoryReranker(ABC):
    """Unified reranker interface used by the memory pipeline."""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[MemoryCandidate],
    ) -> list[MemoryCandidate]:
        """Return reranked candidates."""
