"""Server-local llama types plus compatibility DTO exports."""

from __future__ import annotations

from typing import TypeAlias

from commons.types import JsonObject, JsonScalar, JsonValue
from llm_client.types import DocumentScore, LLMResponse, LLMUsage, ProviderChunk

LlamaModelConfig: TypeAlias = JsonObject
LlamaRequestParams: TypeAlias = JsonObject
LlamaResponsePayload: TypeAlias = JsonValue
LlamaModelHandle: TypeAlias = object
LlamaLogits: TypeAlias = object
LlamaCacheKeyPart: TypeAlias = JsonScalar
LlamaCacheKey: TypeAlias = tuple[LlamaCacheKeyPart, ...]

__all__ = [
    "DocumentScore",
    "JsonValue",
    "LLMResponse",
    "LLMUsage",
    "ProviderChunk",
]
