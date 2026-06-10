"""Embedding provider abstraction and llama.cpp implementation.

The provider interface is intentionally minimal — a single ``embed()``
call accepting a batch of texts — so that the retriever layer is
decoupled from any specific embedding backend.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path


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


class LlamaCppEmbeddingProvider(EmbeddingProvider):
    """``llama-cpp-python`` backed embedding provider.

    Loads a GGUF model with ``embedding=True``.  The blocking llama.cpp
    call runs in the current thread — no ``asyncio.to_thread`` overhead.
    If you need async, call :meth:`embed` which simply wraps the sync call.
    """

    def __init__(
        self,
        gguf_model_path: str | Path,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
    ) -> None:
        self._llama = None
        self._dim = 0
        self._load(gguf_model_path, n_ctx, n_gpu_layers, n_threads, verbose)

    # ── public API ────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper — runs :meth:`embed_sync` in executor."""
        if not texts:
            return []
        if self._llama is None:
            raise EmbeddingProviderError("model not loaded")
        return await asyncio.to_thread(self.embed_sync, texts)

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """同步嵌入 — 直接调用 llama.cpp，无事件循环依赖。"""
        if not texts:
            return []
        if self._llama is None:
            raise EmbeddingProviderError("model not loaded")
        result = self._llama.embed(texts)
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result  # type: ignore[return-value]
        return [result]  # type: ignore[list-item]

    def dimension(self) -> int:
        return self._dim

    def close(self) -> None:
        if self._llama is not None:
            try:
                del self._llama
            except Exception:
                pass
            self._llama = None

    # ── internal ──────────────────────────────────────────────

    def _load(
        self,
        path: str | Path,
        n_ctx: int,
        n_gpu_layers: int,
        n_threads: int,
        verbose: bool,
    ) -> None:
        p = Path(path)
        if not p.is_file():
            raise EmbeddingProviderError(f"GGUF model not found: {p}")
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise EmbeddingProviderError(
                "llama-cpp-python is not installed"
            ) from exc

        self._llama = Llama(
            model_path=str(p),
            embedding=True,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            verbose=verbose,
        )
        probe = self.embed_sync(["dimension probe"])
        self._dim = len(probe[0]) if probe else 0
        if self._dim == 0:
            raise EmbeddingProviderError(
                "model returned zero-dimension vectors"
            )
