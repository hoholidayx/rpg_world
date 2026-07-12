"""Typed Session turn request and execution policy models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TurnMode(StrEnum):
    IC = "ic"
    OOC = "ooc"
    GM = "gm"


def normalize_turn_mode(value: object) -> TurnMode:
    normalized = str(value or "").strip().lower() or TurnMode.IC.value
    try:
        return TurnMode(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid turn mode: {normalized}") from exc


@dataclass(frozen=True)
class TurnRequest:
    text: str
    mode: TurnMode = TurnMode.IC
    narrative_style_id: int | None = None
    request_id: str | None = None

    @classmethod
    def create(
        cls,
        text: str,
        *,
        mode: TurnMode | str | None = None,
        narrative_style_id: int | None = None,
        request_id: str | None = None,
    ) -> "TurnRequest":
        style_id = int(narrative_style_id) if narrative_style_id is not None else None
        if style_id is not None and style_id <= 0:
            raise ValueError("narrative_style_id must be a positive integer or null")
        return cls(
            text=str(text or ""),
            mode=normalize_turn_mode(mode),
            narrative_style_id=style_id,
            request_id=str(request_id or "").strip() or None,
        )


@dataclass(frozen=True)
class TurnExecutionPolicy:
    run_status_preflight: bool
    expose_state_tools: bool
    expose_rp_modules: bool
    apply_narrative_style: bool

    @classmethod
    def for_mode(cls, mode: TurnMode) -> "TurnExecutionPolicy":
        if mode is TurnMode.OOC:
            return cls(
                run_status_preflight=False,
                expose_state_tools=False,
                expose_rp_modules=False,
                apply_narrative_style=False,
            )
        return cls(
            run_status_preflight=True,
            expose_state_tools=True,
            expose_rp_modules=True,
            apply_narrative_style=True,
        )


@dataclass(frozen=True)
class TurnExecutionSnapshot:
    request: TurnRequest
    mode_prompt: str
    narrative_style_id: int | None
    narrative_style_name: str
    narrative_style_prompt: str
    policy: TurnExecutionPolicy

