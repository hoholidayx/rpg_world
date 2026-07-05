"""Stable SSE protocol helpers for Play WebUI streams."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4


PLAY_SSE_SCHEMA_VERSION = "play_sse_v1"
SSE_MEDIA_TYPE = "text/event-stream"
TURN_ID_PREFIX = "turn"
TURN_ID_RANDOM_HEX_LENGTH = 12
DEFAULT_AGENT_ERROR_MESSAGE = "Agent stream failed"


class PlaySSEType(StrEnum):
    TURN_STARTED = "turn_started"
    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TURN_COMPLETED = "turn_completed"
    ERROR = "error"


class AgentEventKind(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class PlaySSEMapping:
    type: PlaySSEType
    payload: dict[str, object]


class PlaySSEStream:
    """Stateful encoder for one Play API SSE response."""

    def __init__(self, session_id: str, *, turn_id: str | None = None) -> None:
        self.session_id = session_id
        self.turn_id = turn_id or new_stream_turn_id(session_id)
        self._event_id = 0

    def turn_started(self, *, mode: str) -> str:
        return self.encode(PlaySSEType.TURN_STARTED, {"mode": mode})

    def agent_event(self, event: dict[str, object]) -> str | None:
        mapping = map_agent_event(event)
        if mapping is None:
            return None
        return self.encode(mapping.type, mapping.payload)

    def error(self, message: str, *, status_code: int | None = None) -> str:
        payload: dict[str, object] = {"message": message}
        if status_code is not None:
            payload["statusCode"] = status_code
        return self.encode(PlaySSEType.ERROR, payload)

    def encode(self, type_: PlaySSEType, payload: dict[str, object] | None = None) -> str:
        self._event_id += 1
        event = {
            "schemaVersion": PLAY_SSE_SCHEMA_VERSION,
            "eventId": self._event_id,
            "sessionId": self.session_id,
            "turnId": self.turn_id,
            "type": type_.value,
            "payload": payload or {},
        }
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def new_stream_turn_id(session_id: str) -> str:
    random_suffix = uuid4().hex[:TURN_ID_RANDOM_HEX_LENGTH]
    return f"{TURN_ID_PREFIX}_{session_id}_{random_suffix}"


def agent_event_kind(event: dict[str, object]) -> str:
    return str(event.get("kind") or event.get("type") or "").lower()


def map_agent_event(event: dict[str, object]) -> PlaySSEMapping | None:
    kind = agent_event_kind(event)
    if kind == AgentEventKind.TEXT:
        return PlaySSEMapping(PlaySSEType.TEXT_DELTA, {"text": str(event.get("content") or "")})
    if kind == AgentEventKind.TOOL_CALL:
        return PlaySSEMapping(PlaySSEType.TOOL_CALL, _tool_call_payload(event))
    if kind == AgentEventKind.TOOL_RESULT:
        return PlaySSEMapping(PlaySSEType.TOOL_RESULT, _tool_result_payload(event))
    if kind == AgentEventKind.DONE:
        return PlaySSEMapping(PlaySSEType.TURN_COMPLETED, _turn_completed_payload(event))
    if kind == AgentEventKind.ERROR:
        message = str(event.get("content") or DEFAULT_AGENT_ERROR_MESSAGE)
        return PlaySSEMapping(PlaySSEType.ERROR, {"message": message})
    return None


def _tool_call_payload(event: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    tool_name = _camel_or_snake(event, "toolName", "tool_name")
    if tool_name:
        payload["toolName"] = str(tool_name)
    tool_arguments = _camel_or_snake(event, "toolArguments", "tool_arguments")
    if tool_arguments is not None:
        payload["toolArguments"] = str(tool_arguments)
    tool_call_id = _camel_or_snake(event, "toolCallId", "tool_call_id")
    if tool_call_id:
        payload["toolCallId"] = str(tool_call_id)
    return payload


def _tool_result_payload(event: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    tool_name = _camel_or_snake(event, "toolName", "tool_name")
    if tool_name:
        payload["toolName"] = str(tool_name)
    tool_result = _camel_or_snake(event, "toolResult", "tool_result")
    if tool_result is not None:
        payload["toolResult"] = str(tool_result)
    result_preview = _camel_or_snake(event, "resultPreview", "tool_result_preview")
    if result_preview is not None:
        payload["resultPreview"] = str(result_preview)
    return payload


def _turn_completed_payload(event: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "text": str(event.get("content") or ""),
    }
    usage = event.get("usage")
    if isinstance(usage, dict):
        payload["usage"] = usage
    model = event.get("model")
    if model:
        payload["model"] = str(model)
    finish_reason = _camel_or_snake(event, "finishReason", "finish_reason")
    if finish_reason:
        payload["finishReason"] = str(finish_reason)
    duration_ms = _camel_or_snake(event, "durationMs", "duration_ms")
    if duration_ms is not None:
        payload["durationMs"] = duration_ms
    return payload


def _camel_or_snake(event: dict[str, object], camel_key: str, snake_key: str) -> object | None:
    value = event.get(camel_key)
    if value is not None:
        return value
    return event.get(snake_key)
