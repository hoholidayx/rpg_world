"""Dictionary protocol for the llama worker process."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

LlamaOperation = Literal["embedding_dimension", "embed", "complete", "complete_stream", "rerank", "shutdown"]


class LlamaRequest(TypedDict, total=False):
    request_id: str
    op: LlamaOperation
    model: dict[str, Any]
    params: dict[str, Any]
    timeout_ms: int


class LlamaError(TypedDict):
    type: str
    message: str


class LlamaResponse(TypedDict, total=False):
    request_id: str
    ok: bool
    result: Any
    error: LlamaError
    stream_done: bool


def make_request(
    request_id: str,
    op: LlamaOperation,
    *,
    model: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout_ms: int = 60000,
) -> LlamaRequest:
    return {
        "request_id": request_id,
        "op": op,
        "model": model or {},
        "params": params or {},
        "timeout_ms": timeout_ms,
    }


def ok_response(request_id: str, result: Any = None) -> LlamaResponse:
    return {"request_id": request_id, "ok": True, "result": result}


def error_response(request_id: str, exc: BaseException | str) -> LlamaResponse:
    if isinstance(exc, BaseException):
        return {
            "request_id": request_id,
            "ok": False,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    return {
        "request_id": request_id,
        "ok": False,
        "error": {"type": "LlamaServiceError", "message": str(exc)},
    }
