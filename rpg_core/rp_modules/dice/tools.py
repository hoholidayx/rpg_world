"""Tools exposed by the Dice RP module."""

from __future__ import annotations

import random

from rpg_core.agent.tools import BaseTool
from rpg_core.rp_modules.dice.models import DiceRollResult
from rpg_core.rp_modules.dice.parser import parse_dice_expression
from rpg_core.settings import DiceModuleSettings

DEFAULT_DICE_EXPRESSION = "1d20"


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
    description = (
        "底层骰子随机能力，供手动调试或其它 RP Module 内部复用。"
        "本工具不应注册到主 LLM 的自然剧情工具 schema。"
    )

    def __init__(self, roller: DiceRoller) -> None:
        self._roller = roller

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "骰子表达式，例如 d20、1d20、2d6+3；省略时使用 1d20。",
                    "default": DEFAULT_DICE_EXPRESSION,
                },
                "reason": {
                    "type": "string",
                    "description": "本次随机取值的唯一叙事原因。",
                },
                "actor": {
                    "type": "string",
                    "description": "执行行动的角色或对象。",
                },
            },
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: object) -> str:
        expression = str(kwargs.get("expression", "") or "").strip() or DEFAULT_DICE_EXPRESSION
        result = self._roller.roll(
            expression,
            reason=str(kwargs.get("reason", "") or ""),
            actor=str(kwargs.get("actor", "") or ""),
        )
        return format_roll_result(result)


class DiceCheckDCTool(BaseTool):
    name = "rp_dice_check_dc"
    description = ""

    def __init__(self, roller: DiceRoller, *, default_dc: int = 12) -> None:
        if default_dc < 0:
            raise ValueError("默认 DC 不能为负数")
        self._roller = roller
        self._default_dc = int(default_dc)
        self.description = (
            "底层 DC 计算能力，供手动调试或其它 RP Module 内部复用。"
            "本工具不应注册到主 LLM 的自然剧情工具 schema。未给出数值时，"
            f"工具会使用 {DEFAULT_DICE_EXPRESSION} 和默认 DC {self._default_dc}。"
        )

    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "完整骰子表达式及唯一修正值，例如 d20、1d20+2；"
                        "省略时使用 1d20。"
                    ),
                    "default": DEFAULT_DICE_EXPRESSION,
                },
                "dc": {
                    "type": "integer",
                    "description": (
                        f"仅在当前规则或上下文明确给出难度时填写；否则省略并使用默认 DC {self._default_dc}。"
                        "total >= dc 为成功。"
                    ),
                    "default": self._default_dc,
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
            "additionalProperties": False,
        }

    async def execute(self, **kwargs: object) -> str:
        expression = str(kwargs.get("expression", "") or "").strip() or DEFAULT_DICE_EXPRESSION
        raw_dc = kwargs.get("dc")
        dc = self._default_dc if raw_dc is None or str(raw_dc).strip() == "" else int(raw_dc)
        result = self._roller.check_dc(
            expression,
            dc=dc,
            modifier=int(kwargs.get("modifier", 0) or 0),
            reason=str(kwargs.get("reason", "") or ""),
            actor=str(kwargs.get("actor", "") or ""),
        )
        return format_roll_result(result)
