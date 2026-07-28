from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rpg_core.scene.status import SceneStatusService
from rpg_core.status.context_service import StatusContextService
from rpg_data.repositories.records import SessionStatusTableRecord
from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


@pytest.fixture(autouse=True)
def _reset_gateways(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def test_gateway_initializes_migrations_and_exposes_services(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(tmp_path / "gateway.sqlite3")

    workspaces = gateway.catalog.list_workspaces()
    characters = gateway.character.list_characters("s_forest001")
    lorebook_entries = gateway.lorebook.list_enabled_entries("s_forest001")
    messages = gateway.messages.list("s_forest001")
    backup_messages = gateway.backup.messages.list("s_forest001")
    message_count = gateway.messages.count("s_forest001")
    backup_message_count = gateway.backup.messages.count("s_forest001")
    forest_definitions = gateway.status.list_story_tables("demo_workspace", 1)
    academy_definitions = gateway.status.list_story_tables("demo_workspace", 2)
    status_tables = gateway.status.list_tables("s_forest001")
    context_tables = StatusContextService(gateway.status).list_tables("s_forest001")
    scene_table = SceneStatusService(gateway.status).get_active_table("s_forest001")

    assert {workspace.id for workspace in workspaces} == {"demo_workspace"}
    assert [character.name for character in characters] == ["Bob", "Alice", "伊芙"]
    assert [entry.name for entry in lorebook_entries] == ["炎心之木", "圆形封印祭坛"]
    assert message_count == 28
    assert backup_message_count == 28
    assert messages[0].content == "我拨开覆盖在石林入口的霜藤，确认 Alice 是否跟在身后。"
    assert [message.turn_id for message in messages[:4]] == [1, 1, 2, 2]
    assert [message.seq_in_turn for message in messages[:4]] == [1, 2, 1, 2]
    assert {
        (message.turn_id, message.seq_in_turn): message.content
        for message in backup_messages
    } == {
        (message.turn_id, message.seq_in_turn): message.content
        for message in messages
    }
    assert [(item.name, item.status_kind) for item in forest_definitions] == [
        ("世界线索", "normal"),
        ("调查进度", "normal"),
        ("Alice 同行状态", "normal"),
        ("北境森林当前场景", "scene"),
    ]
    assert [(item.name, item.status_kind) for item in academy_definitions] == [
        ("世界线索", "normal"),
        ("档案调查进度", "normal"),
        ("莫兰协助状态", "normal"),
        ("奥术学院当前场景", "scene"),
    ]
    assert [table.name for table in status_tables] == [
        "世界线索",
        "调查进度",
        "Alice 同行状态",
        "北境森林当前场景",
    ]
    assert [table.name for table in context_tables] == [
        "世界线索",
        "调查进度",
        "Alice 同行状态",
    ]
    assert scene_table is not None
    assert scene_table.name == "北境森林当前场景"
    story = gateway.catalog.get_session_story("s_forest001")
    assert story is not None
    assert "演示故事" in story.story_prompt
    assert gateway.catalog.get_session_story("missing_session") is None
    assert not (
        tmp_path
        / "data/demo_workspace/template_status/场景/北境森林当前场景.status.json"
    ).exists()


def test_gateway_supports_in_memory_database(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(":memory:")

    assert gateway.catalog.list_workspaces()[0].id == "demo_workspace"
    assert (tmp_path / "data/demo_workspace").is_dir()


def test_catalog_resolves_session_runtime_dir(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "runtime.sqlite3")

    workspace_root = gateway.catalog.get_workspace_runtime_dir("demo_workspace")
    session_workspace_root = gateway.catalog.get_session_workspace_dir("s_forest001")
    session_root = gateway.catalog.get_session_runtime_dir("s_forest001")

    assert workspace_root == (tmp_path / "data/demo_workspace").resolve()
    assert session_workspace_root == workspace_root
    assert session_root == (
        tmp_path / "data/demo_workspace/stories/1/s_forest001"
    ).resolve()
    assert session_root.is_dir()
    with pytest.raises(FileNotFoundError, match="Workspace not found in rpg_data"):
        gateway.catalog.get_workspace_runtime_dir("missing_workspace")
    with pytest.raises(FileNotFoundError, match="Session not found in rpg_data"):
        gateway.catalog.get_session_runtime_dir("missing_session")


def test_gateway_bootstrap_recreates_missing_session_status_copies(tmp_path: Path) -> None:
    db_path = tmp_path / "recover.sqlite3"
    gateway = get_data_service_gateway(db_path)
    original = gateway.status.list_tables("s_forest001")
    assert [table.name for table in original] == [
        "世界线索",
        "调查进度",
        "Alice 同行状态",
        "北境森林当前场景",
    ]

    SessionStatusTableRecord.delete().where(
        SessionStatusTableRecord.session == "s_forest001"
    ).execute()

    reset_data_service_gateways()
    recovered_gateway = get_data_service_gateway(db_path)

    recovered = recovered_gateway.status.list_tables("s_forest001")
    assert [table.name for table in recovered] == [
        "世界线索",
        "调查进度",
        "Alice 同行状态",
        "北境森林当前场景",
    ]


def test_gateway_bootstrap_removes_unindexed_runtime_dirs_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RPG_WORLD_BOOTSTRAP_DELETE_UNINDEXED_DIRS", "true")
    db_path = tmp_path / "cleanup.sqlite3"
    gateway = get_data_service_gateway(db_path)
    assert gateway.catalog.get_session("s_forest001") is not None

    data_dir = tmp_path / "data"
    unindexed_workspace = data_dir / "unindexed_workspace"
    unindexed_story = data_dir / "demo_workspace" / "stories" / "999"
    unindexed_session = data_dir / "demo_workspace" / "stories" / "1" / "s_unindexed"
    for directory in (unindexed_workspace / "stories", unindexed_story, unindexed_session):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker.txt").write_text("unindexed", encoding="utf-8")

    reset_data_service_gateways()
    caplog.set_level(logging.INFO, logger="rpg_data.bootstrap")
    get_data_service_gateway(db_path).catalog.list_workspaces()

    assert not unindexed_workspace.exists()
    assert not unindexed_story.exists()
    assert not unindexed_session.exists()
    assert "removed unindexed runtime directory kind=workspace" in caplog.text
    assert "removed unindexed runtime directory kind=story" in caplog.text
    assert "removed unindexed runtime directory kind=session" in caplog.text
    assert "unindexed_dirs_removed=3" in caplog.text


def test_gateway_bootstrap_can_preserve_unindexed_runtime_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RPG_WORLD_BOOTSTRAP_DELETE_UNINDEXED_DIRS", "false")
    db_path = tmp_path / "preserve.sqlite3"
    get_data_service_gateway(db_path).status.list_tables("s_forest001")

    unindexed_session = tmp_path / "data" / "demo_workspace" / "stories" / "1" / "s_unindexed"
    unindexed_session.mkdir(parents=True, exist_ok=True)
    (unindexed_session / "marker.txt").write_text("unindexed", encoding="utf-8")

    reset_data_service_gateways()
    caplog.set_level(logging.INFO, logger="rpg_data.bootstrap")
    get_data_service_gateway(db_path).catalog.list_workspaces()

    assert unindexed_session.is_dir()
    assert "runtime bootstrap unindexed directory cleanup disabled" in caplog.text
    assert "unindexed_dirs_removed=0" in caplog.text


def test_gateway_is_cached_by_database_path_and_reset_closes(tmp_path: Path) -> None:
    db_path = tmp_path / "cached.sqlite3"
    first = get_data_service_gateway(db_path)
    second = get_data_service_gateway(db_path)

    assert first is second
    database = first.database
    assert not database.is_closed()

    reset_data_service_gateways()

    assert database.is_closed()
    assert get_data_service_gateway(db_path) is not first


def test_gateways_for_different_paths_do_not_share_data(tmp_path: Path) -> None:
    first = get_data_service_gateway(tmp_path / "first.sqlite3")
    second = get_data_service_gateway(tmp_path / "second.sqlite3")

    WorkspaceRepository(first.database).create("first_only", "First Only", "data/first")

    assert any(workspace.id == "first_only" for workspace in first.catalog.list_workspaces())
    assert all(workspace.id != "first_only" for workspace in second.catalog.list_workspaces())
