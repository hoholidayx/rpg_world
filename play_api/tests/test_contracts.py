from __future__ import annotations

from fastapi.testclient import TestClient

from play_api import agent_client
from play_api.main import app


class _FakeAgentClient:
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

    assert client.get("/play-api/v1/sessions").status_code == 422
    assert client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace"},
    ).status_code == 422
    assert client.get(
        "/play-api/v1/scene/current",
        params={"workspace": "demo_workspace", "session_id": "demo_forest_main"},
    ).status_code == 422
    assert client.get("/play-api/v1/commands").status_code == 422
    assert client.post("/play-api/v1/chat/turn", json={"text": "hello"}).status_code == 422

    sessions = client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace", "story_id": 1},
    )
    assert sessions.status_code == 200
    assert sessions.json()[0]["workspace"] == "demo_workspace"
    assert sessions.json()[0]["storyId"] == 1

    missing_story_sessions = client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace", "story_id": 999},
    )
    assert missing_story_sessions.status_code == 404

    scene = client.get(
        "/play-api/v1/scene/current",
        params={"workspace": "demo_workspace", "story_id": 1, "session_id": "demo_forest_main"},
    )
    assert scene.status_code == 200
    assert scene.json()["location"] is None

    missing_session = client.get(
        "/play-api/v1/scene/current",
        params={"workspace": "demo_workspace", "story_id": 2, "session_id": "demo_forest_main"},
    )
    assert missing_session.status_code == 404

    commands = client.get(
        "/play-api/v1/commands",
        params={"workspace": "demo_workspace", "story_id": 1, "session_id": "demo_forest_main"},
    )
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"

    turn = client.post(
        "/play-api/v1/chat/turn",
        json={
            "workspace": "demo_workspace",
            "story_id": 1,
            "session_id": "demo_forest_main",
            "text": "hello",
        },
    )
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert "hello" in turn.json()["reply"]
