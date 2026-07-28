from __future__ import annotations

from fastapi.testclient import TestClient

from commons.scene_time import SceneTime
from play_api.main import app
from rpg_data import models
from rpg_data.services import (
    get_data_service_gateway,
    reset_data_service_gateways,
)


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
        assert initial.json()["storyId"] == 1
        assert initial.json()["pools"]
        assert initial.json()["events"]
        assert initial.json()["outlines"]

        pool = client.post(
            f"{story_path}/pools",
            json={
                "name": "主事件池",
                "description": "测试池",
                "selectionMode": "sequential",
                "priority": 10,
                "cooldownMinutes": 120,
                "enabled": True,
            },
        )
        assert pool.status_code == 201
        assert pool.json()["cooldownMinutes"] == 120
        pool_id = pool.json()["id"]
        updated_pool = client.patch(
            f"{story_path}/pools/{pool_id}",
            json={"cooldownMinutes": 180},
        )
        assert updated_pool.status_code == 200
        assert updated_pool.json()["cooldownMinutes"] == 180
        assert client.patch(
            f"{story_path}/pools/{pool_id}",
            json={"cooldownMinutes": -1},
        ).status_code == 422

        event = client.post(
            f"{story_path}/events",
            json={
                "poolId": pool_id,
                "title": "雨夜来信",
                "directive": "让信使送来一封被雨打湿的信。",
                "dispatchMode": "soft",
                "scheduledTime": None,
                "deadlineTime": {
                    "year": 1,
                    "month": 1,
                    "day": 1,
                    "hour": 9,
                    "minute": 0,
                },
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
        assert scheduled_event.json()["deadlineTime"]["hour"] == 9
        invalid_deadline = client.patch(
            f"{story_path}/events/{event_id}",
            json={
                "deadlineTime": {
                    "year": 1,
                    "month": 1,
                    "day": 1,
                    "hour": 8,
                    "minute": 30,
                }
            },
        )
        assert invalid_deadline.status_code == 422
        renamed_event = client.patch(
            f"{story_path}/events/{event_id}",
            json={"title": "雨夜加急来信"},
        )
        assert renamed_event.status_code == 200
        assert renamed_event.json()["scheduledTime"]["minute"] == 30
        assert renamed_event.json()["deadlineTime"]["hour"] == 9
        cleared_schedule = client.patch(
            f"{story_path}/events/{event_id}",
            json={"scheduledTime": None},
        )
        assert cleared_schedule.status_code == 200
        assert cleared_schedule.json()["scheduledTime"] is None
        assert cleared_schedule.json()["deadlineTime"]["hour"] == 9
        cleared_deadline = client.patch(
            f"{story_path}/events/{event_id}",
            json={"deadlineTime": None},
        )
        assert cleared_deadline.status_code == 200
        assert cleared_deadline.json()["deadlineTime"] is None
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
        created_outline = next(
            item
            for item in aggregate.json()["outlines"]
            if item["id"] == outline_id
        )
        assert created_outline["nodes"][0]["eventId"] == event_id

        runtime = client.get("/play-api/v1/sessions/s_forest001/plot-scheduling")
        assert runtime.status_code == 200
        runtime_payload = runtime.json()
        assert runtime_payload["sessionId"] == "s_forest001"
        runtime_event = next(
            item
            for item in runtime_payload["schedule"]["events"]
            if item["id"] == event_id
        )
        assert runtime_event["title"] == "雨夜加急来信"
        assert runtime_payload["sceneTime"] is not None
        binding = next(
            item
            for item in runtime_payload["eventBindings"]
            if item["eventId"] == event_id
        )
        assert binding == {
            "eventId": event_id,
            "outlineBound": True,
            "outlineNodeReferenceCount": 1,
            "poolLaneEligibleByBinding": False,
        }
        initial_cooldown = next(
            item
            for item in runtime_payload["poolCooldowns"]
            if item["poolId"] == pool_id
        )
        assert initial_cooldown["cooldownMinutes"] == 180
        assert initial_cooldown["status"] == "ready"
        assert initial_cooldown["anchorDecisionId"] is None

        gateway = get_data_service_gateway()
        scene_time = SceneTime.from_mapping(runtime_payload["sceneTime"])
        auto_anchor = gateway.plot_scheduling.append_decisions(
            "s_forest001",
            9001,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=event_id,
                    event_id=event_id,
                    container_id=pool_id,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_FORCED,
                    selection_origin=models.PLOT_SELECTION_ORIGIN_SCHEDULER,
                    scene_time=scene_time,
                    event_snapshot={
                        "eventTitle": "自动冷却锚点",
                        "directive": "自动注入快照。",
                    },
                    reason="自动调度成功",
                ),
            ),
        )[0]
        gateway.plot_scheduling.append_decisions(
            "s_forest001",
            9002,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=event_id,
                    event_id=event_id,
                    container_id=pool_id,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_FORCED,
                    selection_origin=models.PLOT_SELECTION_ORIGIN_MANUAL,
                    scene_time=None,
                    event_snapshot={
                        "eventTitle": "手动注入不改池锚点",
                        "directive": "手动注入快照。",
                    },
                    reason="手动注入",
                ),
            ),
        )
        cooled_payload = client.get(
            "/play-api/v1/sessions/s_forest001/plot-scheduling"
        ).json()
        cooldown = next(
            item
            for item in cooled_payload["poolCooldowns"]
            if item["poolId"] == pool_id
        )
        assert cooldown["status"] == "cooling_down"
        assert cooldown["remainingMinutes"] == 180
        assert cooldown["anchorDecisionId"] == auto_anchor.id
        assert cooldown["anchorTurnId"] == 9001
        assert cooldown["anchorEventId"] == event_id
        persisted = next(
            item
            for item in cooled_payload["decisions"]
            if item["id"] == auto_anchor.id
        )
        assert {
            "version",
            "createdAt",
            "updatedAt",
            "eventSnapshot",
            "sceneTimeOrdinal",
            "containerId",
            "selectionOrigin",
        }.issubset(persisted)
        assert persisted["eventSnapshot"]["directive"] == "自动注入快照。"
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


