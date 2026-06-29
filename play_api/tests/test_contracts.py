from __future__ import annotations

from fastapi.testclient import TestClient

from play_api import agent_client
from play_api.main import app
from play_api.delete_tokens import reset_delete_confirmation_tokens


class _FakeAgentClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def get_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("history", session_id))
        return {
            "history": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "reply"},
            ]
        }

    async def list_commands(self, session_id: str) -> dict[str, object]:
        self.calls.append(("commands", session_id))
        return {"commands": [{"command": "/continue", "description": "继续叙事"}]}

    async def send(self, session_id: str, text: str) -> dict[str, object]:
        self.calls.append(("send", session_id))
        return {"reply": f"agent reply: {text}"}


def test_play_api_contracts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    reset_delete_confirmation_tokens()
    client = TestClient(app)
    demo_session_id = "s_forest001"

    workspaces = client.get("/play-api/v1/workspaces")
    assert workspaces.status_code == 200
    assert {workspace["id"] for workspace in workspaces.json()} == {"demo_workspace"}

    stories = client.get("/play-api/v1/workspaces/demo_workspace/stories")
    assert stories.status_code == 200
    assert stories.json()[0]["title"] == "北境森林 Demo"
    assert client.get("/play-api/v1/workspaces/missing/stories").status_code == 404

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
    assert ("commands", demo_session_id) in fake_agent.calls
    assert ("send", demo_session_id) in fake_agent.calls

    lorebooks = client.get("/play-api/v1/workspaces/demo_workspace/lorebook-entries")
    assert lorebooks.status_code == 200
    assert {entry["name"] for entry in lorebooks.json()} >= {"炎心之木", "圆形封印祭坛"}
    assert lorebooks.json()[0]["workspaceId"] == "demo_workspace"
    assert isinstance(lorebooks.json()[0]["tags"], list)
    assert isinstance(lorebooks.json()[0]["metadata"], dict)
    assert client.get("/play-api/v1/workspaces/missing/lorebook-entries").status_code == 404

    new_entry = client.post(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries",
        json={
            "name": "潮汐信号",
            "content": "海岸线上古老的信号系统。",
            "description": "用于测试世界书管理接口。",
            "tags": ["规则", "组织"],
            "metadata": {"ui": {"displayVersion": "v1.0.0"}},
        },
    )
    assert new_entry.status_code == 200
    assert new_entry.json()["name"] == "潮汐信号"
    assert new_entry.json()["tags"] == ["规则", "组织"]
    assert new_entry.json()["metadata"]["ui"]["displayVersion"] == "v1.0.0"
    assert client.post(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries",
        json={"name": ""},
    ).status_code == 422

    patched = client.patch(
        f"/play-api/v1/workspaces/demo_workspace/lorebook-entries/{new_entry.json()['id']}",
        json={"description": "更新后的短描述", "tags": ["地点"]},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "更新后的短描述"
    assert patched.json()["tags"] == ["地点"]
    assert patched.json()["version"] == 2
    assert client.patch(
        f"/play-api/v1/workspaces/missing/lorebook-entries/{new_entry.json()['id']}",
        json={"name": "Nope"},
    ).status_code == 404

    story_lorebooks = client.get("/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries")
    assert story_lorebooks.status_code == 200
    assert story_lorebooks.json()[0]["mountId"] is not None
    assert client.get("/play-api/v1/workspaces/demo_workspace/stories/999/lorebook-entries").status_code == 404

    mounted = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries/{new_entry.json()['id']}/mount"
    )
    assert mounted.status_code == 200
    assert mounted.json()["name"] == "潮汐信号"
    assert mounted.json()["storyId"] == 1
    duplicate_mount = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries/{new_entry.json()['id']}/mount"
    )
    assert duplicate_mount.status_code == 200
    assert duplicate_mount.json()["mountId"] == mounted.json()["mountId"]

    removed = client.delete(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-mounts/{mounted.json()['mountId']}"
    )
    assert removed.status_code == 204
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-mounts/{mounted.json()['mountId']}"
    ).status_code == 404

    delete_target = client.post(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries",
        json={
            "name": "待删除条目",
            "content": "临时内容",
            "tags": ["tmp"],
        },
    )
    assert delete_target.status_code == 200
    delete_mount = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries/{delete_target.json()['id']}/mount"
    )
    assert delete_mount.status_code == 200
    deleted_entry = client.delete(
        f"/play-api/v1/workspaces/demo_workspace/lorebook-entries/{delete_target.json()['id']}"
    )
    assert deleted_entry.status_code == 204
    assert client.patch(
        f"/play-api/v1/workspaces/demo_workspace/lorebook-entries/{delete_target.json()['id']}",
        json={"name": "Gone"},
    ).status_code == 404

    ops_scan = client.get("/play-api/v1/ops/orphan-runtime")
    assert ops_scan.status_code == 200
    assert "orphanDirectories" in ops_scan.json()
    assert "unindexedStatusFiles" in ops_scan.json()

    ops_mount_entry = client.post(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries",
        json={"name": "运维挂载删除", "content": "ops"},
    )
    assert ops_mount_entry.status_code == 200
    ops_mount = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_mount_entry.json()['id']}/mount"
    )
    assert ops_mount.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-mounts/{ops_mount.json()['mountId']}"
    ).status_code == 409
    ops_mount_token = client.post(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-mounts/{ops_mount.json()['mountId']}/delete-token"
    )
    assert ops_mount_token.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-mounts/{ops_mount.json()['mountId']}",
        headers={"X-Delete-Confirm-Token": ops_mount_token.json()["token"]},
    ).status_code == 204
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-mounts/{ops_mount.json()['mountId']}",
        headers={"X-Delete-Confirm-Token": ops_mount_token.json()["token"]},
    ).status_code == 409

    ops_entry = client.post(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries",
        json={"name": "运维条目删除", "content": "ops"},
    )
    assert ops_entry.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/lorebook-entries/{ops_entry.json()['id']}"
    ).status_code == 409
    ops_entry_token = client.post(
        f"/play-api/v1/ops/workspaces/demo_workspace/lorebook-entries/{ops_entry.json()['id']}/delete-token"
    )
    assert ops_entry_token.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/lorebook-entries/{ops_entry.json()['id']}",
        headers={"X-Delete-Confirm-Token": ops_entry_token.json()["token"]},
    ).status_code == 204
    assert client.post(
        f"/play-api/v1/ops/workspaces/demo_workspace/lorebook-entries/{ops_entry.json()['id']}/delete-token"
    ).status_code == 404
