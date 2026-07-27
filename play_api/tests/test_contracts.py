from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent_service.client import AgentClientError
from commons.scene_time import SceneTime
from play_api import agent_client
from play_api.main import app
from play_api.delete_tokens import reset_delete_confirmation_tokens
from play_api.routers.sessions import _agent_call, _turns_from_history
from play_api.sse_protocol import AgentEventKind, PLAY_SSE_SCHEMA_VERSION, PlaySSEType
from rpg_core.agent.protocol import TurnCancelStatus
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.derivation import SessionDerivationService
from rpg_core.session.role import SessionRoleService
from rpg_core.session.turn_metadata import InvalidTurnMetadataError
from rpg_data import models
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from rpg_memory.story.application import StoryMemoryApplicationService


def _sse_payloads(body: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                raw = line.removeprefix("data:").strip()
                if raw:
                    payload = json.loads(raw)
                    assert isinstance(payload, dict)
                    payloads.append(payload)
    return payloads


class _FakeStreamEvent:
    def __init__(self, **payload: object) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, object]:
        return dict(self._payload)


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
        self.story_main_llm_provider_key: str | None = None
        self.session_main_llm_provider_key: str | None = None

    async def aclose(self) -> None:
        return None

    @staticmethod
    def _main_llm_option(provider_key: str) -> dict[str, object]:
        return {
            "provider_key": provider_key,
            "backend": "openai",
            "model": f"{provider_key}-model",
            "context_window": 64000,
        }

    def _main_llm_selection(self) -> dict[str, object]:
        effective_key = "config_chat"
        effective_source = "config"
        if self.story_main_llm_provider_key is not None:
            effective_key = self.story_main_llm_provider_key
            effective_source = "story"
        if self.session_main_llm_provider_key is not None:
            effective_key = self.session_main_llm_provider_key
            effective_source = "session"
        return {
            "config_default_provider_key": "config_chat",
            "story_provider_key": self.story_main_llm_provider_key,
            "session_provider_key": self.session_main_llm_provider_key,
            "effective_provider_key": effective_key,
            "effective_source": effective_source,
            "effective": self._main_llm_option(effective_key),
            "invalid_overrides": [],
        }

    async def get_main_llm_options(self) -> dict[str, object]:
        self.calls.append(("main-llm-options",))
        return {
            "config_default_provider_key": "config_chat",
            "options": [
                self._main_llm_option("config_chat"),
                self._main_llm_option("alternate_chat"),
            ],
        }

    async def create_session(
        self,
        workspace_id: str,
        story_id: int,
        *,
        title: str = "",
        description: str = "",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "create-session",
                workspace_id,
                str(story_id),
                title,
                description,
            )
        )
        gateway = get_data_service_gateway()
        session = SessionCatalogService(gateway.sessions).create_session(
            workspace_id,
            story_id,
            title=title,
            description=description,
        )
        if session is None:
            raise AgentClientError(
                "story not found in workspace",
                status_code=404,
            )
        return {
            "status": "created",
            "workspace": workspace_id,
            "story_id": story_id,
            "session_id": session.id,
            "title": session.title,
        }

    async def get_story_main_llm(
        self,
        workspace_id: str,
        story_id: int,
    ) -> dict[str, object]:
        self.calls.append(("get-story-main-llm", workspace_id, str(story_id)))
        return self._main_llm_selection()

    async def set_story_main_llm(
        self,
        workspace_id: str,
        story_id: int,
        provider_key: str | None,
    ) -> dict[str, object]:
        self.calls.append(("set-story-main-llm", workspace_id, str(story_id), provider_key or ""))
        self.story_main_llm_provider_key = provider_key
        return self._main_llm_selection()

    async def get_session_main_llm(self, session_id: str) -> dict[str, object]:
        self.calls.append(("get-session-main-llm", session_id))
        return self._main_llm_selection()

    async def set_session_main_llm(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> dict[str, object]:
        self.calls.append(("set-session-main-llm", session_id, provider_key or ""))
        self.session_main_llm_provider_key = provider_key
        return self._main_llm_selection()

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
                {
                    "command": "/continue",
                    "description": "继续叙事",
                    "detail": "用法：/continue。",
                },
                {
                    "command": "/check_dc",
                    "description": "手动 DC 检定",
                    "detail": "用法：/check_dc <expr> dc=<n> [reason]。",
                },
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
            "usageEstimate": {
                "usedTokens": 3,
                "contextLimit": 100,
                "source": "context_preview",
                "accuracy": "estimated",
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
        result: dict[str, object] = {
            "reply": f"agent reply: {text}",
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 5,
                "total_tokens": 14,
                "cached_tokens": 2,
                "source": "provider_usage",
                "accuracy": "accurate",
                "createdAt": "2026-01-01T00:00:00+00:00",
            },
        }
        if text.startswith("/session_switch "):
            result["active_session"] = text.split(maxsplit=1)[1]
        return result

    async def reload_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("reload-history", session_id))
        return {"status": "reloaded"}

    async def bind_player_character(
        self,
        session_id: str,
        player_character_id: int,
        story_opening_id: int | None = None,
    ) -> dict[str, object]:
        self.calls.append((
            "bind-player-character",
            session_id,
            str(player_character_id),
            str(story_opening_id or ""),
        ))
        try:
            gateway = get_data_service_gateway()
            SessionRoleService(gateway.sessions).bind_player_character(
                session_id,
                player_character_id,
                story_opening_id=story_opening_id,
            )
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

    async def delete_session(self, session_id: str) -> dict[str, object]:
        self.calls.append(("delete-session", session_id))
        return {
            "status": "deleted",
            "session_id": session_id,
            "runtime_cleanup": "deleted",
        }

    async def stop(self, session_id: str, request_id: str | None = None) -> dict[str, object]:
        self.calls.append(("stop", session_id, request_id or ""))
        return {"status": TurnCancelStatus.CANCELLED.value, "session_id": session_id, "request_id": request_id}


class _InvalidHistoryAgentClient(_FakeAgentClient):
    async def get_history(self, session_id: str) -> dict[str, object]:
        self.calls.append(("history", session_id))
        return {
            "history": [
                {"messageId": 1, "turnId": 1, "seqInTurn": 1, "role": "user", "content": "hello"},
                {"messageId": 2, "turnId": 1, "seqInTurn": 0, "role": "assistant", "content": "reply"},
            ]
        }


class _RejectingMainLLMAgentClient(_FakeAgentClient):
    async def set_session_main_llm(
        self,
        session_id: str,
        provider_key: str | None,
    ) -> dict[str, object]:
        del session_id, provider_key
        raise AgentClientError("provider is not selectable", status_code=422)


