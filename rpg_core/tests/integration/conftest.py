"""Integration-test fixtures.

These tests use a real agent and real network calls, but only when
``INTEGRATION_TEST=1`` is set. The runtime is redirected to an isolated
temporary workspace so no repository data is touched.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress

import pytest
import pytest_asyncio

from rpg_core import settings as settings_module
from rpg_core.agent.agent import RPGGameAgent
from rpg_core.utils.watcher import get_watcher

_INTEGRATION_MARKER = "integration"


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    if os.environ.get("INTEGRATION_TEST") == "1":
        return

    skip_marker = pytest.mark.skip(reason="set INTEGRATION_TEST=1 to run integration tests")
    for item in items:
        if _INTEGRATION_MARKER in item.keywords:
            item.add_marker(skip_marker)


def _patch_loaded_settings_refs(integration_settings) -> dict[str, object]:
    module_names = (
        "rpg_core.settings",
        "rpg_core.agent.agent",
        "rpg_core.agent.manager",
        "llm_service.manager",
        "llm_service.openai_provider",
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
    settings = settings_module.Settings()
    settings_module.settings = settings
    previous_module_refs = _patch_loaded_settings_refs(settings)
    try:
        yield settings
    finally:
        settings_module.settings = previous
        for module_name, old_settings in previous_module_refs.items():
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "settings"):
                setattr(module, "settings", old_settings)


@pytest.fixture
def integration_workspace(tmp_path, monkeypatch):
    from rpg_data.services import reset_data_service_gateways

    monkeypatch.setenv("RPG_WORLD_DB_PATH", str(tmp_path / "rpg_data.sqlite3"))
    monkeypatch.setenv("RPG_WORLD_WORKSPACE_ROOT_BASE", str(tmp_path))
    reset_data_service_gateways()
    yield tmp_path
    reset_data_service_gateways()


@pytest.fixture
def integration_data_gateway(integration_workspace):  # noqa: ARG001
    from rpg_data.services import get_data_service_gateway

    return get_data_service_gateway()


@pytest_asyncio.fixture
async def integration_agent(integration_settings, integration_workspace, integration_data_gateway):
    session_id = "integration_smoke"
    workspace = str(integration_workspace)
    api_key = integration_settings.resolve_openai_api_key()
    if not api_key:
        pytest.skip(
            "configure agent.api_key or INTEGRATION_OPENAI_API_KEY in rpg_core/tests/integration/settings.test.yaml"
        )
    _ensure_integration_session(integration_data_gateway, integration_workspace, session_id)
    agent = RPGGameAgent(
        session_id=session_id,
        workspace=workspace,
        model=integration_settings.agent_model,
        api_key=api_key,
        base_url=integration_settings.agent_base_url,
        max_tokens=integration_settings.agent_max_tokens,
        temperature=integration_settings.agent_temperature,
    )
    await agent._ensure_initialized()

    try:
        yield agent
    finally:
        consumer = getattr(agent, "_consumer_task", None)
        if consumer is not None:
            consumer.cancel()
            with suppress(asyncio.CancelledError):
                await consumer

        watcher = get_watcher()
        watcher.stop()
        watcher.clear_all()


@pytest.fixture
def integration_session_dir(integration_settings, integration_workspace):
    session_id = "integration_smoke"
    return integration_settings.session_dir(str(integration_workspace), session_id)


def _ensure_integration_session(gateway, integration_workspace, session_id: str) -> None:
    from rpg_data.repositories.session_repo import SessionRepository
    from rpg_data.repositories.story_repo import StoryRepository
    from rpg_data.repositories.workspace_repo import WorkspaceRepository

    workspace_id = "integration_workspace"
    database = gateway.database
    workspaces = WorkspaceRepository(database)
    stories = StoryRepository(database)
    sessions = SessionRepository(database)

    with database.atomic():
        if workspaces.get(workspace_id) is None:
            workspaces.create(workspace_id, "Integration Workspace", str(integration_workspace))
        story = next(
            (candidate for candidate in stories.list(workspace_id) if candidate.title == "Integration Story"),
            None,
        )
        if story is None:
            story = stories.create(workspace_id, "Integration Story")
        if sessions.get(session_id) is None:
            sessions.create(workspace_id, story.id, session_id=session_id, title=session_id)
