from __future__ import annotations

import json

from play_api.sse_protocol import (
    AgentEventKind,
    PLAY_SSE_SCHEMA_VERSION,
    PlaySSEStream,
    PlaySSEType,
    agent_event_kind,
    map_agent_event,
)


def _decode_sse(data: str) -> dict[str, object]:
    assert data.startswith("data:")
    payload = json.loads(data.removeprefix("data:").strip())
    assert isinstance(payload, dict)
    return payload


def test_play_sse_stream_encodes_stable_envelope_and_event_ids() -> None:
    stream = PlaySSEStream("s1", turn_id="turn_test")

    first = _decode_sse(stream.turn_started(mode="ic"))
    second = _decode_sse(stream.agent_event({"kind": AgentEventKind.TEXT.value, "content": "hello"}) or "")

    assert first == {
        "schemaVersion": PLAY_SSE_SCHEMA_VERSION,
        "eventId": 1,
        "sessionId": "s1",
        "turnId": "turn_test",
        "type": PlaySSEType.TURN_STARTED.value,
        "payload": {"mode": "ic"},
    }
    assert second["eventId"] == 2
    assert second["type"] == PlaySSEType.TEXT_DELTA.value
    assert second["payload"] == {"text": "hello"}


def test_map_agent_event_accepts_agent_field_variants() -> None:
    thinking = map_agent_event({
        "kind": AgentEventKind.THINKING.value,
        "content": "checking state",
    })
    tool_call = map_agent_event({
        "kind": AgentEventKind.TOOL_CALL.value,
        "toolName": "roll",
        "tool_arguments": "1d20",
        "toolCallId": "call_1",
    })
    tool_result = map_agent_event({
        "type": AgentEventKind.TOOL_RESULT.value,
        "tool_name": "roll",
        "toolResult": "18",
        "tool_result_preview": "18",
    })

    assert thinking is not None
    assert thinking.type is PlaySSEType.THINKING_DELTA
    assert thinking.payload == {"text": "checking state"}
    assert tool_call is not None
    assert tool_call.type is PlaySSEType.TOOL_CALL
    assert tool_call.payload == {
        "toolName": "roll",
        "toolArguments": "1d20",
        "toolCallId": "call_1",
    }
    assert tool_result is not None
    assert tool_result.type is PlaySSEType.TOOL_RESULT
    assert tool_result.payload == {
        "toolName": "roll",
        "toolResult": "18",
        "resultPreview": "18",
    }


def test_turn_completed_payload_keeps_text_and_committed_turn() -> None:
    mapped = map_agent_event({
        "kind": AgentEventKind.DONE.value,
        "content": "reply",
        "finish_reason": "stop",
        "committed_turn_id": 7,
        "active_session": "s2",
    })

    assert mapped is not None
    assert mapped.type is PlaySSEType.TURN_COMPLETED
    assert mapped.payload == {
        "text": "reply",
        "finishReason": "stop",
        "committedTurnId": 7,
        "activeSession": "s2",
    }


def test_error_payload_preserves_business_error_code_without_http_status() -> None:
    mapped = map_agent_event({
        "kind": AgentEventKind.ERROR.value,
        "content": "bad",
        "error_code": "TURN_METADATA_INVALID",
        "status_code": 409,
    })

    assert mapped is not None
    assert mapped.type is PlaySSEType.ERROR
    assert mapped.payload == {
        "message": "bad",
        "errorCode": "TURN_METADATA_INVALID",
    }


def test_play_stream_error_keeps_business_code_separate_from_status() -> None:
    stream = PlaySSEStream("s1", turn_id="turn_test")

    event = _decode_sse(
        stream.error(
            "LLM service connection failed",
            status_code=503,
            error_code="LLM_SERVICE_UNAVAILABLE",
        )
    )

    assert event["payload"] == {
        "message": "LLM service connection failed",
        "statusCode": 503,
        "errorCode": "LLM_SERVICE_UNAVAILABLE",
    }


def test_unknown_agent_event_is_ignored() -> None:
    assert agent_event_kind({"kind": "round_start"}) == "round_start"
    assert map_agent_event({"kind": "round_start"}) is None