class _StreamingAgentClient(_FakeAgentClient):
    async def stream(self, session_id: str, text: str, request_id: str | None = None):
        self.calls.append(("stream", session_id, text, request_id or ""))
        yield _FakeStreamEvent(kind=AgentEventKind.TEXT.value, content="你推开门")
        yield _FakeStreamEvent(kind=AgentEventKind.TOOL_CALL.value, tool_name="roll", tool_arguments="1d20")
        yield _FakeStreamEvent(kind=AgentEventKind.TOOL_RESULT.value, tool_name="roll", tool_result_preview="18")
        yield _FakeStreamEvent(
            kind=AgentEventKind.DONE.value,
            content="你推开门。",
            usage={
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "total_tokens": 7,
                "cached_tokens": 1,
                "source": "provider_usage",
                "accuracy": "accurate",
                "createdAt": "2026-01-01T00:00:00+00:00",
            },
            model="test-model",
            finish_reason="stop",
            duration_ms=12.3,
            committed_turn_id=4,
            active_session=(
                text.split(maxsplit=1)[1]
                if text.startswith("/session_switch ")
                else None
            ),
        )


def test_history_endpoint_rejects_invalid_turn_metadata(
    tmp_path,
    monkeypatch,
    start_play_client,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _InvalidHistoryAgentClient())
    reset_delete_confirmation_tokens()
    client = start_play_client()

    response = client.get("/play-api/v1/sessions/s_forest001/history")

    assert response.status_code == 409
    assert "history[1]" in response.json()["detail"]


def test_rp_module_config_inheritance_validation_and_history_page(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    monkeypatch.setattr(agent_client, "_client", _FakeAgentClient())

    story_weights = {
        "critical_success": 10,
        "success": 30,
        "success_with_cost": 30,
        "setback": 25,
        "critical_failure": 5,
    }
    session_weights = {
        "critical_success": 0,
        "success": 20,
        "success_with_cost": 50,
        "setback": 25,
        "critical_failure": 5,
    }

    with TestClient(app) as client:
        catalog = client.get("/play-api/v1/rp-modules/catalog")
        assert catalog.status_code == 200
        assert [item["moduleName"] for item in catalog.json()["modules"]] == [
            "message_mode",
            "narrative_outcome",
            "plot_scheduler",
            "dice",
        ]

        story_default = client.get(
            "/play-api/v1/workspaces/demo_workspace/stories/1/rp-modules"
        )
        assert story_default.status_code == 200
        story_outcome = next(
            item
            for item in story_default.json()["modules"]
            if item["moduleName"] == "narrative_outcome"
        )
        assert story_outcome["configSources"]["weights"] == "config"
        assert story_outcome["effectiveConfig"]["weights"] == {
            "critical_success": 5,
            "success": 25,
            "success_with_cost": 40,
            "setback": 25,
            "critical_failure": 5,
        }
        assert [item["code"] for item in story_outcome["outcomeDefinitions"]] == [
            "critical_success",
            "success",
            "success_with_cost",
            "setback",
            "critical_failure",
        ]

        story_override = client.patch(
            "/play-api/v1/workspaces/demo_workspace/stories/1/rp-modules/narrative_outcome",
            json={"config": {"weights": story_weights}},
        )
        assert story_override.status_code == 200
        assert story_override.json()["storyConfig"]["weights"] == story_weights
        assert story_override.json()["configSources"]["weights"] == "story"

        inherited = client.get(
            "/play-api/v1/sessions/s_forest001/rp-modules"
        )
        assert inherited.status_code == 200
        inherited_outcome = next(
            item
            for item in inherited.json()["modules"]
            if item["moduleName"] == "narrative_outcome"
        )
        assert inherited_outcome["sessionConfig"] == {}
        assert inherited_outcome["effectiveConfig"]["weights"] == story_weights
        assert inherited_outcome["configSources"]["weights"] == "story"

        session_override = client.patch(
            "/play-api/v1/sessions/s_forest001/rp-modules/narrative_outcome",
            json={"enabled": True, "config": {"weights": session_weights}},
        )
        assert session_override.status_code == 200
        assert session_override.json()["configSources"]["weights"] == "session"
        assert session_override.json()["effectiveConfig"]["weights"] == session_weights

        cleared = client.delete(
            "/play-api/v1/sessions/s_forest001/rp-modules/narrative_outcome"
        )
        assert cleared.status_code == 200
        assert cleared.json()["sessionConfig"] == {}
        assert cleared.json()["configSources"]["weights"] == "story"

        invalid = client.patch(
            "/play-api/v1/sessions/s_forest001/rp-modules/narrative_outcome",
            json={"config": {"weights": {**session_weights, "success": 19}}},
        )
        assert invalid.status_code == 422

        cleared_story = client.patch(
            "/play-api/v1/workspaces/demo_workspace/stories/1/rp-modules/narrative_outcome",
            json={"config": {}},
        )
        assert cleared_story.status_code == 200
        assert cleared_story.json()["storyConfig"] == {}
        assert cleared_story.json()["configSources"]["weights"] == "config"
        assert client.get(
            "/play-api/v1/workspaces/demo_workspace/stories/1/narrative-outcome"
        ).status_code == 404

        gateway = get_data_service_gateway()
        gateway.narrative_outcomes.append(models.NarrativeOutcomeCreate(
            session_id="s_forest001",
            turn_id=1,
            outcome_code="success_with_cost",
            reason="穿越霜藤",
            actor="Bob",
            sample_value=50,
            effective_weights=models.NarrativeOutcomeWeights(),
            effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
        ))
        gateway.plot_scheduling.append_decisions(
            "s_forest001",
            1,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=22,
                    event_id=22,
                    container_id=202,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_SOFT,
                    scene_time=SceneTime(1, 1, 1, 8),
                    event_snapshot={
                        "eventTitle": "林间钟声",
                        "directive": "让远处的钟声打断当前对话。",
                    },
                ),
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_OUTLINE,
                    source_id=11,
                    event_id=11,
                    container_id=101,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_FORCED,
                    scene_time=SceneTime(1, 1, 1, 8),
                    event_snapshot={
                        "eventTitle": "封印异动",
                        "directive": "描写祭坛封印出现第一次明确异动。",
                    },
                ),
            ),
        )
        gateway.plot_scheduling.append_decisions(
            "s_forest001",
            2,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_OUTLINE,
                    source_id=24,
                    event_id=24,
                    container_id=203,
                    decision_status=models.PLOT_DECISION_ERROR,
                    dispatch_mode=models.PLOT_DISPATCH_SOFT,
                    scene_time=SceneTime(1, 1, 1, 8),
                    event_snapshot={
                        "eventTitle": "裁定失败事件",
                        "directive": "这条错误指令不应公开。",
                    },
                    error_code="JUDGE_UNAVAILABLE",
                    error_message="judge unavailable",
                ),
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=23,
                    event_id=23,
                    container_id=202,
                    decision_status=models.PLOT_DECISION_DEFERRED,
                    dispatch_mode=models.PLOT_DISPATCH_SOFT,
                    scene_time=SceneTime(1, 1, 1, 8),
                    event_snapshot={
                        "eventTitle": "暂缓事件",
                        "directive": "这条指令不应公开。",
                    },
                    reason="当前不适合",
                ),
            ),
        )
        gateway.plot_scheduling.append_decisions(
            "s_forest001",
            3,
            (
                models.StagedPlotScheduleDecision(
                    source_kind=models.PLOT_SOURCE_POOL,
                    source_id=25,
                    event_id=25,
                    container_id=202,
                    decision_status=models.PLOT_DECISION_TRIGGERED,
                    dispatch_mode=models.PLOT_DISPATCH_SOFT,
                    scene_time=SceneTime(1, 1, 1, 8),
                    event_snapshot={
                        "eventTitle": "缺少公开指令",
                    },
                ),
            ),
        )

        history_page = client.get(
            "/play-api/v1/sessions/s_forest001/history-page?limit=50"
        )
        assert history_page.status_code == 200
        turn_one = next(
            turn for turn in history_page.json()["turns"] if turn["turnId"] == 1
        )
        assert turn_one["outcome"] == {
            "outcomeCode": "success_with_cost",
            "label": "成功但有代价",
            "narrativeGuidance": (
                "完整达成 reason 描述的整体目标，同时引入一个与行动相称的代价或复杂化；"
                "不得只完成子步骤，代价不得抵消整体目标已经达成。"
            ),
            "reason": "穿越霜藤",
            "actor": "Bob",
        }
        assert turn_one["plotInjections"] == [
            {
                "eventTitle": "封印异动",
                "directive": "描写祭坛封印出现第一次明确异动。",
            },
            {
                "eventTitle": "林间钟声",
                "directive": "让远处的钟声打断当前对话。",
            },
        ]
        turn_two = next(
            turn for turn in history_page.json()["turns"] if turn["turnId"] == 2
        )
        assert turn_two["plotInjections"] == []
        turn_three = next(
            turn for turn in history_page.json()["turns"] if turn["turnId"] == 3
        )
        assert turn_three["plotInjections"] == []

        history = client.get("/play-api/v1/sessions/s_forest001/history")
        assert history.status_code == 200
        assert history.json()[0]["outcome"]["outcomeCode"] == "success_with_cost"
        assert history.json()[0]["plotInjections"] == turn_one["plotInjections"]

        turn = client.get("/play-api/v1/sessions/s_forest001/turns/1")
        assert turn.status_code == 200
        assert turn.json()["plotInjections"] == turn_one["plotInjections"]
        assert set(turn.json()["plotInjections"][0]) == {"eventTitle", "directive"}


