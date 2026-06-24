from __future__ import annotations

from fastapi.testclient import TestClient

from play_api.main import app


def test_play_api_contracts() -> None:
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
    assert scene.json()["location"] == "雾港钟楼码头"

    commands = client.get("/play-api/v1/commands", params={"workspace": "default"})
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"

    turn = client.post("/play-api/v1/chat/turn", json={"text": "hello"})
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert "hello" in turn.json()["reply"]
