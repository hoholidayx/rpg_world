"""BaseTool — abstract base for all agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract tool that can be registered with a ToolRegistry.

    Subclasses must define:
        - ``name`` (class-level or instance): unique identifier
        - ``description`` (class-level or instance): LLM-facing doc
        - ``parameters()`` → JSON Schema dict
        - ``execute(**kwargs)`` → result string
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Return the JSON Schema for this tool's arguments.

        The schema should follow the OpenAI function calling parameter
        format (type + properties + required).
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool and return a text result for the LLM."""
        ...

    def to_openai_schema(self) -> dict[str, Any]:
        """Return the full OpenAI-compatible tool schema dict."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }
