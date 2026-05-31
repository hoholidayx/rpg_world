"""Standalone RPG Agent — OpenAI-powered, fully decoupled from nanobot."""

from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.agent.prompt import PromptManager

__all__ = ["RPGGameAgent", "PromptManager"]
