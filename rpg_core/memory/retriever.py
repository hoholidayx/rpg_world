"""Retriever abstraction for vector memory recall.

``BaseRetriever`` is the stable interface consumed by ``MemoryManager``.
``DenseRetriever`` is the Phase‑1 implementation (pure dense vector search).

Both sync and async paths are provided.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_world.rpg_core.memory.embedding_provider import EmbeddingProvider
    from rpg_world.rpg_core.memory.vector_store import VectorStore


class BaseRetriever(ABC):
    """Abstract interface for memory retrieval."""

    @abstractmethod
    async def retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Async — returns ``(text, score, metadata)`` tuples."""

    @abstractmethod
    def retrieve_sync(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Sync — no event loop needed."""


class DenseRetriever(BaseRetriever):
    """Pure dense vector retrieval via embedding + VectorStore search."""

    def __init__(
        self, store: VectorStore, embedding: EmbeddingProvider
    ) -> None:
        self._store = store
        self._embedding = embedding

    async def retrieve(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        vecs = await self._embedding.embed([query])
        if not vecs:
            return []
        raw = self._store.search(vecs[0], top_k=top_k)
        return [
            (rec.text, _similarity(dist), dict(rec.metadata))
            for rec, dist in raw
        ]

    def retrieve_sync(
        self, query: str, top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        vecs = self._embedding.embed_sync([query])
        if not vecs:
            return []
        raw = self._store.search(vecs[0], top_k=top_k)
        return [
            (rec.text, _similarity(dist), dict(rec.metadata))
            for rec, dist in raw
        ]


def _similarity(l2_distance: float) -> float:
    return 1.0 / (1.0 + l2_distance)
