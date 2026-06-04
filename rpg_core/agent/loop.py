"""Chat interaction loop — encapsulates the LLM round-trip + tool-call loop.

Extracted as a standalone module so the loop logic is testable independently
and ``RPGGameAgent`` stays focused on orchestration.
"""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from rpg_world.rpg_core.agent.base_provider import LLMProvider
from rpg_world.rpg_core.agent.tools import ToolRegistry
from rpg_world.rpg_core.agent.types import CallRecord, LLMResponse, TurnStats
from rpg_world.rpg_core.settings import settings

_TAG = "[MainAgent]"


class ToolCallRecord:
    """One tool-call iteration — assistant message + corresponding tool results.

    Used to expose intermediate tool calls for UI display without persisting
    them to conversation history.

    Parameters
    ----------
    assistant_message:
        The assistant message dict (role, content, tool_calls).
    tool_results:
        List of tool result message dicts.
    usage:
        Token usage for this LLM round, if available.
    model:
        The model name used for this round.
    duration_ms:
        Wall-clock duration of this LLM call in milliseconds.
    reasoning_content:
        Reasoning/thinking content from the model, if present.
    """

    def __init__(
        self,
        assistant_message: dict[str, Any],
        tool_results: list[dict[str, Any]],
        usage: Any = None,
        model: str | None = None,
        duration_ms: float = 0.0,
        reasoning_content: str | None = None,
    ) -> None:
        self.assistant_message = assistant_message
        self.tool_results = tool_results
        self.usage = usage
        self.model = model
        self.duration_ms = duration_ms
        self.reasoning_content = reasoning_content


class AgentReply:
    """Structured result returned by ``send()`` / ``single_turn()``.

    Contains the final text reply and optional intermediate records
    (tool calls, status sub-agent, and aggregated stats).
    """

    def __init__(
        self,
        text: str,
        tool_records: list[ToolCallRecord] | None = None,
        status_sub_agent_records: list[dict[str, Any]] | None = None,
        stats: TurnStats | None = None,
    ) -> None:
        self.text = text
        self.tool_records = tool_records
        self.status_sub_agent_records = status_sub_agent_records
        self.stats = stats

    def __str__(self) -> str:
        return self.text


async def run_chat_loop(
    provider: LLMProvider,
    tool_registry: ToolRegistry,
    messages: list[dict],
    schemas: list[dict] | None,
    turn_stats: TurnStats | None = None,
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
    turn_stats:
        Optional ``TurnStats`` accumulator.  If provided, each LLM call is
        recorded for aggregated reporting.

    Returns
    -------
    ``(final_reply_text, tool_call_records)`` where ``tool_call_records`` is
    a list of ``ToolCallRecord`` objects describing each tool-call iteration.
    """
    max_calls = settings.max_tool_calls
    tool_call_count = 0
    records: list[ToolCallRecord] = []

    while tool_call_count < max_calls:
        # ── LLM call with timing ──────────────────────────────────
        t0 = time.monotonic()
        result = await provider.chat(messages, tools=schemas)
        duration_ms = (time.monotonic() - t0) * 1000

        # Ensure result is an LLMResponse
        if not isinstance(result, LLMResponse):
            # Handle legacy dict responses gracefully
            content = result.get("content", "")
            tool_calls = result.get("tool_calls")
            if not tool_calls:
                return content, records
            tool_call_count += 1
            asst_msg: dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
            messages.append(asst_msg)
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                tool_result = await tool_registry.execute(name, args)
                tool_msg: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(tool_result),
                }
                messages.append(tool_msg)
                tool_results.append(tool_msg)
            records.append(ToolCallRecord(asst_msg, tool_results))
            continue

        # ── Record call in turn_stats ──────────────────────────────
        if turn_stats is not None:
            turn_stats.add_call(CallRecord(
                source="chat_loop",
                model=result.model or provider.get_default_model(),
                usage=result.usage,
                duration_ms=duration_ms,
                reasoning_content=result.reasoning_content,
            ))

        if not result.tool_calls:
            return result.content, records

        tool_call_count += 1
        if settings.verbose_logging:
            tool_names = [tc["function"]["name"] for tc in result.tool_calls]
            logger.info(
                _TAG + " round {}: {} tool call(s): {}",
                tool_call_count, len(tool_names), tool_names,
            )

        # Assistant tool-call message
        asst_msg = {
            "role": "assistant",
            "content": result.content,
            "tool_calls": result.tool_calls,
        }
        messages.append(asst_msg)

        # Execute tools and collect results
        tool_results = []
        for tc in result.tool_calls:
            name = tc["function"]["name"]
            args = tc["function"]["arguments"]
            if settings.verbose_logging:
                logger.info(_TAG + " calling tool: {}({})", name, args)

            tool_result = await tool_registry.execute(name, args)

            if settings.verbose_logging:
                logger.info(
                    _TAG + " tool result {}: {}",
                    name, str(tool_result)[:200],
                )

            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(tool_result),
            }
            messages.append(tool_msg)
            tool_results.append(tool_msg)

        records.append(ToolCallRecord(
            asst_msg,
            tool_results,
            usage=result.usage,
            model=result.model,
            duration_ms=duration_ms,
            reasoning_content=result.reasoning_content,
        ))

    msg = f"[已达到工具调用上限 {max_calls} 次，终止循环]"
    logger.warning(_TAG + " {}", msg)
    return msg, records
