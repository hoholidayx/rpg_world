"""Standalone RPG Agent — OpenAI-powered, fully decoupled from nanobot."""

from rpg_world.agent.agent import RPGGameAgent
from rpg_world.agent.prompt import PromptManager

__all__ = ["RPGGameAgent", "PromptManager"]
