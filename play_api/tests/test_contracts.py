from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent_service.client import AgentClientError
from play_api import agent_client
from play_api.main import app
from play_api.delete_tokens import reset_delete_confirmation_tokens
from play_api.routers.sessions import _agent_call, _turns_from_history
from rpg_core.session.turn_metadata import InvalidTurnMetadataError
from rpg_data.services import get_data_service_gateway


def test_history_fallback_groups_legacy_messages_by_user_anchor() -> None:
    turns = _turns_from_history(
        [
            {"messageId": 1, "role": "system", "content": "preface"},
            {"messageId": 2, "role": "user", "content": "u1"},
            {"messageId": 3, "role": "assistant", "content": "a1"},
            {"messageId": 4, "role": "user", "content": "u2"},
            {"messageId": 5, "role": "assistant", "content": "a2"},
        ],
        source="agent_internal",
    )

    assert [turn.turn_id for turn in turns] == [1, 2]
    assert [[message.content for message in turn.messages] for turn in turns] == [
        ["preface", "u1", "a1"],
        ["u2", "a2"],
    ]
    assert [[message.seq_in_turn for message in turn.messages] for turn in turns] == [[1, 2, 3], [1, 2]]


def test_history_fallback_groups_legacy_messages_by_pairs_without_user_anchor() -> None:
    turns = _turns_from_history(
        [
            {"messageId": 1, "role": "assistant", "content": "a1"},
            {"messageId": 2, "role": "tool", "content": "tool1"},
            {"messageId": 3, "role": "system", "content": "sys1"},
        ],
        source="agent_internal",
    )

    assert [turn.turn_id for turn in turns] == [1, 2]
    assert [[message.content for message in turn.messages] for turn in turns] == [["a1", "tool1"], ["sys1"]]
    assert [[message.seq_in_turn for message in turn.messages] for turn in turns] == [[1, 2], [1]]


def test_history_api_source_rejects_invalid_turn_metadata() -> None:
    with pytest.raises(InvalidTurnMetadataError, match=r"history\[1\]"):
        _turns_from_history(
            [
                {"messageId": 1, "turnId": 1, "seqInTurn": 1, "role": "user", "content": "u1"},
                {"messageId": 2, "turnId": 1, "seqInTurn": 0, "role": "assistant", "content": "a1"},
                {"messageId": 3, "turnId": 2, "seqInTurn": 1, "role": "user", "content": "u2"},
            ],
            source="api",
        )


def test_history_api_source_rejects_missing_turn_metadata() -> None:
    with pytest.raises(InvalidTurnMetadataError, match=r"history\[0\]"):
        _turns_from_history(
            [
                {"messageId": 1, "role": "user", "content": "u1"},
                {"messageId": 2, "turnId": 1, "seqInTurn": 2, "role": "assistant", "content": "a1"},
            ],
            source="api",
        )


async def test_agent_call_preserves_agent_validation_status() -> None:
    async def fail() -> None:
        raise AgentClientError("invalid turn", status_code=422)

    with pytest.raises(HTTPException) as exc_info:
        await _agent_call(fail())

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "invalid turn"


