"""Worker process entry point for process-isolated llama.cpp calls."""

from __future__ import annotations

import queue
import threading
from multiprocessing.queues import Queue as MPQueue

from rpg_core.common_types import LlamaCacheKey, LlamaResponsePayload
from llama_service.models import LlamaModelCache, model_cache_key
from llama_service.protocol import (
    LlamaRequest,
    LlamaResponse,
    error_response,
    ok_response,
)


class _Actor:
    """Serializes calls for one llama model instance."""

    def __init__(self, response_queue: MPQueue, cache: LlamaModelCache) -> None:
        self._response_queue = response_queue
        self._cache = cache
        self._queue: queue.Queue[LlamaRequest | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="llama-model-actor", daemon=True)
        self._thread.start()

    def submit(self, request: LlamaRequest) -> None:
        self._queue.put(request)

    def stop(self) -> None:
        self._queue.put(None)

    def join(self, timeout: float = 5.0) -> None:
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                return
            request_id = str(request.get("request_id", ""))
            try:
                if request.get("op") == "complete_stream":
                    _handle_stream_request(self._response_queue, self._cache, request)
                else:
                    result = _handle_model_request(self._cache, request)
                    self._response_queue.put(ok_response(request_id, result))
            except Exception as exc:
                self._response_queue.put(error_response(request_id, exc))


class LlamaServiceServer:
    """Dispatch request queue items to per-model actors."""

    def __init__(
        self,
        request_queue: MPQueue,
        response_queue: MPQueue,
        *,
        max_parallel_models: int = 2,
        cache: LlamaModelCache | None = None,
    ) -> None:
        self._request_queue = request_queue
        self._response_queue = response_queue
        self._max_parallel_models = max(1, int(max_parallel_models))
        self._cache = cache or LlamaModelCache()
        self._actors: dict[LlamaCacheKey, _Actor] = {}

    def serve_forever(self) -> None:
        while True:
            request = self._request_queue.get()
            if not isinstance(request, dict):
                continue
            request_id = str(request.get("request_id", ""))
            op = request.get("op")
            if op == "shutdown":
                self._response_queue.put(ok_response(request_id, {"shutdown": True}))
                self.stop()
                return
            try:
                key = model_cache_key(str(op), dict(request.get("model") or {}))
                actor = self._actor_for_key(key)
                actor.submit(request)
            except Exception as exc:
                self._response_queue.put(error_response(request_id, exc))

    def stop(self) -> None:
        for actor in self._actors.values():
            actor.stop()
        for actor in self._actors.values():
            actor.join()
        self._actors.clear()

    def _actor_for_key(self, key: LlamaCacheKey) -> _Actor:
        actor = self._actors.get(key)
        if actor is not None:
            return actor
        if len(self._actors) >= self._max_parallel_models:
            raise RuntimeError("llama max_parallel_models exceeded")
        actor = _Actor(self._response_queue, self._cache)
        self._actors[key] = actor
        return actor


def serve(
    request_queue: MPQueue,
    response_queue: MPQueue,
    *,
    max_parallel_models: int = 2,
) -> None:
    LlamaServiceServer(
        request_queue=request_queue,
        response_queue=response_queue,
        max_parallel_models=max_parallel_models,
    ).serve_forever()


def _handle_model_request(cache: LlamaModelCache, request: LlamaRequest) -> LlamaResponsePayload:
    op = str(request.get("op"))
    model = dict(request.get("model") or {})
    params = dict(request.get("params") or {})
    if op == "embedding_dimension":
        return cache.embedding_dimension(model)
    if op == "embed":
        texts = params.get("texts", [])
        if not isinstance(texts, list):
            raise ValueError("embed params.texts must be a list")
        return cache.embed(model, [str(text) for text in texts])
    if op == "complete":
        return cache.complete(
            model,
            str(params.get("prompt") or ""),
            max_tokens=int(params.get("max_tokens", 512)),
            temperature=float(params.get("temperature", 0.0)),
            stop=list(params.get("stop") or []),
        )
    if op == "rerank":
        documents = params.get("documents", [])
        if not isinstance(documents, list):
            raise ValueError("rerank params.documents must be a list")
        return cache.rerank(
            model,
            str(params.get("query") or ""),
            [str(document) for document in documents],
            instruction=str(params.get("instruction") or ""),
            max_length=int(params.get("max_length", 4096)),
        )
    raise ValueError(f"unsupported op: {op}")


def _handle_stream_request(response_queue: MPQueue, cache: LlamaModelCache, request: LlamaRequest) -> None:
    request_id = str(request.get("request_id", ""))
    params = dict(request.get("params") or {})
    for chunk in cache.complete_stream(
        dict(request.get("model") or {}),
        str(params.get("prompt") or ""),
        max_tokens=int(params.get("max_tokens", 512)),
        temperature=float(params.get("temperature", 0.0)),
        stop=list(params.get("stop") or []),
    ):
        response = ok_response(request_id, chunk)
        response["stream_done"] = False
        response_queue.put(response)
    response = ok_response(request_id, None)
    response["stream_done"] = True
    response_queue.put(response)
