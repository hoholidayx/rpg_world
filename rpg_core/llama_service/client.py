"""Client for the process-isolated llama.cpp worker."""

from __future__ import annotations

from collections.abc import Iterator
import multiprocessing as mp
import queue
import threading
import time
import uuid
from multiprocessing.queues import Queue as MPQueue
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from rpg_world.rpg_core.llama_service.protocol import LlamaOperation, LlamaResponse, make_request


class LlamaClientError(Exception):
    """Base llama client error."""


class LlamaClientTimeout(LlamaClientError):
    """Raised when the llama worker does not answer before timeout."""


class LlamaClientRemoteError(LlamaClientError):
    """Raised when the llama worker returns an error response."""


class LlamaEmbeddingModel:
    """High-level embedding model handle for business-layer callers."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 32768,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        client: LlamaClient | None = None,
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise LlamaClientError(f"GGUF model not found: {path}")
        self._client = client or get_llama_client()
        self._request_timeout_ms = request_timeout_ms
        self._model = {
            "model_path": str(path),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "n_threads": n_threads,
            "verbose": verbose,
        }

    def dimension(self) -> int:
        return self._client.embedding_dimension(
            self._model,
            timeout_ms=self._request_timeout_ms,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed(
            self._model,
            texts,
            timeout_ms=self._request_timeout_ms,
        )


class LlamaCompletionModel:
    """High-level completion model handle for business-layer callers."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        client: LlamaClient | None = None,
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise LlamaClientError(f"GGUF model not found: {path}")
        self._client = client or get_llama_client()
        self._request_timeout_ms = request_timeout_ms
        self._model = {
            "model_path": str(path),
            "n_ctx": n_ctx,
            "n_gpu_layers": n_gpu_layers,
            "verbose": verbose,
        }

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> Any:
        return self._client.complete(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            timeout_ms=self._request_timeout_ms,
        )

    def complete_stream(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
    ) -> Iterator[str]:
        return self._client.complete_stream(
            self._model,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            timeout_ms=self._request_timeout_ms,
        )


