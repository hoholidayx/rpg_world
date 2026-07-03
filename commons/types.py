"""Shared type aliases for JSON/YAML-like payloads."""

from __future__ import annotations

from typing import TypeAlias

from typing_extensions import TypeAliasType

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonScalar: TypeAlias = JsonPrimitive
JsonValue = TypeAliasType("JsonValue", JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"])
JsonObject: TypeAlias = dict[str, JsonValue]

YamlPrimitive: TypeAlias = JsonPrimitive
YamlScalar: TypeAlias = YamlPrimitive
YamlValue = TypeAliasType("YamlValue", YamlPrimitive | list["YamlValue"] | dict[str, "YamlValue"])
YamlMapping: TypeAlias = dict[str, YamlValue]

ConfigValue: TypeAlias = JsonValue
ConfigDict: TypeAlias = JsonObject
Metadata: TypeAlias = JsonObject
DebugInfo: TypeAlias = JsonObject
