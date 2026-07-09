from __future__ import annotations

import pytest

import agent_service.client as client_module
from agent_service.client import AgentClient
from rpg_core.agent.agent_types import StreamEventKind, TurnCancelStatus


class FakeResponse:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeAsyncClient:
    calls: list[tuple[str, str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params=None):
        self.calls.append(("GET", url, {"params": params}))
        if url.endswith("/chat/context-preview"):
            return FakeResponse({"formatVersion": "context-preview.v1", "sessionId": params["session_id"]})
        return FakeResponse({"ok": True, "commands": []})

    async def post(self, url: str, json=None):
        self.calls.append(("POST", url, {"json": json}))
        if url.endswith("/chat/stop"):
            return FakeResponse({
                "status": TurnCancelStatus.CANCELLED.value,
                "session_id": json["session_id"],
                "request_id": json.get("request_id"),
            })
        return FakeResponse({"reply": "ok"})

    def stream(self, method: str, url: str, json=None):
        self.calls.append((method, url, {"json": json}))
        return FakeStreamResponse([
            'data: {"kind": "text", "content": "hi"}',
            'data: {"kind": "done", "content": "hi"}',
        ])


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    FakeAsyncClient.calls.clear()
    monkeypatch.setattr(client_module.httpx, "AsyncClient", FakeAsyncClient)


async def test_client_send_uses_standard_payload() -> None:
    result = await AgentClient(base_url="http://agent").send("s1", "hello")
    assert result == {"reply": "ok"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/send",
        {"json": {"session_id": "s1", "message": "hello"}},
    )


async def test_client_reload_history_uses_standard_payload() -> None:
    result = await AgentClient(base_url="http://agent").reload_history("s1")
    assert result == {"reply": "ok"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/session/reload-history",
        {"json": {"session_id": "s1"}},
    )


async def test_client_bind_player_character_uses_standard_payload() -> None:
    result = await AgentClient(base_url="http://agent").bind_player_character("s1", 42)
    assert result == {"reply": "ok"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/session/player-character",
        {"json": {"session_id": "s1", "player_character_id": 42}},
    )


async def test_client_truncate_turn_uses_standard_payload() -> None:
    result = await AgentClient(base_url="http://agent").truncate_turn("s1", 2)
    assert result == {"reply": "ok"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/session/turns/2/truncate",
        {"json": {"session_id": "s1"}},
    )


async def test_client_session_crud_uses_agent_service_contract() -> None:
    client = AgentClient(base_url="http://agent")
    await client.ensure_session("ws", 1, session_id="s1", title="Default")
    await client.create_session("ws", 1, title="Alt")
    result = await client.list_sessions("ws", 1)

    assert result == {"ok": True, "commands": []}
    assert FakeAsyncClient.calls[-3:] == [
        (
            "POST",
            "http://agent/chat/session/ensure",
            {"json": {"workspace_id": "ws", "story_id": 1, "session_id": "s1", "title": "Default"}},
        ),
        ("POST", "http://agent/chat/sessions", {"json": {"workspace_id": "ws", "story_id": 1, "title": "Alt"}}),
        ("GET", "http://agent/chat/sessions", {"params": {"workspace_id": "ws", "story_id": 1}}),
    ]


async def test_client_get_context_preview_uses_agent_service_contract() -> None:
    result = await AgentClient(base_url="http://agent").get_context_preview("s1")

    assert result == {"formatVersion": "context-preview.v1", "sessionId": "s1"}
    assert FakeAsyncClient.calls[-1] == (
        "GET",
        "http://agent/chat/context-preview",
        {"params": {"session_id": "s1"}},
    )


async def test_client_stream_parses_sse_events() -> None:
    events = [
        event
        async for event in AgentClient(base_url="http://agent").stream("s1", "hello", request_id="req1")
    ]
    assert [event.kind for event in events] == [StreamEventKind.TEXT, StreamEventKind.DONE]
    assert events[-1].content == "hi"
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/stream",
        {"json": {"session_id": "s1", "message": "hello", "request_id": "req1"}},
    )


async def test_client_stream_ignores_invalid_event_status_code(monkeypatch) -> None:
    def stream_with_invalid_status_code(self, method: str, url: str, json=None):  # noqa: ANN001
        self.calls.append((method, url, {"json": json}))
        return FakeStreamResponse([
            'data: {"kind": "error", "content": "bad", "error_code": "TURN_METADATA_INVALID", "status_code": "not-a-number"}',
        ])

    monkeypatch.setattr(FakeAsyncClient, "stream", stream_with_invalid_status_code)

    events = [
        event
        async for event in AgentClient(base_url="http://agent").stream("s1", "hello")
    ]

    assert [event.kind for event in events] == [StreamEventKind.ERROR]
    assert events[0].content == "bad"
    assert events[0].error_code == "TURN_METADATA_INVALID"
    assert events[0].status_code is None


async def test_client_stop_uses_request_id_payload() -> None:
    result = await AgentClient(base_url="http://agent").stop("s1", request_id="req1")

    assert result == {"status": TurnCancelStatus.CANCELLED.value, "session_id": "s1", "request_id": "req1"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/stop",
        {"json": {"session_id": "s1", "request_id": "req1"}},
    )
