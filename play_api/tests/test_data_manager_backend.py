from __future__ import annotations

from pathlib import Path

import pytest

from play_api.backends import data_manager as data_manager_module
from play_api.backends.data_manager import DataManagerBackend
from rpg_core.session.role import (
    PlayerCharacterBindingStatus,
    SessionPlayerCharacterState,
)
from rpg_data import models


class FakeCatalog:
    def list_workspaces(self):
        return [models.Workspace("workspace", "Workspace", "data/workspace")]

    def list_stories(self, workspace: str):
        return [models.Story(
            1,
            workspace,
            "Story",
            story_prompt="Prompt",
            openings=(models.StoryOpening(1, workspace, 1, "Default", "First"),),
        )]

    def create_story(
        self,
        workspace: str,
        *,
        title: str,
        summary: str = "",
        story_prompt: str = "",
        openings=(),
    ):
        if workspace != "workspace":
            return None
        return models.Story(
            2,
            workspace,
            title,
            summary=summary,
            story_prompt=story_prompt,
            openings=tuple(
                models.StoryOpening(index + 2, workspace, 2, item.title, item.message, index)
                for index, item in enumerate(openings)
            ),
        )

    def update_story(
        self,
        workspace: str,
        story_id: int,
        *,
        title: str | None = None,
        summary: str | None = None,
        story_prompt: str | None = None,
        openings=None,
    ):
        if workspace != "workspace":
            return None
        return models.Story(
            story_id,
            workspace,
            title or "Story",
            summary=summary or "Updated summary",
            story_prompt=story_prompt or "Prompt",
            openings=(
                (models.StoryOpening(1, workspace, story_id, "Default", "First"),)
                if openings is None
                else tuple(
                    models.StoryOpening(index + 2, workspace, story_id, item.title, item.message, index)
                    for index, item in enumerate(openings)
                )
            ),
            version=2,
        )

    def list_sessions(self, workspace: str, story_id: int):
        return [models.Session("session", workspace, story_id)]

    def create_session(self, workspace: str, story_id: int, *, title: str = "", description: str = ""):
        return models.Session("created", workspace, story_id, title=title, description=description)

    def get_session(self, session_id: str):
        return models.Session(
            session_id,
            "workspace",
            1,
            lifecycle=(
                models.SESSION_LIFECYCLE_PROVISIONING
                if session_id == "provisioning"
                else models.SESSION_LIFECYCLE_READY
            ),
        )


class FakeGateway:
    def __init__(self) -> None:
        self.catalog = FakeCatalog()
        self.sessions = self
        self.character_management = FakeCharacterManagement()
        self.lorebook_management = FakeLorebookManagement()
        self.status = object()
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


class FakeCharacterManagement:
    def list_characters(self, workspace: str):
        if workspace != "workspace":
            return None
        return [models.Character(1, workspace, "Character")]

    def create_character(self, workspace: str, **kwargs):
        return models.Character(
            2,
            workspace,
            str(kwargs["name"]),
            personality=str(kwargs.get("personality") or ""),
            content=str(kwargs.get("content") or ""),
        )

    def update_character(self, workspace: str, character_id: int, **kwargs):
        return models.Character(character_id, workspace, str(kwargs["name"]), version=2)

    def delete_character(self, workspace: str, character_id: int):
        return workspace == "workspace" and character_id == 1

    def list_details(self, workspace: str, character_id: int):
        if workspace != "workspace":
            return None
        return [models.CharacterDetail(11, character_id, "Detail", tags_json='["tag"]')]

    def create_detail(self, workspace: str, character_id: int, **kwargs):
        return models.CharacterDetail(
            12,
            character_id,
            str(kwargs["name"]),
            content=str(kwargs.get("content") or ""),
            tags_json='["new"]',
            sort_order=int(kwargs.get("sort_order") or 0),
        )

    def update_detail(self, workspace: str, character_id: int, detail_id: int, **kwargs):
        return models.CharacterDetail(
            detail_id,
            character_id,
            str(kwargs["name"]),
            tags_json='["updated"]',
            version=2,
        )

    def delete_detail(self, workspace: str, character_id: int, detail_id: int):
        return workspace == "workspace" and character_id == 1 and detail_id == 11

    def list_story_characters(self, workspace: str, story_id: int):
        return [_character_mount_detail(workspace, story_id)]

    def mount_character(self, workspace: str, story_id: int, character_id: int):
        return _character_mount_detail(workspace, story_id, character_id=character_id)

    def unmount_character(self, workspace: str, story_id: int, mount_id: int):
        return workspace == "workspace" and story_id == 1 and mount_id == 20


