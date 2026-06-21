"""Public reranker abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rpg_world.rpg_core.memory.candidate import MemoryCandidate


class MemoryReranker(ABC):
    """Unified reranker interface used by the memory pipeline."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        """Return reranked candidates."""
