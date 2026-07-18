"""Server-local llama runtime type aliases."""

from __future__ import annotations

from typing import TypeAlias

from commons.types import JsonObject, JsonScalar, JsonValue

LlamaModelConfig: TypeAlias = JsonObject
LlamaRequestParams: TypeAlias = JsonObject
LlamaResponsePayload: TypeAlias = JsonValue
LlamaModelHandle: TypeAlias = object
LlamaLogits: TypeAlias = object
LlamaCacheKeyPart: TypeAlias = JsonScalar
LlamaCacheKey: TypeAlias = tuple[LlamaCacheKeyPart, ...]
