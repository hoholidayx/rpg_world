from __future__ import annotations

from pathlib import Path

import pytest

from rpg_data.repositories.workspace_repo import WorkspaceRepository
from rpg_data.services import get_data_service_gateway, reset_data_service_gateways


@pytest.fixture(autouse=True)
def _reset_gateways():
    reset_data_service_gateways()
    yield
    reset_data_service_gateways()


def test_gateway_initializes_migrations_and_exposes_services(tmp_path: Path) -> None:
    gateway = get_data_service_gateway(tmp_path / "gateway.sqlite3")

    workspaces = gateway.catalog.list_workspaces()
    lorebook_entries = gateway.lorebook.list_enabled_entries("s_forest001")

    assert {workspace["id"] for workspace in workspaces} == {"demo_workspace"}
    assert [entry.name for entry in lorebook_entries] == ["炎心之木", "圆形封印祭坛"]


def test_gateway_supports_in_memory_database() -> None:
    gateway = get_data_service_gateway(":memory:")

    assert gateway.catalog.list_workspaces()[0]["id"] == "demo_workspace"


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