class _FakeAgentClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def get_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("history", session_id))
        return {
            "history": [
                {
                    "messageId": 1,
                    "turnId": 1,
                    "seqInTurn": 1,
                    "role": "user",
                    "content": "hello",
                    "metadata": {"speakerName": "Bob"},
                    "createdAt": "2026-01-01T00:00:00",
                },
                {
                    "messageId": 2,
                    "turnId": 1,
                    "seqInTurn": 2,
                    "role": "assistant",
                    "content": "reply",
                    "metadata": {"speakerName": "Narrator"},
                    "createdAt": "2026-01-01T00:00:01",
                },
            ]
        }

    async def list_commands(self, session_id: str) -> dict[str, object]:
        self.calls.append(("commands", session_id))
        return {
            "commands": [
                {"command": "/continue", "description": "继续叙事"},
                {"command": "/check_dc", "description": "手动 DC 检定"},
            ]
        }

    async def get_context_preview(self, session_id: str) -> dict[str, object]:
        self.calls.append(("context-preview", session_id))
        return {
            "formatVersion": "context-preview.v1",
            "sessionId": session_id,
            "hotHistoryRounds": 5,
            "totals": {
                "layerCount": 1,
                "activeLayers": 1,
                "tokenCount": 3,
                "messageCount": 1,
            },
            "layers": [
                {
                    "index": 0,
                    "type": "fixed_layer",
                    "role": "system",
                    "status": "active",
                    "charCount": 12,
                    "tokenCount": 3,
                    "description": "fixed",
                    "content": "## Fixed",
                }
            ],
            "messages": [{"role": "system", "content": "## Fixed"}],
        }

    async def send(self, session_id: str, text: str) -> dict[str, object]:
        self.calls.append(("send", session_id))
        return {"reply": f"agent reply: {text}"}

    async def reload_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("reload-history", session_id))
        return {"status": "reloaded"}

    async def bind_player_character(self, session_id: str, player_character_id: int) -> dict[str, object]:
        self.calls.append(("bind-player-character", session_id, str(player_character_id)))
        try:
            get_data_service_gateway().session_roles.bind_player_character(session_id, player_character_id)
        except ValueError as exc:
            raise AgentClientError(str(exc), status_code=422) from exc
        except FileNotFoundError as exc:
            raise AgentClientError(str(exc), status_code=404) from exc
        return {"status": "bound", "session_id": session_id, "player_character_id": player_character_id}

    async def truncate_turn(self, session_id: str, turn_id: int) -> dict[str, object]:
        self.calls.append(("truncate-turn", session_id, str(turn_id)))
        return {
            "status": "truncated",
            "session_id": session_id,
            "turn_id": turn_id,
            "removed": 2,
            "agent_sync_status": "synced",
        }

    async def delete_message(self, session_id: str, message_id: int) -> dict[str, object]:
        self.calls.append(("delete-message", session_id, str(message_id)))
        return {"status": "deleted"}


class _InvalidHistoryAgentClient(_FakeAgentClient):
    async def get_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("history", session_id))
        return {
            "history": [
                {"messageId": 1, "turnId": 1, "seqInTurn": 1, "role": "user", "content": "hello"},
                {"messageId": 2, "turnId": 1, "seqInTurn": 0, "role": "assistant", "content": "reply"},
            ]
        }


def test_history_endpoint_rejects_invalid_turn_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _InvalidHistoryAgentClient())
    reset_delete_confirmation_tokens()
    client = TestClient(app)

    response = client.get("/play-api/v1/sessions/s_forest001/history")

    assert response.status_code == 409
    assert "history[1]" in response.json()["detail"]


