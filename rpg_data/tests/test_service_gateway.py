from __future__ import annotations

import logging
from pathlib import Path

import pytest

from rpg_data.repositories.records import SessionStatusTableRecord, SessionStatusTypeRecord
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
    message_count = gateway.messages.count("s_forest001")
    backup_message_count = gateway.backup.messages.count("s_forest001")
    status_types = gateway.status.list_types("demo_workspace")
    status_tables = gateway.status.list_tables("s_forest001")

    assert {workspace["id"] for workspace in workspaces} == {"demo_workspace"}
    assert [character.name for character in characters] == ["Bob", "Alice"]
    assert [entry.name for entry in lorebook_entries] == ["炎心之木", "圆形封印祭坛"]
    assert message_count == 0
    assert backup_message_count == 0
    assert [(item.name, item.builtin_key) for item in status_types] == [
        ("场景", "scene"),
        ("世界状态", ""),
    ]
    assert [(item.type_name, item.name) for item in status_tables] == [
        ("场景", "北境森林当前场景"),
        ("世界状态", "世界线索"),
    ]
    assert status_tables[0].headers == ("属性", "值")
    assert status_tables[0].rows[0] == ("时间", "第 1 年 1 月 1 日 8 时 30 分")
    assert (
        tmp_path
        / "data/demo_workspace/template_status/场景/北境森林当前场景.csv"
    ).is_file()
    assert (
        tmp_path
        / "data/demo_workspace/stories/1/s_forest001/status/场景/北境森林当前场景.csv"
    ).is_file()


def test_gateway_supports_in_memory_database(
    tmp_path: Path,
) -> None:
    gateway = get_data_service_gateway(":memory:")

    assert gateway.catalog.list_workspaces()[0]["id"] == "demo_workspace"
    assert (tmp_path / "data/demo_workspace").is_dir()


def test_gateway_recovers_demo_session_files_without_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "recover.sqlite3"
    gateway = get_data_service_gateway(db_path)
    original = gateway.status.list_tables("s_forest001")
    assert original
    original_paths = [
        tmp_path / "data/demo_workspace" / table.relative_path
        for table in original
    ]
    assert all(path.is_file() for path in original_paths)

    SessionStatusTableRecord.delete().where(
        SessionStatusTableRecord.session == "s_forest001"
    ).execute()
    SessionStatusTypeRecord.delete().where(
        SessionStatusTypeRecord.session == "s_forest001"
    ).execute()
    assert all(path.is_file() for path in original_paths)

    reset_data_service_gateways()
    recovered_gateway = get_data_service_gateway(db_path)

    assert [
        (table.type_name, table.name)
        for table in recovered_gateway.status.list_tables("s_forest001")
    ] == [
        ("场景", "北境森林当前场景"),
        ("世界状态", "世界线索"),
    ]


def test_gateway_bootstrap_removes_orphan_runtime_dirs_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS", raising=False)
    db_path = tmp_path / "cleanup.sqlite3"
    gateway = get_data_service_gateway(db_path)
    assert gateway.catalog.get_session("s_forest001") is not None

    data_dir = tmp_path / "data"
    orphan_workspace = data_dir / "orphan_workspace"
    orphan_story = data_dir / "demo_workspace" / "stories" / "999"
    orphan_session = data_dir / "demo_workspace" / "stories" / "1" / "s_orphan"
    for directory in (orphan_workspace / "stories", orphan_story, orphan_session):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker.txt").write_text("orphan", encoding="utf-8")

    reset_data_service_gateways()
    caplog.set_level(logging.INFO, logger="rpg_data.bootstrap")
    get_data_service_gateway(db_path).catalog.list_workspaces()

    assert not orphan_workspace.exists()
    assert not orphan_story.exists()
    assert not orphan_session.exists()
    assert "removed orphan runtime directory kind=workspace" in caplog.text
    assert "removed orphan runtime directory kind=story" in caplog.text
    assert "removed orphan runtime directory kind=session" in caplog.text
    assert "orphan_dirs_removed=3" in caplog.text


def test_gateway_bootstrap_removes_unindexed_status_csv_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS", raising=False)
    db_path = tmp_path / "cleanup_status.sqlite3"
    gateway = get_data_service_gateway(db_path)
    tables = gateway.status.list_tables("s_forest001")
    assert tables

    data_dir = tmp_path / "data" / "demo_workspace"
    indexed_session_path = data_dir / tables[0].relative_path
    orphan_session_csv = indexed_session_path.with_name("孤儿状态.csv")
    orphan_template_csv = data_dir / "template_status" / "场景" / "孤儿模板.csv"
    orphan_note = indexed_session_path.with_name("notes.txt")
    orphan_session_csv.write_text("名称\n孤儿\n", encoding="utf-8")
    orphan_template_csv.write_text("名称\n孤儿\n", encoding="utf-8")
    orphan_note.write_text("keep me", encoding="utf-8")

    reset_data_service_gateways()
    caplog.set_level(logging.INFO, logger="rpg_data.bootstrap")
    get_data_service_gateway(db_path).status.list_tables("s_forest001")

    assert indexed_session_path.is_file()
    assert orphan_note.is_file()
    assert not orphan_session_csv.exists()
    assert not orphan_template_csv.exists()
    assert "removed unindexed status csv kind=session" in caplog.text
    assert "removed unindexed status csv kind=template" in caplog.text
    assert "orphan_status_files_removed=2" in caplog.text


def test_gateway_bootstrap_can_preserve_orphan_runtime_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RPG_WORLD_BOOTSTRAP_DELETE_ORPHAN_DIRS", "false")
    db_path = tmp_path / "preserve.sqlite3"
    get_data_service_gateway(db_path).status.list_tables("s_forest001")

    orphan_session = tmp_path / "data" / "demo_workspace" / "stories" / "1" / "s_orphan"
    orphan_session.mkdir(parents=True, exist_ok=True)
    (orphan_session / "marker.txt").write_text("orphan", encoding="utf-8")
    orphan_status_csv = (
        tmp_path
        / "data"
        / "demo_workspace"
        / "stories"
        / "1"
        / "s_forest001"
        / "status"
        / "场景"
        / "孤儿状态.csv"
    )
    orphan_status_csv.write_text("名称\n孤儿\n", encoding="utf-8")

    reset_data_service_gateways()
    caplog.set_level(logging.INFO, logger="rpg_data.bootstrap")
    get_data_service_gateway(db_path).catalog.list_workspaces()

    assert orphan_session.is_dir()
    assert orphan_status_csv.is_file()
    assert "runtime bootstrap orphan directory cleanup disabled" in caplog.text
    assert "runtime bootstrap unindexed status file cleanup disabled" in caplog.text
    assert "orphan_dirs_removed=0" in caplog.text
    assert "orphan_status_files_removed=0" in caplog.text



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

    assert any(workspace["id"] == "first_only" for workspace in first.catalog.list_workspaces())
    assert all(workspace["id"] != "first_only" for workspace in second.catalog.list_workspaces())
