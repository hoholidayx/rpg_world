"""Shared catalog setup for deterministic backend integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rpg_core.agent.agent import RPGGameAgent
from rpg_core.session.role import SessionRoleService
from rpg_core.session.status import SessionStatusLifecycleService
from rpg_core.status.administration import StatusTableAdministrationService
from rpg_data import models
from rpg_data.services.gateway import DataServiceGateway


@dataclass(frozen=True)
class IntegrationCatalog:
    workspace_id: str
    story: models.Story
    session: models.Session
    character: models.StoryCharacter


async def shutdown_agent(agent: RPGGameAgent) -> None:
    await agent.close()


def create_integration_session(
    gateway: DataServiceGateway,
    integration_workspace: Path,
    session_id: str,
    *,
    with_status: bool = False,
    bind_role: bool = True,
    first_message: str = "",
) -> IntegrationCatalog:
    """Seed one catalog session through a single shared test-support boundary."""

    from rpg_data.repositories.session_repo import SessionRepository
    from rpg_data.repositories.story_repo import StoryRepository
    from rpg_data.repositories.story_character_repo import StoryCharacterRepository
    from rpg_data.repositories.workspace_repo import WorkspaceRepository

    workspace_id = "integration_workspace"
    database = gateway.database
    story_characters = StoryCharacterRepository(database)
    workspaces = WorkspaceRepository(database)
    stories = StoryRepository(database)
    sessions = SessionRepository(database)
    story_title = "Integration Status Story" if with_status else "Integration Story"

    with database.atomic():
        if workspaces.get(workspace_id) is None:
            workspaces.create(
                workspace_id,
                "Integration Workspace",
                str(integration_workspace),
            )
        story = next(
            (
                candidate
                for candidate in stories.list(workspace_id)
                if candidate.title == story_title
            ),
            None,
        )
        if story is None:
            story = stories.create(
                workspace_id,
                story_title,
                openings=(
                    (
                        models.StoryOpeningInput(
                            title="Integration Opening",
                            message=first_message,
                        ),
                    )
                    if first_message
                    else ()
                ),
            )
        elif first_message and (
            not story.openings or story.openings[0].message != first_message
        ):
            story = stories.update(
                story.id,
                openings=(
                    models.StoryOpeningInput(
                        id=story.openings[0].id if story.openings else None,
                        title=(
                            story.openings[0].title
                            if story.openings
                            else "Integration Opening"
                        ),
                        message=first_message,
                    ),
                ),
            )
            assert story is not None

        session = sessions.get(session_id)
        if session is None:
            session = sessions.create(
                workspace_id,
                story.id,
                session_id=session_id,
                title=session_id,
            )
        character = _ensure_test_role(
            story_characters=story_characters,
            workspace_id=workspace_id,
            story_id=story.id,
        )
        for module in gateway.rp_modules.list_catalog():
            if module.default_story_enabled:
                gateway.rp_modules.upsert_story_module(
                    workspace_id,
                    story.id,
                    module.module_name,
                    enabled=True,
                    config={},
                )

    if with_status:
        _ensure_integration_status(gateway, workspace_id, story.id)
        SessionStatusLifecycleService(gateway.sessions).initialize(session_id)
    if bind_role:
        SessionRoleService(gateway.sessions).bind_player_character(
            session_id,
            character.id,
        )
    return IntegrationCatalog(workspace_id, story, session, character)


def ensure_integration_session(
    gateway: DataServiceGateway,
    integration_workspace: Path,
    session_id: str,
) -> None:
    create_integration_session(gateway, integration_workspace, session_id)


def _ensure_integration_status(
    gateway: DataServiceGateway,
    workspace_id: str,
    story_id: int,
) -> None:
    if gateway.status.list_story_tables(workspace_id, story_id):
        return
    administration = StatusTableAdministrationService(gateway.status)
    administration.create_story_table(
        workspace_id,
        story_id,
        "集成当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        document=models.StatusTableDocument.from_data(
            models.StatusTableData(
                headers=("属性", "值"),
                rows=(
                    ("时间", "第 2 年 3 月 4 日 5 时"),
                    ("位置", "集成测试大厅"),
                    ("在场人物", "测试者"),
                ),
            )
        ),
        sort_order=10,
    )
    administration.create_story_table(
        workspace_id,
        story_id,
        "集成线索",
        document=models.StatusTableDocument.from_data(
            models.StatusTableData(
                headers=("属性", "值"),
                rows=(("线索", "状态表已挂载"),),
            )
        ),
        sort_order=20,
    )
def _ensure_test_role(
    *,
    story_characters,
    workspace_id: str,
    story_id: int,
):
    character = next(
        (
            candidate
            for candidate in story_characters.list(
                workspace_id=workspace_id,
                story_id=story_id,
            )
            if candidate.name == "Integration Tester"
        ),
        None,
    )
    if character is None:
        character = story_characters.create(
            workspace_id,
            story_id,
            "Integration Tester",
            description=(
                "You are the player-controlled role used by integration tests."
            ),
        )
    return character
