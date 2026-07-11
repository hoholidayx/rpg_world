"""Dice RP module composition."""

from __future__ import annotations

import random

from rpg_core.rp_modules.base import RPModule
from rpg_core.rp_modules.constants import RP_MODULE_DICE_NAME
from rpg_core.rp_modules.dice.parser import DiceParseError
from rpg_core.rp_modules.dice.tools import (
    DiceRoller,
    format_roll_result,
)
from rpg_core.rp_modules.models import ModuleCommand, ModuleStatus
from rpg_core.settings import DiceModuleSettings


class DiceModule(RPModule):
    """Low-level dice parser plus manual debugging commands."""

    name = RP_MODULE_DICE_NAME

    def __init__(
        self,
        settings: DiceModuleSettings | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings or DiceModuleSettings()
        self._roller = DiceRoller(self.settings, rng=rng)

    def get_tools(self):
        # Low-level dice tools intentionally stay out of the main LLM schema.
        return []

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
            tools=(),
            fixed_section_ids=(),
            config_summary={
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
        if not args:
            return "[错误] 用法：/check_dc <expr> [dc=<n>] [reason]"

        expression = args[0]
        dc = self.settings.default_dc
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
