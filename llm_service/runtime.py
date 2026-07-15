"""Direct llama.cpp runtime with per-model actors and cooperative deadlines."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Iterator
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Generic, TypeVar, cast

from llm_service.models import LlamaModelCache, model_cache_key
from llm_service.settings import settings
from llm_service.types import LlamaCacheKey, LlamaModelConfig, LlamaResponsePayload

T = TypeVar("T")
logger = logging.getLogger(__name__)


class LlamaRuntimeCapacityError(RuntimeError):
    """The configured number of concurrently loaded llama models was exceeded."""


class LlamaRuntimeTimeoutError(TimeoutError):
    """A queued or running llama request exceeded its configured deadline."""


class LlamaRuntimeCancelledError(RuntimeError):
    """A running llama callback observed cooperative cancellation."""


@dataclass
class _RuntimeControl:
    deadline: float
    cancel_event: threading.Event = field(default_factory=threading.Event)
    timed_out: bool = False

    def cancelled(self) -> bool:
        if not self.cancel_event.is_set() and time.monotonic() >= self.deadline:
            self.timed_out = True
            self.cancel_event.set()
        return self.cancel_event.is_set()

    def cancel(self, *, timed_out: bool = False) -> None:
        self.timed_out = self.timed_out or timed_out
        self.cancel_event.set()

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())


@dataclass(frozen=True)
class _RuntimeJob(Generic[T]):
    future: Future[T]
    callback: Callable[[_RuntimeControl], T]
    control: _RuntimeControl


class _ModelActor:
    """Run one model cache key serially and cooperatively stop active work."""

    def __init__(self, *, shutdown_grace_seconds: float) -> None:
        self._queue: queue.Queue[_RuntimeJob[object] | None] = queue.Queue()
        self._guard = threading.Lock()
        self._closed = False
        self._current: _RuntimeJob[object] | None = None
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._thread = threading.Thread(
            target=self._run,
            name="llm-service-llama-model",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        callback: Callable[[_RuntimeControl], T],
        *,
        timeout_ms: int,
    ) -> _RuntimeJob[T]:
        future: Future[T] = Future()
        control = _RuntimeControl(
            deadline=time.monotonic() + max(1, int(timeout_ms)) / 1000.0
        )
        job = _RuntimeJob(future=future, callback=callback, control=control)
        with self._guard:
            if self._closed:
                raise RuntimeError("llama model actor is closed")
            self._queue.put(cast(_RuntimeJob[object], job))
        return job

    def close(self) -> bool:
        with self._guard:
            if self._closed:
                return not self._thread.is_alive()
            self._closed = True
            if self._current is not None:
                self._current.control.cancel()
            while True:
                try:
                    pending = self._queue.get_nowait()
                except queue.Empty:
                    break
                if pending is not None:
                    pending.control.cancel()
                    pending.future.cancel()
            self._queue.put(None)
        self._thread.join(timeout=self._shutdown_grace_seconds)
        return not self._thread.is_alive()

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            with self._guard:
                self._current = job
            if job.control.cancelled():
                self._finish_cancelled(job)
                with self._guard:
                    if self._current is job:
                        self._current = None
                continue
            if not job.future.set_running_or_notify_cancel():
                with self._guard:
                    if self._current is job:
                        self._current = None
                continue
            try:
                result = job.callback(job.control)
                if job.control.cancelled():
                    self._finish_cancelled(job)
                elif not job.future.done():
                    job.future.set_result(result)
            except BaseException as exc:
                if job.control.cancelled():
                    self._finish_cancelled(job)
                elif not job.future.done():
                    job.future.set_exception(exc)
            finally:
                with self._guard:
                    if self._current is job:
                        self._current = None

    @staticmethod
    def _finish_cancelled(job: _RuntimeJob[object]) -> None:
        if job.future.done():
            return
        if job.control.timed_out:
            job.future.set_exception(
                LlamaRuntimeTimeoutError("llama runtime request timed out")
            )
        else:
            job.future.set_exception(
                LlamaRuntimeCancelledError("llama runtime request cancelled")
            )


class DirectLlamaRuntime:
    """Per-model actors serialize calls and bound cross-model work."""

    def __init__(
        self,
        *,
        max_parallel_models: int,
        cache: LlamaModelCache | None = None,
        shutdown_grace_ms: int = 5000,
    ) -> None:
        self._max_parallel_models = max(1, int(max_parallel_models))
        self._cache = cache or LlamaModelCache()
        self._shutdown_grace_seconds = max(1, int(shutdown_grace_ms)) / 1000.0
        self._actors: dict[LlamaCacheKey, _ModelActor] = {}
        self._guard = threading.RLock()
        self._closed = False

    def embedding_dimension(
        self,
        model: LlamaModelConfig,
        *,
        request_timeout_ms: int = 60000,
    ) -> int:
        return self._call(
            "embedding_dimension",
            model,
            lambda _control: self._cache.embedding_dimension(model),
            request_timeout_ms=request_timeout_ms,
        )

    async def embedding_dimension_async(
        self,
        model: LlamaModelConfig,
        *,
        request_timeout_ms: int = 60000,
    ) -> int:
        return await self._call_async(
            "embedding_dimension",
            model,
            lambda _control: self._cache.embedding_dimension(model),
            request_timeout_ms=request_timeout_ms,
        )

    def embed(
        self,
        model: LlamaModelConfig,
        texts: list[str],
        *,
        request_timeout_ms: int = 60000,
    ) -> list[list[float]]:
        return self._call(
            "embed",
            model,
            lambda _control: self._cache.embed(model, texts),
            request_timeout_ms=request_timeout_ms,
        )

    async def embed_async(
        self,
        model: LlamaModelConfig,
        texts: list[str],
        *,
        request_timeout_ms: int = 60000,
    ) -> list[list[float]]:
        return await self._call_async(
            "embed",
            model,
            lambda _control: self._cache.embed(model, texts),
            request_timeout_ms=request_timeout_ms,
        )

    def complete(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
        request_timeout_ms: int = 60000,
    ) -> LlamaResponsePayload:
        return self._call(
            "complete",
            model,
            lambda control: self._cache.complete(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                cancelled=control.cancelled,
            ),
            request_timeout_ms=request_timeout_ms,
        )

    async def complete_async(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
        request_timeout_ms: int = 60000,
    ) -> LlamaResponsePayload:
        return await self._call_async(
            "complete",
            model,
            lambda control: self._cache.complete(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                cancelled=control.cancelled,
            ),
            request_timeout_ms=request_timeout_ms,
        )

    def complete_stream(
        self,
        model: LlamaModelConfig,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
        request_timeout_ms: int = 60000,
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
            request_timeout_ms=request_timeout_ms,
        )
        future.add_done_callback(lambda completed: _finish_stream_queue(completed, chunks))
        deadline = time.monotonic() + max(1, request_timeout_ms) / 1000.0
        try:
            while True:
                try:
                    item = chunks.get(timeout=max(0.001, deadline - time.monotonic()))
                except queue.Empty as exc:
                    cancelled.set()
                    future.cancel()
                    raise LlamaRuntimeTimeoutError(
                        "llama runtime stream timed out"
                    ) from exc
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
        request_timeout_ms: int = 60000,
    ) -> Future[None]:
        def consume(control: _RuntimeControl) -> None:
            def is_cancelled() -> bool:
                stopped = cancelled.is_set() or control.cancelled()
                if cancelled.is_set():
                    control.cancel()
                return stopped

            for chunk in self._cache.complete_stream(
                model,
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop,
                cancelled=is_cancelled,
            ):
                if is_cancelled():
                    break
                on_chunk(chunk)

        return self._submit_job(
            "complete_stream",
            model,
            consume,
            request_timeout_ms=request_timeout_ms,
        ).future

    def rerank(
        self,
        model: LlamaModelConfig,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
        request_timeout_ms: int = 60000,
    ) -> list[dict[str, float]]:
        return self._call(
            "rerank",
            model,
            lambda control: self._cache.rerank(
                model,
                query,
                documents,
                instruction=instruction,
                max_length=max_length,
                cancelled=control.cancelled,
            ),
            request_timeout_ms=request_timeout_ms,
        )

    async def rerank_async(
        self,
        model: LlamaModelConfig,
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
        request_timeout_ms: int = 60000,
    ) -> list[dict[str, float]]:
        return await self._call_async(
            "rerank",
            model,
            lambda control: self._cache.rerank(
                model,
                query,
                documents,
                instruction=instruction,
                max_length=max_length,
                cancelled=control.cancelled,
            ),
            request_timeout_ms=request_timeout_ms,
        )

    def _call(
        self,
        op: str,
        model: LlamaModelConfig,
        callback: Callable[[_RuntimeControl], T],
        *,
        request_timeout_ms: int,
    ) -> T:
        job = self._submit_job(
            op,
            model,
            callback,
            request_timeout_ms=request_timeout_ms,
        )
        try:
            return job.future.result(timeout=max(0.001, job.control.remaining()))
        except FutureTimeoutError as exc:
            job.control.cancel(timed_out=True)
            job.future.cancel()
            raise LlamaRuntimeTimeoutError(
                f"llama runtime request timed out: op={op}"
            ) from exc

    async def _call_async(
        self,
        op: str,
        model: LlamaModelConfig,
        callback: Callable[[_RuntimeControl], T],
        *,
        request_timeout_ms: int,
    ) -> T:
        job = self._submit_job(
            op,
            model,
            callback,
            request_timeout_ms=request_timeout_ms,
        )
        wrapped = asyncio.wrap_future(job.future)
        try:
            return await asyncio.wait_for(
                wrapped,
                timeout=max(0.001, job.control.remaining()),
            )
        except TimeoutError as exc:
            job.control.cancel(timed_out=True)
            job.future.cancel()
            raise LlamaRuntimeTimeoutError(
                f"llama runtime request timed out: op={op}"
            ) from exc
        except asyncio.CancelledError:
            job.control.cancel()
            job.future.cancel()
            raise

    def _submit_job(
        self,
        op: str,
        model: LlamaModelConfig,
        callback: Callable[[_RuntimeControl], T],
        *,
        request_timeout_ms: int,
    ) -> _RuntimeJob[T]:
        return self._actor_for(op, model).submit(
            callback,
            timeout_ms=request_timeout_ms,
        )

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
            actor = _ModelActor(
                shutdown_grace_seconds=self._shutdown_grace_seconds
            )
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
            if not actor.close():
                logger.error(
                    "llama actor did not exit within %.3fs; native call is still draining",
                    self._shutdown_grace_seconds,
                )


def _finish_stream_queue(
    completed: Future[None],
    chunks: queue.Queue[str | BaseException | None],
) -> None:
    try:
        completed.result()
    except BaseException as exc:
        chunks.put(exc)
    else:
        chunks.put(None)


_runtime: DirectLlamaRuntime | None = None
_runtime_lock = threading.RLock()


def get_direct_llama_runtime() -> DirectLlamaRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DirectLlamaRuntime(
                max_parallel_models=settings.runtime.llama_max_parallel_models,
                shutdown_grace_ms=settings.runtime.llama_shutdown_grace_ms,
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
        self._request_timeout_ms = max(1, int(request_timeout_ms))
        self._model: LlamaModelConfig = {
            "model_path": str(Path(model_path)),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "n_threads": n_threads,
            "verbose": verbose,
        }

    def dimension(self) -> int:
        return self._runtime.embedding_dimension(
            self._model,
            request_timeout_ms=self._request_timeout_ms,
        )

    async def dimension_async(self) -> int:
        return await self._runtime.embedding_dimension_async(
            self._model,
            request_timeout_ms=self._request_timeout_ms,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._runtime.embed(
            self._model,
            texts,
            request_timeout_ms=self._request_timeout_ms,
        )

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        return await self._runtime.embed_async(
            self._model,
            texts,
            request_timeout_ms=self._request_timeout_ms,
        )


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
        self.request_timeout_ms = max(1, int(request_timeout_ms))
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
            request_timeout_ms=self.request_timeout_ms,
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
            request_timeout_ms=self.request_timeout_ms,
        )

    def complete_stream(self, prompt: str, *, max_tokens: int, temperature: float, stop=None):  # noqa: ANN001
        yield from self._runtime.complete_stream(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            request_timeout_ms=self.request_timeout_ms,
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
            request_timeout_ms=self.request_timeout_ms,
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
        self._request_timeout_ms = max(1, int(request_timeout_ms))
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
            request_timeout_ms=self._request_timeout_ms,
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
            request_timeout_ms=self._request_timeout_ms,
        )
