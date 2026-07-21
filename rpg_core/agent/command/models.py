"""Typed public contracts for slash-command registration and results."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rpg_data.model.session import Session
    from rpg_core.rp_modules.models import ModuleCommand
    from rpg_core.session import SessionManager
    from rpg_core.session.role import SessionPlayerCharacterBindResult
    from rpg_core.session.reset import SessionResetResult


class AgentCommandTarget(Protocol):
    """Stable internal surface available to slash-command handlers."""

    @property
    def session_id(self) -> str: ...

    @property
    def session_manager(self) -> SessionManager: ...

    async def reset_session(self) -> SessionResetResult: ...
    async def reload_rpg_context(self) -> None: ...
    async def reindex_memory(self) -> bool: ...
    def list_commands(self) -> list[CommandDef]: ...
    async def get_context_json(self, user_input: str = "", **kwargs) -> str: ...
    async def get_context_markdown(self, user_input: str = "", **kwargs) -> str: ...
    def render_role_bind_prompt(self, *, error: str = "") -> str: ...
    def bind_player_character_by_index(
        self,
        index: int,
        opening_index: int | None = None,
        *,
        story_opening_id: int | None = None,
    ): ...
    def list_story_sessions(self) -> list[Session]: ...
    def create_story_session(self, title: str) -> Session | None: ...
    def can_switch_session(self, session_id: str) -> bool: ...


@dataclass
class CommandDef:
    """Display metadata for one slash command."""

    name: str
    description: str
    detail: str


@dataclass
class CommandResult:
    """Typed result returned by slash-command dispatch."""

    reply: str = ""
    stats: dict[str, object] | None = None
    handled: bool = False
    role_bind_result: SessionPlayerCharacterBindResult | None = None
    active_session: str | None = None


HandlerFunc = Callable[[AgentCommandTarget, list[str]], Awaitable[str | CommandResult]]
CommandProvider = Callable[[], list["ModuleCommand"]]
