"""Embedding provider abstraction and llama.cpp implementation.

The provider interface is intentionally minimal — a single ``embed()``
call accepting a batch of texts — so that the retriever layer is
decoupled from any specific embedding backend.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path

from openai import AsyncOpenAI

from rpg_world.rpg_core.memory.asyncio_utils import run_awaitable_sync


class EmbeddingProviderError(Exception):
    """Raised when the embedding provider cannot fulfil a request."""


class EmbeddingProvider(ABC):
    """Abstract interface for text embedding models."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts; returns one vector per text."""

    @abstractmethod
    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous version of :meth:`embed`, avoids event loop overhead."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding vector dimension."""

    def close(self) -> None:
        """Release resources.  Default no-op."""


class LlamaClientEmbeddingProvider(EmbeddingProvider):
    """Process-isolated llama.cpp embedding provider."""

    def __init__(
        self,
        gguf_model_path: str | Path,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
    ) -> None:
        from rpg_world.rpg_core.llama_service import LlamaEmbeddingModel

        self._model = LlamaEmbeddingModel(
            gguf_model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
            request_timeout_ms=request_timeout_ms,
        )
        self._dim = self._model.dimension()
        if self._dim == 0:
            raise EmbeddingProviderError("model returned zero-dimension vectors")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self.embed_sync, texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._model.embed(texts)

    def dimension(self) -> int:
        return self._dim


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._timeout_ms = timeout_ms
        self._dimension: int | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        vectors = [list(item.embedding) for item in response.data]
        if vectors and self._dimension is None:
            self._dimension = len(vectors[0])
        return vectors

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return run_awaitable_sync(self.embed(texts))

    def dimension(self) -> int:
        if self._dimension is not None:
            return self._dimension
        vectors = self.embed_sync(["dimension probe"])
        return len(vectors[0]) if vectors else 0