def test_main_llm_endpoints_expose_camel_case_and_forward_selection(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)

    with TestClient(app) as client:
        options = client.get("/play-api/v1/llm/main-agent/options")
        story_default = client.get(
            "/play-api/v1/workspaces/demo_workspace/stories/1/main-llm"
        )
        story_selected = client.patch(
            "/play-api/v1/workspaces/demo_workspace/stories/1/main-llm",
            json={"providerKey": "alternate_chat"},
        )
        session_inherits = client.get(
            "/play-api/v1/sessions/s_forest001/main-llm"
        )
        session_selected = client.patch(
            "/play-api/v1/sessions/s_forest001/main-llm",
            json={"providerKey": "config_chat"},
        )
        session_cleared = client.patch(
            "/play-api/v1/sessions/s_forest001/main-llm",
            json={"providerKey": None},
        )
        empty_update = client.patch(
            "/play-api/v1/sessions/s_forest001/main-llm",
            json={},
        )
        missing_session = client.get(
            "/play-api/v1/sessions/missing/main-llm"
        )

    assert options.status_code == 200
    assert options.json()["configDefaultProviderKey"] == "config_chat"
    assert [item["providerKey"] for item in options.json()["options"]] == [
        "config_chat",
        "alternate_chat",
    ]
    assert set(options.json()["options"][0]) == {
        "providerKey",
        "backend",
        "model",
        "contextWindow",
    }
    assert story_default.status_code == 200
    assert story_default.json()["effectiveSource"] == "config"
    assert story_selected.status_code == 200
    assert story_selected.json()["storyProviderKey"] == "alternate_chat"
    assert story_selected.json()["effectiveSource"] == "story"
    assert session_inherits.status_code == 200
    assert session_inherits.json()["effectiveSource"] == "story"
    assert session_selected.status_code == 200
    assert session_selected.json()["sessionProviderKey"] == "config_chat"
    assert session_selected.json()["effectiveSource"] == "session"
    assert session_cleared.status_code == 200
    assert session_cleared.json()["sessionProviderKey"] is None
    assert session_cleared.json()["effectiveSource"] == "story"
    assert empty_update.status_code == 422
    assert missing_session.status_code == 404
    assert fake_agent.calls == [
        ("main-llm-options",),
        ("get-story-main-llm", "demo_workspace", "1"),
        ("set-story-main-llm", "demo_workspace", "1", "alternate_chat"),
        ("get-session-main-llm", "s_forest001"),
        ("set-session-main-llm", "s_forest001", "config_chat"),
        ("set-session-main-llm", "s_forest001", ""),
    ]


