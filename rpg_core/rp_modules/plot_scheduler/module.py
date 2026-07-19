"""Plot Scheduler RP Module: fixed contract and scratch-backed dynamic sections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rpg_core.context import FixedLayerSection, RPModuleRuntimeSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_PLOT_SCHEDULER_NAME,
    RP_MODULE_PLOT_SCHEDULER_SECTION_ID,
    RP_MODULE_PLOT_SCHEDULER_SOURCE,
    RP_MODULE_PLOT_SCHEDULER_TURN_SECTION_ID,
)
from rpg_core.rp_modules.models import ModuleContextRequest, ModuleStatus
from rpg_core.settings import PlotSchedulerModuleSettings

if TYPE_CHECKING:
    from rpg_core.agent.turn.transaction import TurnScratch


class PlotSchedulerModule(RPModule):
    name = RP_MODULE_PLOT_SCHEDULER_NAME

    def __init__(
        self,
        *,
        session_id: str,
        settings: PlotSchedulerModuleSettings | None = None,
    ) -> None:
        self.session_id = session_id
        self.settings = settings or PlotSchedulerModuleSettings()
        self._active_scratch: TurnScratch | None = None

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        return [
            FixedLayerSection(
                id=RP_MODULE_PLOT_SCHEDULER_SECTION_ID,
                title="剧情动态调度协议",
                source=RP_MODULE_PLOT_SCHEDULER_SOURCE,
                priority=75,
                content=(
                    "- 当 RP_MODULES 动态层出现“本轮剧情调度”时，其中事件已经由系统完成"
                    "时间检查与软约束判断；必须在当前回复中实际开始或推进，不得再次评估、延期、"
                    "忽略、询问玩家是否执行或泄露调度机制。\n"
                    "- 同轮可能同时包含一个大纲节点和一个事件池事件；按给定顺序兼容地落实全部指令，"
                    "不得用其中一个替代另一个。\n"
                    "- 调度只约束世界、NPC 与剧情发展，不替玩家角色决定内心、台词或自主行动。\n"
                    "- 应自然衔接当前地点、人物和状态，不要原样复述后台指令。"
                ),
            )
        ]

    def get_runtime_sections(
        self,
        request: ModuleContextRequest,
    ) -> list[RPModuleRuntimeSection]:
        scratch = self._active_scratch if request.include_staged_turn else None
        if scratch is None or not scratch.plot_schedule_injections:
            return []
        items = []
        for index, injection in enumerate(scratch.plot_schedule_injections, start=1):
            items.append({
                "order": index,
                "source": injection.source_kind,
                "container": injection.container_name,
                "event": injection.event_title,
                "dispatchMode": injection.dispatch_mode,
                "sceneTime": injection.scene_time.format(),
                "directive": injection.directive,
                **({"suitabilityReason": injection.reason} if injection.reason else {}),
            })
        return [
            RPModuleRuntimeSection(
                id=RP_MODULE_PLOT_SCHEDULER_TURN_SECTION_ID,
                title="本轮剧情调度",
                source=RP_MODULE_PLOT_SCHEDULER_SOURCE,
                priority=75,
                content=(
                    "以下指令已经触发，必须在当前回复中全部落实：\n"
                    + json.dumps(items, ensure_ascii=False, indent=2)
                ),
            )
        ]

    def bind_turn(self, scratch: TurnScratch) -> None:
        self._active_scratch = scratch

    def unbind_turn(self, scratch: TurnScratch) -> None:
        if self._active_scratch is scratch:
            self._active_scratch = None

    def status(self) -> ModuleStatus:
        return ModuleStatus(
            name=self.name,
            enabled=self.settings.enabled,
            fixed_section_ids=(RP_MODULE_PLOT_SCHEDULER_SECTION_ID,),
            config_summary={
                "judge_history_turns": self.settings.judge_history_turns,
                "soft_retry_intervening_turns": (
                    self.settings.soft_retry_intervening_turns
                ),
            },
        )
