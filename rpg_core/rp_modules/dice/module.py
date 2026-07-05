"""Dice RP module composition."""

from __future__ import annotations

import random

from rpg_core.context import FixedLayerSection
from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import (
    RP_MODULE_DICE_NAME,
    RP_MODULE_DICE_SECTION_ID,
    RP_MODULE_DICE_SOURCE,
)
from rpg_core.rp_modules.dice.parser import DiceParseError
from rpg_core.rp_modules.dice.tools import (
    DiceCheckDCTool,
    DiceRoller,
    DiceRollTool,
    format_roll_result,
)
from rpg_core.rp_modules.models import ModuleCommand, ModuleStatus
from rpg_core.settings import DiceModuleSettings


class DiceModule(RPModule):
    """Dice and random adjudication module."""

    name = RP_MODULE_DICE_NAME

    def __init__(
        self,
        settings: DiceModuleSettings | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings or DiceModuleSettings()
        self._roller = DiceRoller(self.settings, rng=rng)
        self._tools = [
            DiceRollTool(self._roller),
            DiceCheckDCTool(self._roller),
        ]

    def get_fixed_sections(self) -> list[FixedLayerSection]:
        return [
            FixedLayerSection(
                id=RP_MODULE_DICE_SECTION_ID,
                title="骰子与随机裁定",
                source=RP_MODULE_DICE_SOURCE,
                priority=80,
                content=(
                    "- 用户明确要求掷骰、检定或随机裁定时，必须调用 "
                    "rp_dice_roll 或 rp_dice_check_dc，不得口头编造点数。\n"
                    "- 当行动结果明显不确定且会改变剧情走向时，可以建议或主动进行检定。\n"
                    "- 检定前只说明可感知风险或难度，不剧透隐藏信息。\n"
                    "- 检定后把结果转译成自然 RP 叙事；失败应引入代价、复杂化、延迟、暴露或资源消耗，而不是阻断剧情。\n"
                    "- 骰子只裁定行动后果，不替玩家角色选择行动或台词。"
                ),
            )
        ]

    def get_tools(self):
        return list(self._tools)

    def get_commands(self) -> list[ModuleCommand]:
        return [
            ModuleCommand(
                name="/roll",
                description="手动掷骰",
                detail="用法：/roll <expr> [reason]。例如 /roll 1d20+2 潜行越过甲板。",
                handler=self._cmd_roll,
            ),
            ModuleCommand(
                name="/check_dc",
                description="手动 DC 检定",
                detail="用法：/check_dc <expr> dc=<n> [reason]。例如 /check_dc 1d20+2 dc=12 潜行。",
                handler=self._cmd_check_dc,
            ),
        ]

    def status(self) -> ModuleStatus:
        return ModuleStatus(
            name=self.name,
            enabled=self.settings.enabled,
            tools=tuple(tool.name for tool in self._tools),
            fixed_section_ids=tuple(section.id for section in self.get_fixed_sections()),
            config_summary={
                "allow_auto_checks": self.settings.allow_auto_checks,
                "default_dc": self.settings.default_dc,
                "max_dice_count": self.settings.max_dice_count,
                "max_die_sides": self.settings.max_die_sides,
            },
        )

    async def _cmd_roll(self, _agent, args: list[str]) -> str:
        if not args:
            return "[错误] 用法：/roll <expr> [reason]"
        expression = args[0]
        reason = " ".join(args[1:]).strip()
        try:
            return format_roll_result(self._roller.roll(expression, reason=reason))
        except (DiceParseError, ValueError) as exc:
            return f"[错误] {exc}"

    async def _cmd_check_dc(self, _agent, args: list[str]) -> str:
        if len(args) < 2:
            return "[错误] 用法：/check_dc <expr> dc=<n> [reason]"

        expression = args[0]
        dc: int | None = None
        reason_parts: list[str] = []
        for token in args[1:]:
            if token.startswith("dc="):
                raw_dc = token.removeprefix("dc=").strip()
                try:
                    dc = int(raw_dc)
                except ValueError:
                    return "[错误] dc 必须是整数，例如 dc=12"
            else:
                reason_parts.append(token)

        if dc is None:
            return "[错误] 缺少 dc=<n>，例如 /check_dc 1d20+2 dc=12"

        try:
            return format_roll_result(
                self._roller.check_dc(
                    expression,
                    dc=dc,
                    reason=" ".join(reason_parts).strip(),
                )
            )
        except (DiceParseError, ValueError) as exc:
            return f"[错误] {exc}"
