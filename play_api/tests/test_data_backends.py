from __future__ import annotations

import pytest

from play_api.backends import data_backends as data_backends_module
from play_api.backends.data_backends import (
    PlayCatalogBackend,
    PlayStoryAssetBackend,
)
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


class FakeLorebookManagement:
    def list_entries(self, workspace: str, story_id: int):
        if workspace != "workspace":
            return None
        return [models.StoryLorebookEntry(1, workspace, story_id, "Entry")]

    def create_entry(self, workspace: str, story_id: int, **kwargs):
        return models.StoryLorebookEntry(
            2,
            workspace,
            story_id,
            str(kwargs["name"]),
            content=str(kwargs.get("content") or ""),
            description=str(kwargs.get("description") or ""),
        )

    def update_entry(self, workspace: str, story_id: int, entry_id: int, **kwargs):
        return models.StoryLorebookEntry(
            entry_id,
            workspace,
            story_id,
            str(kwargs["name"]),
            version=2,
        )

    def delete_entry(self, workspace: str, story_id: int, entry_id: int):
        return workspace == "workspace" and story_id == 1 and entry_id == 1


class FakeCharacterManagement:
    def list_characters(self, workspace: str, story_id: int):
        if workspace != "workspace":
            return None
        return [models.StoryCharacter(1, workspace, story_id, "Character")]

    def create_character(self, workspace: str, story_id: int, **kwargs):
        return models.StoryCharacter(
            2,
            workspace,
            story_id,
            str(kwargs["name"]),
            description=str(kwargs.get("description") or ""),
        )

    def update_character(self, workspace: str, story_id: int, character_id: int, **kwargs):
        return models.StoryCharacter(
            character_id,
            workspace,
            story_id,
            str(kwargs["name"]),
            version=2,
        )

    def delete_character(self, workspace: str, story_id: int, character_id: int):
        return workspace == "workspace" and story_id == 1 and character_id == 1

    def list_details(self, workspace: str, story_id: int, character_id: int):
        if workspace != "workspace":
            return None
        return [models.CharacterDetail(11, character_id, "Detail", tags_json='["tag"]')]

    def create_detail(self, workspace: str, story_id: int, character_id: int, **kwargs):
        return models.CharacterDetail(
            12,
            character_id,
            str(kwargs["name"]),
            content=str(kwargs.get("content") or ""),
            tags_json='["new"]',
            sort_order=int(kwargs.get("sort_order") or 0),
        )

    def update_detail(self, workspace: str, story_id: int, character_id: int, detail_id: int, **kwargs):
        return models.CharacterDetail(
            detail_id,
            character_id,
            str(kwargs["name"]),
            tags_json='["updated"]',
            version=2,
        )

    def delete_detail(self, workspace: str, story_id: int, character_id: int, detail_id: int):
        return (
            workspace == "workspace"
            and story_id == 1
            and character_id == 1
            and detail_id == 11
        )


@pytest.mark.asyncio
async def test_narrow_data_backends_receive_only_their_services(
    monkeypatch,
) -> None:
    catalog_data = FakeCatalog()
    monkeypatch.setattr(
        data_backends_module,
        "SessionCatalogService",
        lambda fake_data: fake_data,
    )

    class FakeRoleService:
        @staticmethod
        def get_state(_session_id: str) -> SessionPlayerCharacterState:
            return SessionPlayerCharacterState(
                status=PlayerCharacterBindingStatus.INVALID,
            )

    monkeypatch.setattr(
        data_backends_module,
        "SessionRoleService",
        lambda _fake_gateway: FakeRoleService(),
    )

    catalog = PlayCatalogBackend(
        catalog=catalog_data,
        sessions=catalog_data,
        session_composer=object(),
        rp_modules=object(),
    )
    assets = PlayStoryAssetBackend(
        catalog=catalog_data,
        character_management=FakeCharacterManagement(),
        lorebook_management=FakeLorebookManagement(),
        status_administration=object(),
        plot_management=object(),
        plot_story_projection=object(),
        scene=object(),
    )

    assert not hasattr(catalog, "_gateway")
    assert not hasattr(assets, "_gateway")
    assert await catalog.list_workspaces() == [{"id": "workspace", "name": "Workspace", "description": None}]
    assert (await catalog.list_stories("workspace"))[0]["title"] == "Story"
    assert (await catalog.list_stories("workspace"))[0]["story_prompt"] == "Prompt"
    assert (await catalog.list_stories("workspace"))[0]["openings"][0]["message"] == "First"
    assert (await catalog.create_story("workspace", title="New Story"))["title"] == "New Story"
    assert (await catalog.create_story("missing", title="New Story")) is None
    assert (await catalog.update_story("workspace", 1, summary="Updated summary"))["summary"] == "Updated summary"
    assert (await catalog.update_story("missing", 1, summary="Updated summary")) is None
    assert (await catalog.list_sessions("workspace", 1))[0]["id"] == "session"
    assert (await catalog.get_session("session"))["id"] == "session"
    assert await catalog.get_session("provisioning") is None
    assert await assets.list_session_status_tables("provisioning") is None
    document = models.StatusTableDocument.from_rows()
    assert await assets.create_session_status_table(
        "provisioning",
        name="hidden",
        status_kind=models.STATUS_KIND_NORMAL,
        document=document,
    ) is None
    assert await assets.update_session_status_table(
        "provisioning",
        1,
        name="hidden",
    ) is None
    assert await assets.delete_session_status_table("provisioning", 1) is None
    assert (await assets.list_characters("workspace", 1))[0]["name"] == "Character"
    assert (await assets.list_characters("workspace", 1))[0]["details"][0]["tags"] == ["tag"]
    assert (await assets.create_character("workspace", 1, name="New"))["name"] == "New"
    assert (await assets.get_character("workspace", 1, 1))["name"] == "Character"
    assert await assets.get_character("missing", 1, 1) is None
    assert (await assets.update_character("workspace", 1, 1, name="Updated"))["name"] == "Updated"
    assert await assets.delete_character("workspace", 1, 1) is True
    assert (await assets.create_character_detail("workspace", 1, 1, name="New Detail"))["name"] == "New Detail"
    assert (await assets.update_character_detail("workspace", 1, 1, 11, name="Updated Detail"))["version"] == 2
    assert await assets.delete_character_detail("workspace", 1, 1, 11) is True
    assert (await assets.list_lorebook_entries("workspace", 1))[0]["name"] == "Entry"
    assert (await assets.create_lorebook_entry("workspace", 1, name="New"))["name"] == "New"
    assert (await assets.get_lorebook_entry("workspace", 1, 1))["name"] == "Entry"
    assert await assets.get_lorebook_entry("missing", 1, 1) is None
    assert (await assets.update_lorebook_entry("workspace", 1, 1, name="Updated"))["name"] == "Updated"
    assert await assets.delete_lorebook_entry("workspace", 1, 1) is True
