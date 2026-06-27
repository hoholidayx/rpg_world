from __future__ import annotations

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
    status_types = gateway.status.list_types("demo_workspace")
    status_tables = gateway.status.list_tables("s_forest001")

    assert {workspace["id"] for workspace in workspaces} == {"demo_workspace"}
    assert [character.name for character in characters] == ["Bob", "Alice"]
    assert [entry.name for entry in lorebook_entries] == ["炎心之木", "圆形封印祭坛"]
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
