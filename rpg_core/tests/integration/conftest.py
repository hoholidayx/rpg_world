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

from rpg_world.rpg_core import settings as settings_module
from rpg_world.rpg_core.agent.agent import RPGGameAgent
from rpg_world.rpg_core.utils.watcher import get_watcher

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
        "rpg_world.rpg_core.settings",
        "rpg_world.rpg_core.agent.agent",
        "rpg_world.rpg_core.agent.manager",
        "rpg_world.rpg_core.agent.openai_provider",
        "rpg_world.rpg_core.session.manager",
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
def integration_workspace(tmp_path):
    return tmp_path


@pytest_asyncio.fixture
async def integration_agent(integration_settings, integration_workspace):
    session_id = "integration_smoke"
    workspace = str(integration_workspace)
    api_key = integration_settings.resolve_openai_api_key()
    if not api_key:
        pytest.skip(
            "configure agent.api_key or INTEGRATION_OPENAI_API_KEY in rpg_core/tests/integration/settings.test.yaml"
        )
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
