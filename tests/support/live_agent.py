"""Shared support for opt-in real-Provider Agent acceptance tests."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from llm_client.provider import RemoteLLMProvider
from llm_client.types import LLMResponse

if TYPE_CHECKING:
    from rpg_core.agent.agent import RPGGameAgent
    from rpg_core.agent.turn.runner import AgentReply


DEMO_WORKSPACE_ID = "demo_workspace"
DEMO_STORY_TITLE = "奥术学院 Demo"
DEMO_SESSION_ID = "s_academy01"
DEMO_PLAYER_CHARACTER_NAME = "Alice"


@dataclass
class RecordedLiveCall:
    """One real Provider chat call captured at the process boundary."""

    biz_key: str
    messages: list[dict[str, object]]
    tools: list[dict[str, object]] | None
    transport: str = "chat"
    provider_key: str = ""
    configured_model: str = ""
    response: dict[str, object] | None = None
    duration_ms: float = 0.0
    error_type: str | None = None
    error_message: str | None = None


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
    """Record real remote calls without changing their messages or schemas.

    Only the observable Provider contract is captured.  Authentication
    headers and private reasoning content never pass through this facade and
    therefore cannot enter the recording.
    """

    calls: list[RecordedLiveCall] = []
    original_chat = RemoteLLMProvider.chat
    original_chat_stream = RemoteLLMProvider.chat_stream

    async def recorded_chat(self, messages, tools=None):  # noqa: ANN001, ANN202
        call = RecordedLiveCall(
            biz_key=str(self.biz_key),
            messages=strip_private_reasoning(deepcopy(messages)),
            tools=deepcopy(tools),
            provider_key=str(self.provider_key),
            configured_model=str(self.get_default_model()),
        )
        calls.append(call)
        started = time.perf_counter()
        try:
            result = await original_chat(self, messages, tools)
        except Exception as exc:
            call.error_type = type(exc).__name__
            call.error_message = str(exc)
            raise
        finally:
            call.duration_ms = (time.perf_counter() - started) * 1000
        call.response = _recorded_response(result)
        return result

    async def recorded_chat_stream(  # noqa: ANN001, ANN202
        self,
        messages,
        tools=None,
    ):
        call = RecordedLiveCall(
            biz_key=str(self.biz_key),
            messages=strip_private_reasoning(deepcopy(messages)),
            tools=deepcopy(tools),
            transport="chat_stream",
            provider_key=str(self.provider_key),
            configured_model=str(self.get_default_model()),
        )
        calls.append(call)
        started = time.perf_counter()
        chunks: list[dict[str, object]] = []
        try:
            async for chunk in original_chat_stream(self, messages, tools):
                chunks.append({
                    "content": str(chunk.content or ""),
                    "toolCalls": deepcopy(chunk.tool_calls),
                    "finishReason": chunk.finish_reason,
                    "usage": asdict(chunk.usage) if chunk.usage is not None else None,
                    "model": chunk.model,
                    "requestId": chunk.request_id,
                    "created": chunk.created,
                })
                yield chunk
        except Exception as exc:
            call.error_type = type(exc).__name__
            call.error_message = str(exc)
            raise
        finally:
            call.duration_ms = (time.perf_counter() - started) * 1000
            call.response = {"chunks": chunks}

    monkeypatch.setattr(RemoteLLMProvider, "chat", recorded_chat)
    monkeypatch.setattr(
        RemoteLLMProvider,
        "chat_stream",
        recorded_chat_stream,
    )
    return calls


def _recorded_response(result: LLMResponse) -> dict[str, object]:
    return {
        "content": str(result.content or ""),
        "toolCalls": deepcopy(result.tool_calls),
        "finishReason": result.finish_reason,
        "usage": asdict(result.usage) if result.usage is not None else None,
        "model": result.model,
        "requestId": result.request_id,
        "created": result.created,
    }


def strip_private_reasoning(value):  # noqa: ANN001, ANN201
    """Remove Provider reasoning text while preserving observable messages."""

    if isinstance(value, dict):
        return {
            key: strip_private_reasoning(item)
            for key, item in value.items()
            if str(key).replace("_", "").replace("-", "").casefold()
            not in {"reasoningcontent", "thinkingcontent"}
        }
    if isinstance(value, list):
        return [strip_private_reasoning(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_private_reasoning(item) for item in value)
    return value


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
    "strip_private_reasoning",
]
