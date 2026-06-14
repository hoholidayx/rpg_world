from __future__ import annotations

from rpg_world.api.tests.conftest import FakeSessionManager


def test_workspace_contracts(client, monkeypatch):
    http = client["client"]

    res = http.get("/api/v1/workspaces")
    assert res.status_code == 200
    assert any(item["label"] == "默认（根工作区）" for item in res.json()["workspaces"])

    res = http.post("/api/v1/workspaces", json={"name": "alpha"})
    assert res.status_code == 200
    assert res.json()["name"] == "data/alpha"

    res = http.get("/api/v1/workspaces")
    assert any(item["name"] == "data/alpha" for item in res.json()["workspaces"])

    res = http.put("/api/v1/workspaces/data/alpha", json={"name": "beta"})
    assert res.status_code == 200
    assert res.json()["to"] == "data/beta"

    res = http.delete("/api/v1/workspaces/data/beta")
    assert res.status_code == 200
    assert res.json()["workspace"] == "data/beta"


def test_session_contracts(client):
    http = client["client"]

    res = http.post("/api/v1/workspaces/data/demo/sessions", json={"session_id": "s1"})
    assert res.status_code == 200

    res = http.get("/api/v1/workspaces/data/demo/sessions")
    assert res.status_code == 200
    assert res.json()["sessions"] == ["s1"]

    res = http.post(
        "/api/v1/workspaces/data/demo/sessions/s1/clone",
        json={"target_session_id": "s2"},
    )
    assert res.status_code == 200
    assert res.json()["target"] == "s2"

    res = http.delete("/api/v1/workspaces/data/demo/sessions/s1")
    assert res.status_code == 200
    assert res.json()["session_id"] == "s1"

    res = http.post("/api/v1/workspaces/data/demo/sessions", json={})
    assert res.status_code == 422


def test_character_lorebook_status_contracts(client):
    http = client["client"]
    character_mgr = client["character_mgr"]
    lorebook_mgr = client["lorebook_mgr"]
    status_mgr = client["status_mgr"]

    res = http.post("/api/v1/characters", json={"name": "Alice", "content": "hello"})
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Alice"

    res = http.get("/api/v1/characters/Alice")
    assert res.status_code == 200
    assert res.json()["name"] == "Alice"

    res = http.post(
        "/api/v1/characters/Alice/details",
        json={"name": "detail1", "content": "x", "tags": ["t1"]},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "detail1"

    res = http.get("/api/v1/characters/Alice/details")
    assert res.status_code == 200
    assert res.json()["details"][0]["name"] == "detail1"

    res = http.put(
        "/api/v1/characters/Alice/details/detail1",
        json={"name": "detail1", "content": "updated"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["content"] == "updated"

    res = http.delete("/api/v1/characters/Alice/details/detail1")
    assert res.status_code == 200

    res = http.post("/api/v1/lorebook/entries", json={"name": "Lore1", "content": "l"})
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "Lore1"

    res = http.get("/api/v1/lorebook/entries/Lore1")
    assert res.status_code == 200
    assert res.json()["name"] == "Lore1"

    res = http.post("/api/v1/status/types", json={"name": "全局状态"})
    assert res.status_code == 200

    res = http.post(
        "/api/v1/status/types/全局状态/tables",
        json={"name": "世界状态", "headers": ["a"], "rows": [["b"]]},
    )
    assert res.status_code == 200

    res = http.get("/api/v1/status/types/全局状态/tables/世界状态")
    assert res.status_code == 200
    assert res.json()["headers"] == ["a"]

    res = http.put(
        "/api/v1/status/types/全局状态/tables/世界状态",
        json={"headers": ["c"], "rows": [["d"]]},
    )
    assert res.status_code == 200
    assert res.json()["data"]["headers"] == ["c"]

    res = http.put(
        "/api/v1/status/types/全局状态/tables/世界状态/rename",
        json={"name": "新状态"},
    )
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "新状态"

    res = http.delete("/api/v1/status/types/全局状态")
    assert res.status_code == 200

    assert "Alice" in character_mgr.characters
    assert "Lore1" in lorebook_mgr.entries
    assert "全局状态" not in status_mgr.tables


def test_chat_contracts(client):
    http = client["client"]

    res = http.get("/api/v1/chat/history", params={"workspace": "data/demo", "session_id": "s1"})
    assert res.status_code == 200
    assert res.json()["history"][0]["content"] == "hello"

    res = http.post(
        "/api/v1/chat/send",
        params={"workspace": "data/demo"},
        json={"session_id": "s1", "message": "ping"},
    )
    assert res.status_code == 200
    assert res.json()["reply"] == "reply:ping"

    res = http.post(
        "/api/v1/chat/command",
        params={"workspace": "data/demo"},
        json={"session_id": "s1", "command": "/clear"},
    )
    assert res.status_code == 200
    assert res.json()["reply"] == "cmd:/clear"

    res = http.get(
        "/api/v1/chat/commands",
        params={"workspace": "data/demo", "session_id": "s1"},
    )
    assert res.status_code == 200
    assert res.json()["commands"][0]["command"] == "/clear"
    assert any(cmd["command"] == "/help" for cmd in res.json()["commands"])

    res = http.post(
        "/api/v1/chat/stream",
        params={"workspace": "data/demo"},
        json={"session_id": "s1", "message": "hello"},
    )
    assert res.status_code == 200
    assert "stream:hello" in res.text


def test_request_validation(client):
    http = client["client"]

    res = http.post("/api/v1/workspaces", json={})
    assert res.status_code == 422

    res = http.post("/api/v1/chat/send", params={"workspace": "data/demo"}, json={"session_id": "s1"})
    assert res.status_code == 422

    res = http.post("/api/v1/status/types", json={"unexpected": "x"})
    assert res.status_code == 422