class LlamaRerankModel:
    """High-level rerank model handle for Qwen-style yes/no logit scoring."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        request_timeout_ms: int = 60000,
        client: LlamaClient | None = None,
    ) -> None:
        path = Path(model_path)
        if not path.is_file():
            raise LlamaClientError(f"GGUF model not found: {path}")
        self._client = client or get_llama_client()
        self._request_timeout_ms = request_timeout_ms
        self._model = {
            "model_path": str(path),
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
        return self._client.rerank(
            self._model,
            query,
            documents,
            instruction=instruction,
            max_length=max_length,
            timeout_ms=self._request_timeout_ms,
        )


ProcessFactory = Callable[[MPQueue, MPQueue, int], mp.Process]


class LlamaClient:
    """Singleton-friendly client that owns a lazy llama worker process."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        request_timeout_ms: int = 60000,
        startup_timeout_ms: int = 120000,
        max_parallel_models: int = 2,
        process_factory: ProcessFactory | None = None,
    ) -> None:
        self.enabled = enabled
        self.request_timeout_ms = request_timeout_ms
        self.startup_timeout_ms = startup_timeout_ms
        self.max_parallel_models = max_parallel_models
        self._process_factory = process_factory or _default_process_factory
        self._request_queue: MPQueue | None = None
        self._response_queue: MPQueue | None = None
        self._process: mp.Process | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._responses: dict[str, list[LlamaResponse]] = {}
        self._closed = False

    def configure(
        self,
        *,
        enabled: bool,
        request_timeout_ms: int,
        startup_timeout_ms: int,
        max_parallel_models: int,
    ) -> None:
        with self._lock:
            self.enabled = enabled
            self.request_timeout_ms = request_timeout_ms
            self.startup_timeout_ms = startup_timeout_ms
            self.max_parallel_models = max_parallel_models

    def embedding_dimension(self, model: dict[str, Any], timeout_ms: int | None = None) -> int:
        return int(self.request("embedding_dimension", model=model, timeout_ms=timeout_ms))

    def embed(
        self,
        model: dict[str, Any],
        texts: list[str],
        timeout_ms: int | None = None,
    ) -> list[list[float]]:
        result = self.request("embed", model=model, params={"texts": texts}, timeout_ms=timeout_ms)
        return result

    def complete(
        self,
        model: dict[str, Any],
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
        timeout_ms: int | None = None,
    ) -> Any:
        return self.request(
            "complete",
            model=model,
            params={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": stop or [],
            },
            timeout_ms=timeout_ms,
        )

    def complete_stream(
        self,
        model: dict[str, Any],
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str] | None = None,
        timeout_ms: int | None = None,
    ) -> Iterator[str]:
        for response in self.stream_request(
            "complete_stream",
            model=model,
            params={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": stop or [],
            },
            timeout_ms=timeout_ms,
        ):
            result = response.get("result")
            if result is not None:
                yield str(result)

    def rerank(
        self,
        model: dict[str, Any],
        query: str,
        documents: list[str],
        *,
        instruction: str,
        max_length: int,
        timeout_ms: int | None = None,
    ) -> list[dict[str, float]]:
        result = self.request(
            "rerank",
            model=model,
            params={
                "query": query,
                "documents": documents,
                "instruction": instruction,
                "max_length": max_length,
            },
            timeout_ms=timeout_ms,
        )
        return list(result or [])

    def request(
        self,
        op: LlamaOperation,
        *,
        model: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> Any:
        if not self.enabled:
            raise LlamaClientError("llama process client disabled")
        request_id = uuid.uuid4().hex
        timeout = timeout_ms if timeout_ms is not None else self.request_timeout_ms
        with self._condition:
            self._ensure_started_locked()
            assert self._request_queue is not None
            self._request_queue.put(
                make_request(
                    request_id,
                    op,
                    model=model,
                    params=params,
                    timeout_ms=timeout,
                )
            )
            deadline = time.monotonic() + max(1, timeout) / 1000.0
            while not self._responses.get(request_id):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._responses.pop(request_id, None)
                    raise LlamaClientTimeout(f"llama request timed out: op={op}")
                self._condition.wait(timeout=min(remaining, 0.25))
                self._raise_if_process_dead_locked()
            pending = self._responses.get(request_id) or []
            response = pending.pop(0)
            if pending:
                self._responses[request_id] = pending
            else:
                self._responses.pop(request_id, None)
        if response.get("ok"):
            return response.get("result")
        error = response.get("error") or {}
        raise LlamaClientRemoteError(f"{error.get('type', 'RemoteError')}: {error.get('message', '')}")

    def stream_request(
        self,
        op: LlamaOperation,
        *,
        model: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> Iterator[LlamaResponse]:
        if not self.enabled:
            raise LlamaClientError("llama process client disabled")
        request_id = uuid.uuid4().hex
        timeout = timeout_ms if timeout_ms is not None else self.request_timeout_ms
        with self._condition:
            self._ensure_started_locked()
            assert self._request_queue is not None
            self._request_queue.put(
                make_request(
                    request_id,
                    op,
                    model=model,
                    params=params,
                    timeout_ms=timeout,
                )
            )

        deadline = time.monotonic() + max(1, timeout) / 1000.0
        while True:
            with self._condition:
                while not self._responses.get(request_id):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._responses.pop(request_id, None)
                        raise LlamaClientTimeout(f"llama stream request timed out: op={op}")
                    self._condition.wait(timeout=min(remaining, 0.25))
                    self._raise_if_process_dead_locked()
                pending = self._responses.get(request_id) or []
                response = pending.pop(0)
                if pending:
                    self._responses[request_id] = pending
                else:
                    self._responses.pop(request_id, None)

            if not response.get("ok"):
                error = response.get("error") or {}
                raise LlamaClientRemoteError(f"{error.get('type', 'RemoteError')}: {error.get('message', '')}")
            yield response
            if response.get("stream_done"):
                return

    def shutdown(self, timeout_ms: int | None = None) -> None:
        timeout = timeout_ms if timeout_ms is not None else min(self.request_timeout_ms, 10000)
        with self._condition:
            if self._process is None:
                self._closed = True
                return
        try:
            self.request("shutdown", timeout_ms=timeout)
        except Exception as exc:
            logger.warning("[LlamaClient] shutdown request failed: {}", exc)
        with self._condition:
            process = self._process
        if process is not None:
            process.join(timeout=max(1, timeout) / 1000.0)
            if process.is_alive():
                logger.warning("[LlamaClient] worker did not exit in time; terminating")
                process.terminate()
                process.join(timeout=2.0)
        with self._condition:
            self._mark_unavailable_locked()
            self._closed = True

    def _ensure_started_locked(self) -> None:
        if self._closed:
            self._closed = False
        if self._process is not None and self._process.is_alive():
            return
        self._mark_unavailable_locked()
        self._request_queue = mp.Queue()
        self._response_queue = mp.Queue()
        self._process = self._process_factory(
            self._request_queue,
            self._response_queue,
            self.max_parallel_models,
        )
        self._process.start()
        self._reader = threading.Thread(
            target=self._read_responses,
            name="llama-client-reader",
            daemon=True,
        )
        self._reader.start()
        logger.info("[LlamaClient] worker started pid={}", self._process.pid)

    def _read_responses(self) -> None:
        while True:
            with self._lock:
                response_queue = self._response_queue
                process = self._process
            if response_queue is None or process is None:
                return
            try:
                response = response_queue.get(timeout=0.2)
            except queue.Empty:
                with self._lock:
                    if self._process is not process:
                        return
                continue
            if not isinstance(response, dict):
                continue
            request_id = str(response.get("request_id", ""))
            with self._condition:
                self._responses.setdefault(request_id, []).append(response)
                self._condition.notify_all()

    def _raise_if_process_dead_locked(self) -> None:
        if self._process is not None and not self._process.is_alive():
            exitcode = self._process.exitcode
            self._mark_unavailable_locked()
            raise LlamaClientError(f"llama worker exited unexpectedly: exitcode={exitcode}")

    def _mark_unavailable_locked(self) -> None:
        self._request_queue = None
        self._response_queue = None
        self._process = None
        self._reader = None
        self._responses.clear()


def _default_process_factory(
    request_queue: MPQueue,
    response_queue: MPQueue,
    max_parallel_models: int,
) -> mp.Process:
    from rpg_world.rpg_core.llama_service.server import serve

    return mp.Process(
        target=serve,
        args=(request_queue, response_queue),
        kwargs={"max_parallel_models": max_parallel_models},
        name="rpg-world-llama-service",
        daemon=True,
    )


_CLIENT: LlamaClient | None = None


def get_llama_client() -> LlamaClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = LlamaClient()
    return _CLIENT


def configure_llama_client_from_memory_settings(memory_settings: Any) -> LlamaClient:
    """Configure the process-wide llama client from ``MemorySettings``."""
    client = get_llama_client()
    client.configure(
        enabled=bool(getattr(memory_settings, "llama_process_enabled", True)),
        request_timeout_ms=int(getattr(memory_settings, "llama_request_timeout_ms", 60000)),
        startup_timeout_ms=int(getattr(memory_settings, "llama_startup_timeout_ms", 120000)),
        max_parallel_models=int(getattr(memory_settings, "llama_max_parallel_models", 2)),
    )
    return client


def set_llama_client(client: LlamaClient | None) -> None:
    global _CLIENT
    _CLIENT = client
