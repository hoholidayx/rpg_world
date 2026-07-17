"""Canonical identities shared across Dream domain and persistence boundaries."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["dream_derived_source_fingerprint"]


def dream_derived_source_fingerprint(
    *,
    version: int,
    content_hash: str,
    source_turn_start: int,
    source_turn_end: int,
    evidence_message_ids: Iterable[int] = (),
) -> str:
    """Return the canonical identity for a summary or Story Memory source."""

    return (
        f"{int(version)}:{str(content_hash)}:"
        f"{int(source_turn_start)}:{int(source_turn_end)}:"
        f"{','.join(str(int(item)) for item in evidence_message_ids)}"
    )