def test_main_llm_endpoint_preserves_agent_validation_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    monkeypatch.setattr(agent_client, "_client", _RejectingMainLLMAgentClient())

    with TestClient(app) as client:
        response = client.patch(
            "/play-api/v1/sessions/s_forest001/main-llm",
            json={"providerKey": "removed_chat"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "provider is not selectable"


def test_history_page_endpoint_returns_turn_window(
    tmp_path,
    monkeypatch,
    start_play_client,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    reset_delete_confirmation_tokens()
    gateway = get_data_service_gateway()
    session_id = "s_forest001"
    gateway.messages.clear(session_id)
    for turn_id in range(1, 6):
        gateway.messages.append(session_id, "user", f"u{turn_id}", turn_id=turn_id, seq_in_turn=1)
        gateway.messages.append(session_id, "assistant", f"a{turn_id}", turn_id=turn_id, seq_in_turn=2)

    client = start_play_client()

    latest = client.get(f"/play-api/v1/sessions/{session_id}/history-page", params={"limit": 2})
    before = client.get(
        f"/play-api/v1/sessions/{session_id}/history-page",
        params={"limit": 2, "beforeTurnId": 4},
    )
    after = client.get(
        f"/play-api/v1/sessions/{session_id}/history-page",
        params={"limit": 2, "afterTurnId": 2},
    )

    assert latest.status_code == 200
    assert [turn["turnId"] for turn in latest.json()["turns"]] == [4, 5]
    assert latest.json()["startTurnId"] == 4
    assert latest.json()["endTurnId"] == 5
    assert latest.json()["latestTurnId"] == 5
    assert latest.json()["hasBefore"] is True
    assert latest.json()["hasAfter"] is False
    assert latest.json()["limit"] == 2
    assert latest.json()["turns"][0]["messages"][0]["content"] == "u4"

    assert before.status_code == 200
    assert [turn["turnId"] for turn in before.json()["turns"]] == [2, 3]
    assert before.json()["hasBefore"] is True
    assert before.json()["hasAfter"] is True

    assert after.status_code == 200
    assert [turn["turnId"] for turn in after.json()["turns"]] == [3, 4]
    assert after.json()["hasBefore"] is True
    assert after.json()["hasAfter"] is True

    exact = client.get(f"/play-api/v1/sessions/{session_id}/turns/3")
    missing = client.get(f"/play-api/v1/sessions/{session_id}/turns/99")

    assert exact.status_code == 200
    assert exact.json()["turnId"] == 3
    assert [message["content"] for message in exact.json()["messages"]] == ["u3", "a3"]
    assert missing.status_code == 404
    assert missing.json()["detail"] == "turn not found"


def test_history_page_endpoint_validates_query_and_rejects_dirty_writes(
    tmp_path,
    monkeypatch,
    start_play_client,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    reset_delete_confirmation_tokens()
    gateway = get_data_service_gateway()
    session_id = "s_forest001"
    gateway.messages.clear(session_id)
    first = gateway.messages.append(session_id, "user", "u1", turn_id=1, seq_in_turn=1)
    gateway.messages.append(session_id, "assistant", "a1", turn_id=1, seq_in_turn=2)

    client = start_play_client()

    both = client.get(
        f"/play-api/v1/sessions/{session_id}/history-page",
        params={"beforeTurnId": 3, "afterTurnId": 1},
    )
    too_large = client.get(f"/play-api/v1/sessions/{session_id}/history-page", params={"limit": 201})

    assert both.status_code == 400
    assert too_large.status_code == 422
    with pytest.raises(ValueError):
        gateway.messages.update(first.id, seq_in_turn=0)


def test_session_summary_endpoints_return_previews_and_lazy_detail(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    reset_delete_confirmation_tokens()
    gateway = get_data_service_gateway()
    session_id = "s_forest001"
    session_root = gateway.catalog.get_session_runtime_dir(session_id)
    summaries = session_root / "summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / "overall.md").write_text(
        "---\ntype: overall\nlast_batch_id: 2\n---\n\n# 北境追踪\n\n线索已经汇合。",
        encoding="utf-8",
    )
    (summaries / "001-start.md").write_text(
        "---\nbatch_id: 1\ntitle: 起点\ntime: 清晨\nlocation: 林地\ncharacters:\n  - Bob\n---\n\n发现足迹。",
        encoding="utf-8",
    )
    (summaries / "002-gate.md").write_text(
        "---\nbatch_id: 2\ntitle: 石门\ntime: 正午\nlocation: 遗迹\ncharacters:\n  - Bob\n  - Alice\n---\n\n抵达石门。",
        encoding="utf-8",
    )
    gateway.messages.clear(session_id)
    rows = []
    for turn_id in range(1, 5):
        rows.append(
            gateway.messages.append(
                session_id,
                "user",
                f"u{turn_id}",
                turn_id=turn_id,
                seq_in_turn=1,
            )
        )
        rows.append(
            gateway.messages.append(
                session_id,
                "assistant",
                f"a{turn_id}",
                turn_id=turn_id,
                seq_in_turn=2,
            )
        )
    gateway.messages.mark_summary_processed(
        session_id,
        [row.id for row in rows[:4]],
        batch_id=1,
    )
    gateway.messages.mark_summary_processed(
        session_id,
        [row.id for row in rows[4:]],
        batch_id=2,
    )

    with TestClient(app) as client:
        index_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries"
        )
        detail_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries/2"
        )
        overall_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries/overall"
        )
        missing_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries/999"
        )
        invalid_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries/not-a-batch"
        )
        (summaries / "overall.md").unlink()
        batch_only_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries"
        )
        for path in summaries.glob("*.md"):
            path.unlink()
        empty_response = client.get(
            f"/play-api/v1/sessions/{session_id}/summaries"
        )
        missing_session_response = client.get(
            "/play-api/v1/sessions/missing/summaries"
        )

    assert index_response.status_code == 200
    payload = index_response.json()
    assert payload["overall"]["title"] == "北境追踪"
    assert payload["overall"]["lastBatchId"] == 2
    assert payload["overall"]["turnStart"] == 1
    assert payload["overall"]["turnEnd"] == 4
    assert [item["batchId"] for item in payload["batches"]] == [2, 1]
    assert payload["batches"][0]["characters"] == ["Bob", "Alice"]
    assert payload["batches"][0]["turnStart"] == 3
    assert payload["batches"][0]["turnEnd"] == 4
    assert "markdown" not in payload["batches"][0]
    assert detail_response.status_code == 200
    assert detail_response.json()["markdown"] == "抵达石门。"
    assert overall_response.status_code == 200
    assert overall_response.json()["markdown"] == "线索已经汇合。"
    assert missing_response.status_code == 404
    assert invalid_response.status_code == 404
    assert batch_only_response.status_code == 200
    assert batch_only_response.json()["overall"] is None
    assert len(batch_only_response.json()["batches"]) == 2
    assert empty_response.status_code == 200
    assert empty_response.json() == {"overall": None, "batches": []}
    assert missing_session_response.status_code == 404


