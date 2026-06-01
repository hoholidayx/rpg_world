"""Chat interaction loop — encapsulates the LLM round-trip + tool-call loop.

Extracted as a standalone module so the loop logic is testable independently
and ``RPGGameAgent`` stays focused on orchestration.
"""

from __future__ import annotations

from typing import Any

from rpg_world.rpg_core.agent.openai_provider import OpenAIProvider
from rpg_world.rpg_core.agent.tools import ToolRegistry
from rpg_world.rpg_core.settings import settings


class ToolCallRecord:
    """One tool-call iteration — assistant message + corresponding tool results.

    Used to expose intermediate tool calls for UI display without persisting
    them to conversation history.
    """

    def __init__(
        self,
        assistant_message: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> None:
        self.assistant_message = assistant_message
        self.tool_results = tool_results


class AgentReply:
    """Structured result returned by ``send()`` / ``single_turn()``.

    Contains the final text reply *and* optional intermediate tool-call
    records for UI display.
    """

    def __init__(
        self,
        text: str,
        tool_records: list[ToolCallRecord] | None = None,
    ) -> None:
        self.text = text
        self.tool_records = tool_records

    def __str__(self) -> str:
        return self.text


async def run_chat_loop(
    provider: OpenAIProvider,
    tool_registry: ToolRegistry,
    messages: list[dict],
    schemas: list[dict] | None,
) -> tuple[str, list[ToolCallRecord]]:
    """Chat interaction loop — LLM call + optional tool-call loop.

    Parameters
    ----------
    provider:
        The LLM provider to call for chat completions.
    tool_registry:
        Registered tool instances — used to dispatch ``tool_calls`` by name.
    messages:
        The working message buffer (e.g. 5-layer RPG context).  Assistant
        tool-call messages and tool results are appended here for subsequent
        LLM rounds.  **Not** the agent's persistent ``_history``.
    schemas:
        OpenAI tool/function schemas passed to the LLM on each round, or
        ``None`` to skip tool calling entirely.

    Returns
    -------
    ``(final_reply_text, tool_call_records)`` where ``tool_call_records`` is
    a list of ``ToolCallRecord`` objects describing each tool-call iteration.
    """
    max_calls = settings.max_tool_calls
    tool_call_count = 0
    records: list[ToolCallRecord] = []

    while tool_call_count < max_calls:
        result = await provider.chat(messages, tools=schemas)

        if not result.get("tool_calls"):
            return result["content"], records

        tool_call_count += 1

        # Assistant tool-call message
        asst_msg: dict[str, Any] = {
            "role": "assistant",
            "content": result["content"],
            "tool_calls": result["tool_calls"],
        }
        messages.append(asst_msg)

        # Execute tools and collect results
        tool_results: list[dict[str, Any]] = []
        for tc in result["tool_calls"]:
            tool_result = await tool_registry.execute(
                tc["function"]["name"],
                tc["function"]["arguments"],
            )
            tool_msg: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(tool_result),
            }
            messages.append(tool_msg)
            tool_results.append(tool_msg)

        records.append(ToolCallRecord(asst_msg, tool_results))

    return f"[已达到工具调用上限 {max_calls} 次，终止循环]", records
