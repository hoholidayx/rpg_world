"""Stable slash-command API."""

from rpg_core.agent.command.dispatcher import CommandDispatcher
from rpg_core.agent.command.handlers import format_command_help
from rpg_core.agent.command.models import (
    AgentCommandTarget,
    CommandDef,
    CommandResult,
)

__all__ = [
    "AgentCommandTarget",
    "CommandDef",
    "CommandDispatcher",
    "CommandResult",
    "format_command_help",
]
