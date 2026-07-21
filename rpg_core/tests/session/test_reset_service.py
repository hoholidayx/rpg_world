from __future__ import annotations

import pytest

from commons.scene_time import SceneTime
from rpg_core.session.catalog import SessionCatalogService
from rpg_core.session.reset import SessionResetService
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionRoleService,
)
from rpg_core.status.manager import StatusManager
from rpg_data import models
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways
from rp_memory.story_memory_service import StoryMemoryApplicationService


def _story_memory(gateway):  # noqa: ANN001, ANN202
    return StoryMemoryApplicationService(gateway.story_memory)


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path, monkeypatch):  # noqa: ANN001
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path / "workspaces"))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def _prepared_session(tmp_path):  # noqa: ANN001, ANN202
    gateway = get_data_service_gateway(tmp_path / "session-reset.sqlite3")
    session = SessionCatalogService(gateway.sessions).create_session(
        "demo_workspace",
        1,
        title="Reset target",
    )
    assert session is not None
    session_id = str(session.id)

    role_result = SessionRoleService(gateway.sessions).bind_player_character(session_id, 1)
    assert role_result.state.player is not None
    gateway.catalog.set_session_main_llm_provider_key(session_id, "session_chat")
    override = gateway.rp_modules.upsert_session_override(
        session_id,
        "narrative_outcome",
        enabled=False,
        config={},
    )
    assert override is not None

    gateway.messages.append(
        session_id,
        models.MESSAGE_ROLE_USER,
        "进入森林",
        turn_id=2,
        seq_in_turn=1,
    )
    gateway.backup.messages.append(
        session_id,
        models.MESSAGE_ROLE_USER,
        "进入森林",
        turn_id=2,
        seq_in_turn=1,
    )
    _story_memory(gateway).add_detail(session_id, "发现石碑", turn_id=2)
    gateway.narrative_outcomes.record(
        session_id=session_id,
        turn_id=2,
        outcome_code="success",
        reason="寻找道路",
        actor="",
        sample_value=20,
        effective_weights=models.NarrativeOutcomeWeights(),
        effective_source=models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
    )

    template_copy = next(
        table
        for table in gateway.status.list_tables(session_id)
        if table.source_table_id is not None
    )
    changed_document = template_copy.document.with_existing_values([
        (template_copy.document.rows[0].key, "会话中的旧值")
    ])
    gateway.status.save_table(template_copy.id, changed_document)
    source_template = gateway.status.get_template(int(template_copy.source_table_id))
    assert source_template is not None
    current_template_document = source_template.document.with_existing_values([
        (source_template.document.rows[0].key, "Story 当前模板值")
    ])
    gateway.status.update_template(
        source_template.id,
        document=current_template_document,
    )

    deferred_document = models.StatusTableDocument.from_rows(rows=[
        models.StatusTableRow(
            "长期进度",
            "旧值",
            update_frequency=models.STATUS_UPDATE_FREQUENCY_DEFERRED,
            deferred_interval_turns=2,
        )
    ])
    native_table = gateway.status.create_table(
        session_id,
        "会话原生表",
        document=deferred_document,
    )
    StatusManager(session_id, gateway.status).commit_deferred_update(
        native_table.id,
        deferred_document.with_existing_values([("长期进度", "已推进")]),
        processed_keys=["长期进度"],
        last_processed_turn_id=2,
        base_document=deferred_document,
    )
    native_table = gateway.status.get_table_by_id(native_table.id)
    return (
        gateway,
        session_id,
        role_result.state.player,
        template_copy.name,
        native_table,
    )


def test_reset_clears_runtime_rows_and_rebuilds_current_story_status(tmp_path) -> None:
    gateway, session_id, bound_player, template_name, native_before = _prepared_session(
        tmp_path
    )
    backup_count = gateway.backup.messages.count(session_id)

    result = SessionResetService(gateway.sessions).reset(session_id)

    assert result.session_id == session_id
    assert result.messages_cleared >= 2
    assert result.narrative_outcomes_cleared == 1
    assert result.story_memories_cleared == 1
    assert result.template_status_tables_cleared >= 1
    assert result.template_status_tables_initialized >= 1
    assert result.session_native_status_tables_reset == 1
    assert result.deferred_progress_cleared == 1
    assert result.first_message
    messages = gateway.messages.list(session_id)
    assert [(row.role, row.content, row.turn_id, row.seq_in_turn) for row in messages] == [
        (models.MESSAGE_ROLE_ASSISTANT, result.first_message, 1, 1)
    ]
    assert gateway.narrative_outcomes.list_for_turns(session_id, [2]) == []
    assert _story_memory(gateway).list(session_id) == []
    assert gateway.status.list_deferred_progress(session_id) == []
    rebuilt = gateway.status.get_table(session_id, template_name)
    assert rebuilt.document.rows[0].value == "Story 当前模板值"
    native_after = gateway.status.get_table_by_id(native_before.id)
    assert native_after.id == native_before.id
    assert native_after.name == native_before.name
    assert native_after.origin == models.STATUS_ORIGIN_SESSION_NATIVE
    assert native_after.status_kind == native_before.status_kind
    assert native_after.description == native_before.description
    assert native_after.sort_order == native_before.sort_order
    assert native_after.metadata_json == native_before.metadata_json
    assert native_after.document.key_column == native_before.document.key_column
    assert native_after.document.value_column == native_before.document.value_column
    assert native_after.document.metadata == native_before.document.metadata
    assert native_after.document.rows[0].key == "长期进度"
    assert native_after.document.rows[0].value == ""
    assert (
        native_after.document.rows[0].update_frequency
        == models.STATUS_UPDATE_FREQUENCY_DEFERRED
    )
    assert native_after.document.rows[0].deferred_interval_turns == 2

    assert gateway.backup.messages.count(session_id) == backup_count + 1
    state = SessionRoleService(gateway.sessions).get_state(session_id)
    assert state.status == PlayerCharacterBindingStatus.BOUND
    assert state.player == bound_player
    session = gateway.catalog.get_session(session_id)
    assert session is not None
    assert session.title == "Reset target"
    assert session.main_llm_provider_key == "session_chat"
    assert gateway.rp_modules.get_session_override(
        session_id,
        "narrative_outcome",
    ) is not None


