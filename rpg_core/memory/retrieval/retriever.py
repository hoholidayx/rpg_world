"""Retriever abstraction for vector memory recall.

``BaseRetriever`` is the stable interface consumed by ``MemoryManager``.
``SqlVecRetriever`` is the vector retrieval implementation.

Both sync and async paths are provided.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.llm.base_provider import LLMProvider as EmbeddingProvider
    from rpg_world.rpg_core.memory.storage.vector_store import VectorStore


class BaseRetriever(ABC):
    """Abstract interface for memory retrieval."""

    @abstractmethod
    async def retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Async - returns ``(text, score, metadata)`` tuples."""

    @abstractmethod
    def retrieve_sync(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Sync - no event loop needed."""


def _similarity(l2_distance: float) -> float:
    return 1.0 / (1.0 + l2_distance)

