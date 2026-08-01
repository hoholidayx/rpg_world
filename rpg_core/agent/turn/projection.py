"""Turn-local projection for main-Agent provider rounds."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from rpg_core.context.models import (
    Message,
    RPGContext,
    RPModuleRuntimePlacement,
    RPModuleRuntimeSection,
    RPModulesLayer,
)
from rpg_core.tooling.registry import ToolRegistry


class MainRoundProjection:
    """Re-project scratch-sensitive RP sections and tools for every LLM round.

    The initially prepared Context remains the source for all stable layers.
    Only RP Module runtime sections are re-evaluated after a tool transcript
    exists, so a staged Narrative Outcome can replace its pending contract
    without changing the Fixed Layer or earlier cache prefix.
    """

    def __init__(
        self,
        *,
        base_context: RPGContext,
        runtime_sections: Callable[[], Sequence[RPModuleRuntimeSection]],
        tool_registry: ToolRegistry | None,
        schemas: Callable[[], list[dict] | None],
    ) -> None:
        self._base_context = base_context
        self._runtime_sections = runtime_sections
        self._tool_registry = tool_registry
        self._schemas = schemas

    def messages_for_round(
        self,
        transcript: Sequence[Message],
    ) -> list[Message]:
        context = self._base_context
        if transcript:
            system_sections, user_suffixes = _partition_runtime_sections(
                self._runtime_sections()
            )
            context = replace(
                self._base_context,
                rp_modules=RPModulesLayer(sections=system_sections),
                user_message=replace(
                    self._base_context.user_message,
                    runtime_suffixes=user_suffixes,
                ),
            )
        return [*context.to_message_objects(), *transcript]

    def schemas_for_round(self) -> list[dict] | None:
        return self._schemas()

    async def execute_tool(self, name: str, arguments: str) -> str:
        if self._tool_registry is None or name not in self._allowed_tool_names():
            return f"Error: unknown tool {name!r}"
        return await self._tool_registry.execute(name, arguments)

    def _allowed_tool_names(self) -> frozenset[str]:
        return frozenset(
            str(schema.get("function", {}).get("name", ""))
            for schema in (self.schemas_for_round() or [])
            if isinstance(schema.get("function"), dict)
        )


def _partition_runtime_sections(
    sections: Sequence[RPModuleRuntimeSection],
) -> tuple[list[RPModuleRuntimeSection], list[RPModuleRuntimeSection]]:
    system_sections: list[RPModuleRuntimeSection] = []
    user_suffixes: list[RPModuleRuntimeSection] = []
    for section in sections:
        placement = RPModuleRuntimePlacement(section.placement)
        if placement is RPModuleRuntimePlacement.RP_MODULES:
            system_sections.append(section)
        elif placement is RPModuleRuntimePlacement.USER_SUFFIX:
            user_suffixes.append(section)
    return system_sections, user_suffixes


__all__ = ["MainRoundProjection"]
