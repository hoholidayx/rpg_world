"""Isolated, deterministic backend integration-test fixtures."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pytest
import pytest_asyncio

from llm_client.manager import LLMClientManager
from rpg_core import settings as settings_module
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.agent.manager import AgentManager
from rpg_core.tests.integration.scripted_llm import (
    ScriptedLLMManager,
)
from rpg_core.utils.watcher import get_watcher
from rpg_data import models

_INTEGRATION_MARKER = "integration"
_LIVE_LLM_MARKER = "live_llm"


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    integration_enabled = os.environ.get("INTEGRATION_TEST") == "1"
    live_enabled = os.environ.get("LIVE_LLM_TEST") == "1"
    for item in items:
        if _INTEGRATION_MARKER in item.keywords and not integration_enabled:
            item.add_marker(pytest.mark.skip(reason="set INTEGRATION_TEST=1 to run integration tests"))
        elif _LIVE_LLM_MARKER in item.keywords and not live_enabled:
            item.add_marker(pytest.mark.skip(reason="set LIVE_LLM_TEST=1 to run live LLM tests"))


def _patch_loaded_settings_refs(integration_settings) -> dict[str, object]:
    module_names = (
        "rpg_core.settings",
        "rpg_core.agent.agent",
        "rpg_core.agent.turn.runner",
        "rpg_core.agent.manager",
        "rpg_core.agent.sub_agents.status.agent",
        "rpg_core.agent.sub_agents.memory.agent",
        "rpg_core.summary.compressor",
        "rpg_core.session.manager",
    )
    previous: dict[str, object] = {}
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "settings"):
            previous[module_name] = getattr(module, "settings")
            setattr(module, "settings", integration_settings)
    return previous


@pytest.fixture
def integration_settings(monkeypatch):
    monkeypatch.setenv("RPG_WORLD_PROFILE", "test")
    previous = settings_module.settings
    current = settings_module.Settings()
    settings_module.settings = current
    previous_module_refs = _patch_loaded_settings_refs(current)
    try:
        yield current
    finally:
        settings_module.settings = previous
        for module_name, old_settings in previous_module_refs.items():
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "settings"):
                setattr(module, "settings", old_settings)


@pytest_asyncio.fixture
async def integration_workspace(tmp_path, monkeypatch):
    from rpg_data.services import reset_data_service_gateways

    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_data.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    watcher = get_watcher()
    monkeypatch.setattr(watcher, "start", lambda: None)
    monkeypatch.setattr(watcher, "stop", lambda: None)
    reset_data_service_gateways()
    await AgentManager.areset()
    yield tmp_path
    await AgentManager.areset()
    reset_data_service_gateways()


@pytest.fixture
def integration_data_gateway(integration_workspace):  # noqa: ARG001
    from rpg_data.services import get_data_service_gateway

    return get_data_service_gateway()


@pytest.fixture
def scripted_llm_manager(monkeypatch) -> ScriptedLLMManager:
    manager = ScriptedLLMManager()
    monkeypatch.setattr(LLMClientManager, "get", classmethod(lambda cls: manager))
    return manager


@pytest_asyncio.fixture
async def integration_agent_factory(
    integration_settings,  # noqa: ARG001
    integration_workspace,
    integration_data_gateway,
    scripted_llm_manager,  # noqa: ARG001
):
    agents: list[RPGGameAgent] = []

    async def factory(
        session_id: str,
        *,
        with_status: bool = False,
        bind_role: bool = True,
        first_message: str = "",
    ) -> RPGGameAgent:
        _create_integration_session(
            integration_data_gateway,
            integration_workspace,
            session_id,
            with_status=with_status,
            bind_role=bind_role,
            first_message=first_message,
        )
        agent = RPGGameAgent(session_id=session_id)
        await agent.initialize()
        agents.append(agent)
        return agent

    try:
        yield factory
    finally:
        for agent in agents:
            await _shutdown_agent(agent)
        watcher = get_watcher()
        watcher.stop()
        watcher.clear_all()
        await AgentManager.areset()


@pytest_asyncio.fixture
async def integration_agent(integration_agent_factory):
    return await integration_agent_factory("integration_smoke")


@pytest_asyncio.fixture
async def integration_status_agent(integration_agent_factory):
    return await integration_agent_factory("integration_status", with_status=True)


async def _shutdown_agent(agent: RPGGameAgent) -> None:
    await agent.close()


@dataclass(frozen=True)
class IntegrationCatalog:
    workspace_id: str
    story: models.Story
    session: models.Session
    character: models.Character


def _create_integration_session(
    gateway,
    integration_workspace,
    session_id: str,
    *,
    with_status: bool = False,
    bind_role: bool = True,
    first_message: str = "",
) -> IntegrationCatalog:
    from rpg_data.repositories.character_repo import CharacterRepository
    from rpg_data.repositories.session_repo import SessionRepository
    from rpg_data.repositories.story_repo import StoryRepository
    from rpg_data.repositories.story_character_repo import StoryCharacterRepository
    from rpg_data.repositories.workspace_repo import WorkspaceRepository

    workspace_id = "integration_workspace"
    database = gateway.database
    characters = CharacterRepository(database)
    story_characters = StoryCharacterRepository(database)
    workspaces = WorkspaceRepository(database)
    stories = StoryRepository(database)
    sessions = SessionRepository(database)
    story_title = "Integration Status Story" if with_status else "Integration Story"

    with database.atomic():
        if workspaces.get(workspace_id) is None:
            workspaces.create(workspace_id, "Integration Workspace", str(integration_workspace))
        story = next(
            (candidate for candidate in stories.list(workspace_id) if candidate.title == story_title),
            None,
        )
        if story is None:
            story = stories.create(
                workspace_id,
                story_title,
                openings=(
                    models.StoryOpeningInput(
                        title="Integration Opening",
                        message=first_message,
                    ),
                ) if first_message else (),
            )
        elif first_message and (
            not story.openings or story.openings[0].message != first_message
        ):
            story = stories.update(
                story.id,
                openings=(
                    models.StoryOpeningInput(
                        id=story.openings[0].id if story.openings else None,
                        title=(story.openings[0].title if story.openings else "Integration Opening"),
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
            characters=characters,
            story_characters=story_characters,
            workspace_id=workspace_id,
            story_id=story.id,
        )
        gateway.rp_modules.mount_story_defaults(story.id)

    if with_status:
        _mount_integration_status(gateway, workspace_id, story.id)
        gateway.status.initialize_session_tables(session_id)
    if bind_role:
        gateway.session_roles.bind_by_index(session_id, 1)
    return IntegrationCatalog(workspace_id, story, session, character)


def _ensure_integration_session(gateway, integration_workspace, session_id: str) -> None:
    _create_integration_session(gateway, integration_workspace, session_id)


def _ensure_integration_session_with_status(gateway, integration_workspace, session_id: str) -> None:
    _create_integration_session(
        gateway,
        integration_workspace,
        session_id,
        with_status=True,
    )


def _mount_integration_status(gateway, workspace_id: str, story_id: int) -> None:
    if gateway.status.list_story_mounts(workspace_id, story_id):
        return
    scene_template = gateway.status.create_template(
        workspace_id,
        "集成当前场景",
        status_kind=models.STATUS_KIND_SCENE,
        rows=[
            ["时间", "第 2 年 3 月 4 日 5 时"],
            ["位置", "集成测试大厅"],
            ["在场人物", "测试者"],
        ],
        sort_order=10,
    )
    normal_template = gateway.status.create_template(
        workspace_id,
        "集成线索",
        rows=[["线索", "状态表已挂载"]],
        sort_order=20,
    )
    gateway.status.mount_template(workspace_id, story_id, scene_template.id, sort_order=10)
    gateway.status.mount_template(workspace_id, story_id, normal_template.id, sort_order=20)


def _ensure_test_role(*, characters, story_characters, workspace_id: str, story_id: int):
    character = next(
        (
            candidate
            for candidate in characters.list(workspace_id)
            if candidate.name == "Integration Tester"
        ),
        None,
    )
    if character is None:
        character = characters.create(
            workspace_id,
            "Integration Tester",
            personality="A concise test role used by integration tests.",
            content="You are the player-controlled role for integration tests.",
        )
    story_characters.mount(workspace_id, story_id, character.id)
    return character
