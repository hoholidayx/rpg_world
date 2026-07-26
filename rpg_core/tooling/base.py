"""Framework-free base contract shared by RPG tool providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


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
    def parameters(self) -> dict[str, object]:
        """Return the JSON Schema for this tool's arguments.

        The schema should follow the OpenAI function calling parameter
        format (type + properties + required).
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: object) -> str:
        """Run the tool and return a text result for the LLM."""
        ...

    def render_invalid_arguments_error(self, message: str) -> str | None:
        """Optionally render a tool-specific error for pre-dispatch JSON failures.

        The registry calls this hook when arguments are malformed JSON or do
        not decode to a named-argument object. Returning ``None`` preserves the
        registry's legacy plain-text error behavior.
        """
        del message
        return None

    def to_openai_schema(self) -> dict[str, object]:
        """Return the full OpenAI-compatible tool schema dict."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }
