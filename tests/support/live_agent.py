"""Shared support for opt-in real-Provider Agent acceptance tests."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from llm_client.provider import RemoteLLMProvider

if TYPE_CHECKING:
    from rpg_core.agent.agent import RPGGameAgent
    from rpg_core.agent.turn.runner import AgentReply


DEMO_WORKSPACE_ID = "demo_workspace"
DEMO_STORY_TITLE = "奥术学院 Demo"
DEMO_SESSION_ID = "s_academy01"
DEMO_PLAYER_CHARACTER_NAME = "Alice"


@dataclass(frozen=True)
class RecordedLiveCall:
    """One real Provider chat call captured at the process boundary."""

    biz_key: str
    messages: list[dict[str, object]]
    tools: list[dict[str, object]] | None


@dataclass(frozen=True)
class LiveDemoHarness:
    """Initialized Agent over the canonical migration-0002 academy Session."""

    agent: RPGGameAgent
    workspace_id: str
    story_id: int
    session_id: str
    player_character_name: str
    calls: list[RecordedLiveCall]


@dataclass(frozen=True)
class ToolInvocation:
    """One main-Agent tool invocation paired with its returned result."""

    name: str
    call_id: str
    arguments: dict[str, object]
    result: object


def install_live_call_recorder(
    monkeypatch,
) -> list[RecordedLiveCall]:
    """Record real remote calls without changing their messages or schemas."""

    calls: list[RecordedLiveCall] = []
    original_chat = RemoteLLMProvider.chat

    async def recorded_chat(self, messages, tools=None):  # noqa: ANN001, ANN202
        calls.append(
            RecordedLiveCall(
                biz_key=str(self.biz_key),
                messages=deepcopy(messages),
                tools=deepcopy(tools),
            )
        )
        return await original_chat(self, messages, tools)

    monkeypatch.setattr(RemoteLLMProvider, "chat", recorded_chat)
    return calls


def main_tool_invocations(
    reply: AgentReply,
    tool_name: str | None = None,
) -> list[ToolInvocation]:
    """Decode main-Agent tool records while preserving plain-text results."""

    invocations: list[ToolInvocation] = []
    for record in reply.tool_records or []:
        results_by_call_id = {
            str(result.get("tool_call_id", "")): result
            for result in record.tool_results
        }
        raw_calls = record.assistant_message.get("tool_calls", [])
        for tool_call in raw_calls if isinstance(raw_calls, list) else []:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if not isinstance(function, dict):
                continue
            name = str(function.get("name", ""))
            if tool_name is not None and name != tool_name:
                continue
            call_id = str(tool_call.get("id", ""))
            tool_result = results_by_call_id.get(call_id)
            if tool_result is None:
                raise AssertionError(f"missing result for tool call {call_id!r}")
            arguments = _json_object(function.get("arguments"), "tool arguments")
            raw_result = str(tool_result.get("content", ""))
            invocations.append(
                ToolInvocation(
                    name=name,
                    call_id=call_id,
                    arguments=arguments,
                    result=_decode_json_or_text(raw_result),
                )
            )
    return invocations


def main_tool_call_names(reply: AgentReply) -> list[str]:
    return [invocation.name for invocation in main_tool_invocations(reply)]


def status_tool_records(
    reply: AgentReply,
    tool_name: str | None = None,
) -> list[dict[str, object]]:
    """Return copied StatusSubAgent records, optionally filtered by tool name."""

    return [
        dict(record)
        for record in reply.status_sub_agent_records or []
        if tool_name is None or record.get("tool_name") == tool_name
    ]


def status_record_arguments(record: dict[str, object]) -> dict[str, object]:
    return _json_object(record.get("arguments"), "status tool arguments")


def status_record_result(record: dict[str, object]) -> object:
    return _decode_json_or_text(str(record.get("result", "")))


def provider_tool_names(call: RecordedLiveCall) -> set[str]:
    """Extract function names from the exact schemas sent to a Provider."""

    names: set[str] = set()
    for schema in call.tools or []:
        function = schema.get("function")
        if isinstance(function, dict):
            name = str(function.get("name", ""))
            if name:
                names.add(name)
    return names


def first_call_with_tools(
    calls: list[RecordedLiveCall],
    *,
    biz_key: str,
    required_names: set[str],
) -> RecordedLiveCall:
    """Find the first actual Provider call containing a required schema set."""

    for call in calls:
        if (
            call.biz_key == biz_key
            and required_names <= provider_tool_names(call)
        ):
            return call
    raise AssertionError(
        f"no {biz_key!r} Provider call exposed tools {sorted(required_names)!r}"
    )


def status_snapshot(gateway, session_id: str) -> dict[str, dict[str, str]]:
    """Read committed Scene and normal status values by stable table/key names."""

    return {
        table.name: {
            row.key: str(row.value or "")
            for row in table.document.rows
        }
        for table in gateway.status.list_tables(session_id)
    }


def persisted_turn(gateway, session_id: str, turn_id: int):
    return [
        row
        for row in gateway.messages.list(session_id)
        if row.turn_id == turn_id
    ]


def _json_object(value: object, label: str) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label} must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise AssertionError(f"{label} must be a JSON object")
    return decoded


def _decode_json_or_text(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


__all__ = [
    "DEMO_PLAYER_CHARACTER_NAME",
    "DEMO_SESSION_ID",
    "DEMO_STORY_TITLE",
    "DEMO_WORKSPACE_ID",
    "LiveDemoHarness",
    "RecordedLiveCall",
    "ToolInvocation",
    "first_call_with_tools",
    "install_live_call_recorder",
    "main_tool_call_names",
    "main_tool_invocations",
    "persisted_turn",
    "status_record_arguments",
    "status_record_result",
    "status_snapshot",
    "status_tool_records",
]
