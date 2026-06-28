from __future__ import annotations

import pytest

import agent_service.client as client_module
from agent_service.client import AgentClient
from rpg_core.agent.agent_types import StreamEventKind


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
        return FakeResponse({"ok": True, "commands": []})

    async def post(self, url: str, json=None):
        self.calls.append(("POST", url, {"json": json}))
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
    result = await AgentClient(base_url="http://agent").send("data/ws", "s1", "hello")
    assert result == {"reply": "ok"}
    assert FakeAsyncClient.calls[-1] == (
        "POST",
        "http://agent/chat/send",
        {"json": {"workspace": "data/ws", "session_id": "s1", "message": "hello"}},
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


async def test_client_stream_parses_sse_events() -> None:
    events = [
        event
        async for event in AgentClient(base_url="http://agent").stream("data/ws", "s1", "hello")
    ]
    assert [event.kind for event in events] == [StreamEventKind.TEXT, StreamEventKind.DONE]
    assert events[-1].content == "hi"
