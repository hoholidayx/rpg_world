"""Dice expression parser for the Dice RP module."""

from __future__ import annotations

import re

from rpg_core.rp_modules.dice.models import DiceExpression

_DICE_RE = re.compile(r"(?P<count>[1-9]\d*)?d(?P<sides>[1-9]\d*)(?P<modifier>[+-]\d+)?")


class DiceParseError(ValueError):
    """Raised when a dice expression is invalid."""


def parse_dice_expression(
    expression: str,
    *,
    max_dice_count: int = 100,
    max_die_sides: int = 1000,
    max_modifier_abs: int = 100000,
) -> DiceExpression:
    """Parse expressions like ``d20`` or ``2d6+3``."""
    text = expression.strip().lower().replace(" ", "")
    if not text:
        raise DiceParseError("骰子表达式不能为空")

    match = _DICE_RE.fullmatch(text)
    if match is None:
        raise DiceParseError("骰子表达式格式错误，示例: d20、1d20、2d6+3")

    count = int(match.group("count") or "1")
    sides = int(match.group("sides"))
    modifier = int(match.group("modifier") or "0")

    if count < 1 or count > max_dice_count:
        raise DiceParseError(f"骰子数量必须在 1..{max_dice_count} 之间")
    if sides < 2 or sides > max_die_sides:
        raise DiceParseError(f"骰子面数必须在 2..{max_die_sides} 之间")
    if abs(modifier) > max_modifier_abs:
        raise DiceParseError(f"修正值绝对值不能超过 {max_modifier_abs}")

    return DiceExpression(count=count, sides=sides, modifier=modifier)