def test_session_story_memory_endpoint_pages_filters_and_reports_stats(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    reset_delete_confirmation_tokens()
    gateway = get_data_service_gateway()
    story_memory = StoryMemoryApplicationService(gateway.story_memory)
    session_id = "s_forest001"
    story_memory.clear(session_id)
    gateway.messages.clear(session_id)

    first_turn = [
        gateway.messages.append(session_id, "user", "发现门锁。", turn_id=1, seq_in_turn=1),
        gateway.messages.append(session_id, "assistant", "门锁上有月纹。", turn_id=1, seq_in_turn=2),
    ]
    second_turn = [
        gateway.messages.append(session_id, "user", "检查月纹。", turn_id=2, seq_in_turn=1),
        gateway.messages.append(session_id, "assistant", "月纹指向北塔。", turn_id=2, seq_in_turn=2),
    ]
    first = story_memory.add_details_and_mark_processed(
        session_id,
        [{
            "text": "门锁带有月纹。",
            "turn_id": 1,
            "memory_kind": "event",
            "evidence_message_ids": [first_turn[1].id],
        }],
        message_ids=[row.id for row in first_turn],
    )[0]
    second = story_memory.add_detail(
        session_id,
        "月纹指向北塔。",
        turn_id=2,
        memory_kind="clue",
        epistemic_status="confirmed",
        salience=0.9,
        dream_processed=True,
        evidence_message_ids=[second_turn[1].id],
    )

    with TestClient(app) as client:
        page_response = client.get(
            f"/play-api/v1/sessions/{session_id}/story-memories",
            params={"pageSize": 1},
        )
        filter_response = client.get(
            f"/play-api/v1/sessions/{session_id}/story-memories",
            params={"memoryKind": "event", "dreamProcessed": "false"},
        )
        missing_response = client.get(
            "/play-api/v1/sessions/missing/story-memories"
        )
        invalid_kind_response = client.get(
            f"/play-api/v1/sessions/{session_id}/story-memories",
            params={"memoryKind": "invalid"},
        )
        invalid_page_response = client.get(
            f"/play-api/v1/sessions/{session_id}/story-memories",
            params={"page": 0},
        )

    assert page_response.status_code == 200
    payload = page_response.json()
    assert payload["page"] == 1
    assert payload["pageSize"] == 1
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [second.id]
    assert payload["items"][0]["evidence"] == [
        {"messageId": second_turn[1].id, "turnId": 2}
    ]
    assert payload["stats"] == {
        "totalFacts": 2,
        "dreamProcessedFacts": 1,
        "pendingDreamFacts": 1,
        "unprocessedSourceTurns": 1,
        "latestUpdatedAt": payload["stats"]["latestUpdatedAt"],
    }
    assert payload["stats"]["latestUpdatedAt"]
    assert filter_response.status_code == 200
    assert [item["id"] for item in filter_response.json()["items"]] == [first.id]
    assert missing_response.status_code == 404
    assert invalid_kind_response.status_code == 422
    assert invalid_page_response.status_code == 422


def test_stream_endpoint_uses_play_sse_envelope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    fake_agent = _StreamingAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    reset_delete_confirmation_tokens()

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/play-api/v1/sessions/s_forest001/stream",
            json={"text": "hello", "requestId": "req-play"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    events = _sse_payloads(body)
    assert [event["type"] for event in events] == [
        PlaySSEType.TURN_STARTED.value,
        PlaySSEType.TEXT_DELTA.value,
        PlaySSEType.TOOL_CALL.value,
        PlaySSEType.TOOL_RESULT.value,
        PlaySSEType.TURN_COMPLETED.value,
    ]
    assert [event["eventId"] for event in events] == [1, 2, 3, 4, 5]
    assert {event["schemaVersion"] for event in events} == {PLAY_SSE_SCHEMA_VERSION}
    assert {event["sessionId"] for event in events} == {"s_forest001"}
    assert len({event["turnId"] for event in events}) == 1
    assert str(events[0]["turnId"]).startswith("turn_s_forest001_")
    assert events[0]["payload"] == {"mode": "neutral"}
    assert events[1]["payload"] == {"text": "你推开门"}
    assert events[2]["payload"] == {"toolName": "roll", "toolArguments": "1d20"}
    assert events[3]["payload"] == {"toolName": "roll", "resultPreview": "18"}
    assert events[4]["payload"] == {
        "text": "你推开门。",
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 4,
            "total_tokens": 7,
            "cached_tokens": 1,
            "source": "provider_usage",
            "accuracy": "accurate",
            "createdAt": "2026-01-01T00:00:00+00:00",
        },
        "model": "test-model",
        "finishReason": "stop",
        "durationMs": 12.3,
        "committedTurnId": 4,
    }
    assert ("stream", "s_forest001", "hello", "req-play") in fake_agent.calls


def test_stream_endpoint_keeps_source_envelope_and_exposes_active_session(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _StreamingAgentClient())
    reset_delete_confirmation_tokens()

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/play-api/v1/sessions/s_forest001/stream",
            json={"text": "/session_switch s_target"},
        ) as response:
            body = "".join(response.iter_text())

    completed = _sse_payloads(body)[-1]
    assert completed["sessionId"] == "s_forest001"
    assert completed["payload"]["activeSession"] == "s_target"


def test_turn_endpoint_exposes_active_session_without_changing_source_envelope(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    monkeypatch.setattr(agent_client, "_client", _FakeAgentClient())
    reset_delete_confirmation_tokens()

    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/sessions/s_forest001/turn",
            json={"text": "/session_switch s_target"},
        )

    assert response.status_code == 200
    assert response.json()["sessionId"] == "s_forest001"
    assert response.json()["activeSession"] == "s_target"


