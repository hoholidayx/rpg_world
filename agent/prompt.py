"""Prompt manager — provides system prompts for the standalone RPG agent."""

from __future__ import annotations


class PromptManager:
    """Manages system prompts for the RPG agent.

    Usage::

        pm = PromptManager(world_name="Nanobot Realm")
        system_prompt = pm.system_prompt
    """

    def __init__(self, world_name: str = "Nanobot Realm") -> None:
        self._world_name = world_name

    @property
    def system_prompt(self) -> str:
        """Return the base system prompt for the RPG game master."""
        return (
            f"You are the game master of {self._world_name}, an immersive RPG world. "
            "Respond in character, advance the story, and keep the narrative engaging. "
            "Use the provided world context, character cards, and status information "
            "to inform your responses."
        )