def test_session_plot_story_masks_spoilers_and_projects_triggered_sources(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "RPG_WORLD_DB_PATH",
        str(tmp_path / "plot-story-api.sqlite3"),
    )
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    gateway = get_data_service_gateway()
    story = gateway.catalog.create_story(
        "demo_workspace",
        title="剧情防剧透隔离故事",
    )
    assert story is not None
    session = gateway.catalog.create_session(
        "demo_workspace",
        story.id,
        session_id="s_plot_story",
        title="剧情防剧透隔离会话",
    )
    assert session is not None
    story_path = (
        f"/play-api/v1/workspaces/demo_workspace/stories/{story.id}"
        "/plot-scheduling"
    )
    session_path = f"/play-api/v1/sessions/{session.id}/plot-story"

    with TestClient(app) as client:
        empty = client.get(session_path)
        assert empty.status_code == 200
        assert empty.json() == {
            "sessionId": session.id,
            "spoilerProtectionEnabled": True,
            "outlines": [],
            "pools": [],
        }
        assert client.get(
            "/play-api/v1/sessions/missing/plot-story"
        ).status_code == 404

        pool_response = client.post(
            f"{story_path}/pools",
            json={
                "name": "迷雾事件池",
                "description": "沿途可能发生的插曲。",
                "selectionMode": "sequential",
            },
        )
        assert pool_response.status_code == 201
        pool_id = pool_response.json()["id"]

        def _create_event(
            title: str,
            directive: str,
            *,
            position: int,
        ) -> int:
            response = client.post(
                f"{story_path}/events",
                json={
                    "poolId": pool_id,
                    "title": title,
                    "description": f"{title}的公开详情。",
                    "directive": directive,
                    "suitabilityHint": f"{title}的适宜条件。",
                    "position": position,
                },
            )
            assert response.status_code == 201
            return int(response.json()["id"])

        first_event_id = _create_event(
            "公开起点",
            "固定展示第一项。",
            position=0,
        )
        repeated_event_id = _create_event(
            "已触发事件",
            "只展示已成功注入的事件。",
            position=1,
        )
        hidden_event_id = _create_event(
            "未来秘密",
            "默认响应绝不能泄露这条指令。",
            position=2,
        )

        outline_response = client.post(
            f"{story_path}/outlines",
            json={
                "name": "主线",
                "description": "依次推进的故事线。",
            },
        )
        assert outline_response.status_code == 201
        outline_id = outline_response.json()["id"]

        node_ids: list[int] = []
        for position, event_id in enumerate(
            (first_event_id, repeated_event_id, hidden_event_id)
        ):
            response = client.post(
                f"{story_path}/outlines/{outline_id}/nodes",
                json={
                    "eventId": event_id,
                    "scheduledTime": {
                        "year": 1,
                        "month": 1,
                        "day": 1,
                        "hour": 8 + position,
                        "minute": 0,
                    },
                    "position": position,
                },
            )
            assert response.status_code == 201
            node_ids.append(int(response.json()["id"]))

        gateway.plot_scheduling.append_decisions(
            session.id,
            7,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_OUTLINE,
                    source_id=node_ids[1],
                    event_id=repeated_event_id,
                    container_id=outline_id,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_SOFT,
                    scene_time=SceneTime(1, 1, 1, 9),
                    event_snapshot={
                        "eventTitle": "裁定时旧标题",
                        "directive": "裁定账本内部快照不得公开。",
                    },
                    reason="内部裁定理由不得公开",
                ),
            ),
        )
        renamed = client.patch(
            f"{story_path}/events/{repeated_event_id}",
            json={"title": "编辑后的已触发事件"},
        )
        assert renamed.status_code == 200

        masked_response = client.get(session_path)
        assert masked_response.status_code == 200
        masked = masked_response.json()
        assert masked["spoilerProtectionEnabled"] is True

        outline_nodes = masked["outlines"][0]["nodes"]
        pool_nodes = masked["pools"][0]["nodes"]
        assert outline_nodes[0]["eventDetail"]["title"] == "公开起点"
        assert pool_nodes[0]["eventDetail"]["title"] == "公开起点"

        repeated_outline = outline_nodes[1]
        assert repeated_outline["eventInjected"] is True
        assert repeated_outline["sourceInjected"] is True
        assert repeated_outline["eventInjectionCount"] == 1
        assert repeated_outline["sourceInjectionCount"] == 1
        assert repeated_outline["lastEventInjectionTurnId"] == 7
        assert repeated_outline["lastSourceInjectionTurnId"] == 7
        assert (
            repeated_outline["eventDetail"]["title"]
            == "编辑后的已触发事件"
        )

        repeated_pool = pool_nodes[1]
        assert repeated_pool["eventInjected"] is True
        assert repeated_pool["sourceInjected"] is False
        assert repeated_pool["eventDetail"]["eventId"] == repeated_event_id

        expected_hidden_keys = {
            "slotKey",
            "position",
            "revealed",
            "enabled",
            "sessionDisabled",
            "eventInjected",
            "eventInjectionCount",
            "lastEventInjectionTurnId",
            "sourceInjected",
            "sourceInjectionCount",
            "lastSourceInjectionTurnId",
            "eventDetail",
        }
        for hidden in (outline_nodes[2], pool_nodes[2]):
            assert set(hidden) == expected_hidden_keys
            assert hidden["revealed"] is False
            assert hidden["eventDetail"] is None

        def _all_keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return set(value).union(
                    *(_all_keys(item) for item in value.values()),
                )
            if isinstance(value, list):
                return set().union(*(_all_keys(item) for item in value))
            return set()

        assert _all_keys(masked).isdisjoint(
            {
                "decisionStatus",
                "eventSnapshot",
                "reason",
                "errorCode",
                "errorMessage",
                "containerId",
                "sceneTimeOrdinal",
                "sourceId",
                "createdAt",
            }
        )

        revealed_response = client.get(
            f"{session_path}?revealSpoilers=true"
        )
        assert revealed_response.status_code == 200
        revealed = revealed_response.json()
        assert revealed["spoilerProtectionEnabled"] is False
        assert (
            revealed["outlines"][0]["nodes"][2]["eventDetail"]["eventId"]
            == hidden_event_id
        )
        assert (
            revealed["pools"][0]["nodes"][2]["eventDetail"]["title"]
            == "未来秘密"
        )

    reset_data_service_gateways()


