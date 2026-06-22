"""Shared type aliases for structured rpg_core payloads.

Keep these aliases narrow enough for JSON/YAML style data while avoiding
scattered ``object`` annotations on core data paths.
"""

from __future__ import annotations

from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = "JsonScalar | list[JsonValue] | dict[str, JsonValue]"
JsonObject: TypeAlias = dict[str, JsonValue]

ConfigValue: TypeAlias = JsonValue
ConfigDict: TypeAlias = JsonObject
Metadata: TypeAlias = JsonObject
DebugInfo: TypeAlias = JsonObject

LlamaModelConfig: TypeAlias = ConfigDict
LlamaRequestParams: TypeAlias = ConfigDict
LlamaResponsePayload: TypeAlias = JsonValue
LlamaModelHandle: TypeAlias = object
LlamaLogits: TypeAlias = object
LlamaCacheKeyPart: TypeAlias = JsonScalar
LlamaCacheKey: TypeAlias = tuple[LlamaCacheKeyPart, ...]