def _character_mount_detail(
    workspace: str,
    story_id: int,
    *,
    character_id: int = 1,
    mount_id: int = 20,
) -> models.StoryCharacterDetail:
    return models.StoryCharacterDetail(
        mount=models.StoryCharacter(mount_id, workspace, story_id, character_id),
        character=models.Character(character_id, workspace, "Character"),
    )


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
    monkeypatch.setattr(
        data_manager_module,
        "SessionCatalogService",
        lambda fake_gateway: fake_gateway.catalog,
    )

    class FakeRoleService:
        @staticmethod
        def get_state(_session_id: str) -> SessionPlayerCharacterState:
            return SessionPlayerCharacterState(
                status=PlayerCharacterBindingStatus.INVALID,
            )

    monkeypatch.setattr(
        data_manager_module,
        "SessionRoleService",
        lambda _fake_gateway: FakeRoleService(),
    )

    db_path = tmp_path / "play.sqlite3"
    backend = DataManagerBackend(db_path)

    assert requested_paths == [db_path]
    assert gateway.initialize_calls == 1
    assert await backend.list_workspaces() == [{"id": "workspace", "name": "Workspace", "description": None}]
    assert (await backend.list_stories("workspace"))[0]["title"] == "Story"
    assert (await backend.list_stories("workspace"))[0]["story_prompt"] == "Prompt"
    assert (await backend.list_stories("workspace"))[0]["openings"][0]["message"] == "First"
    assert (await backend.create_story("workspace", title="New Story"))["title"] == "New Story"
    assert (await backend.create_story("missing", title="New Story")) is None
    assert (await backend.update_story("workspace", 1, summary="Updated summary"))["summary"] == "Updated summary"
    assert (await backend.update_story("missing", 1, summary="Updated summary")) is None
    assert (await backend.list_sessions("workspace", 1))[0]["id"] == "session"
    assert (await backend.create_session("workspace", 1, title="Title"))["title"] == "Title"
    assert (await backend.get_session("session"))["id"] == "session"
    assert await backend.get_session("provisioning") is None
    assert await backend.list_session_summaries("provisioning") is None
    assert await backend.get_session_summary("provisioning", "overall") is None
    assert await backend.list_session_status_tables("provisioning") is None
    document = models.StatusTableDocument.from_rows()
    assert await backend.create_session_status_table(
        "provisioning",
        name="hidden",
        status_kind=models.STATUS_KIND_NORMAL,
        document=document,
    ) is None
    assert await backend.update_session_status_table(
        "provisioning",
        1,
        name="hidden",
    ) is None
    assert await backend.delete_session_status_table("provisioning", 1) is None
    assert (await backend.list_characters("workspace"))[0]["name"] == "Character"
    assert (await backend.list_characters("workspace"))[0]["details"][0]["tags"] == ["tag"]
    assert (await backend.create_character("workspace", name="New"))["name"] == "New"
    assert (await backend.get_character("workspace", 1))["name"] == "Character"
    assert await backend.get_character("missing", 1) is None
    assert (await backend.update_character("workspace", 1, name="Updated"))["name"] == "Updated"
    assert await backend.delete_character("workspace", 1) is True
    assert (await backend.create_character_detail("workspace", 1, name="New Detail"))["name"] == "New Detail"
    assert (await backend.update_character_detail("workspace", 1, 11, name="Updated Detail"))["version"] == 2
    assert await backend.delete_character_detail("workspace", 1, 11) is True
    assert (await backend.list_story_characters("workspace", 1))[0]["mount_id"] == 20
    assert (await backend.mount_character("workspace", 1, 1))["mount_id"] == 20
    assert await backend.unmount_character("workspace", 1, 20) is True
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
