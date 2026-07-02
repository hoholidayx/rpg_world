"""Tools exposed by the Dice RP module."""

from __future__ import annotations

import random

from rpg_core.agent.tools import BaseTool
from rpg_core.rp_modules.dice.models import DiceRollResult
from rpg_core.rp_modules.dice.parser import parse_dice_expression
from rpg_core.settings import DiceModuleSettings


class DiceRoller:
    """Reusable dice roller with injectable RNG for tests."""

    def __init__(
        self,
        settings: DiceModuleSettings | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings or DiceModuleSettings()
        self._rng = rng or random.Random()

    def roll(self, expression: str, *, reason: str = "", actor: str = "") -> DiceRollResult:
        parsed = parse_dice_expression(
            expression,
            max_dice_count=self._settings.max_dice_count,
            max_die_sides=self._settings.max_die_sides,
        )
        rolls = tuple(self._rng.randint(1, parsed.sides) for _ in range(parsed.count))
        return DiceRollResult(
            expression=parsed,
            rolls=rolls,
            reason=reason.strip(),
            actor=actor.strip(),
        )

    def check_dc(
        self,
        expression: str,
        *,
        dc: int,
        modifier: int = 0,
        reason: str = "",
        actor: str = "",
    ) -> DiceRollResult:
        if dc < 0:
            raise ValueError("DC 不能为负数")
        if abs(modifier) > 100000:
            raise ValueError("额外修正值绝对值不能超过 100000")

        parsed = parse_dice_expression(
            expression,
            max_dice_count=self._settings.max_dice_count,
            max_die_sides=self._settings.max_die_sides,
        )
        rolls = tuple(self._rng.randint(1, parsed.sides) for _ in range(parsed.count))
        return DiceRollResult(
            expression=parsed,
            rolls=rolls,
            extra_modifier=modifier,
            dc=dc,
            reason=reason.strip(),
            actor=actor.strip(),
        )


def format_roll_result(result: DiceRollResult) -> str:
    """Format a roll result for the LLM or slash command output."""
    parts = [
        f"expression={result.expression.normalized}",
        f"rolls={list(result.rolls)}",
        f"modifier={result.modifier}",
    ]
    if result.extra_modifier:
        parts.append(f"extra_modifier={result.extra_modifier}")
    parts.append(f"total={result.total}")
    if result.dc is not None:
        parts.append(f"dc={result.dc}")
        parts.append(f"outcome={result.outcome}")
    if result.reason:
        parts.append(f"reason={result.reason}")
    if result.actor:
        parts.append(f"actor={result.actor}")
    prefix = "检定结果" if result.dc is not None else "骰子结果"
    return f"{prefix}: " + ", ".join(parts)


class DiceRollTool(BaseTool):
    name = "rp_dice_roll"
    description = "执行一次骰子掷骰。用户明确要求掷骰或随机裁定时使用，不要伪造点数。"

    def __init__(self, roller: DiceRoller) -> None:
        self._roller = roller

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "骰子表达式，例如 d20、1d20、2d6+3。",
                },
                "reason": {
                    "type": "string",
                    "description": "本次掷骰的叙事原因。",
                },
                "actor": {
                    "type": "string",
                    "description": "执行行动的角色或对象。",
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: object) -> str:
        result = self._roller.roll(
            str(kwargs.get("expression", "")),
            reason=str(kwargs.get("reason", "") or ""),
            actor=str(kwargs.get("actor", "") or ""),
        )
        return format_roll_result(result)


class DiceCheckDCTool(BaseTool):
    name = "rp_dice_check_dc"
    description = "执行一次 DC 检定，返回 success 或 failure。"

    def __init__(self, roller: DiceRoller) -> None:
        self._roller = roller

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "骰子表达式，例如 d20、1d20、2d6+3。",
                },
                "dc": {
                    "type": "integer",
                    "description": "检定难度，total >= dc 为成功。",
                },
                "modifier": {
                    "type": "integer",
                    "description": "表达式之外的额外修正值。",
                },
                "reason": {
                    "type": "string",
                    "description": "本次检定的叙事原因。",
                },
                "actor": {
                    "type": "string",
                    "description": "执行行动的角色或对象。",
                },
            },
            "required": ["expression", "dc"],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: object) -> str:
        result = self._roller.check_dc(
            str(kwargs.get("expression", "")),
            dc=int(kwargs.get("dc", 0)),
            modifier=int(kwargs.get("modifier", 0) or 0),
            reason=str(kwargs.get("reason", "") or ""),
            actor=str(kwargs.get("actor", "") or ""),
        )
        return format_roll_result(result)
