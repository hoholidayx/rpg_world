"""Dictionary protocol for the llama worker process."""

from __future__ import annotations

from typing import Literal, TypedDict

from rpg_world.rpg_core.common_types import LlamaModelConfig, LlamaRequestParams, LlamaResponsePayload

LlamaOperation = Literal["embedding_dimension", "embed", "complete", "complete_stream", "rerank", "shutdown"]


class LlamaRequest(TypedDict, total=False):
    request_id: str
    op: LlamaOperation
    model: LlamaModelConfig
    params: LlamaRequestParams
    timeout_ms: int


class LlamaError(TypedDict):
    type: str
    message: str


class LlamaResponse(TypedDict, total=False):
    request_id: str
    ok: bool
    result: LlamaResponsePayload
    error: LlamaError
    stream_done: bool


def make_request(
    request_id: str,
    op: LlamaOperation,
    *,
    model: LlamaModelConfig | None = None,
    params: LlamaRequestParams | None = None,
    timeout_ms: int = 60000,
) -> LlamaRequest:
    return {
        "request_id": request_id,
        "op": op,
        "model": model or {},
        "params": params or {},
        "timeout_ms": timeout_ms,
    }


def ok_response(request_id: str, result: LlamaResponsePayload = None) -> LlamaResponse:
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
