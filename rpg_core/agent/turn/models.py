"""Immutable inputs and small data carriers for one Agent turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rpg_core.agent.agent_types import TurnStats
    from rpg_core.agent.loop import ToolCallRecord
    from rpg_core.agent.tools import ToolRegistry
    from rpg_core.context.rpg_context import Message, PersistentMemoryFact
    from rpg_core.main_llm import MainLLMSelection
    from rpg_core.rp_modules.models import RPModuleSelectionSnapshot


class TurnMode(StrEnum):
    """Supported semantic modes for a normal text turn."""

    IC = "ic"
    OOC = "ooc"
    GM = "gm"


DEFAULT_TURN_MODE = TurnMode.IC


def normalize_turn_mode(value: object) -> TurnMode:
    normalized = str(value or "").strip().lower() or DEFAULT_TURN_MODE.value
    try:
        return TurnMode(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid turn mode: {normalized}") from exc


@dataclass(frozen=True)
class TurnRequest:
    """Caller-owned input. It never contains resolved services or mutable state."""

    text: str
    mode: TurnMode = DEFAULT_TURN_MODE
    narrative_style_id: int | None = None
    request_id: str | None = None

    @classmethod
    def create(
        cls,
        text: str,
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
        request_id: str | None = None,
    ) -> "TurnRequest":
        style_id = int(narrative_style_id) if narrative_style_id is not None else None
        if style_id is not None and style_id <= 0:
            raise ValueError("narrative_style_id must be a positive integer or null")
        return cls(
            text=str(text or ""),
            mode=normalize_turn_mode(mode),
            narrative_style_id=style_id,
            request_id=str(request_id or "").strip() or None,
        )


@dataclass(frozen=True)
class TurnExecutionPolicy:
    """Mode-derived switches applied consistently across the whole turn."""

    run_status_preflight: bool
    expose_state_tools: bool
    expose_rp_modules: bool
    apply_narrative_style: bool

    @classmethod
    def for_mode(cls, mode: TurnMode) -> "TurnExecutionPolicy":
        if mode is TurnMode.OOC:
            return cls(
                run_status_preflight=False,
                expose_state_tools=False,
                expose_rp_modules=False,
                apply_narrative_style=False,
            )
        return cls(
            run_status_preflight=True,
            expose_state_tools=True,
            expose_rp_modules=True,
            apply_narrative_style=True,
        )


@dataclass(frozen=True)
class TurnPlayerCharacterSnapshot:
    """Session player identity frozen before Context gates and LLM work."""

    character_id: int
    mount_id: int
    story_id: int
    name: str


@dataclass(frozen=True)
class TurnExecutionSnapshot:
    """Resolved mode, style, player identity, and Story prompt for one turn."""

    request: TurnRequest
    mode_prompt: str
    narrative_style_id: int | None
    narrative_style_name: str
    narrative_style_prompt: str
    policy: TurnExecutionPolicy
    player_character: TurnPlayerCharacterSnapshot | None = None
    rendered_story_prompt: str = ""


@dataclass(frozen=True)
class TurnExecutionPlan:
    """All immutable selections resolved before a transaction begins."""

    execution: TurnExecutionSnapshot
    main_llm: "MainLLMSelection"
    rp_modules: "RPModuleSelectionSnapshot"
    persistent_memory: tuple["PersistentMemoryFact", ...] = ()

    @property
    def request(self) -> TurnRequest:
        return self.execution.request


@dataclass(frozen=True)
class TurnBypass:
    """A command or guard reply that completes before turn allocation."""

    text: str
    reason: str


@dataclass(frozen=True)
class PreparedTurn:
    """Context and tools prepared against one transaction scratch."""

    messages: list["Message"]
    tool_registry: "ToolRegistry | None"
    schemas: list[dict] | None


@dataclass(frozen=True)
class TurnResult:
    """Protocol-neutral result produced after a successful commit."""

    text: str
    tool_records: list["ToolCallRecord"]
    status_sub_agent_records: list[dict[str, object]] | None
    stats: "TurnStats"
    committed_turn_id: int
