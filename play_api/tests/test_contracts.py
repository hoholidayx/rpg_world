from __future__ import annotations

from fastapi.testclient import TestClient

from play_api import agent_client
from play_api.main import app


class _FakeAgentClient:
    async def list_sessions(self, workspace: str, session_id: str) -> dict[str, object]:
        return {"sessions": ["demo_session"]}

    async def get_history(self, workspace: str, session_id: str) -> dict[str, object]:
        return {
            "history": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "reply"},
            ]
        }

    async def list_commands(self, workspace: str, session_id: str) -> dict[str, object]:
        return {"commands": [{"command": "/continue", "description": "继续叙事"}]}

    async def send(self, workspace: str, session_id: str, text: str) -> dict[str, object]:
        return {"reply": f"agent reply: {text}"}


def test_play_api_contracts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setattr(agent_client, "_client", _FakeAgentClient())
    client = TestClient(app)

    workspaces = client.get("/play-api/v1/workspaces")
    assert workspaces.status_code == 200
    assert {workspace["id"] for workspace in workspaces.json()} == {"demo_workspace"}

    sessions = client.get("/play-api/v1/sessions", params={"workspace": "demo_workspace"})
    assert sessions.status_code == 200
    assert sessions.json()[0]["workspace"] == "demo_workspace"

    scene = client.get(
        "/play-api/v1/scene/current",
        params={"workspace": "demo_workspace", "sessionId": "demo_session"},
    )
    assert scene.status_code == 200
    assert scene.json()["location"] is None

    commands = client.get("/play-api/v1/commands", params={"workspace": "demo_workspace"})
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"

    turn = client.post(
        "/play-api/v1/chat/turn",
        json={"workspace": "demo_workspace", "session_id": "demo_session", "text": "hello"},
    )
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert "hello" in turn.json()["reply"]
