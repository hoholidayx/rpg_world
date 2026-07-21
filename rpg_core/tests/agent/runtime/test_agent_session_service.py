from __future__ import annotations

from types import SimpleNamespace

import pytest

from commons.scene_time import SceneTime
from rpg_core.agent.runtime.session import AgentSessionService
from rpg_core.context.models import Message, Role
from rpg_core.rp_modules.plot_scheduler import PlotScheduleLedgerService
from rpg_core.session import SessionManager
from rpg_core.session.reset import SessionResetService
from rpg_core.session.role import SessionRoleService
from rpg_data import models
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


class _StatusManager:
    def __init__(self) -> None:
        self.boundaries: list[int] = []

    def clamp_deferred_progress(self, max_turn_id: int) -> int:
        self.boundaries.append(max_turn_id)
        return 0


class _UnusedSessionData:
    @staticmethod
    def list_messages(_session_id: str) -> list[models.SessionMessage]:
        return []

    @staticmethod
    def resolve_session_runtime_dir(_session_id: str):  # noqa: ANN201
        raise AssertionError("runtime directory is not used by this test")


def test_history_truncate_clamps_deferred_progress() -> None:
    session = SessionManager(history_enabled=False)
    session.replace_history([
        Message(Role.USER, "第一轮", turn_id=1, seq_in_turn=1),
        Message(Role.ASSISTANT, "第一轮回复", turn_id=1, seq_in_turn=2),
        Message(Role.USER, "第二轮", turn_id=2, seq_in_turn=1),
        Message(Role.ASSISTANT, "第二轮回复", turn_id=2, seq_in_turn=2),
    ], persist=False)
    status = _StatusManager()
    lifecycle = SimpleNamespace(
        initialized=True,
        session_id="s_status_progress",
        session_manager=session,
        resources=SimpleNamespace(status_manager=status),
    )
    service = AgentSessionService(
        lifecycle=lifecycle,
        tool_service=object(),
        data=_UnusedSessionData(),
        catalog_creator=object(),
        role_service=object(),
        reset_service=object(),
    )

    result = service.truncate_history_from_turn_now(2)

    assert result["removed"] == 2
    assert status.boundaries == [1]


@pytest.mark.asyncio
async def test_agent_reset_clears_plot_ledger_and_preserves_overrides(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "agent-session-reset.sqlite3"
    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(database_path))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "workspaces"))
    reset_data_service_gateways()
    gateway = get_data_service_gateway()
    pool = gateway.plot_scheduling.create_pool(
        story_id=1,
        name="清理测试池",
        description="",
        selection_mode=models.PLOT_POOL_RANDOM,
        priority=0,
        enabled=True,
    )
    event = gateway.plot_scheduling.create_event(
        story_id=1,
        pool_id=pool.id,
        title="清理测试事件",
        directive="推进测试事件。",
        description="",
        suitability_hint="",
        dispatch_mode=models.PLOT_DISPATCH_FORCED,
        scheduled_time=None,
        position=0,
        enabled=True,
        allow_repeat=False,
        repeat_cooldown_minutes=0,
    )
    gateway.plot_scheduling.set_session_event_disabled(
        "s_forest001",
        event.id,
        True,
    )
    PlotScheduleLedgerService(gateway.plot_scheduling).record(
        "s_forest001",
        1,
        (
            models.StagedPlotScheduleDecision(
                source_kind=models.PLOT_SOURCE_POOL,
                source_id=event.id,
                event_id=event.id,
                container_id=pool.id,
                decision_status=models.PLOT_DECISION_TRIGGERED,
                dispatch_mode=models.PLOT_DISPATCH_FORCED,
                scene_time=SceneTime(1, 1, 1, 8),
                event_snapshot={"eventTitle": event.title},
            ),
        ),
    )

    calls: list[str] = []

    class _ResetSessionManager:
        def load(self) -> None:
            calls.append("load")

    class _ResetLifecycle:
        initialized = True
        session_id = "s_forest001"
        session_manager = _ResetSessionManager()

        async def release_resources(self) -> None:
            calls.append("release")

        async def reload_resources(self, _tool_service: object) -> None:
            calls.append("reload")

    service = AgentSessionService(
        lifecycle=_ResetLifecycle(),
        tool_service=object(),
        data=gateway.sessions,
        catalog_creator=object(),
        role_service=SessionRoleService(gateway.sessions),
        reset_service=SessionResetService(gateway.sessions),
    )
    try:
        result = await service.reset_session()

        assert result.plot_schedule_decisions_cleared == 1
        assert gateway.plot_scheduling.list_session_decisions("s_forest001") == []
        _, overrides = gateway.plot_scheduling.get_session_schedule("s_forest001")
        assert overrides.disabled_event_ids == frozenset((event.id,))
        assert calls == ["release", "reload", "load"]
    finally:
        reset_data_service_gateways()


def test_session_catalog_commands_stay_within_current_story() -> None:
    current = models.Session("current", "workspace", 7)
    ready = models.Session("ready", "workspace", 7)
    provisioning = models.Session(
        "provisioning",
        "workspace",
        7,
        lifecycle=models.SESSION_LIFECYCLE_PROVISIONING,
    )
    other_story = models.Session("other_story", "workspace", 8)
    sessions = {
        row.id: row
        for row in (current, ready, provisioning, other_story)
    }
    list_calls: list[tuple[str, int]] = []
    create_calls: list[tuple[str, int, str]] = []

    class _CatalogData(_UnusedSessionData):
        @staticmethod
        def get_session(session_id: str):  # noqa: ANN205
            return sessions.get(session_id)

        @staticmethod
        def list_sessions(workspace_id: str, story_id: int):  # noqa: ANN205
            list_calls.append((workspace_id, story_id))
            return [current, ready]

    class _CatalogCreator:
        @staticmethod
        def create_session(
            workspace_id: str,
            story_id: int,
            *,
            title: str,
        ) -> models.Session:
            create_calls.append((workspace_id, story_id, title))
            return models.Session("created", workspace_id, story_id, title=title)

    service = AgentSessionService(
        lifecycle=SimpleNamespace(session_id="current"),
        tool_service=object(),
        data=_CatalogData(),
        catalog_creator=_CatalogCreator(),
        role_service=object(),
        reset_service=object(),
    )

    assert service.list_story_sessions() == [current, ready]
    created = service.create_story_session("New Session")
    assert created is not None and created.id == "created"
    assert service.can_switch_session("ready") is True
    assert service.can_switch_session("provisioning") is False
    assert service.can_switch_session("other_story") is False
    assert service.can_switch_session("missing") is False
    assert list_calls == [("workspace", 7)]
    assert create_calls == [("workspace", 7, "New Session")]


def test_session_catalog_commands_require_current_catalog_session() -> None:
    class _MissingCatalogData(_UnusedSessionData):
        @staticmethod
        def get_session(_session_id: str):  # noqa: ANN205
            return None

    service = AgentSessionService(
        lifecycle=SimpleNamespace(session_id="missing"),
        tool_service=object(),
        data=_MissingCatalogData(),
        catalog_creator=object(),
        role_service=object(),
        reset_service=object(),
    )

    with pytest.raises(
        FileNotFoundError,
        match="Session not found in rpg_data: missing",
    ):
        service.list_story_sessions()
