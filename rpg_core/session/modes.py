"""Transport-neutral semantic modes shared by session messages and turns."""

from __future__ import annotations

from enum import StrEnum


class TurnMode(StrEnum):
    """Supported semantic modes for a normal text turn."""

    IC = "ic"
    OOC = "ooc"
    GM = "gm"


DEFAULT_TURN_MODE = TurnMode.IC


def normalize_turn_mode(value: object) -> TurnMode:
    """Normalize an external mode value to the canonical shared enum."""

    normalized = str(value or "").strip().lower() or DEFAULT_TURN_MODE.value
    try:
        return TurnMode(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid turn mode: {normalized}") from exc
