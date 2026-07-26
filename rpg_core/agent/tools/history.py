"""Main-Agent tools for searching and reading committed Session history."""

from __future__ import annotations

import json

from rpg_core.agent.tools.history_query import (
    HISTORY_READ_MAX_ADJACENT_TURNS,
    HISTORY_SEARCH_DEFAULT_LIMIT,
    HISTORY_SEARCH_MAX_LIMIT,
    HISTORY_SEARCH_MAX_TERM_CHARS,
    HISTORY_SEARCH_MAX_TERMS,
    HistoryQueryService,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry

HISTORY_SEARCH_TOOL_NAME = "history_search"
HISTORY_READ_TOOL_NAME = "history_read"
SENSITIVE_HISTORY_TOOL_NAMES = frozenset({
    HISTORY_SEARCH_TOOL_NAME,
    HISTORY_READ_TOOL_NAME,
})


class HistoryToolSet:
    """Narrow reusable access to the two committed-history query tools."""

    def __init__(self, service: HistoryQueryService) -> None:
        self._tools = (
            HistorySearchTool(service),
            HistoryReadTool(service),
        )
        registry = ToolRegistry()
        registry.register_all(list(self._tools))
        self._registry = registry

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        return self._tools

    @property
    def names(self) -> frozenset[str]:
        return SENSITIVE_HISTORY_TOOL_NAMES

    def schemas(self) -> list[dict[str, object]]:
        return self._registry.get_openai_schemas()

    async def execute(self, name: str, arguments_json: str) -> str:
        if name not in self.names:
            raise PermissionError(f"{name!r} is not a history query tool")
        return await self._registry.execute(name, arguments_json)

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register_all(list(self._tools))


class _HistoryTool(BaseTool):
    """Shared structured argument errors for sensitive history tools."""

    def render_invalid_arguments_error(self, message: str) -> str:
        return _json({
            "ok": False,
            "errorCode": "invalid_arguments",
            "message": str(message),
        })


class HistorySearchTool(_HistoryTool):
    """Find candidate turns in the current Session's committed history."""

    name = HISTORY_SEARCH_TOOL_NAME
    description = (
        "Search the current Session's committed conversation history for specific "
        "literal terms. This SQL main history is the source for exact events and "
        "wording. Use this first to locate candidate turn IDs, then call "
        "history_read to inspect the complete turn and its surrounding context. "
        "For coarse older-story orientation, summary_search may locate a useful "
        "Summary and source turn range first."
    )

    def __init__(self, service: HistoryQueryService) -> None:
        self._service = service

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "terms": {
                    "type": "array",
                    "description": (
                        "Specific names, places, events, or phrases to find. "
                        "Terms use OR matching."
                    ),
                    "items": {
                        "type": "string",
                        "maxLength": HISTORY_SEARCH_MAX_TERM_CHARS,
                    },
                    "minItems": 1,
                    "maxItems": HISTORY_SEARCH_MAX_TERMS,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of unique candidate turns to return.",
                    "minimum": 1,
                    "maximum": HISTORY_SEARCH_MAX_LIMIT,
                    "default": HISTORY_SEARCH_DEFAULT_LIMIT,
                },
            },
            "required": ["terms"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        terms: object = None,
        limit: object = HISTORY_SEARCH_DEFAULT_LIMIT,
        **unexpected: object,
    ) -> str:
        if unexpected:
            result = {
                "ok": False,
                "errorCode": "invalid_arguments",
                "message": "包含不支持的参数",
            }
        else:
            result = await self._service.search(terms=terms, limit=limit)
        return _json(result)


class HistoryReadTool(_HistoryTool):
    """Read one turn and a bounded window of neighboring committed turns."""

    name = HISTORY_READ_TOOL_NAME
    description = (
        "Read the complete messages for a turn returned by history_search, plus "
        "a small number of neighboring turns. Use history_search first unless "
        "the exact turn ID is already known. Prefer this committed SQL source over "
        "Summary whenever exact wording, actors, outcomes, or conflicting facts "
        "must be resolved."
    )

    def __init__(self, service: HistoryQueryService) -> None:
        self._service = service

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "turn_id": {
                    "type": "integer",
                    "description": "Positive turn ID to use as the context anchor.",
                    "minimum": 1,
                },
                "before_turns": {
                    "type": "integer",
                    "description": "Number of existing turns to include before the anchor.",
                    "minimum": 0,
                    "maximum": HISTORY_READ_MAX_ADJACENT_TURNS,
                    "default": 1,
                },
                "after_turns": {
                    "type": "integer",
                    "description": "Number of existing turns to include after the anchor.",
                    "minimum": 0,
                    "maximum": HISTORY_READ_MAX_ADJACENT_TURNS,
                    "default": 1,
                },
            },
            "required": ["turn_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        turn_id: object = None,
        before_turns: object = 1,
        after_turns: object = 1,
        **unexpected: object,
    ) -> str:
        if unexpected:
            result = {
                "ok": False,
                "errorCode": "invalid_arguments",
                "message": "包含不支持的参数",
            }
        else:
            result = await self._service.read(
                turn_id=turn_id,
                before_turns=before_turns,
                after_turns=after_turns,
            )
        return _json(result)


def _json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
