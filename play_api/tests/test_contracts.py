from __future__ import annotations

from fastapi.testclient import TestClient

from play_api import agent_client
from play_api.main import app


class _FakeAgentClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def get_history(self, workspace: str, session_id: str) -> dict[str, object]:
        self.calls.append(("history", workspace, session_id))
        return {
            "history": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "reply"},
            ]
        }

    async def list_commands(self, workspace: str, session_id: str) -> dict[str, object]:
        self.calls.append(("commands", workspace, session_id))
        return {"commands": [{"command": "/continue", "description": "继续叙事"}]}

    async def send(self, workspace: str, session_id: str, text: str) -> dict[str, object]:
        self.calls.append(("send", workspace, session_id))
        return {"reply": f"agent reply: {text}"}


def test_play_api_contracts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    client = TestClient(app)
    demo_session_id = "s_forest001"

    workspaces = client.get("/play-api/v1/workspaces")
    assert workspaces.status_code == 200
    assert {workspace["id"] for workspace in workspaces.json()} == {"demo_workspace"}

    assert client.get("/play-api/v1/sessions").status_code == 422
    assert client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace"},
    ).status_code == 422
    assert client.get("/play-api/v1/sessions/missing/scene").status_code == 404
    assert client.post(f"/play-api/v1/sessions/{demo_session_id}/turn", json={}).status_code == 422

    sessions = client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace", "story_id": 1},
    )
    assert sessions.status_code == 200
    assert sessions.json()[0]["workspace"] == "demo_workspace"
    assert sessions.json()[0]["storyId"] == 1
    assert sessions.json()[0]["id"] == demo_session_id

    session = client.get(f"/play-api/v1/sessions/{demo_session_id}")
    assert session.status_code == 200
    assert session.json()["title"] == "北境森林主线"

    missing_story_sessions = client.get(
        "/play-api/v1/sessions",
        params={"workspace": "demo_workspace", "story_id": 999},
    )
    assert missing_story_sessions.status_code == 404

    created = client.post(
        "/play-api/v1/sessions",
        json={"workspaceId": "demo_workspace", "storyId": 1, "title": "新会话"},
    )
    assert created.status_code == 200
    assert created.json()["id"].startswith("s_")
    assert len(created.json()["id"]) == 12
    assert created.json()["id"][2:].isalnum()
    assert created.json()["title"] == "新会话"

    scene = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/scene",
    )
    assert scene.status_code == 200
    assert scene.json()["location"] is None

    commands = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/commands",
    )
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"

    turn = client.post(
        f"/play-api/v1/sessions/{demo_session_id}/turn",
        json={
            "text": "hello",
        },
    )
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert "hello" in turn.json()["reply"]
    assert ("commands", "demo_workspace", demo_session_id) in fake_agent.calls
    assert ("send", "demo_workspace", demo_session_id) in fake_agent.calls
