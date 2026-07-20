from __future__ import annotations

from fastapi.testclient import TestClient

from play_api.main import app
from rpg_data.services import reset_data_service_gateways


def test_plot_scheduling_story_crud_and_session_runtime_contract(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "plot-api.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    story_path = "/play-api/v1/workspaces/demo_workspace/stories/1/plot-scheduling"

    with TestClient(app) as client:
        initial = client.get(story_path)
        assert initial.status_code == 200
        assert initial.json() == {
            "storyId": 1,
            "pools": [],
            "events": [],
            "outlines": [],
        }

        pool = client.post(
            f"{story_path}/pools",
            json={
                "name": "主事件池",
                "description": "测试池",
                "selectionMode": "sequential",
                "priority": 10,
                "enabled": True,
            },
        )
        assert pool.status_code == 201
        pool_id = pool.json()["id"]

        event = client.post(
            f"{story_path}/events",
            json={
                "poolId": pool_id,
                "title": "雨夜来信",
                "directive": "让信使送来一封被雨打湿的信。",
                "dispatchMode": "soft",
                "scheduledTime": None,
                "allowRepeat": False,
                "repeatCooldownMinutes": 0,
            },
        )
        assert event.status_code == 201
        event_id = event.json()["id"]

        scheduled_event = client.patch(
            f"{story_path}/events/{event_id}",
            json={
                "scheduledTime": {
                    "year": 1,
                    "month": 1,
                    "day": 1,
                    "hour": 8,
                    "minute": 30,
                }
            },
        )
        assert scheduled_event.status_code == 200
        assert scheduled_event.json()["scheduledTime"]["minute"] == 30
        renamed_event = client.patch(
            f"{story_path}/events/{event_id}",
            json={"title": "雨夜加急来信"},
        )
        assert renamed_event.status_code == 200
        assert renamed_event.json()["scheduledTime"]["minute"] == 30
        cleared_schedule = client.patch(
            f"{story_path}/events/{event_id}",
            json={"scheduledTime": None},
        )
        assert cleared_schedule.status_code == 200
        assert cleared_schedule.json()["scheduledTime"] is None
        invalid_null_title = client.patch(
            f"{story_path}/events/{event_id}",
            json={"title": None},
        )
        assert invalid_null_title.status_code == 422

        outline = client.post(
            f"{story_path}/outlines",
            json={"name": "雨夜主线", "priority": 20},
        )
        assert outline.status_code == 201
        outline_id = outline.json()["id"]
        node = client.post(
            f"{story_path}/outlines/{outline_id}/nodes",
            json={
                "eventId": event_id,
                "scheduledTime": {
                    "year": 1,
                    "month": 1,
                    "day": 1,
                    "hour": 9,
                    "minute": 0,
                },
                "dispatchMode": "forced",
            },
        )
        assert node.status_code == 201
        node_id = node.json()["id"]
        invalid_null_node_time = client.patch(
            f"{story_path}/outlines/{outline_id}/nodes/{node_id}",
            json={"scheduledTime": None},
        )
        assert invalid_null_node_time.status_code == 422

        aggregate = client.get(story_path)
        assert aggregate.status_code == 200
        assert aggregate.json()["outlines"][0]["nodes"][0]["eventId"] == event_id

        runtime = client.get("/play-api/v1/sessions/s_forest001/plot-scheduling")
        assert runtime.status_code == 200
        assert runtime.json()["sessionId"] == "s_forest001"
        assert runtime.json()["schedule"]["events"][0]["title"] == "雨夜加急来信"
        assert runtime.json()["sceneTime"] is not None
        max_page = client.get(
            "/play-api/v1/sessions/s_forest001/plot-scheduling?limit=200"
        )
        assert max_page.status_code == 200

        event_override = client.put(
            f"/play-api/v1/sessions/s_forest001/plot-scheduling/event-overrides/{event_id}",
            json={"disabled": True},
        )
        assert event_override.status_code == 200
        assert event_override.json()["disabledEventIds"] == [event_id]
        node_override = client.put(
            f"/play-api/v1/sessions/s_forest001/plot-scheduling/node-overrides/{node_id}",
            json={"disabled": True},
        )
        assert node_override.status_code == 200
        assert node_override.json()["disabledOutlineNodeIds"] == [node_id]

        referenced_delete = client.delete(f"{story_path}/events/{event_id}")
        assert referenced_delete.status_code == 409

    reset_data_service_gateways()
