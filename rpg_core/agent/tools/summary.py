"""Main-Agent tools for searching and reading rendered Session summaries."""

from __future__ import annotations

import json

from rpg_core.agent.tools.summary_query import (
    SUMMARY_SEARCH_DEFAULT_LIMIT,
    SUMMARY_SEARCH_MAX_LIMIT,
    SUMMARY_SEARCH_MAX_TERM_CHARS,
    SUMMARY_SEARCH_MAX_TERMS,
    SummaryQueryService,
)
from rpg_core.tooling.base import BaseTool
from rpg_core.tooling.registry import ToolRegistry

SUMMARY_SEARCH_TOOL_NAME = "summary_search"
SUMMARY_READ_TOOL_NAME = "summary_read"
SENSITIVE_SUMMARY_TOOL_NAMES = frozenset({
    SUMMARY_SEARCH_TOOL_NAME,
    SUMMARY_READ_TOOL_NAME,
})


class SummaryToolSet:
    """Reusable access to the two derived-Summary lookup tools."""

    def __init__(self, service: SummaryQueryService) -> None:
        self._tools = (
            SummarySearchTool(service),
            SummaryReadTool(service),
        )
        registry = ToolRegistry()
        registry.register_all(list(self._tools))
        self._registry = registry

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        return self._tools

    @property
    def names(self) -> frozenset[str]:
        return SENSITIVE_SUMMARY_TOOL_NAMES

    def schemas(self) -> list[dict[str, object]]:
        return self._registry.get_openai_schemas()

    async def execute(self, name: str, arguments_json: str) -> str:
        if name not in self.names:
            raise PermissionError(f"{name!r} is not a Summary query tool")
        return await self._registry.execute(name, arguments_json)

    def register_into(self, registry: ToolRegistry) -> None:
        registry.register_all(list(self._tools))


class _SummaryTool(BaseTool):
    """Shared structured argument errors for sensitive Summary tools."""

    def render_invalid_arguments_error(self, message: str) -> str:
        return _json({
            "ok": False,
            "errorCode": "invalid_arguments",
            "message": str(message),
        })


class SummarySearchTool(_SummaryTool):
    """Find coarse-grained derived summaries and their source turn ranges."""

    name = SUMMARY_SEARCH_TOOL_NAME
    description = (
        "Search the current Session's derived Summary documents by literal terms "
        "across title, time, location, characters, and body text. Use this for "
        "fast coarse-grained orientation and inspect resolvedTurnRange to locate "
        "the underlying committed history. Then use summary_read for the full "
        "summary; use history_search/history_read when exact wording, actors, "
        "outcomes, or ambiguous facts must be verified."
    )

    def __init__(self, service: SummaryQueryService) -> None:
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
                        "maxLength": SUMMARY_SEARCH_MAX_TERM_CHARS,
                    },
                    "minItems": 1,
                    "maxItems": SUMMARY_SEARCH_MAX_TERMS,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of Summary matches to return.",
                    "minimum": 1,
                    "maximum": SUMMARY_SEARCH_MAX_LIMIT,
                    "default": SUMMARY_SEARCH_DEFAULT_LIMIT,
                },
            },
            "required": ["terms"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        terms: object = None,
        limit: object = SUMMARY_SEARCH_DEFAULT_LIMIT,
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


class SummaryReadTool(_SummaryTool):
    """Read one complete derived Summary and its source-location metadata."""

    name = SUMMARY_READ_TOOL_NAME
    description = (
        "Read one Summary returned by summary_search using summary_id='overall' "
        "or a decimal Batch ID string. Summary is secondary, derived evidence: "
        "it may guide a decision when unambiguous, but resolvedTurnRange should "
        "be used with history_search/history_read to verify exact or conflicting "
        "facts against committed SQL history."
    )

    def __init__(self, service: SummaryQueryService) -> None:
        self._service = service

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "summary_id": {
                    "type": "string",
                    "description": (
                        "The literal value 'overall' or a decimal Batch ID "
                        "returned by summary_search."
                    ),
                    "minLength": 1,
                    "maxLength": 32,
                },
            },
            "required": ["summary_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        summary_id: object = None,
        **unexpected: object,
    ) -> str:
        if unexpected:
            result = {
                "ok": False,
                "errorCode": "invalid_arguments",
                "message": "包含不支持的参数",
            }
        else:
            result = await self._service.read(summary_id=summary_id)
        return _json(result)


def _json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
