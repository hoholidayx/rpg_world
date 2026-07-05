from __future__ import annotations

import random

import pytest

from rpg_core.agent.tools import BaseTool
from rpg_core.rp_modules import registry as registry_module
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_DICE_SECTION_ID,
)
from rpg_core.rp_modules.registry import RPModuleRegistry
from rpg_core.settings import DiceModuleSettings, RPModuleSettings


def test_registry_loads_default_modules():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(),
        rng_factory=lambda: random.Random(0),
    )

    assert [module.name for module in registry.enabled_modules()] == [RP_MODULE_DICE_NAME]
    assert [section.id for section in registry.get_fixed_sections()] == [RP_MODULE_DICE_SECTION_ID]
    assert [tool.name for tool in registry.get_tools()] == ["rp_dice_roll", "rp_dice_check_dc"]
    assert registry.get_runtime_sections() == []
    assert [command.name for command in registry.get_commands()] == [
        "/rp_modules",
        "/rp_module",
        "/roll",
        "/check_dc",
    ]


def test_registry_global_disable_returns_empty_collections():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(enabled=False),
    )

    assert registry.enabled_modules() == []
    assert registry.get_fixed_sections() == []
    assert registry.get_tools() == []
    assert registry.get_commands() == []
    assert registry.get_runtime_sections() == []


def test_registry_keeps_framework_commands_when_dice_disabled():
    registry = RPModuleRegistry(
        session_id="s1",
        world_name="world",
        settings=RPModuleSettings(dice=DiceModuleSettings(enabled=False)),
    )

    assert registry.enabled_modules() == []
    assert registry.get_fixed_sections() == []
    assert [command.name for command in registry.get_commands()] == ["/rp_modules", "/rp_module"]
    status = registry.module_status(RP_MODULE_DICE_NAME)
    assert status.enabled is False
    assert status.config_summary["default_dc"] == 12


def test_registry_rejects_duplicate_public_tool_names(monkeypatch):
    class DuplicateTool(BaseTool):
        name = "rp_duplicate"
        description = "duplicate"

        def parameters(self):
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            return "ok"

    class DuplicateDiceModule:
        name = RP_MODULE_DICE_NAME

        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_tools(self):
            return [DuplicateTool(), DuplicateTool()]

        def get_fixed_sections(self):
            return []

        def get_runtime_sections(self, request):
            return []

        def get_commands(self):
            return []

    monkeypatch.setattr(registry_module, "DiceModule", DuplicateDiceModule)

    with pytest.raises(ValueError, match="Duplicate RP module tool name"):
        RPModuleRegistry(
            session_id="s1",
            world_name="world",
            settings=RPModuleSettings(),
        )