def test_reset_rolls_back_all_database_changes_when_status_rebuild_fails(
    tmp_path,
    monkeypatch,
) -> None:
    gateway, session_id, _bound_player, _template_name, _native = _prepared_session(
        tmp_path
    )
    messages_before = gateway.messages.list(session_id)
    memories_before = _story_memory(gateway).list(session_id)
    tables_before = gateway.status.list_tables(session_id)
    backup_count = gateway.backup.messages.count(session_id)

    def fail_reset(_session_id: str, _plan: models.SessionStatusResetPlan):  # noqa: ANN202
        raise RuntimeError("status rebuild failed")

    monkeypatch.setattr(gateway.sessions, "apply_status_reset_plan", fail_reset)

    with pytest.raises(RuntimeError, match="status rebuild failed"):
        SessionResetService(gateway.sessions).reset(session_id)

    assert gateway.messages.list(session_id) == messages_before
    assert _story_memory(gateway).list(session_id) == memories_before
    assert gateway.status.list_tables(session_id) == tables_before
    assert gateway.narrative_outcomes.get_for_turn(session_id, 2) is not None
    assert gateway.backup.messages.count(session_id) == backup_count


def test_reset_fails_atomically_when_native_table_name_conflicts_with_story_template(
    tmp_path,
) -> None:
    gateway, session_id, _bound_player, template_name, native_table = _prepared_session(
        tmp_path
    )
    template_copy = gateway.status.get_table(session_id, template_name)
    assert template_copy.source_table_id is not None
    gateway.status.update_template(
        int(template_copy.source_table_id),
        name=native_table.name,
    )
    messages_before = gateway.messages.list(session_id)
    tables_before = gateway.status.list_tables(session_id)
    backup_count = gateway.backup.messages.count(session_id)

    with pytest.raises(ValueError, match="conflict.*会话原生表"):
        SessionResetService(gateway.sessions).reset(session_id)

    assert gateway.messages.list(session_id) == messages_before
    assert gateway.status.list_tables(session_id) == tables_before
    assert gateway.backup.messages.count(session_id) == backup_count


def test_reset_without_valid_binding_does_not_append_first_message(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "session-reset-unbound.sqlite3")
    session = SessionCatalogService(gateway.sessions).create_session(
        "demo_workspace",
        1,
        title="Unbound reset",
    )
    assert session is not None
    gateway.messages.append(
        session.id,
        models.MESSAGE_ROLE_USER,
        "旧消息",
        turn_id=1,
        seq_in_turn=1,
    )

    result = SessionResetService(gateway.sessions).reset(session.id)

    assert result.first_message == ""
    assert gateway.messages.list(session.id) == []
    assert gateway.backup.messages.count(session.id) == 0


def test_core_reset_clears_plot_decision_ledger(tmp_path) -> None:
    gateway = get_data_service_gateway(tmp_path / "session-reset-plot.sqlite3")
    gateway.plot_scheduling.append_decisions(
        "s_forest001",
        1,
        (
            models.StagedPlotScheduleDecision(
                source_kind=models.PLOT_SOURCE_POOL,
                source_id=1,
                event_id=1,
                container_id=1,
                decision_status=models.PLOT_DECISION_TRIGGERED,
                dispatch_mode=models.PLOT_DISPATCH_FORCED,
                scene_time=SceneTime(1, 1, 1, 8),
                event_snapshot={"eventTitle": "数据层不决定是否清理"},
            ),
        ),
    )

    result = SessionResetService(gateway.sessions).reset("s_forest001")

    assert result.plot_schedule_decisions_cleared == 1
    assert gateway.plot_scheduling.list_session_decisions("s_forest001") == []


def test_reset_rolls_back_when_story_opening_cannot_render(tmp_path) -> None:
    gateway, session_id, _bound_player, _template_name, _native = _prepared_session(
        tmp_path
    )
    session = gateway.catalog.get_session(session_id)
    assert session is not None
    gateway.database.execute_sql(
        "UPDATE rpg_story_openings SET message = ? WHERE id = ?",
        ("欢迎，{UNKNOWN_ROLE}。", session.story_opening_id),
    )
    messages_before = gateway.messages.list(session_id)
    tables_before = gateway.status.list_tables(session_id)
    progress_before = gateway.status.list_deferred_progress(session_id)
    backup_count = gateway.backup.messages.count(session_id)

    with pytest.raises(ValueError):
        SessionResetService(gateway.sessions).reset(session_id)

    assert gateway.messages.list(session_id) == messages_before
    assert gateway.status.list_tables(session_id) == tables_before
    assert gateway.status.list_deferred_progress(session_id) == progress_before
    assert gateway.backup.messages.count(session_id) == backup_count