def test_play_api_contracts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
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
    assert stories.json()[0]["storyPrompt"] == "用于验证 workspace、story、session、角色卡与 lorebook 挂载关系的演示故事。"
    assert "北境森林的霜雾" in stories.json()[0]["firstMessage"]
    assert "description" not in stories.json()[0]
    assert client.get("/play-api/v1/workspaces/missing/stories").status_code == 404
    new_story = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories",
        json={
            "title": "雾港钟楼",
            "summary": "潮湿港口的失踪案。",
            "storyPrompt": "固定故事提示词，仅存储展示。",
            "firstMessage": "你听见远处钟声。",
        },
    )
    assert new_story.status_code == 200
    assert new_story.json()["workspace"] == "demo_workspace"
    assert new_story.json()["title"] == "雾港钟楼"
    assert new_story.json()["summary"] == "潮湿港口的失踪案。"
    assert new_story.json()["storyPrompt"] == "固定故事提示词，仅存储展示。"
    assert new_story.json()["firstMessage"] == "你听见远处钟声。"
    assert client.post(
        "/play-api/v1/workspaces/demo_workspace/stories",
        json={"title": " "},
    ).status_code == 422
    assert client.post(
        "/play-api/v1/workspaces/missing/stories",
        json={"title": "不存在 workspace 的故事"},
    ).status_code == 404
    patched_story = client.patch(
        f"/play-api/v1/workspaces/demo_workspace/stories/{new_story.json()['id']}",
        json={
            "summary": "钟楼与沉船旧账。",
            "storyPrompt": "更新后的固定故事提示词。",
        },
    )
    assert patched_story.status_code == 200
    assert patched_story.json()["title"] == "雾港钟楼"
    assert patched_story.json()["summary"] == "钟楼与沉船旧账。"
    assert patched_story.json()["storyPrompt"] == "更新后的固定故事提示词。"
    assert patched_story.json()["firstMessage"] == "你听见远处钟声。"
    assert client.patch(
        f"/play-api/v1/workspaces/demo_workspace/stories/{new_story.json()['id']}",
        json={"title": ""},
    ).status_code == 422
    assert client.patch(
        "/play-api/v1/workspaces/demo_workspace/stories/99999",
        json={"summary": "missing"},
    ).status_code == 404

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
    assert sessions.json()[0]["playerCharacterStatus"] == "bound"
    assert sessions.json()[0]["playerCharacter"]["name"] == "Bob"

    session = client.get(f"/play-api/v1/sessions/{demo_session_id}")
    assert session.status_code == 200
    assert session.json()["title"] == "北境森林主线"
    assert session.json()["playerCharacterStatus"] == "bound"
    assert session.json()["playerCharacter"]["name"] == "Bob"

    history = client.get(f"/play-api/v1/sessions/{demo_session_id}/history")
    assert history.status_code == 200
    assert history.json()[0]["turnId"] == 1
    assert "canRetry" not in history.json()[0]
    assert history.json()[0]["messages"][0]["messageId"] == 1
    assert history.json()[0]["messages"][0]["metadata"]["speakerName"] == "Bob"

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
    assert created.json()["playerCharacterStatus"] == "invalid"
    assert created.json()["playerCharacter"] is None

    scene = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/scene",
    )
    assert scene.status_code == 200
    assert scene.json()["location"] == "北境森林·石林·圆形封印祭坛"
    assert scene.json()["time"] == "第 1 年 1 月 1 日 8 时 30 分"
    assert scene.json()["presentCharacters"] == ["Bob", "Alice"]

    commands = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/commands",
    )
    assert commands.status_code == 200
    assert commands.json()[0]["name"] == "/continue"
    assert commands.json()[1]["name"] == "/check_dc"

    context_preview = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/context-preview",
    )
    assert context_preview.status_code == 200
    assert context_preview.json()["formatVersion"] == "context-preview.v1"
    assert context_preview.json()["sessionId"] == demo_session_id
    assert context_preview.json()["totals"]["tokenCount"] == 3
    assert context_preview.json()["layers"][0]["content"] == "## Fixed"
    assert context_preview.json()["messages"][0]["content"] == "## Fixed"

    turn = client.post(
        f"/play-api/v1/sessions/{demo_session_id}/turn",
        json={
            "text": "hello",
        },
    )
    assert turn.status_code == 200
    assert turn.json()["status"] == "completed"
    assert "hello" in turn.json()["reply"]

    truncate = client.post(f"/play-api/v1/sessions/{demo_session_id}/turns/2/truncate")
    assert truncate.status_code == 200
    assert truncate.json()["status"] == "truncated"
    assert truncate.json()["turnId"] == 2
    assert truncate.json()["removed"] == 2

    delete_message = client.delete(f"/play-api/v1/sessions/{demo_session_id}/messages/1")
    assert delete_message.status_code == 200
    assert delete_message.json()["status"] == "deleted"

    assert ("commands", demo_session_id) in fake_agent.calls
    assert ("context-preview", demo_session_id) in fake_agent.calls
    assert ("send", demo_session_id) in fake_agent.calls
    assert ("truncate-turn", demo_session_id, "2") in fake_agent.calls
    assert ("delete-message", demo_session_id, "1") in fake_agent.calls

    characters = client.get("/play-api/v1/workspaces/demo_workspace/characters")
    assert characters.status_code == 200
    assert {character["name"] for character in characters.json()} >= {"Bob", "Alice"}
    assert characters.json()[0]["workspaceId"] == "demo_workspace"
    assert isinstance(characters.json()[0]["details"], list)
    assert isinstance(characters.json()[0]["metadata"], dict)
    assert client.get("/play-api/v1/workspaces/missing/characters").status_code == 404

    new_character = client.post(
        "/play-api/v1/workspaces/demo_workspace/characters",
        json={
            "name": "守夜人伊凡",
            "personality": "谨慎，疲惫但可靠",
            "content": "灯塔旧守夜人，知道潮汐与失火名单。",
            "metadata": {"ui": {"displayVersion": "v1.0.0", "roleLabel": "NPC"}},
        },
    )
    assert new_character.status_code == 200
    assert new_character.json()["name"] == "守夜人伊凡"
    assert new_character.json()["personality"] == "谨慎，疲惫但可靠"
    assert new_character.json()["metadata"]["ui"]["roleLabel"] == "NPC"
    assert client.post(
        "/play-api/v1/workspaces/demo_workspace/characters",
        json={"name": ""},
    ).status_code == 422

    patched_character = client.patch(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}",
        json={"personality": "谨慎，口风很紧", "metadata": {"ui": {"displayVersion": "v1.0.1"}}},
    )
    assert patched_character.status_code == 200
    assert patched_character.json()["personality"] == "谨慎，口风很紧"
    assert patched_character.json()["version"] == 2
    assert client.patch(
        f"/play-api/v1/workspaces/missing/characters/{new_character.json()['id']}",
        json={"name": "Nope"},
    ).status_code == 404

    new_detail = client.post(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}/details",
        json={
            "name": "禁忌话题",
            "content": "拒绝谈论灯塔失火当夜。",
            "tags": ["秘密", "话题"],
            "sortOrder": 10,
        },
    )
    assert new_detail.status_code == 200
    assert new_detail.json()["name"] == "禁忌话题"
    assert new_detail.json()["tags"] == ["秘密", "话题"]
    assert new_detail.json()["sortOrder"] == 10

    patched_detail = client.patch(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}/details/{new_detail.json()['id']}",
        json={"content": "只在午夜后透露线索。", "tags": ["秘密"], "sortOrder": 20},
    )
    assert patched_detail.status_code == 200
    assert patched_detail.json()["content"] == "只在午夜后透露线索。"
    assert patched_detail.json()["tags"] == ["秘密"]
    assert patched_detail.json()["sortOrder"] == 20
    assert patched_detail.json()["version"] == 2
    assert client.patch(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}/details/99999",
        json={"name": "Nope"},
    ).status_code == 404

    story_characters = client.get("/play-api/v1/workspaces/demo_workspace/stories/1/characters")
    assert story_characters.status_code == 200
    assert story_characters.json()[0]["mountId"] is not None
    assert client.get("/play-api/v1/workspaces/demo_workspace/stories/999/characters").status_code == 404
    bob = next(character for character in story_characters.json() if character["name"] == "Bob")
    bound_created = client.patch(
        f"/play-api/v1/sessions/{created.json()['id']}/player-character",
        json={"playerCharacterId": bob["id"]},
    )
    assert bound_created.status_code == 200
    assert bound_created.json()["playerCharacterStatus"] == "bound"
    assert bound_created.json()["playerCharacter"]["name"] == "Bob"
    assert ("bind-player-character", created.json()["id"], str(bob["id"])) in agent_client.get_agent_client().calls
    invalid_bind = client.patch(
        f"/play-api/v1/sessions/{created.json()['id']}/player-character",
        json={"playerCharacterId": 99999},
    )
    assert invalid_bind.status_code == 422

    mounted_character = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/characters/{new_character.json()['id']}/mount"
    )
    assert mounted_character.status_code == 200
    assert mounted_character.json()["name"] == "守夜人伊凡"
    assert mounted_character.json()["storyId"] == 1
    duplicate_character_mount = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/characters/{new_character.json()['id']}/mount"
    )
    assert duplicate_character_mount.status_code == 200
    assert duplicate_character_mount.json()["mountId"] == mounted_character.json()["mountId"]

    removed_character_mount = client.delete(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/character-mounts/{mounted_character.json()['mountId']}"
    )
    assert removed_character_mount.status_code == 204
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/character-mounts/{mounted_character.json()['mountId']}"
    ).status_code == 404

    delete_character_target = client.post(
        "/play-api/v1/workspaces/demo_workspace/characters",
        json={"name": "待删除角色", "content": "临时角色"},
    )
    assert delete_character_target.status_code == 200
    delete_character_detail = client.post(
        f"/play-api/v1/workspaces/demo_workspace/characters/{delete_character_target.json()['id']}/details",
        json={"name": "临时细节", "content": "tmp"},
    )
    assert delete_character_detail.status_code == 200
    delete_character_mount = client.post(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/characters/{delete_character_target.json()['id']}/mount"
    )
    assert delete_character_mount.status_code == 200
    deleted_character = client.delete(
        f"/play-api/v1/workspaces/demo_workspace/characters/{delete_character_target.json()['id']}"
    )
    assert deleted_character.status_code == 204
    assert client.patch(
        f"/play-api/v1/workspaces/demo_workspace/characters/{delete_character_target.json()['id']}",
        json={"name": "Gone"},
    ).status_code == 404
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}/details/{new_detail.json()['id']}"
    ).status_code == 204
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/characters/{new_character.json()['id']}/details/{new_detail.json()['id']}"
    ).status_code == 404

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

    status_templates = client.get("/play-api/v1/workspaces/demo_workspace/status-templates")
    assert status_templates.status_code == 200
    assert {item["statusKind"] for item in status_templates.json()} == {"scene", "normal"}
    mounted_scene_template = next(item for item in status_templates.json() if item["statusKind"] == "scene")
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/status-templates/{mounted_scene_template['id']}"
    ).status_code == 409
    assert client.get("/play-api/v1/workspaces/missing/status-templates").status_code == 404

    new_status_template = client.post(
        "/play-api/v1/workspaces/demo_workspace/status-templates",
        json={
            "name": "测试状态表",
            "statusKind": "normal",
            "keyColumn": "属性",
            "valueColumn": "值",
            "rows": [{"key": "钟声", "value": "未响", "runtimeKeyLocked": False}],
            "metadata": {"ui": {"compact": True}},
        },
    )
    assert new_status_template.status_code == 200
    assert new_status_template.json()["name"] == "测试状态表"
    assert new_status_template.json()["rows"][0]["key"] == "钟声"
    assert new_status_template.json()["metadata"]["ui"]["compact"] is True

    patched_status_template = client.patch(
        f"/play-api/v1/workspaces/demo_workspace/status-templates/{new_status_template.json()['id']}",
        json={
            "description": "更新后的状态表",
            "rows": [{"key": "钟声", "value": "响起", "runtimeKeyLocked": True}],
        },
    )
    assert patched_status_template.status_code == 200
    assert patched_status_template.json()["description"] == "更新后的状态表"
    assert patched_status_template.json()["rows"][0]["runtimeKeyLocked"] is True
    assert client.patch(
        f"/play-api/v1/workspaces/demo_workspace/status-templates/{new_status_template.json()['id']}",
        json={"statusKind": "scene"},
    ).status_code == 422

    status_mounts = client.get("/play-api/v1/workspaces/demo_workspace/stories/1/status-mounts")
    assert status_mounts.status_code == 200
    assert {item["statusKind"] for item in status_mounts.json()} == {"scene", "normal"}
    new_status_mount = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/1/status-mounts",
        json={"templateId": new_status_template.json()["id"], "sortOrder": 30},
    )
    assert new_status_mount.status_code == 200
    assert new_status_mount.json()["tableName"] == "测试状态表"
    assert client.delete(
        f"/play-api/v1/workspaces/demo_workspace/stories/1/status-mounts/{new_status_mount.json()['id']}"
    ).status_code == 204

    session_status_tables = client.get(f"/play-api/v1/sessions/{demo_session_id}/status-tables")
    assert session_status_tables.status_code == 200
    assert {item["name"] for item in session_status_tables.json()} >= {"世界线索", "北境森林当前场景"}
    assert client.get("/play-api/v1/sessions/missing/status-tables").status_code == 404

    new_session_table = client.post(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables",
        json={
            "name": "会话临时表",
            "rows": [{"key": "余烬", "value": "微光"}],
        },
    )
    assert new_session_table.status_code == 200
    assert new_session_table.json()["origin"] == "session_native"
    patched_session_table = client.patch(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables/{new_session_table.json()['id']}",
        json={
            "name": "会话状态",
            "description": "运行时描述更新",
            "sortOrder": 88,
            "rows": [{"key": "余烬", "value": "熄灭"}],
        },
    )
    assert patched_session_table.status_code == 200
    assert patched_session_table.json()["name"] == "会话状态"
    assert patched_session_table.json()["description"] == "运行时描述更新"
    assert patched_session_table.json()["sortOrder"] == 88
    assert patched_session_table.json()["rows"][0]["value"] == "熄灭"
    assert client.patch(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables/{new_session_table.json()['id']}",
        json={"statusKind": "scene"},
    ).status_code == 422
    assert client.delete(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables/{new_session_table.json()['id']}"
    ).status_code == 204

    new_scene_session_table = client.post(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables",
        json={
            "name": "会话场景",
            "statusKind": "scene",
            "rows": [{"key": "位置", "value": "石门"}],
        },
    )
    assert new_scene_session_table.status_code == 200
    assert new_scene_session_table.json()["statusKind"] == "scene"
    assert new_scene_session_table.json()["rows"][0]["runtimeKeyLocked"] is True
    assert client.delete(
        f"/play-api/v1/sessions/{demo_session_id}/status-tables/{new_scene_session_table.json()['id']}"
    ).status_code == 204

    workspace_root = tmp_path / "data" / "demo_workspace"
    unindexed_session_dir = workspace_root / "stories" / "1" / "s_unindexed_ops"
    unindexed_session_dir.mkdir(parents=True, exist_ok=True)
    (unindexed_session_dir / "marker.txt").write_text("tmp", encoding="utf-8")
    top_unindexed_workspace = tmp_path / "data" / "unindexed_workspace"
    (top_unindexed_workspace / "stories").mkdir(parents=True, exist_ok=True)

    unindexed_scan = client.get(
        "/play-api/v1/ops/unindexed-runtime",
        params={"workspace_id": "demo_workspace"},
    )
    assert unindexed_scan.status_code == 200
    items = unindexed_scan.json()["items"]
    assert any(item["category"] == "runtime_directory" and item["sessionId"] == "s_unindexed_ops" for item in items)
    assert all(item["category"] == "runtime_directory" for item in items)
    assert all(item["workspaceId"] == "demo_workspace" for item in items)
    assert all(item["kind"] != "workspace" for item in items)
    assert client.get(
        "/play-api/v1/ops/unindexed-runtime",
        params={"workspace_id": "missing"},
    ).status_code == 404

    runtime_item = next(item for item in items if item["category"] == "runtime_directory" and item["sessionId"] == "s_unindexed_ops")
    batch_items = [runtime_item]
    assert client.post("/play-api/v1/ops/unindexed-runtime/delete", json={"items": batch_items}).status_code == 409
    runtime_token = client.post("/play-api/v1/ops/unindexed-runtime/delete-token", json={"items": batch_items})
    assert runtime_token.status_code == 200
    assert client.post(
        "/play-api/v1/ops/unindexed-runtime/delete",
        json={"items": batch_items},
        headers={"X-Delete-Confirm-Token": "bad-token"},
    ).status_code == 409
    deleted_runtime = client.post(
        "/play-api/v1/ops/unindexed-runtime/delete",
        json={"items": batch_items},
        headers={"X-Delete-Confirm-Token": runtime_token.json()["token"]},
    )
    assert deleted_runtime.status_code == 204
    assert not unindexed_session_dir.exists()
    assert client.post(
        "/play-api/v1/ops/unindexed-runtime/delete",
        json={"items": batch_items},
        headers={"X-Delete-Confirm-Token": runtime_token.json()["token"]},
    ).status_code == 409

    stale_token = client.post("/play-api/v1/ops/unindexed-runtime/delete-token", json={"items": batch_items})
    assert stale_token.status_code == 404

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
