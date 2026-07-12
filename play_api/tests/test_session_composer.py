from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from play_api.main import app
from play_api.routers.sessions import PlayChatRequest
from rpg_data.services import reset_data_service_gateways


def test_play_chat_request_normalizes_optional_mode() -> None:
    for value in (None, "", "   "):
        assert PlayChatRequest.model_validate({"text": "hello", "mode": value}).mode == "ic"
    assert PlayChatRequest.model_validate({"text": "hello", "mode": " OOC "}).mode == "ooc"
    assert PlayChatRequest.model_validate({"text": "hello"}).mode == "ic"
    with pytest.raises(ValidationError, match="invalid turn mode"):
        PlayChatRequest.model_validate({"text": "hello", "mode": "chat"})


def test_play_session_composer_management_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "composer.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    client = TestClient(app)

    modes = client.get("/play-api/v1/workspaces/demo_workspace/turn-modes")
    assert modes.status_code == 200
    assert [item["mode"] for item in modes.json()] == ["ic", "ooc", "gm"]
    updated_mode = client.patch(
        "/play-api/v1/workspaces/demo_workspace/turn-modes/ooc",
        json={"shortName": "幕后", "prompt": "只讨论设定"},
    )
    assert updated_mode.status_code == 200
    assert updated_mode.json()["shortName"] == "幕后"
    assert client.patch(
        "/play-api/v1/workspaces/demo_workspace/turn-modes/chat",
        json={"shortName": "聊天", "prompt": ""},
    ).status_code == 422

    created_style = client.post(
        "/play-api/v1/workspaces/demo_workspace/narrative-styles",
        json={"name": "冷峻留白", "prompt": "使用冷峻留白。", "sortOrder": 40},
    )
    assert created_style.status_code == 200
    style_id = created_style.json()["id"]
    assert client.post(
        "/play-api/v1/workspaces/demo_workspace/narrative-styles",
        json={"name": "冷峻留白", "prompt": "duplicate"},
    ).status_code == 409

    mount = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/1/narrative-styles",
        json={"narrativeStyleId": style_id},
    )
    assert mount.status_code == 200
    mount_id = mount.json()["mountId"]
    base = client.patch(
        "/play-api/v1/workspaces/demo_workspace/stories/1/narrative-styles/base",
        json={"mountId": mount_id},
    )
    assert base.status_code == 200 and base.json()["isBase"] is True

    enabled_reply = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/1/quick-replies",
        json={"title": "观察", "message": "我仔细观察四周。", "sortOrder": 10},
    )
    disabled_reply = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/1/quick-replies",
        json={"title": "停用", "message": "不展示", "sortOrder": 0, "enabled": False},
    )
    assert enabled_reply.status_code == 200 and disabled_reply.status_code == 200

    composer = client.get("/play-api/v1/sessions/s_forest001/composer")
    assert composer.status_code == 200
    assert composer.json()["baseNarrativeStyleId"] == style_id
    assert composer.json()["modes"][1]["shortName"] == "幕后"
    assert [item["title"] for item in composer.json()["quickReplies"]] == ["观察"]

    deleted = client.delete(
        f"/play-api/v1/workspaces/demo_workspace/narrative-styles/{style_id}"
    )
    assert deleted.status_code == 204
    composer_after_delete = client.get("/play-api/v1/sessions/s_forest001/composer")
    assert composer_after_delete.json()["baseNarrativeStyleId"] is None
    reset_data_service_gateways()
