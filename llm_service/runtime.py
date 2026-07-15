"""Direct in-process llama.cpp runtime owned only by LLM Service."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Iterator
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generic, TypeVar, cast

from llm_service.models import LlamaModelCache, model_cache_key
from llm_service.settings import settings
from llm_service.types import LlamaCacheKey, LlamaModelConfig, LlamaResponsePayload

T = TypeVar("T")


class LlamaRuntimeCapacityError(RuntimeError):
    """The configured number of concurrently loaded llama models was exceeded."""


@dataclass(frozen=True)
class _RuntimeJob(Generic[T]):
    future: Future[T]
    callback: Callable[[], T]


class _ModelActor:
    """Run one model cache key serially and skip cancelled queued work."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_RuntimeJob[object] | None] = queue.Queue()
        self._guard = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name="llm-service-llama-model",
            daemon=True,
        )
        self._thread.start()

    def submit(self, callback: Callable[[], T]) -> Future[T]:
        future: Future[T] = Future()
        with self._guard:
            if self._closed:
                raise RuntimeError("llama model actor is closed")
            self._queue.put(
                _RuntimeJob(
                    future=cast(Future[object], future),
                    callback=cast(Callable[[], object], callback),
                )
            )
        return future

    def close(self) -> None:
        with self._guard:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    pending = self._queue.get_nowait()
                except queue.Empty:
                    break
                if pending is not None:
                    pending.future.cancel()
            self._queue.put(None)
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            if not job.future.set_running_or_notify_cancel():
                continue
            try:
                job.future.set_result(job.callback())
            except BaseException as exc:
                job.future.set_exception(exc)


