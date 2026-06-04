"""Standalone RPG Agent — OpenAI-powered, fully decoupled from nanobot.

Sub-agents now live in ``rpg_world.rpg_core.agent.sub_agents`` for a
dedicated package with shared ``BaseSubAgent`` infrastructure.
Old import paths still work — see ``sub_agents/`` for new exports.
"""

from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.agent.prompt import PromptManager
from rpg_world.rpg_core.agent.sub_agents import (
    MemoryAgentResult,
    MemorySubAgent,
    StatusSubAgent,
)

__all__ = [
    "RPGGameAgent",
    "MemoryAgentResult",
    "MemorySubAgent",
    "PromptManager",
    "StatusSubAgent",
]