def test_stop_endpoint_forwards_request_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    reset_delete_confirmation_tokens()

    with TestClient(app) as client:
        response = client.post(
            "/play-api/v1/sessions/s_forest001/stop",
            json={"requestId": "req-play"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == TurnCancelStatus.CANCELLED.value
    assert response.json()["requestId"] == "req-play"
    assert ("stop", "s_forest001", "req-play") in fake_agent.calls


def test_delete_session_endpoint_forwards_to_agent_owner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    reset_delete_confirmation_tokens()

    with TestClient(app) as client:
        response = client.delete("/play-api/v1/sessions/s_forest001")

    assert response.status_code == 200
    assert response.json() == {
        "status": "deleted",
        "sessionId": "s_forest001",
        "runtimeCleanup": "deleted",
    }
    assert ("delete-session", "s_forest001") in fake_agent.calls


def test_provisioning_session_is_hidden_from_play_session_and_status_routes(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    gateway = get_data_service_gateway()
    derivations = SessionDerivationService(gateway.sessions)
    job = derivations.create_job("s_forest001", 1)
    derivations.start_job(job.id)
    target = derivations.materialize_target(job.id).session
    table_id = gateway.status.list_tables(target.id)[0].id

    with TestClient(app) as client:
        responses = [
            client.get(f"/play-api/v1/sessions/{target.id}"),
            client.get(f"/play-api/v1/sessions/{target.id}/status-tables"),
            client.post(
                f"/play-api/v1/sessions/{target.id}/status-tables",
                json={"name": "hidden", "rows": []},
            ),
            client.patch(
                f"/play-api/v1/sessions/{target.id}/status-tables/{table_id}",
                json={"name": "hidden"},
            ),
            client.delete(
                f"/play-api/v1/sessions/{target.id}/status-tables/{table_id}"
            ),
        ]

    assert all(response.status_code == 404 for response in responses)
    assert gateway.catalog.get_session(target.id) is not None


def test_play_api_contracts(
    tmp_path,
    monkeypatch,
    start_play_client,
) -> None:
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_world.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    fake_agent = _FakeAgentClient()
    monkeypatch.setattr(agent_client, "_client", fake_agent)
    reset_delete_confirmation_tokens()
    client = start_play_client()
    demo_session_id = "s_forest001"

    workspaces = client.get("/play-api/v1/workspaces")
    assert workspaces.status_code == 200
    assert {workspace["id"] for workspace in workspaces.json()} == {"demo_workspace"}

    stories = client.get("/play-api/v1/workspaces/demo_workspace/stories")
    assert stories.status_code == 200
    assert stories.json()[0]["title"] == "北境森林 Demo"
    assert stories.json()[0]["storyPrompt"] == "用于验证 Story 直属角色卡、世界书、状态表与 Session 运行时副本的演示故事。"
    assert "北境森林的霜雾" in stories.json()[0]["openings"][0]["message"]
    assert "description" not in stories.json()[0]
    assert client.get("/play-api/v1/workspaces/missing/stories").status_code == 404
    new_story = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories",
        json={
            "title": "雾港钟楼",
            "summary": "潮湿港口的失踪案。",
            "storyPrompt": "固定故事提示词，仅存储展示。",
            "openings": [{"title": "钟声", "message": "你听见远处钟声。"}],
        },
    )
    assert new_story.status_code == 200
    assert new_story.json()["workspace"] == "demo_workspace"
    assert new_story.json()["title"] == "雾港钟楼"
    assert new_story.json()["summary"] == "潮湿港口的失踪案。"
    assert new_story.json()["storyPrompt"] == "固定故事提示词，仅存储展示。"
    assert new_story.json()["openings"][0]["title"] == "钟声"
    assert new_story.json()["openings"][0]["message"] == "你听见远处钟声。"
    templated_story = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories",
        json={
            "title": "角色模板故事",
            "storyPrompt": "当前玩家是 {USER_PLAY_ROLE_NAME}。",
            "openings": [{"title": "欢迎", "message": "欢迎，{USER_PLAY_ROLE_NAME}。"}],
        },
    )
    assert templated_story.status_code == 200
    assert templated_story.json()["storyPrompt"] == "当前玩家是 {USER_PLAY_ROLE_NAME}。"
    assert templated_story.json()["openings"][0]["message"] == "欢迎，{USER_PLAY_ROLE_NAME}。"
    invalid_template = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories",
        json={
            "title": "非法模板",
            "openings": [{"title": "坏模板", "message": "欢迎，{UNKNOWN_ROLE}。"}],
        },
    )
    assert invalid_template.status_code == 422
    assert "UNKNOWN_ROLE" in invalid_template.text
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
    assert patched_story.json()["openings"][0]["message"] == "你听见远处钟声。"
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
        json={
            "workspaceId": "demo_workspace",
            "storyId": 1,
            "title": "新会话",
            "description": "经 Agent 创建",
        },
    )
    assert created.status_code == 200
    assert created.json()["id"].startswith("s_")
    assert len(created.json()["id"]) == 12
    assert created.json()["id"][2:].isalnum()
    assert created.json()["title"] == "新会话"
    assert created.json()["description"] == "经 Agent 创建"
    assert created.json()["playerCharacterStatus"] == "invalid"
    assert created.json()["playerCharacter"] is None

    scene = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/scene",
    )
    assert scene.status_code == 200
    assert scene.json()["location"] == "北境森林·石林·祭坛下层回廊"
    assert scene.json()["time"] == "第 1 年 1 月 1 日 9 时 20 分"
    assert scene.json()["presentCharacters"] == ["Bob", "Alice", "灰烬守门人"]

    commands = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/commands",
    )
    assert commands.status_code == 200
    assert commands.json() == [
        {
            "name": "/continue",
            "description": "继续叙事",
            "detail": "用法：/continue。",
            "mode": "slash",
        },
        {
            "name": "/check_dc",
            "description": "手动 DC 检定",
            "detail": "用法：/check_dc <expr> dc=<n> [reason]。",
            "mode": "slash",
        },
    ]

    context_preview = client.get(
        f"/play-api/v1/sessions/{demo_session_id}/context-preview",
    )
    assert context_preview.status_code == 200
    assert context_preview.json()["formatVersion"] == "context-preview.v1"
    assert context_preview.json()["sessionId"] == demo_session_id
    assert context_preview.json()["totals"]["tokenCount"] == 3
    assert context_preview.json()["usageEstimate"]["usedTokens"] == 3
    assert context_preview.json()["usageEstimate"]["contextLimit"] == 100
    assert context_preview.json()["layers"][0]["content"] == "## Fixed"
    assert context_preview.json()["messages"][0]["content"] == "## Fixed"

    turn = client.post(
        f"/play-api/v1/sessions/{demo_session_id}/turn",
        json={
            "text": "hello",
        },
    )
    assert turn.status_code == 200
    assert turn.json()["usage"]["prompt_tokens"] == 9
    assert turn.json()["usage"]["source"] == "provider_usage"
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
    assert (
        "create-session",
        "demo_workspace",
        "1",
        "新会话",
        "经 Agent 创建",
    ) in fake_agent.calls

    character_base = "/play-api/v1/workspaces/demo_workspace/stories/1/characters"
    characters = client.get(character_base)
    assert characters.status_code == 200
    assert {character["name"] for character in characters.json()} >= {"Bob", "Alice"}
    assert characters.json()[0]["workspaceId"] == "demo_workspace"
    assert isinstance(characters.json()[0]["details"], list)
    assert isinstance(characters.json()[0]["metadata"], dict)
    assert "mountId" not in characters.json()[0]
    assert client.get(
        "/play-api/v1/workspaces/missing/stories/1/characters"
    ).status_code == 404
    assert client.get(
        "/play-api/v1/workspaces/demo_workspace/characters"
    ).status_code == 404

    new_character = client.post(
        character_base,
        json={
            "name": "守夜人伊凡",
            "description": "灯塔旧守夜人，知道潮汐与失火名单。",
            "sortOrder": 37,
            "metadata": {"ui": {"displayVersion": "v1.0.0", "roleLabel": "NPC"}},
        },
    )
    assert new_character.status_code == 200
    assert new_character.json()["name"] == "守夜人伊凡"
    assert new_character.json()["description"] == "灯塔旧守夜人，知道潮汐与失火名单。"
    assert new_character.json()["sortOrder"] == 37
    assert new_character.json()["metadata"]["ui"]["roleLabel"] == "NPC"
    duplicate_character = client.post(
        character_base,
        json={"name": "守夜人伊凡"},
    )
    assert duplicate_character.status_code == 409
    assert duplicate_character.json()["detail"] == (
        "Character write violated persisted constraints"
    )
    assert client.post(
        character_base,
        json={"name": ""},
    ).status_code == 422

    patched_character = client.patch(
        f"{character_base}/{new_character.json()['id']}",
        json={
            "description": "谨慎而且口风很紧的守夜人。",
            "metadata": {"ui": {"displayVersion": "v1.0.1"}},
        },
    )
    assert patched_character.status_code == 200
    assert patched_character.json()["description"] == "谨慎而且口风很紧的守夜人。"
    assert patched_character.json()["version"] == 2
    assert client.patch(
        f"/play-api/v1/workspaces/missing/stories/1/characters/{new_character.json()['id']}",
        json={"name": "Nope"},
    ).status_code == 404

    new_detail = client.post(
        f"{character_base}/{new_character.json()['id']}/details",
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
    assert client.post(
        f"{character_base}/{new_character.json()['id']}/details",
        json={"name": "禁忌话题"},
    ).status_code == 409

    patched_detail = client.patch(
        f"{character_base}/{new_character.json()['id']}/details/{new_detail.json()['id']}",
        json={"content": "只在午夜后透露线索。", "tags": ["秘密"], "sortOrder": 20},
    )
    assert patched_detail.status_code == 200
    assert patched_detail.json()["content"] == "只在午夜后透露线索。"
    assert patched_detail.json()["tags"] == ["秘密"]
    assert patched_detail.json()["sortOrder"] == 20
    assert patched_detail.json()["version"] == 2
    assert client.patch(
        f"{character_base}/{new_character.json()['id']}/details/{new_detail.json()['id']}",
        json={"name": ""},
    ).status_code == 422
    assert client.patch(
        f"{character_base}/{new_character.json()['id']}/details/99999",
        json={"name": "Nope"},
    ).status_code == 404

    story_characters = client.get("/play-api/v1/workspaces/demo_workspace/stories/1/characters")
    assert story_characters.status_code == 200
    assert "mountId" not in story_characters.json()[0]
    assert client.get("/play-api/v1/workspaces/demo_workspace/stories/999/characters").status_code == 404
    bob = next(character for character in story_characters.json() if character["name"] == "Bob")
    opening_options = client.get(
        f"/play-api/v1/sessions/{created.json()['id']}/opening-options",
        params={"playerCharacterId": bob["id"]},
    )
    assert opening_options.status_code == 200
    assert opening_options.json()["canSelectOpening"] is True
    assert opening_options.json()["defaultOpeningId"] == opening_options.json()["items"][0]["id"]
    assert "Bob" in opening_options.json()["items"][0]["renderedMessage"]
    selected_opening_id = opening_options.json()["defaultOpeningId"]
    bound_created = client.patch(
        f"/play-api/v1/sessions/{created.json()['id']}/player-character",
        json={"playerCharacterId": bob["id"], "storyOpeningId": selected_opening_id},
    )
    assert bound_created.status_code == 200
    assert bound_created.json()["playerCharacterStatus"] == "bound"
    assert bound_created.json()["playerCharacter"]["name"] == "Bob"
    assert bound_created.json()["storyOpeningId"] == selected_opening_id
    assert (
        "bind-player-character",
        created.json()["id"],
        str(bob["id"]),
        str(selected_opening_id),
    ) in agent_client.get_agent_client().calls
    invalid_bind = client.patch(
        f"/play-api/v1/sessions/{created.json()['id']}/player-character",
        json={"playerCharacterId": 99999},
    )
    assert invalid_bind.status_code == 422

    same_name_other_story = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/2/characters",
        json={"name": "守夜人伊凡"},
    )
    assert same_name_other_story.status_code == 200
    assert same_name_other_story.json()["storyId"] == 2
    assert same_name_other_story.json()["id"] != new_character.json()["id"]
    assert client.post(
        f"{character_base}/{new_character.json()['id']}/mount"
    ).status_code == 404

    delete_character_target = client.post(
        character_base,
        json={"name": "待删除角色", "description": "临时角色"},
    )
    assert delete_character_target.status_code == 200
    delete_character_detail = client.post(
        f"{character_base}/{delete_character_target.json()['id']}/details",
        json={"name": "临时细节", "content": "tmp"},
    )
    assert delete_character_detail.status_code == 200
    gateway = get_data_service_gateway()
    SessionRoleService(gateway.sessions).bind_player_character(
        created.json()["id"],
        delete_character_target.json()["id"],
    )
    deleted_character = client.delete(
        f"{character_base}/{delete_character_target.json()['id']}"
    )
    assert deleted_character.status_code == 204
    invalidated_session = client.get(
        f"/play-api/v1/sessions/{created.json()['id']}"
    )
    assert invalidated_session.status_code == 200
    assert invalidated_session.json()["playerCharacterStatus"] == "invalid"
    assert client.patch(
        f"{character_base}/{delete_character_target.json()['id']}",
        json={"name": "Gone"},
    ).status_code == 404
    assert client.delete(
        f"{character_base}/{new_character.json()['id']}/details/{new_detail.json()['id']}"
    ).status_code == 204
    assert client.delete(
        f"{character_base}/{new_character.json()['id']}/details/{new_detail.json()['id']}"
    ).status_code == 404

    lorebook_base = "/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries"
    lorebooks = client.get(lorebook_base)
    assert lorebooks.status_code == 200
    assert {entry["name"] for entry in lorebooks.json()} >= {"炎心之木", "圆形封印祭坛"}
    assert lorebooks.json()[0]["workspaceId"] == "demo_workspace"
    assert isinstance(lorebooks.json()[0]["tags"], list)
    assert isinstance(lorebooks.json()[0]["metadata"], dict)
    assert "mountId" not in lorebooks.json()[0]
    assert client.get(
        "/play-api/v1/workspaces/missing/stories/1/lorebook-entries"
    ).status_code == 404
    assert client.get(
        "/play-api/v1/workspaces/demo_workspace/lorebook-entries"
    ).status_code == 404

    new_entry = client.post(
        lorebook_base,
        json={
            "name": "潮汐信号",
            "content": "海岸线上古老的信号系统。",
            "description": "用于测试世界书管理接口。",
            "tags": ["规则", "组织"],
            "sortOrder": 45,
            "metadata": {"ui": {"displayVersion": "v1.0.0"}},
        },
    )
    assert new_entry.status_code == 200
    assert new_entry.json()["name"] == "潮汐信号"
    assert new_entry.json()["tags"] == ["规则", "组织"]
    assert new_entry.json()["sortOrder"] == 45
    assert new_entry.json()["metadata"]["ui"]["displayVersion"] == "v1.0.0"
    duplicate_lorebook = client.post(
        lorebook_base,
        json={"name": "潮汐信号"},
    )
    assert duplicate_lorebook.status_code == 409
    assert duplicate_lorebook.json()["detail"] == (
        "Lorebook entry write violated persisted constraints"
    )
    assert client.post(
        lorebook_base,
        json={"name": ""},
    ).status_code == 422

    patched = client.patch(
        f"{lorebook_base}/{new_entry.json()['id']}",
        json={"description": "更新后的短描述", "tags": ["地点"]},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "更新后的短描述"
    assert patched.json()["tags"] == ["地点"]
    assert patched.json()["version"] == 2
    assert client.patch(
        f"{lorebook_base}/{new_entry.json()['id']}",
        json={"name": ""},
    ).status_code == 422
    assert client.patch(
        f"/play-api/v1/workspaces/missing/stories/1/lorebook-entries/{new_entry.json()['id']}",
        json={"name": "Nope"},
    ).status_code == 404

    story_lorebooks = client.get("/play-api/v1/workspaces/demo_workspace/stories/1/lorebook-entries")
    assert story_lorebooks.status_code == 200
    assert "mountId" not in story_lorebooks.json()[0]
    assert client.get("/play-api/v1/workspaces/demo_workspace/stories/999/lorebook-entries").status_code == 404

    same_name_other_story = client.post(
        "/play-api/v1/workspaces/demo_workspace/stories/2/lorebook-entries",
        json={"name": "潮汐信号"},
    )
    assert same_name_other_story.status_code == 200
    assert same_name_other_story.json()["storyId"] == 2
    assert same_name_other_story.json()["id"] != new_entry.json()["id"]
    assert client.post(
        f"{lorebook_base}/{new_entry.json()['id']}/mount"
    ).status_code == 404

    delete_target = client.post(
        lorebook_base,
        json={
            "name": "待删除条目",
            "content": "临时内容",
            "tags": ["tmp"],
        },
    )
    assert delete_target.status_code == 200
    deleted_entry = client.delete(
        f"{lorebook_base}/{delete_target.json()['id']}"
    )
    assert deleted_entry.status_code == 204
    assert client.patch(
        f"{lorebook_base}/{delete_target.json()['id']}",
        json={"name": "Gone"},
    ).status_code == 404

    status_base = "/play-api/v1/workspaces/demo_workspace/stories/1/status-tables"
    story_status_tables = client.get(status_base)
    assert story_status_tables.status_code == 200
    assert {item["statusKind"] for item in story_status_tables.json()} == {"scene", "normal"}
    assert all("mountOrigin" not in item for item in story_status_tables.json())
    assert client.get(
        "/play-api/v1/workspaces/missing/stories/1/status-tables"
    ).status_code == 404
    assert client.get(
        "/play-api/v1/workspaces/demo_workspace/status-templates"
    ).status_code == 404
    assert client.get(
        "/play-api/v1/workspaces/demo_workspace/stories/1/status-mounts"
    ).status_code == 404
    scene_story_table = next(
        item for item in story_status_tables.json() if item["statusKind"] == "scene"
    )

    new_story_status = client.post(
        status_base,
        json={
            "name": "测试状态表",
            "statusKind": "normal",
            "keyColumn": "属性",
            "valueColumn": "值",
            "rows": [
                {
                    "key": "钟声",
                    "value": "未响",
                    "runtimeKeyLocked": False,
                    "updateRule": "钟楼被明确敲响时更新",
                },
                {
                    "key": "长期警戒",
                    "value": "低",
                },
            ],
            "metadata": {"ui": {"compact": True}},
        },
    )
    assert new_story_status.status_code == 200
    assert new_story_status.json()["name"] == "测试状态表"
    assert new_story_status.json()["storyId"] == 1
    assert new_story_status.json()["rows"][0]["key"] == "钟声"
    assert new_story_status.json()["rows"][0]["updateRule"] == "钟楼被明确敲响时更新"
    assert "updateFrequency" not in new_story_status.json()["rows"][0]
    assert "deferredIntervalTurns" not in new_story_status.json()["rows"][1]
    assert new_story_status.json()["metadata"]["ui"]["compact"] is True
    assert client.post(
        status_base,
        json={
            "name": "旧频率字段",
            "rows": [{
                "key": "事件",
                "value": "未发生",
                "updateFrequency": "realtime",
            }],
        },
    ).status_code == 422
    assert client.post(
        status_base,
        json={
            "name": "隐藏写权限字段",
            "rows": [{
                "key": "位置",
                "value": "林地",
                "llmWritable": False,
            }],
        },
    ).status_code == 422
    scene_rule_patch = client.patch(
        f"{status_base}/{scene_story_table['id']}",
        json={
            "rows": [{
                "key": "位置",
                "value": "林地",
                "updateRule": "角色抵达林地时更新",
            }],
        },
    )
    assert scene_rule_patch.status_code == 200
    assert scene_rule_patch.json()["rows"][0]["updateRule"] == "角色抵达林地时更新"

    patched_story_status = client.patch(
        f"{status_base}/{new_story_status.json()['id']}",
        json={
            "description": "更新后的状态表",
            "rows": [{"key": "钟声", "value": "响起", "runtimeKeyLocked": True}],
        },
    )
    assert patched_story_status.status_code == 200
    assert patched_story_status.json()["description"] == "更新后的状态表"
    assert patched_story_status.json()["rows"][0]["runtimeKeyLocked"] is True
    converted_story_status = client.patch(
        f"{status_base}/{new_story_status.json()['id']}",
        json={"statusKind": "scene"},
    )
    assert converted_story_status.status_code == 200
    assert converted_story_status.json()["statusKind"] == "scene"

    character_story_status = client.post(
        status_base,
        json={
            "name": "角色私有状态",
            "statusKind": "normal",
            "rows": [{"key": "姿态", "value": "观察"}],
            "storyCharacterId": bob["id"],
        },
    )
    assert character_story_status.status_code == 200
    assert character_story_status.json()["storyCharacterId"] == bob["id"]

    source_for_copy = client.post(
        status_base,
        json={
            "name": "删除源后保留副本",
            "rows": [{"key": "标记", "value": "保留"}],
        },
    )
    assert source_for_copy.status_code == 200
    copy_session = client.post(
        "/play-api/v1/sessions",
        json={
            "workspaceId": "demo_workspace",
            "storyId": 1,
            "title": "状态源删除测试",
        },
    )
    assert copy_session.status_code == 200
    copied_tables = client.get(
        f"/play-api/v1/sessions/{copy_session.json()['id']}/status-tables"
    )
    copied_source = next(
        item
        for item in copied_tables.json()
        if item["name"] == "删除源后保留副本"
    )
    assert copied_source["sourceStoryStatusTableId"] == source_for_copy.json()["id"]
    assert client.delete(
        f"{status_base}/{source_for_copy.json()['id']}"
    ).status_code == 204
    retained_tables = client.get(
        f"/play-api/v1/sessions/{copy_session.json()['id']}/status-tables"
    )
    retained_copy = next(
        item
        for item in retained_tables.json()
        if item["name"] == "删除源后保留副本"
    )
    assert retained_copy["origin"] == "story_copy"
    assert retained_copy["sourceStoryStatusTableId"] is None
    assert client.delete(
        f"{status_base}/{character_story_status.json()['id']}"
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

    ops_entry = client.post(
        lorebook_base,
        json={"name": "运维条目删除", "content": "ops"},
    )
    assert ops_entry.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_entry.json()['id']}"
    ).status_code == 409
    ops_entry_token = client.post(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_entry.json()['id']}/delete-token"
    )
    assert ops_entry_token.status_code == 200
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_entry.json()['id']}",
        headers={"X-Delete-Confirm-Token": ops_entry_token.json()["token"]},
    ).status_code == 204
    assert client.delete(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_entry.json()['id']}",
        headers={"X-Delete-Confirm-Token": ops_entry_token.json()["token"]},
    ).status_code == 409
    assert client.post(
        f"/play-api/v1/ops/workspaces/demo_workspace/stories/1/lorebook-entries/{ops_entry.json()['id']}/delete-token"
    ).status_code == 404
