from __future__ import annotations

from fastapi.testclient import TestClient

from play_api.main import app
from play_api import agent_client as play_agent_client


class FakeAgentClient:
    async def list_commands(self, workspace: str, session_id: str):
        return {"commands": [{"command": "/continue", "description": "继续当前剧情"}]}

    async def send(self, workspace: str, session_id: str, text: str):
        return {"reply": f"reply:{text}"}

    async def list_sessions(self, workspace: str, session_id: str):
        return {"sessions": [session_id], "active_session": session_id}


def test_play_api_contracts(monkeypatch) -> None:
    monkeypatch.setattr(play_agent_client, "get_agent_client", lambda: FakeAgentClient())
    client = TestClient(app)

    workspaces = client.get("/play-api/v1/workspaces")
    assert workspaces.status_code == 200
    assert workspaces.json()[0]["id"] == "default"

    sessions = client.get("/play-api/v1/sessions", params={"workspace": "default"})
    assert sessions.status_code == 200
    assert sessions.json()[0]["workspace"] == "default"

    scene = client.get(
        "/play-api/v1/scene/current",
        params={"workspace": "default", "sessionId": "demo_session"},
    )
    assert scene.status_code == 200
    assert scene.json()["location"] == "未设定地点"

    commands = client.get("/play-api/v1/commands", params={"workspace": "default"})
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"

    turn = client.post("/play-api/v1/chat/turn", json={"text": "hello"})
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert turn.json()["reply"] == "reply:hello"
