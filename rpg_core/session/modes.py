"""Transport-neutral semantic modes shared by session messages and turns."""

from __future__ import annotations

from enum import StrEnum


class TurnMode(StrEnum):
    """Supported semantic modes for a normal text turn."""

    NEUTRAL = "neutral"
    IC = "ic"
    OOC = "ooc"
    GM = "gm"


DEFAULT_TURN_MODE = TurnMode.NEUTRAL
ALL_MESSAGE_MODES = frozenset(TurnMode)
WORLD_ADVANCING_MODES = frozenset({
    TurnMode.NEUTRAL,
    TurnMode.IC,
    TurnMode.GM,
})


def is_world_advancing_mode(value: object) -> bool:
    """Return whether one persisted/requested mode may advance story facts."""

    try:
        return normalize_turn_mode(value) in WORLD_ADVANCING_MODES
    except ValueError:
        return False


def normalize_turn_mode(value: object) -> TurnMode:
    """Normalize an external mode value to the canonical shared enum."""

    normalized = str(value or "").strip().lower() or DEFAULT_TURN_MODE.value
    try:
        return TurnMode(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid turn mode: {normalized}") from exc
