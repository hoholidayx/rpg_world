from __future__ import annotations

from pathlib import Path

import pytest

from play_api.backends import data_manager as data_manager_module
from play_api.backends.data_manager import DataManagerBackend
from rpg_data import models


class FakeCatalog:
    def list_workspaces(self):
        return [models.Workspace("workspace", "Workspace", "data/workspace")]

    def list_stories(self, workspace: str):
        return [models.Story(1, workspace, "Story")]

    def list_sessions(self, workspace: str, story_id: int):
        return [models.Session("session", workspace, story_id)]

    def create_session(self, workspace: str, story_id: int, *, title: str = "", description: str = ""):
        return models.Session("created", workspace, story_id, title=title, description=description)

    def get_session(self, session_id: str):
        return models.Session(session_id, "workspace", 1)


class FakeGateway:
    def __init__(self) -> None:
        self.catalog = FakeCatalog()
        self.lorebook_management = FakeLorebookManagement()
        self.initialize_calls = 0
        self.close_calls = 0
        self.database = object()

    def initialize(self) -> None:
        self.initialize_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class FakeLorebookManagement:
    def list_entries(self, workspace: str):
        if workspace != "workspace":
            return None
        return [models.LorebookEntry(1, workspace, "Entry")]

    def create_entry(self, workspace: str, **kwargs):
        return models.LorebookEntry(
            2,
            workspace,
            str(kwargs["name"]),
            content=str(kwargs.get("content") or ""),
            description=str(kwargs.get("description") or ""),
        )

    def update_entry(self, workspace: str, entry_id: int, **kwargs):
        return models.LorebookEntry(entry_id, workspace, str(kwargs["name"]), version=2)

    def delete_entry(self, workspace: str, entry_id: int):
        return workspace == "workspace" and entry_id == 1

    def list_story_entries(self, workspace: str, story_id: int):
        return [_lorebook_detail(workspace, story_id)]

    def mount_entry(self, workspace: str, story_id: int, entry_id: int):
        return _lorebook_detail(workspace, story_id, entry_id=entry_id)

    def unmount_entry(self, workspace: str, story_id: int, mount_id: int):
        return workspace == "workspace" and story_id == 1 and mount_id == 10


def _lorebook_detail(
    workspace: str,
    story_id: int,
    *,
    entry_id: int = 1,
    mount_id: int = 10,
) -> models.StoryLorebookEntryDetail:
    return models.StoryLorebookEntryDetail(
        mount=models.StoryLorebookEntry(mount_id, workspace, story_id, entry_id),
        entry=models.LorebookEntry(entry_id, workspace, "Entry"),
    )


@pytest.mark.asyncio
async def test_data_manager_backend_uses_gateway(monkeypatch, tmp_path: Path) -> None:
    gateway = FakeGateway()
    requested_paths: list[Path] = []

    def fake_get_gateway(path: Path):
        requested_paths.append(path)
        return gateway

    monkeypatch.setattr(data_manager_module, "get_data_service_gateway", fake_get_gateway)

    db_path = tmp_path / "play.sqlite3"
    backend = DataManagerBackend(db_path)

    assert requested_paths == [db_path]
    assert gateway.initialize_calls == 1
    assert await backend.list_workspaces() == [{"id": "workspace", "name": "Workspace", "description": None}]
    assert (await backend.list_stories("workspace"))[0]["title"] == "Story"
    assert (await backend.list_sessions("workspace", 1))[0]["id"] == "session"
    assert (await backend.create_session("workspace", 1, title="Title"))["title"] == "Title"
    monkeypatch.setattr(
        data_manager_module,
        "scan_orphan_runtime_data",
        lambda database: {"orphan_directories": [], "unindexed_status_files": []},
    )
    assert (await backend.get_session("session"))["id"] == "session"
    assert await backend.scan_orphan_runtime() == {"orphan_directories": [], "unindexed_status_files": []}
    assert (await backend.list_lorebook_entries("workspace"))[0]["name"] == "Entry"
    assert (await backend.create_lorebook_entry("workspace", name="New"))["name"] == "New"
    assert (await backend.get_lorebook_entry("workspace", 1))["name"] == "Entry"
    assert await backend.get_lorebook_entry("missing", 1) is None
    assert (await backend.update_lorebook_entry("workspace", 1, name="Updated"))["name"] == "Updated"
    assert await backend.delete_lorebook_entry("workspace", 1) is True
    assert (await backend.list_story_lorebook_entries("workspace", 1))[0]["mount_id"] == 10
    assert (await backend.mount_lorebook_entry("workspace", 1, 1))["mount_id"] == 10
    assert (await backend.get_lorebook_mount("workspace", 1, 10))["mount_id"] == 10
    assert await backend.get_lorebook_mount("workspace", 1, 999) is None
    assert await backend.unmount_lorebook_entry("workspace", 1, 10) is True

    backend.close()

    assert gateway.close_calls == 1
