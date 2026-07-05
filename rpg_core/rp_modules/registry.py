"""Session-scoped RP Module registry."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import TYPE_CHECKING

from rpg_core.agent.tools import BaseTool
from rpg_core.context import FixedLayerSection, RPModuleRuntimeSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
)
from rpg_core.rp_modules.dice import DiceModule
from rpg_core.rp_modules.models import ModuleCommand, ModuleContextRequest, ModuleStatus
from rpg_core.settings import RPModuleSettings

if TYPE_CHECKING:
    from rpg_core.scene import SceneTracker
    from rpg_core.status.manager import StatusManager


class RPModuleRegistry:
    """Collect enabled RP modules for one agent session."""

    def __init__(
        self,
        *,
        session_id: str,
        world_name: str,
        status_mgr: "StatusManager | None" = None,
        scene_tracker: "SceneTracker | None" = None,
        settings: RPModuleSettings | None = None,
        rng_factory: Callable[[], random.Random] | None = None,
    ) -> None:
        self.session_id = session_id
        self.world_name = world_name
        self.status_mgr = status_mgr
        self.scene_tracker = scene_tracker
        self.settings = settings or RPModuleSettings()
        self._rng_factory = rng_factory or random.Random
        self._modules: dict[str, RPModule] = {}
        self._tool_to_module: dict[str, str] = {}
        self._disabled_status: dict[str, ModuleStatus] = {}
        self._load_modules()

    def enabled_modules(self) -> list[RPModule]:
        return [self._modules[name] for name in sorted(self._modules)]

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        sections: list[FixedLayerSection] = []
        for module in self.enabled_modules():
            sections.extend(module.get_fixed_sections())
        return sorted(sections, key=lambda section: (section.priority, section.id))

    def get_runtime_sections(
        self,
        request: ModuleContextRequest | None = None,
    ) -> list[RPModuleRuntimeSection]:
        request = request or ModuleContextRequest(session_id=self.session_id)
        sections: list[RPModuleRuntimeSection] = []
        for module in self.enabled_modules():
            sections.extend(module.get_runtime_sections(request))
        return sorted(sections, key=lambda section: (section.priority, section.id))

    def get_tools(self) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for module in self.enabled_modules():
            tools.extend(module.get_tools())
        return tools

    def get_commands(self) -> list[ModuleCommand]:
        if not self.settings.enabled:
            return []

        commands = [
            ModuleCommand(
                name="/rp_modules",
                description="列出已启用 RP Modules",
                detail="用法：/rp_modules。显示当前启用的 RP 玩法模块和公开工具。",
                handler=self._cmd_rp_modules,
            ),
            ModuleCommand(
                name="/rp_module",
                description="查看 RP Module 状态",
                detail=f"用法：/rp_module <name>。例如 /rp_module {RP_MODULE_DICE_NAME}。",
                handler=self._cmd_rp_module,
            ),
        ]
        for module in self.enabled_modules():
            commands.extend(module.get_commands())
        return commands

    def module_status(self, name: str) -> ModuleStatus:
        module = self._modules.get(name)
        if module is not None:
            return module.status()
        return self._disabled_status.get(name) or ModuleStatus(name=name, enabled=False)

    def _load_modules(self) -> None:
        if not self.settings.enabled:
            return
        if self.settings.dice.enabled:
            self._modules[RP_MODULE_DICE_NAME] = DiceModule(
                settings=self.settings.dice,
                rng=self._rng_factory(),
            )
        else:
            self._disabled_status[RP_MODULE_DICE_NAME] = ModuleStatus(
                name=RP_MODULE_DICE_NAME,
                enabled=False,
                config_summary={
                    "allow_auto_checks": self.settings.dice.allow_auto_checks,
                    "default_dc": self.settings.dice.default_dc,
                    "max_dice_count": self.settings.dice.max_dice_count,
                    "max_die_sides": self.settings.dice.max_die_sides,
                },
            )
        self._validate_tool_names()

    def _validate_tool_names(self) -> None:
        for module in self.enabled_modules():
            for tool in module.get_tools():
                owner = self._tool_to_module.get(tool.name)
                if owner is not None:
                    raise ValueError(
                        f"Duplicate RP module tool name {tool.name!r}: {owner} and {module.name}"
                    )
                self._tool_to_module[tool.name] = module.name

    async def _cmd_rp_modules(self, _agent, _args: list[str]) -> str:
        if not self.settings.enabled:
            return "RP Modules 未启用。"

        modules = self.enabled_modules()
        lines = ["已启用 RP Modules:"]
        if not modules:
            lines.append("- （无）")
            return "\n".join(lines)
        for module in modules:
            tools = ",".join(tool.name for tool in module.get_tools()) or "无"
            lines.append(f"- {module.name}: tools={tools}")
        return "\n".join(lines)

    async def _cmd_rp_module(self, _agent, args: list[str]) -> str:
        if not self.settings.enabled:
            return "RP Modules 未启用。"
        if not args:
            return "[错误] 用法：/rp_module <name>"

        name = args[0].strip().lower()
        status = self.module_status(name)
        if name not in self._known_module_names() and not status.enabled:
            return f"[错误] 未知 RP Module: {name}"

        lines = [
            f"RP Module: {status.name}",
            f"启用: {'是' if status.enabled else '否'}",
        ]
        if status.tools:
            lines.append(f"工具: {', '.join(status.tools)}")
        if status.config_summary:
            config = ", ".join(f"{key}={value}" for key, value in status.config_summary.items())
            lines.append(f"配置: {config}")
        if name == RP_MODULE_DICE_NAME:
            lines.append("策略: 自然 RP 中遇到关键不确定节点可调用骰子；/roll 与 /check_dc 仅作手动入口。")
            lines.append("审计: MVP 不落盘记录最近 rolls。")
        return "\n".join(lines)

    def _known_module_names(self) -> set[str]:
        return {
            RP_MODULE_DICE_NAME,
        }