class DirectLlamaRuntime:
    """Per-model actors serialize calls and bound cross-model work."""

    def __init__(
        self,
        *,
        max_parallel_models: int,
        cache: LlamaModelCache | None = None,
    ) -> None:
        self._max_parallel_models = max(1, int(max_parallel_models))
        self._cache = cache or LlamaModelCache()
        self._actors: dict[LlamaCacheKey, _ModelActor] = {}
        self._guard = threading.RLock()
        self._closed = False

    def embedding_dimension(self, model: LlamaModelConfig) -> int:
        return self._call("embedding_dimension", model, lambda: self._cache.embedding_dimension(model))

    def embed(self, model: LlamaModelConfig, texts: list[str]) -> list[list[float]]:
        return self._call("embed", model, lambda: self._cache.embed(model, texts))

    async def embed_async(
        self,
        model: LlamaModelConfig,
        texts: list[str],
    ) -> list[list[float]]:
        return await self._call_async("embed", model, lambda: self._cache.embed(model, texts))

    def complete(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> LlamaResponsePayload:
        return self._call(
            "complete",
            model,
            lambda: self._cache.complete(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
            ),
        )

    async def complete_async(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> LlamaResponsePayload:
        return await self._call_async(
            "complete",
            model,
            lambda: self._cache.complete(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
            ),
        )

    def complete_stream(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> Iterator[str]:
        chunks: queue.Queue[str | BaseException | None] = queue.Queue()
        cancelled = threading.Event()
        future = self.start_complete_stream(
            model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            on_chunk=chunks.put,
            cancelled=cancelled,
        )

        def _finished(completed: Future[None]) -> None:
            try:
                completed.result()
            except BaseException as exc:
                chunks.put(exc)
            else:
                chunks.put(None)

        future.add_done_callback(_finished)
        try:
            while True:
                item = chunks.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            cancelled.set()
            future.cancel()

    def start_complete_stream(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None,
        on_chunk: Callable[[str], None],
        cancelled: threading.Event,
    ) -> Future[None]:
        def _consume() -> None:
            for chunk in self._cache.complete_stream(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
            ):
                if cancelled.is_set():
                    break
                on_chunk(chunk)

        return self._submit("complete_stream", model, _consume)

    def rerank(
        self,
        model: LlamaModelConfig,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
    ) -> list[dict[str, float]]:
        return self._call(
            "rerank",
            model,
            lambda: self._cache.rerank(
                model,
                query,
                documents,
                instruction=instruction,
                max_length=max_length,
            ),
        )

    async def rerank_async(
        self,
        model: LlamaModelConfig,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
    ) -> list[dict[str, float]]:
        return await self._call_async(
            "rerank",
            model,
            lambda: self._cache.rerank(
                model,
                query,
                documents,
                instruction=instruction,
                max_length=max_length,
            ),
        )

    def _call(self, op: str, model: LlamaModelConfig, callback: Callable[[], T]) -> T:
        return self._submit(op, model, callback).result()

    async def _call_async(
        self,
        op: str,
        model: LlamaModelConfig,
        callback: Callable[[], T],
    ) -> T:
        future = self._submit(op, model, callback)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            raise

    def _submit(
        self,
        op: str,
        model: LlamaModelConfig,
        callback: Callable[[], T],
    ) -> Future[T]:
        return self._actor_for(op, model).submit(callback)

    def _actor_for(self, op: str, model: LlamaModelConfig) -> _ModelActor:
        key = model_cache_key(op, model)
        with self._guard:
            if self._closed:
                raise RuntimeError("llama runtime is closed")
            actor = self._actors.get(key)
            if actor is not None:
                return actor
            if len(self._actors) >= self._max_parallel_models:
                raise LlamaRuntimeCapacityError(
                    "llama max_parallel_models exceeded: "
                    f"configured={self._max_parallel_models} requested={key!r}"
                )
            actor = _ModelActor()
            self._actors[key] = actor
            return actor

    def close(self) -> None:
        with self._guard:
            if self._closed:
                return
            self._closed = True
            actors = tuple(self._actors.values())
            self._actors.clear()
        for actor in actors:
            actor.close()


_runtime: DirectLlamaRuntime | None = None
_runtime_lock = threading.RLock()


def get_direct_llama_runtime() -> DirectLlamaRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DirectLlamaRuntime(
                max_parallel_models=settings.runtime.llama_max_parallel_models
            )
        return _runtime


def set_direct_llama_runtime_for_tests(runtime: DirectLlamaRuntime | None) -> None:
    global _runtime
    with _runtime_lock:
        previous = _runtime
        _runtime = runtime
    if previous is not None and previous is not runtime:
        previous.close()


def reset_direct_llama_runtime() -> None:
    set_direct_llama_runtime_for_tests(None)


class DirectLlamaEmbeddingModel:
    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        runtime: DirectLlamaRuntime | None = None,
    ) -> None:
        self._runtime = runtime or get_direct_llama_runtime()
        self._model: LlamaModelConfig = {
            "model_path": str(Path(model_path)),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "n_threads": n_threads,
            "verbose": verbose,
        }

    def dimension(self) -> int:
        return self._runtime.embedding_dimension(self._model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._runtime.embed(self._model, texts)

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        return await self._runtime.embed_async(self._model, texts)


class DirectLlamaCompletionModel:
    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        runtime: DirectLlamaRuntime | None = None,
    ) -> None:
        self._runtime = runtime or get_direct_llama_runtime()
        self._model: LlamaModelConfig = {
            "model_path": str(Path(model_path)),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "verbose": verbose,
        }

    def complete(self, prompt: str, *, max_tokens: int, temperature: float, stop=None):  # noqa: ANN001
        return self._runtime.complete(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

    async def complete_async(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop=None,  # noqa: ANN001
    ) -> LlamaResponsePayload:
        return await self._runtime.complete_async(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

    def complete_stream(self, prompt: str, *, max_tokens: int, temperature: float, stop=None):  # noqa: ANN001
        yield from self._runtime.complete_stream(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
        )

    def start_complete_stream(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None,
        on_chunk: Callable[[str], None],
        cancelled: threading.Event,
    ) -> Future[None]:
        return self._runtime.start_complete_stream(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            on_chunk=on_chunk,
            cancelled=cancelled,
        )


class DirectLlamaRerankModel:
    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        runtime: DirectLlamaRuntime | None = None,
    ) -> None:
        self._runtime = runtime or get_direct_llama_runtime()
        self._model: LlamaModelConfig = {
            "model_path": str(Path(model_path)),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "verbose": verbose,
        }

    def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
    ) -> list[dict[str, float]]:
        return self._runtime.rerank(
            self._model,
            query,
            documents,
            instruction=instruction,
            max_length=max_length,
        )

    async def rerank_async(
        self,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
    ) -> list[dict[str, float]]:
        return await self._runtime.rerank_async(
            self._model,
            query,
            documents,
            instruction=instruction,
            max_length=max_length,
        )