def test_manual_plot_decision_contract_allows_missing_scene_time(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "RPG_WORLD_DB_PATH",
        str(tmp_path / "plot-manual-decision-api.sqlite3"),
    )
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    gateway = get_data_service_gateway()
    schedule, _overrides = gateway.plot_scheduling.get_session_schedule(
        "s_forest001"
    )
    event = schedule.events[0]
    gateway.plot_scheduling.append_decisions(
        "s_forest001",
        99,
        (
            models.StagedPlotScheduleDecision(
                source_kind=models.PLOT_SOURCE_POOL,
                source_id=event.id,
                event_id=event.id,
                container_id=event.pool_id,
                decision_status=models.PLOT_DECISION_TRIGGERED,
                dispatch_mode=models.PLOT_DISPATCH_FORCED,
                selection_origin=models.PLOT_SELECTION_ORIGIN_MANUAL,
                scene_time=None,
                event_snapshot={
                    "eventTitle": "手动冻结标题",
                    "directive": "手动冻结指令。",
                },
                reason="OOC/GM 手动标记",
            ),
        ),
    )

    with TestClient(app) as client:
        response = client.get(
            "/play-api/v1/sessions/s_forest001/plot-scheduling"
        )

    assert response.status_code == 200
    manual = next(
        item
        for item in response.json()["decisions"]
        if item["turnId"] == 99
    )
    assert manual["selectionOrigin"] == "manual"
    assert manual["sceneTime"] is None
    assert manual["sceneTimeOrdinal"] is None
    assert manual["eventSnapshot"]["eventTitle"] == "手动冻结标题"
    reset_data_service_gateways()
