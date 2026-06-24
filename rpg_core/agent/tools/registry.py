"""ToolRegistry — register, list schemas, and dispatch tool calls."""

from __future__ import annotations

import json

from rpg_core.agent.tools.base import BaseTool


class ToolRegistry:
    """Registry for agent tools.

    Usage::

        registry = ToolRegistry()
        registry.register(ReadFileTool(workspace_root))
        registry.register_all([ListFilesTool(...), GrepTool(...)])

        schemas = registry.get_openai_schemas()   # → list[dict]
        result = await registry.execute("read_file", '{"path": "foo.txt"}')
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a single tool instance."""
        if not tool.name:
            raise ValueError(f"Tool {type(tool).__name__} has empty name")
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def register_all(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for t in tools:
            self.register(t)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def get_openai_schemas(self) -> list[dict[str, object]]:
        """Return the full list of OpenAI tool-call schemas."""
        return [t.to_openai_schema() for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, name: str, arguments_json: str) -> str:
        """Execute a tool by name.

        Args:
            name: Tool name (must be registered).
            arguments_json: JSON-encoded named arguments.

        Returns:
            Text result suitable for the LLM to read.
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool {name!r}"

        try:
            kwargs = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            return f"Error: invalid arguments JSON for {name!r}: {exc}"

        try:
            return await tool.execute(**kwargs)
        except Exception as exc:
            return f"Error executing {name!r}: {exc}"

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
