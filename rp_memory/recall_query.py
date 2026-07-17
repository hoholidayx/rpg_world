"""Structured, turn-local inputs for RP memory query planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecallQueryContext:
    """Inputs allowed to influence one recall without mutating shared state."""

    current_input: str
    recent_turns: tuple[str, ...] = ()
    player_character: str = ""
    scene_time: str = ""
    scene_location: str = ""

    @classmethod
    def from_query(cls, query: str) -> "RecallQueryContext":
        return cls(current_input=" ".join(str(query or "").split()))

    def planner_prompt(self) -> str:
        recent = "\n\n".join(self.recent_turns) or "（无）"
        return (
            "## 当前输入\n"
            f"{self.current_input}\n\n"
            "## 玩家角色\n"
            f"{self.player_character or '（未知）'}\n\n"
            "## 当前场景\n"
            f"时间：{self.scene_time or '（未知）'}\n"
            f"地点：{self.scene_location or '（未知）'}\n\n"
            "## 最近两个 IC/GM Turn\n"
            f"{recent}"
        )

    def deterministic_expansions(self) -> tuple[str, ...]:
        values: list[str] = []
        scene = " ".join(
            value for value in (self.player_character, self.scene_time, self.scene_location) if value
        )
        if scene:
            values.append(scene[:160])
        values.extend(turn[:240] for turn in self.recent_turns if turn.strip())
        return tuple(_dedupe(values))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
