"""Built-in RP Module definitions and immutable Story/Session selection snapshots."""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence

from commons.types import JsonObject, JsonValue
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_NARRATIVE_OUTCOME_NAME,
    RP_MODULE_PLOT_SCHEDULER_NAME,
)
from rpg_core.rp_modules.dice import DiceModule
from rpg_core.rp_modules.models import (
    ModuleCommand,
    RPModuleDefinition,
    RPModuleSelection,
    RPModuleSelectionSnapshot,
)
from rpg_core.rp_modules.narrative_outcome import NarrativeOutcomeModule
from rpg_core.rp_modules.narrative_outcome.models import NarrativeOutcomeSelection
from rpg_core.rp_modules.plot_scheduler import PlotSchedulerModule
from rpg_core.rp_modules.runtime import RPModuleTurnRuntime
from rpg_core.settings import (
    DiceModuleSettings,
    NarrativeOutcomeModuleSettings,
    PlotSchedulerModuleSettings,
    RPModuleSettings,
)
from rpg_data import models as data_models
from rpg_data.model.rp_modules import SessionRPModuleOverride, StoryRPModule


class RPModuleRegistry:
    """Resolve persistent mounts into immutable snapshots and local runtimes."""

    def __init__(
        self,
        *,
        settings: RPModuleSettings | None = None,
        rng_factory: Callable[[], random.Random] | None = None,
    ) -> None:
        self.settings = settings or RPModuleSettings()
        self._rng_factory = rng_factory or random.Random
        self._definitions = (
            RPModuleDefinition(
                name=RP_MODULE_NARRATIVE_OUTCOME_NAME,
                display_name="剧情结果裁定",
                description="按五档随机结果裁定存在外部实质变数的剧情分支。",
                sort_order=10,
                configurable_fields=("auto_adjudication_enabled", "weights"),
                config_validator=self._validate_narrative_config,
                system_config_resolver=self._narrative_system_config,
                module_factory=self._create_narrative_module,
            ),
            RPModuleDefinition(
                name=RP_MODULE_PLOT_SCHEDULER_NAME,
                display_name="剧情动态调度",
                description="按照 scene 时间动态注入剧情大纲节点与事件池事件。",
                sort_order=15,
                configurable_fields=(),
                config_validator=self._validate_plot_scheduler_config,
                system_config_resolver=self._plot_scheduler_system_config,
                module_factory=self._create_plot_scheduler_module,
            ),
            RPModuleDefinition(
                name=RP_MODULE_DICE_NAME,
                display_name="骰子调试",
                description="提供 /roll 与 /check_dc 低层随机调试命令。",
                sort_order=20,
                configurable_fields=("default_dc",),
                config_validator=self._validate_dice_config,
                system_config_resolver=self._dice_system_config,
                module_factory=self._create_dice_module,
            ),
        )

    def definitions(self) -> tuple[RPModuleDefinition, ...]:
        return self._definitions

    def definition(self, module_name: str) -> RPModuleDefinition | None:
        name = str(module_name or "").strip().lower()
        return next((item for item in self._definitions if item.name == name), None)

    def validate_config_patch(
        self,
        module_name: str,
        config: Mapping[str, JsonValue],
    ) -> JsonObject:
        definition = self.definition(module_name)
        if definition is None:
            raise KeyError(f"unknown RP module: {module_name}")
        raw = dict(config)
        unexpected = sorted(set(raw) - set(definition.configurable_fields))
        if unexpected:
            raise ValueError(
                f"unsupported {definition.name} config field(s): {unexpected}"
            )
        return definition.config_validator(raw)

    def create_runtime(
        self,
        snapshot: RPModuleSelectionSnapshot,
    ) -> RPModuleTurnRuntime:
        modules = []
        for selected in snapshot.enabled_modules:
            definition = self.definition(selected.name)
            if definition is None:
                continue
            modules.append(definition.module_factory(snapshot.session_id, selected))
        return RPModuleTurnRuntime(snapshot, modules)

    def commands_for_snapshot(
        self,
        snapshot: RPModuleSelectionSnapshot,
    ) -> list[ModuleCommand]:
        async def list_modules(_agent, _args: list[str]) -> str:
            return self._format_modules(snapshot)

        async def show_module(_agent, args: list[str]) -> str:
            return self._format_module(snapshot, args)

        commands = [
            ModuleCommand(
                name="/rp_modules",
                description="列出当前 Story/Session 的 RP Modules",
                detail="用法：/rp_modules。显示模块挂载、覆盖与有效状态。",
                handler=list_modules,
            ),
            ModuleCommand(
                name="/rp_module",
                description="查看 RP Module 状态",
                detail="用法：/rp_module <name>。",
                handler=show_module,
            ),
        ]
        runtime = self.create_runtime(snapshot)
        for module in runtime.enabled_modules():
            commands.extend(module.get_commands())
        return commands

    def build_snapshot(
        self,
        *,
        session_id: str,
        story_id: int,
        mounts: Sequence[StoryRPModule],
        overrides: Sequence[SessionRPModuleOverride],
    ) -> RPModuleSelectionSnapshot:
        mount_by_name = {mount.module_name: mount for mount in mounts}
        override_by_name = {override.module_name: override for override in overrides}
        selected: list[RPModuleSelection] = []
        for definition in self._definitions:
            system_enabled, system_config = self._system_module_config(definition.name)
            mount = mount_by_name.get(definition.name)
            override = override_by_name.get(definition.name)
            story_config = self.validate_config_patch(
                definition.name,
                mount.config if mount is not None else {},
            )
            session_config = self.validate_config_patch(
                definition.name,
                override.config if override is not None else {},
            )
            effective_config = dict(system_config)
            sources = {key: data_models.NARRATIVE_OUTCOME_SOURCE_CONFIG for key in system_config}
            for key, value in story_config.items():
                effective_config[key] = value
                sources[key] = data_models.NARRATIVE_OUTCOME_SOURCE_STORY
            for key, value in session_config.items():
                effective_config[key] = value
                sources[key] = data_models.NARRATIVE_OUTCOME_SOURCE_SESSION
            story_mounted = mount is not None
            story_enabled = bool(mount.enabled) if mount is not None else False
            session_enabled = override.enabled if override is not None else None
            effective_enabled = bool(
                self.settings.enabled
                and system_enabled
                and story_mounted
                and story_enabled
                and session_enabled is not False
            )
            selected.append(
                RPModuleSelection(
                    name=definition.name,
                    display_name=definition.display_name,
                    description=definition.description,
                    sort_order=definition.sort_order,
                    system_enabled=system_enabled,
                    story_mounted=story_mounted,
                    story_enabled=story_enabled,
                    session_enabled_override=session_enabled,
                    effective_enabled=effective_enabled,
                    system_config=system_config,
                    story_config=story_config,
                    session_config=session_config,
                    effective_config=effective_config,
                    config_sources=sources,
                )
            )
        return RPModuleSelectionSnapshot(
            session_id=session_id,
            story_id=story_id,
            global_enabled=self.settings.enabled,
            modules=tuple(sorted(selected, key=lambda item: (item.sort_order, item.name))),
        )

    def _system_module_config(self, module_name: str) -> tuple[bool, JsonObject]:
        definition = self.definition(module_name)
        if definition is None:
            raise KeyError(f"unknown RP module: {module_name}")
        return definition.system_config_resolver(self.settings)

    @staticmethod
    def _validate_narrative_config(raw: Mapping[str, JsonValue]) -> JsonObject:
        normalized: JsonObject = {}
        if "auto_adjudication_enabled" in raw:
            value = raw["auto_adjudication_enabled"]
            if not isinstance(value, bool):
                raise ValueError("auto_adjudication_enabled must be a boolean")
            normalized["auto_adjudication_enabled"] = value
        if "weights" in raw:
            value = raw["weights"]
            if not isinstance(value, Mapping):
                raise ValueError("weights must be an object")
            normalized["weights"] = data_models.NarrativeOutcomeWeights.from_mapping(
                value
            ).to_dict()
        return normalized

    @staticmethod
    def _validate_dice_config(raw: Mapping[str, JsonValue]) -> JsonObject:
        if "default_dc" not in raw:
            return {}
        value = raw["default_dc"]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("default_dc must be a positive integer")
        return {"default_dc": value}

    @staticmethod
    def _validate_plot_scheduler_config(raw: Mapping[str, JsonValue]) -> JsonObject:
        if raw:
            raise ValueError("plot_scheduler does not expose Story/Session config fields")
        return {}

    @staticmethod
    def _narrative_system_config(settings: object) -> tuple[bool, JsonObject]:
        current = settings.narrative_outcome
        return current.enabled, {
            "auto_adjudication_enabled": current.auto_adjudication_enabled,
            "weights": current.default_weights.to_dict(),
        }

    @staticmethod
    def _dice_system_config(settings: object) -> tuple[bool, JsonObject]:
        current = settings.dice
        return current.enabled, {"default_dc": current.default_dc}

    @staticmethod
    def _plot_scheduler_system_config(
        settings: object,
    ) -> tuple[bool, JsonObject]:
        current = settings.plot_scheduler
        return current.enabled, {
            "judge_history_turns": current.judge_history_turns,
            "soft_retry_intervening_turns": current.soft_retry_intervening_turns,
        }

    def _create_narrative_module(
        self,
        session_id: str,
        selected: RPModuleSelection,
    ) -> NarrativeOutcomeModule:
        weights = data_models.NarrativeOutcomeWeights.from_mapping(
            _mapping(selected.effective_config["weights"], "weights")
        )
        return NarrativeOutcomeModule(
            session_id=session_id,
            settings=NarrativeOutcomeModuleSettings(
                enabled=True,
                auto_adjudication_enabled=bool(
                    selected.effective_config["auto_adjudication_enabled"]
                ),
                default_weights=weights,
            ),
            rng=self._rng_factory(),
            selection=NarrativeOutcomeSelection(
                effective_weights=weights,
                effective_source=selected.config_sources.get(
                    "weights",
                    data_models.NARRATIVE_OUTCOME_SOURCE_CONFIG,
                ),
            ),
        )

    def _create_dice_module(
        self,
        _session_id: str,
        selected: RPModuleSelection,
    ) -> DiceModule:
        return DiceModule(
            settings=DiceModuleSettings(
                enabled=True,
                default_dc=int(selected.effective_config["default_dc"]),
                max_dice_count=self.settings.dice.max_dice_count,
                max_die_sides=self.settings.dice.max_die_sides,
            ),
            rng=self._rng_factory(),
        )

    def _create_plot_scheduler_module(
        self,
        session_id: str,
        selected: RPModuleSelection,
    ) -> PlotSchedulerModule:
        return PlotSchedulerModule(
            session_id=session_id,
            settings=PlotSchedulerModuleSettings(
                enabled=True,
                judge_history_turns=int(
                    selected.effective_config["judge_history_turns"]
                ),
                soft_retry_intervening_turns=int(
                    selected.effective_config["soft_retry_intervening_turns"]
                ),
            ),
        )

    @staticmethod
    def _format_modules(snapshot: RPModuleSelectionSnapshot) -> str:
        lines = ["RP Modules:"]
        for module in snapshot.modules:
            state = "启用" if module.effective_enabled else "停用"
            lines.append(f"- {module.name}: {state}")
        return "\n".join(lines)

    def _format_module(
        self,
        snapshot: RPModuleSelectionSnapshot,
        args: list[str],
    ) -> str:
        if not args:
            return "[错误] 用法：/rp_module <name>"
        selected = snapshot.get(args[0].strip().lower())
        if selected is None:
            return f"[错误] 未知 RP Module: {args[0]}"
        lines = [
            f"RP Module: {selected.name}",
            f"Story 挂载: {'是' if selected.story_mounted else '否'}",
            f"Story 启用: {'是' if selected.story_enabled else '否'}",
            f"Session 覆盖: {selected.session_enabled_override}",
            f"有效启用: {'是' if selected.effective_enabled else '否'}",
            f"有效配置: {_plain_value(selected.effective_config)}",
        ]
        if selected.name == RP_MODULE_DICE_NAME:
            lines.append("策略: 仅提供 /roll 与 /check_dc，不进入 LLM 工具 schema。")
        if selected.name == RP_MODULE_NARRATIVE_OUTCOME_NAME:
            lines.append("工具: rp_story_outcome")
            lines.append("策略: 当前主流程唯一的剧情随机决策模块。")
        if selected.name == RP_MODULE_PLOT_SCHEDULER_NAME:
            lines.append("策略: scene 时间驱动；动态指令只在已分配的 turn scratch 中生成。")
        return "\n".join(lines)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _plain_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_value(item) for item in value]
    return value
