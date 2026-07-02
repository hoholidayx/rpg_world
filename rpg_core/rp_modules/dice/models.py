"""Dice module data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiceExpression:
    """Parsed dice expression."""

    count: int
    sides: int
    modifier: int = 0

    @property
    def normalized(self) -> str:
        text = f"{self.count}d{self.sides}"
        if self.modifier > 0:
            return f"{text}+{self.modifier}"
        if self.modifier < 0:
            return f"{text}{self.modifier}"
        return text


@dataclass(frozen=True)
class DiceRollResult:
    """Result of a dice roll or DC check."""

    expression: DiceExpression
    rolls: tuple[int, ...]
    extra_modifier: int = 0
    dc: int | None = None
    reason: str = ""
    actor: str = ""

    @property
    def modifier(self) -> int:
        return self.expression.modifier + self.extra_modifier

    @property
    def total(self) -> int:
        return sum(self.rolls) + self.modifier

    @property
    def outcome(self) -> str | None:
        if self.dc is None:
            return None
        return "success" if self.total >= self.dc else "failure"
